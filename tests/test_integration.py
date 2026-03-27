"""
Integration test: verify the full pipeline works end-to-end.
Uses mock adapter (no real Xiaomi devices needed).
"""
import pytest
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from core.api.routes import create_app
from core.events.bus import EventBus
from core.discovery import DiscoveryOrchestrator
from core.rules.engine import RulesEngine
from core.memory.store import MemoryStore
from core.brain.skill_loader import SkillLoader
from core.brain.engine import Brain
from core.models import Device, Sensor, Capability, Event, EventType, ActionResult
from adapters.base import BaseAdapter


def fake_generated_package(name: str, device_type: str) -> dict:
    return {
        "folder_name": name,
        "skill_name": name,
        "files": {
            "SKILL.md": (
                f"---\nname: {name}\ndescription: generated test skill\n"
                f"metadata:\n  device_types:\n    - {device_type}\n  version: 0.1.0\n---\n\n# {name}\n"
            ),
            "references/knowledge.md": "# Knowledge\n",
            "references/decide.md": "Return `none` when no action is needed.\n## Current Data\n{current_data}\n## Device Capabilities\n{capabilities}\n## User Preferences\n{user_preferences}\n## Learned Profile\n{learned_profile}\n## Recent Decision History\n{recent_history}\n## Domain Knowledge\n{knowledge}\n",
            "references/learn.md": "Return structured JSON.\n## History\n{history}\n## Current Learned Profile\n{current_profile}\n",
            "scripts/actions.py": "from core.models import DeviceCommand\n\ndef turn_on(device_id: str, reason: str = \"\") -> DeviceCommand:\n    return DeviceCommand(device_id=device_id, action=\"turn_on\", source=\"brain\", reason=reason)\n",
        },
    }


def fake_generated_spec(name: str, device_type: str) -> dict:
    return {
        "folder_name": name,
        "skill_name": name,
        "description": "generated test skill",
        "device_types": [device_type],
        "domain_summary": f"Skill for {device_type}",
        "knowledge_points": ["Keep behavior safe."],
        "hard_rules": ["Return none when context is unclear."],
        "supported_actions": [{"name": "turn_on", "params": []}],
        "learning_focus": ["Observe repeated user actions"],
    }


class FakeHumidifierAdapter(BaseAdapter):
    name = "fake"

    def __init__(self):
        self.executed_commands = []
        self.last_action = None

    async def discover(self):
        return [Device(
            device_id="fake_hum_01",
            name="Test Humidifier",
            adapter="fake",
            type="humidifier",
            capabilities=[
                Capability(name="set_humidity", params={"min": 30, "max": 80}),
                Capability(name="turn_on"),
                Capability(name="turn_off"),
            ],
            sensors=[
                Sensor(name="power", unit="on/off", value=False),
                Sensor(name="humidity", unit="%", value=25.0),
                Sensor(name="water_level", unit="%", value=80.0),
            ],
        )]

    async def subscribe(self, device):
        if self.last_action in {"turn_on", "on"}:
            device.get_sensor("power").value = True
        elif self.last_action in {"turn_off", "off"}:
            device.get_sensor("power").value = False

    async def execute(self, device_id, action, params):
        self.last_action = action
        self.executed_commands.append({"device_id": device_id, "action": action, "params": params})
        return ActionResult(device_id=device_id, action=action, success=True)


class FakeSettings:
    def get(self, key, default=None):
        return default


class TestIntegrationPipeline:
    async def test_rules_engine_exists_but_is_not_required_for_brain_pipeline(self, tmp_path):
        rules = RulesEngine()
        rules.load_defaults()
        assert len(rules.rules) >= 2

    async def test_skill_loader_finds_skills(self):
        """Verify all default skills are discoverable."""
        loader = SkillLoader(skills_dir="skills")
        skills = loader.discover()
        names = {s.meta.name for s in skills}
        assert "humidifier" in names
        assert "air_conditioner" in names
        assert "light" in names
        assert "coordinator" in names

    async def test_memory_round_trip(self, tmp_path):
        """Memory can write and read preferences + history."""
        store = MemoryStore(base_dir=str(tmp_path / "memory"))

        await store.update_preferences("default", "comfort.temperature", "24°C")
        prefs = await store.get_preferences("default")
        assert "24°C" in prefs

        await store.append_history("default", {
            "device_id": "test_01", "action": "turn_on", "reason": "test",
        })
        history = await store.get_history("default")
        assert len(history) == 1

    async def test_brain_parse_llm_response(self, tmp_path):
        """Brain can parse LLM responses into commands."""
        bus = EventBus()
        loader = SkillLoader(skills_dir="skills")
        loader.discover()
        memory = MemoryStore(base_dir=str(tmp_path / "memory"))

        brain = Brain(bus=bus, skill_loader=loader, memory=memory)

        # Test JSON parsing
        cmd = brain._parse_llm_response(
            '{"action": "set_humidity", "params": {"value": 55}, "reason": "too dry"}',
            "test_device",
        )
        assert cmd is not None
        assert cmd.action == "set_humidity"
        assert cmd.params["value"] == 55

    async def test_full_pipeline_with_mock_llm(self, tmp_path):
        """Full pipeline: discovery → planner → skill execution → verification."""
        bus = EventBus()
        adapter = FakeHumidifierAdapter()
        discovery = DiscoveryOrchestrator(bus=bus, adapters=[adapter])
        loader = SkillLoader(skills_dir="skills")
        loader.discover()
        memory = MemoryStore(base_dir=str(tmp_path / "memory"))
        brain = Brain(bus=bus, skill_loader=loader, memory=memory)
        brain.set_environment_provider(discovery.get_all_devices)

        # Discover
        await discovery.scan()

        mock_outputs = [
            '[{"skill_name": "humidifier", "goal": "raise humidity", "reason": "humidity is low", "priority": 10}]',
            '{"action": "turn_on", "params": {}, "reason": "humidity is below comfort zone"}',
        ]
        brain._invoke_llm_text = AsyncMock(side_effect=mock_outputs)

        cycle = await brain.run_cycle()

        assert len(cycle.plan_items) == 1
        assert cycle.plan_items[0].skill_name == "humidifier"
        assert len(cycle.execution_results) == 1
        assert len(cycle.execution_results[0].actions) == 1
        assert cycle.execution_results[0].actions[0].action == "turn_on"
        assert cycle.execution_results[0].verifications[0].verified is True

        history = await memory.get_history("default")
        assert len(history) == 1
        assert history[0]["action"] == "turn_on"
        assert history[0]["skill_name"] == "humidifier"

    async def test_auto_generate_missing_system_skill_for_device_type(self, tmp_path: Path):
        temp_skills = tmp_path / "skills"
        shutil.copytree("skills", temp_skills)

        loader = SkillLoader(skills_dir=str(temp_skills))
        loader.discover()
        skill_creator = loader.get_skill("skill_creator")
        assert skill_creator is not None
        actions_module = loader.load_actions(skill_creator)
        assert actions_module is not None

        device = Device(
            device_id="fan_01",
            name="Desk Fan",
            adapter="fake",
            type="fan",
            capabilities=[
                Capability(name="turn_on"),
                Capability(name="turn_off"),
                Capability(name="set_mode", params={"inputs": [{"name": "mode", "type": "string"}]}),
            ],
        )

        discovery = DiscoveryOrchestrator(bus=EventBus(), adapters=[])
        discovery.devices[device.device_id] = device
        brain = Brain(bus=EventBus(), skill_loader=loader, memory=MemoryStore(base_dir=str(tmp_path / "memory")))

        with patch("anima_skill_skill_creator._build_llm", return_value=object()), patch(
            "anima_skill_skill_creator._generate_skill_spec_with_llm",
            return_value=(fake_generated_spec("fan", "fan"), []),
        ), patch(
            "anima_skill_skill_creator._generate_file_with_llm",
            side_effect=[
                (fake_generated_package("fan", "fan")["files"]["SKILL.md"], []),
                (fake_generated_package("fan", "fan")["files"]["references/knowledge.md"], []),
                (fake_generated_package("fan", "fan")["files"]["references/decide.md"], []),
                (fake_generated_package("fan", "fan")["files"]["references/learn.md"], []),
                (fake_generated_package("fan", "fan")["files"]["scripts/actions.py"], []),
            ],
        ):
            result = await actions_module.ensure_system_skills_for_devices(
                context={"discovery": discovery, "brain": brain, "settings": {}},
                params={"devices": [device]},
                reply="",
            )

        assert result["status"] == "created"
        assert "fan" in result["created_skills"]
        assert (temp_skills / "system" / "fan" / "SKILL.md").exists()
        assert loader.get_system_skill_for_device("fan") is not None

    async def test_environment_endpoint_returns_snapshot(self, tmp_path):
        bus = EventBus()
        adapter = FakeHumidifierAdapter()
        discovery = DiscoveryOrchestrator(bus=bus, adapters=[adapter])
        loader = SkillLoader(skills_dir="skills")
        loader.discover()
        memory = MemoryStore(base_dir=str(tmp_path / "memory"))
        brain = Brain(bus=bus, skill_loader=loader, memory=memory)
        brain.set_environment_provider(discovery.get_all_devices)

        await discovery.scan()

        ac = Device(
            device_id="ac_01",
            name="AC",
            adapter="fake",
            type="air_conditioner",
            sensors=[Sensor(name="temperature", unit="°C", value=26.5)],
        )
        discovery.devices[ac.device_id] = ac

        app = create_app({
            "discovery": discovery,
            "brain": brain,
            "memory": memory,
            "settings": FakeSettings(),
        })
        client = TestClient(app)

        response = client.get("/api/environment")

        assert response.status_code == 200
        data = response.json()
        assert "devices" in data
        assert "signals" in data
        assert "humidity" in data["signals"]
        assert "temperature" in data["signals"]

    async def test_refresh_environment_endpoint_refreshes_existing_devices(self, tmp_path):
        bus = EventBus()
        adapter = FakeHumidifierAdapter()
        discovery = DiscoveryOrchestrator(bus=bus, adapters=[adapter])
        loader = SkillLoader(skills_dir="skills")
        loader.discover()
        memory = MemoryStore(base_dir=str(tmp_path / "memory"))
        brain = Brain(bus=bus, skill_loader=loader, memory=memory)
        brain.set_environment_provider(discovery.get_all_devices)

        await discovery.scan()
        device = discovery.get_device("fake_hum_01")
        device.get_sensor("humidity").value = None

        async def fake_subscribe(target):
            target.get_sensor("humidity").value = 42

        adapter.subscribe = fake_subscribe

        app = create_app({
            "discovery": discovery,
            "brain": brain,
            "memory": memory,
            "settings": FakeSettings(),
        })
        client = TestClient(app)

        response = client.post("/api/environment/refresh")

        assert response.status_code == 200
        data = response.json()
        assert data["refreshed"] == 1
        assert data["failed"] == 0
        assert data["environment"]["signals"]["humidity"][0]["value"] == 42
