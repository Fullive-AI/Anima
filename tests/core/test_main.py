import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from core.main import Anima
from core.models import (
    ActionVerificationResult,
    BrainCycleResult,
    Device,
    Event,
    EventType,
    Sensor,
    SkillActionSpec,
    SkillExecutionResult,
    SkillPlanItem,
)
from core.scheduler.scheduler import Scheduler


class TestMain:
    def test_register_scheduler_jobs_uses_minute_refresh_and_two_hour_discovery(self):
        anima = Anima.__new__(Anima)
        anima.scheduler = Scheduler()
        anima.discovery = SimpleNamespace(
            scan=AsyncMock(),
            refresh_device_states=AsyncMock(),
        )
        anima.preference_learner = SimpleNamespace(run_now=AsyncMock())
        anima._run_brain_cycle_serially = AsyncMock()

        anima._register_scheduler_jobs()

        assert anima.scheduler.jobs["device_scan"].interval_seconds == 7200
        assert anima.scheduler.jobs["environment_refresh"].interval_seconds == 60
        assert anima.scheduler.jobs["learn_preferences"].interval_seconds == 300
        assert anima.scheduler.jobs["brain_tick"].interval_seconds == 60

    async def test_sensor_update_triggers_brain_cycle_without_rules(self):
        anima = Anima.__new__(Anima)
        device = Device(
            device_id="hum_01",
            name="Humidifier",
            adapter="fake",
            type="humidifier",
            sensors=[Sensor(name="humidity", unit="%", value=30)],
        )

        class FakeDiscovery:
            def __init__(self, target):
                self.target = target
                self.executed = []
                self.updated = []

            def get_device(self, device_id):
                return self.target if device_id == self.target.device_id else None

            def update_device_sensors(self, device_id, sensor_data):
                self.updated.append((device_id, sensor_data))

            async def execute_command(self, device_id, action, params):
                self.executed.append((device_id, action, params))

        anima.discovery = FakeDiscovery(device)
        anima.brain = type("Brain", (), {"run_cycle": AsyncMock()})()

        event = Event(
            type=EventType.SENSOR_UPDATED,
            device_id="hum_01",
            data={"humidity": 35},
        )

        await anima._on_sensor_update(event)
        await anima._brain_cycle_task

        anima.brain.run_cycle.assert_awaited_once()
        assert anima.discovery.updated == [("hum_01", {"humidity": 35})]

    async def test_sensor_update_queues_follow_up_cycle_when_one_is_inflight(self):
        anima = Anima.__new__(Anima)
        device = Device(
            device_id="hum_01",
            name="Humidifier",
            adapter="fake",
            type="humidifier",
            sensors=[Sensor(name="humidity", unit="%", value=30)],
        )

        class FakeDiscovery:
            def __init__(self, target):
                self.target = target
                self.updated = []

            def get_device(self, device_id):
                return self.target if device_id == self.target.device_id else None

            def update_device_sensors(self, device_id, sensor_data):
                self.updated.append((device_id, sensor_data))

        started = asyncio.Event()
        release = asyncio.Event()
        cycle_calls: list[str] = []

        async def run_cycle():
            cycle_calls.append("run")
            if len(cycle_calls) == 1:
                started.set()
                await release.wait()

        anima.discovery = FakeDiscovery(device)
        anima.brain = type("Brain", (), {"run_cycle": AsyncMock(side_effect=run_cycle)})()

        first_task = asyncio.create_task(anima._run_brain_cycle_serially())
        await started.wait()

        event = Event(
            type=EventType.SENSOR_UPDATED,
            device_id="hum_01",
            data={"humidity": 35},
        )
        await anima._on_sensor_update(event)

        assert anima.brain.run_cycle.await_count == 1

        release.set()
        await first_task

        assert anima.brain.run_cycle.await_count == 2
        assert anima.discovery.updated == [("hum_01", {"humidity": 35})]

    async def test_bootstrap_startup_runs_brain_cycle_immediately(self):
        anima = Anima.__new__(Anima)
        anima.settings_store = SimpleNamespace(get=lambda key, default=None: default)
        anima.virtual_adapter = SimpleNamespace(register_device=MagicMock())
        anima.discovery = SimpleNamespace(
            scan=AsyncMock(),
            devices={},
            _adapter_map={},
        )
        anima._sync_device_rooms = MagicMock()
        anima._ensure_system_skills_for_devices = AsyncMock()
        anima._ensure_cold_start_profiles = AsyncMock()
        anima._maybe_start_onboarding = AsyncMock()
        anima._run_brain_cycle_serially = AsyncMock()

        await anima._bootstrap_startup({"settings": object()})

        anima.discovery.scan.assert_awaited_once()
        anima._ensure_system_skills_for_devices.assert_awaited_once()
        anima._ensure_cold_start_profiles.assert_awaited_once()
        anima._maybe_start_onboarding.assert_awaited_once()
        anima._run_brain_cycle_serially.assert_awaited_once()

    async def test_brain_cycle_pushes_events_when_execution_results_exist_without_tasks(self):
        queue: asyncio.Queue[str] = asyncio.Queue()
        plan_item = SkillPlanItem(
            skill_name="humidifier",
            device_type="humidifier",
            goal="提高室内湿度",
            reason="当前湿度偏低",
            priority=1,
        )
        action = SkillActionSpec(
            skill_name="humidifier",
            device_id="hum_01",
            action="set_humidity",
            params={"value": 50},
            reason="当前湿度偏低",
            expected_state={"target_humidity": 50},
        )
        verification = ActionVerificationResult(
            device_id="hum_01",
            action="set_humidity",
            verified=True,
            attempts=1,
            status="unverifiable_but_executed",
        )
        cycle_result = BrainCycleResult(
            execution_results=[
                SkillExecutionResult(
                    plan_item=plan_item,
                    actions=[action],
                    verifications=[verification],
                )
            ],
        )

        anima = Anima.__new__(Anima)
        anima._app_state = {"_brain_event_queues": [queue]}
        anima._brain_cycle_lock = asyncio.Lock()
        anima._brain_cycle_pending = True
        anima._brain_cycle_task = None
        anima.brain = SimpleNamespace(run_cycle=AsyncMock(return_value=cycle_result))

        await anima._drain_brain_cycles()

        payload = json.loads(await asyncio.wait_for(queue.get(), timeout=1))
        assert payload["type"] == "proactive_action"
        assert payload["skill"] == "humidifier"
        assert payload["action"] == "set_humidity"
        assert payload["verification_passed"] is True
