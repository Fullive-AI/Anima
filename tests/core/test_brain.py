from core.brain.engine import Brain
from core.brain.skill_loader import SkillLoader
from core.models import (
    Capability,
    Device,
    DeviceCommand,
    Sensor,
    SkillActionSpec,
    SkillSummary,
)
from skills.system.air_purifier.scripts.actions import execute as execute_air_purifier_skill


class TestBrain:
    def test_build_context(self):
        brain = Brain.__new__(Brain)
        brain._skill_loader = SkillLoader(skills_dir="skills")
        brain._skill_loader.discover()
        brain._environment_provider = None

        device = Device(
            device_id="hum_01",
            name="Humidifier",
            adapter="miot",
            type="humidifier",
            sensors=[Sensor(name="humidity", unit="%", value=35)],
        )

        skill = brain._skill_loader.get_skill_for_device("humidifier")
        context = brain._build_prompt_context(
            skill=skill,
            device=device,
            user_memory={
                "preferences": "likes 55%",
                "history": [],
                "learned": "",
                "learned_profiles": {"humidifier": '{"stable_preferences":["55% humidity"]}'},
            },
            planner_goal="raise humidity",
            planner_reason="room is dry",
        )
        assert "humidity" in context.lower()
        assert "35" in context
        assert "55% humidity" in context
        assert "current environment state" in context.lower()
        assert "planner intent" in context.lower()

    def test_get_environment_state(self):
        brain = Brain.__new__(Brain)
        current_device = Device(
            device_id="hum_01",
            name="Humidifier",
            adapter="miot",
            type="humidifier",
            sensors=[Sensor(name="humidity", unit="%", value=35)],
        )
        peer_device = Device(
            device_id="ac_01",
            name="AC",
            adapter="miot",
            type="air_conditioner",
            sensors=[Sensor(name="temperature", unit="°C", value=27)],
        )
        brain._environment_provider = lambda: [current_device, peer_device]

        snapshot = brain.get_environment_state()

        assert snapshot["current_device_id"] is None
        assert len(snapshot["devices"]) == 2
        assert "humidity" in snapshot["signals"]
        assert "temperature" in snapshot["signals"]

    def test_parse_llm_response_valid_json(self):
        brain = Brain.__new__(Brain)
        response = '{"action": "set_humidity", "params": {"value": 55}, "reason": "too dry", "confidence": 0.91, "expected_outcome": "raise humidity", "should_wait_seconds": 900}'
        result = brain._parse_llm_response(response, "hum_01")
        assert result is not None
        assert result.action == "set_humidity"
        assert result.params["value"] == 55
        assert result.confidence == 0.91
        assert result.expected_outcome == "raise humidity"
        assert result.should_wait_seconds == 900

    def test_parse_planner_response_fills_device_type(self):
        brain = Brain.__new__(Brain)
        response = '[{"skill_name":"humidifier","goal":"raise humidity","reason":"dry","priority":5}]'
        result = brain._parse_planner_response(
            response,
            [SkillSummary(name="humidifier", description="skill", device_type="humidifier")],
        )
        assert len(result) == 1
        assert result[0].skill_name == "humidifier"
        assert result[0].device_type == "humidifier"
        assert result[0].priority == 5

    def test_build_planner_prompt_includes_humidifier_threshold_hint(self):
        brain = Brain.__new__(Brain)
        prompt = brain._build_planner_prompt(
            devices=[],
            environment_state={},
            user_memory={},
            lightweight_skills=[SkillSummary(name="humidifier", description="humidity control", device_type="humidifier")],
        )
        assert "below 50%" in prompt
        assert "humidifier" in prompt

    def test_load_planner_hints_from_markdown_file(self):
        brain = Brain.__new__(Brain)
        hints = brain._load_planner_hints()
        assert "# Planner Hints" in hints
        assert "below 50%" in hints

    def test_build_chat_planner_prompt_includes_system_action_schema(self):
        brain = Brain.__new__(Brain)
        prompt = brain._build_chat_planner_prompt(
            message="帮我扫描设备",
            devices=[],
            environment_state={},
            user_memory={},
            skill_summaries=[SkillSummary(name="device_discovery", description="scan devices", device_type="")],
        )
        assert "system_action" in prompt
        assert "scan_local_devices" in prompt

    def test_sanitize_command_with_capability_limits(self):
        brain = Brain.__new__(Brain)
        device = Device(
            device_id="hum_01",
            name="Humidifier",
            adapter="miot",
            type="humidifier",
            capabilities=[
                Capability(name="set_humidity", params={"min": 30, "max": 80, "step": 5}),
            ],
        )
        command = DeviceCommand(device_id="hum_01", action="set_humidity", params={"value": 83})
        result = brain._sanitize_command_for_device(command, device)
        assert result is not None
        assert result.params["value"] == 80

    def test_derive_expected_state(self):
        brain = Brain.__new__(Brain)
        command = DeviceCommand(device_id="light_01", action="set_brightness", params={"value": 60})
        expected = brain._derive_expected_state(command)
        assert expected == {"brightness": 60}

    async def test_execute_action_with_retry_verifies_state(self):
        brain = Brain.__new__(Brain)
        device = Device(
            device_id="light_01",
            name="Light",
            adapter="fake",
            type="light",
            sensors=[Sensor(name="power", unit="on/off", value=False)],
        )

        class FakeDiscovery:
            def __init__(self, target):
                self.target = target
                self.calls = 0

            async def execute_command(self, device_id, action, params):
                self.calls += 1
                return type("Result", (), {"message": "", "success": True})()

            async def refresh_device_states(self, device_ids=None):
                self.target.get_sensor("power").value = True
                return {"refreshed": 1, "failed": 0}

            def get_device(self, device_id):
                return self.target

        discovery = FakeDiscovery(device)
        action_spec = SkillActionSpec(
            skill_name="light",
            device_id="light_01",
            action="turn_on",
            params={},
            expected_state={"power": True},
        )

        verification = await brain._execute_action_with_retry(action_spec, discovery)

        assert verification.verified is True
        assert verification.status == "verified"
        assert verification.attempts == 1

    async def test_execute_action_with_retry_does_not_treat_failed_command_as_success(self):
        brain = Brain.__new__(Brain)
        device = Device(
            device_id="speaker_01",
            name="Speaker",
            adapter="fake",
            type="speaker",
            sensors=[],
        )

        class FakeDiscovery:
            async def execute_command(self, device_id, action, params):
                return type("Result", (), {"message": "speaker rejected request", "success": False})()

            async def refresh_device_states(self, device_ids=None):
                return {"refreshed": 1, "failed": 0}

            def get_device(self, device_id):
                return device

        verification = await brain._execute_action_with_retry(
            SkillActionSpec(
                skill_name="speaker",
                device_id="speaker_01",
                action="play_random_audio",
                params={},
                expected_state={},
            ),
            FakeDiscovery(),
        )

        assert verification.verified is False
        assert verification.status == "verification_failed"
        assert verification.message == "speaker rejected request"

    async def test_air_purifier_execute_maps_turn_off_intent_to_off_action(self):
        purifier = Device(
            device_id="purifier_01",
            name="Purifier",
            adapter="fake",
            type="air_purifier",
            online=True,
            capabilities=[Capability(name="on"), Capability(name="off")],
        )

        class FakeDiscovery:
            def get_devices_by_type(self, device_type):
                assert device_type == "air_purifier"
                return [purifier]

        actions = await execute_air_purifier_skill(
            context={"discovery": FakeDiscovery(), "brain": object()},
            plan_item=type(
                "PlanItem",
                (),
                {
                    "goal": "turn off the air purifier",
                    "reason": "用户要求关闭空气净化器",
                },
            )(),
        )

        assert len(actions) == 1
        assert actions[0]["action"] == "off"
        assert actions[0]["expected_state"] == {"power": False}

    async def test_handle_chat_message_runs_unified_graph_for_system_action(self, tmp_path):
        loader = SkillLoader(skills_dir="skills")
        loader.discover()
        memory = __import__("core.memory.store", fromlist=["MemoryStore"]).MemoryStore(base_dir=str(tmp_path / "memory"))
        brain = Brain(bus=object(), skill_loader=loader, memory=memory)

        class FakeDiscovery:
            def __init__(self):
                self.devices = {}

            def get_all_devices(self):
                return []

            def get_devices_by_type(self, device_type):
                return []

            async def scan(self):
                self.devices["dev1"] = Device(
                    device_id="dev1",
                    name="Lamp",
                    adapter="fake",
                    type="light",
                )
                return [self.devices["dev1"]]

        class FakeSettings:
            def get(self, key, default=None):
                if key == "llm_api_key":
                    return "sk-test"
                return default

        discovery = FakeDiscovery()
        brain.set_environment_provider(discovery.get_all_devices)
        brain._invoke_llm_text = __import__("unittest.mock", fromlist=["AsyncMock"]).AsyncMock(
            return_value='{"reply":"我先扫描一下当前设备。","should_execute":true,"system_action":"scan_local_devices","system_skill":"device_discovery","params":{},"skill_plan_items":[]}'
        )

        result = await brain.handle_chat_message(
            "帮我扫描设备",
            {"discovery": discovery, "settings": FakeSettings(), "brain": brain},
        )

        assert result["action"] == "scan_local_devices"
        assert result["new_devices"] == 1

    async def test_handle_chat_message_runs_speaker_skill_for_random_playback(self, tmp_path):
        loader = SkillLoader(skills_dir="skills")
        loader.discover()
        memory = __import__("core.memory.store", fromlist=["MemoryStore"]).MemoryStore(base_dir=str(tmp_path / "memory"))
        brain = Brain(bus=object(), skill_loader=loader, memory=memory)

        speaker = Device(
            device_id="speaker_01",
            name="Xiaomi Smart Speaker",
            adapter="miot",
            type="speaker",
            capabilities=[Capability(name="play_random_audio"), Capability(name="stop_audio")],
        )

        class FakeDiscovery:
            def __init__(self, target):
                self.target = target
                self.executed = []

            def get_all_devices(self):
                return [self.target]

            def get_devices_by_type(self, device_type):
                return [self.target] if device_type == "speaker" else []

            async def execute_command(self, device_id, action, params):
                self.executed.append((device_id, action, params))
                return type("Result", (), {"message": "", "success": True})()

            async def refresh_device_states(self, device_ids=None):
                return {"refreshed": 1, "failed": 0}

            def get_device(self, device_id):
                return self.target if device_id == self.target.device_id else None

        class FakeSettings:
            def get(self, key, default=None):
                if key == "llm_api_key":
                    return "sk-test"
                return default

        discovery = FakeDiscovery(speaker)
        brain.set_environment_provider(discovery.get_all_devices)
        brain._invoke_llm_text = __import__("unittest.mock", fromlist=["AsyncMock"]).AsyncMock(
            return_value='{"reply":"我来随机放一首。","should_execute":true,"system_action":"none","system_skill":"","params":{},"skill_plan_items":[{"skill_name":"speaker","goal":"play random music on the speaker","reason":"user asked to play music","priority":10}]}'
        )

        result = await brain.handle_chat_message(
            "随机放一首歌",
            {"discovery": discovery, "settings": FakeSettings(), "brain": brain},
        )

        assert result["executed"] is True
        assert result["execution_results"][0]["actions"][0]["action"] == "play_random_audio"
        assert discovery.executed == [("speaker_01", "play_random_audio", {})]
