import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from core.brain.engine import Brain
from core.brain.skill_loader import SkillLoader
from core.memory.store import MemoryStore
from core.models import Device, Sensor, DeviceCommand, Capability


class TestBrain:
    def test_build_context(self):
        brain = Brain.__new__(Brain)
        brain._skill_loader = SkillLoader(skills_dir="skills")
        brain._skill_loader.discover()
        brain._environment_provider = None

        device = Device(
            device_id="hum_01", name="Humidifier", adapter="miot",
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
        )
        assert "humidity" in context.lower()
        assert "35" in context
        assert "55% humidity" in context
        assert "current environment state" in context.lower()

    def test_build_context_includes_environment_state(self):
        brain = Brain.__new__(Brain)
        brain._skill_loader = SkillLoader(skills_dir="skills")
        brain._skill_loader.discover()

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

        skill = brain._skill_loader.get_skill_for_device("humidifier")
        context = brain._build_prompt_context(
            skill=skill,
            device=current_device,
            user_memory={
                "preferences": "",
                "history": [],
                "learned": "",
                "learned_profiles": {},
            },
        )

        assert '"current_device_id": "hum_01"' in context
        assert '"temperature"' in context
        assert '"humidity"' in context

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

    def test_parse_llm_response_with_markdown_fence(self):
        brain = Brain.__new__(Brain)
        response = '```json\n{"action": "turn_on", "params": {}, "reason": "test"}\n```'
        result = brain._parse_llm_response(response, "hum_01")
        assert result is not None
        assert result.action == "turn_on"

    def test_parse_llm_response_none_action(self):
        brain = Brain.__new__(Brain)
        response = '{"action": "none", "params": {}, "reason": "all good"}'
        result = brain._parse_llm_response(response, "hum_01")
        assert result is None

    def test_parse_llm_response_invalid(self):
        brain = Brain.__new__(Brain)
        result = brain._parse_llm_response("I don't know what to do", "hum_01")
        assert result is None

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

    def test_sanitize_command_with_enum_options(self):
        brain = Brain.__new__(Brain)
        device = Device(
            device_id="ac_01",
            name="AC",
            adapter="miot",
            type="air_conditioner",
            capabilities=[
                Capability(
                    name="set_mode",
                    params={
                        "inputs": [
                            {"name": "mode", "type": "enum", "options": ["auto", "cool", "heat"], "default": "auto"}
                        ]
                    },
                ),
            ],
        )
        command = DeviceCommand(device_id="ac_01", action="set_mode", params={"mode": "dry"})
        result = brain._sanitize_command_for_device(command, device)
        assert result is not None
        assert result.params["mode"] == "auto"

    def test_reject_unsupported_action_when_capabilities_known(self):
        brain = Brain.__new__(Brain)
        device = Device(
            device_id="light_01",
            name="Light",
            adapter="miot",
            type="light",
            capabilities=[Capability(name="set_brightness", params={})],
        )
        command = DeviceCommand(device_id="light_01", action="set_color_temp", params={"kelvin": 3000})
        result = brain._sanitize_command_for_device(command, device)
        assert result is None
