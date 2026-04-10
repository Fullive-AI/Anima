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
from core.media.audio_registry import LocalAudioRegistry
from core.events.bus import EventBus
from core.devices.discovery import DiscoveryOrchestrator
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
                f"metadata:\n  device_types:\n    - {device_type}\n  version: 0.1.0\n---\n\n# {name}\n\n"
                "## Goal\nGenerate a safe test skill.\n\n"
                "## Load These Resources\n- `references/knowledge.md`\n- `references/decide.md`\n- `references/learn.md`\n- `scripts/actions.py`\n\n"
                "## Working Rules\n- Keep the skill narrow.\n- Return `none` when context is unclear.\n"
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


def fake_sparse_generated_spec(name: str, device_type: str) -> dict:
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
        "primary_steps": [],
        "success_criteria": [],
        "constraints": [],
        "needed_inputs": [],
        "assumptions": [],
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

    def get_xiaomi_credentials(self):
        return None


def fake_request_analysis(*, clarification: bool = False) -> dict:
    return {
        "summary": "Generate a reusable automation skill.",
        "goal": "Create a narrow skill package.",
        "trigger_description": "Use when the described automation should run.",
        "primary_steps": ["Read context", "Choose action", "Return safe no-op when needed"],
        "success_criteria": ["The skill is specific", "The package stays consistent"],
        "constraints": ["Keep the scope narrow"],
        "needed_inputs": ["device state"],
        "assumptions": [],
        "should_ask_clarification": clarification,
        "clarification_questions": ["What exact trigger should start this automation?"] if clarification else [],
    }


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

    async def test_memory_cold_start_bootstrap_generates_context_from_devices(self, tmp_path):
        store = MemoryStore(base_dir=str(tmp_path / "memory"))

        result = await store.ensure_cold_start_profiles(
            device_types=["humidifier", "speaker"],
            user_id="default",
            style="comfort_first",
        )

        prefs = await store.get_preferences("default")
        profiles = await store.get_learned_profiles("default")

        assert result["preferences_created"] is True
        assert result["profiles_created"] == ["humidifier", "speaker"]
        assert "45-55%" in prefs
        assert "voice interactions low-noise" in prefs
        assert "humidifier" in profiles
        assert "speaker" in profiles

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
        assert any(item["action"] == "plan.execute_skill" for item in history)
        assert any(item["action"] == "turn_on" for item in history)
        execution_entry = next(item for item in history if item["action"] == "turn_on")
        assert execution_entry["skill_name"] == "humidifier"

    async def test_full_pipeline_with_task_plan_cycle(self, tmp_path):
        bus = EventBus()
        adapter = FakeHumidifierAdapter()
        discovery = DiscoveryOrchestrator(bus=bus, adapters=[adapter])
        loader = SkillLoader(skills_dir="skills")
        loader.discover()
        memory = MemoryStore(base_dir=str(tmp_path / "memory"))
        brain = Brain(bus=bus, skill_loader=loader, memory=memory)
        brain.set_environment_provider(discovery.get_all_devices)

        await discovery.scan()

        mock_outputs = [
            '{"task_plan_items":[{"kind":"refresh_environment","reason":"confirm stale state","priority":5},{"kind":"execute_skill","skill_name":"humidifier","goal":"raise humidity","reason":"humidity is low","priority":10}]}',
            '{"action": "turn_on", "params": {}, "reason": "humidity is below comfort zone"}',
        ]
        brain._invoke_llm_text = AsyncMock(side_effect=mock_outputs)

        cycle = await brain.run_cycle()

        assert len(cycle.task_plan_items) == 2
        assert cycle.task_plan_items[0].kind == "refresh_environment"
        assert cycle.task_plan_items[1].kind == "execute_skill"
        assert len(cycle.plan_items) == 1
        assert cycle.plan_items[0].skill_name == "humidifier"
        assert len(cycle.execution_results) == 1
        assert cycle.execution_results[0].actions[0].action == "turn_on"
        history = await memory.get_history("default")
        assert any(item["action"] == "plan.refresh_environment" for item in history)
        assert any(item["action"] == "plan.execute_skill" for item in history)

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

    async def test_create_custom_skill_requests_clarification_before_generating(self, tmp_path: Path):
        temp_skills = tmp_path / "skills"
        shutil.copytree("skills", temp_skills)

        loader = SkillLoader(skills_dir=str(temp_skills))
        loader.discover()
        skill_creator = loader.get_skill("skill_creator")
        assert skill_creator is not None
        actions_module = loader.load_actions(skill_creator)
        assert actions_module is not None

        brain = Brain(bus=EventBus(), skill_loader=loader, memory=MemoryStore(base_dir=str(tmp_path / "memory")))

        with patch("anima_skill_skill_creator._build_llm", return_value=object()), patch(
            "anima_skill_skill_creator._analyze_request_with_llm",
            return_value=(fake_request_analysis(clarification=True), []),
        ), patch(
            "anima_skill_skill_creator._generate_package_with_llm",
            new_callable=AsyncMock,
        ) as generate_package_mock:
            result = await actions_module.create_custom_skill(
                context={"brain": brain, "settings": {}},
                params={"request": "做个自动化 skill"},
                reply="",
            )

        assert result["status"] == "needs_clarification"
        assert result["questions"] == ["What exact trigger should start this automation?"]
        generate_package_mock.assert_not_awaited()

    async def test_create_custom_skill_stops_reasking_after_follow_up_clarification(self, tmp_path: Path):
        temp_skills = tmp_path / "skills"
        shutil.copytree("skills", temp_skills)

        loader = SkillLoader(skills_dir=str(temp_skills))
        loader.discover()
        skill_creator = loader.get_skill("skill_creator")
        assert skill_creator is not None
        actions_module = loader.load_actions(skill_creator)
        assert actions_module is not None

        brain = Brain(bus=EventBus(), skill_loader=loader, memory=MemoryStore(base_dir=str(tmp_path / "memory")))

        with patch("anima_skill_skill_creator._build_llm", return_value=object()), patch(
            "anima_skill_skill_creator._analyze_request_with_llm",
            new_callable=AsyncMock,
            return_value=(fake_request_analysis(clarification=True), []),
        ) as analyze_mock, patch(
            "anima_skill_skill_creator._generate_package_with_llm",
            new_callable=AsyncMock,
            return_value=(fake_generated_package("wake_up_reminder", "reminder"), []),
        ) as generate_package_mock:
            result = await actions_module.create_custom_skill(
                context={"brain": brain, "settings": {}},
                params={
                    "request": (
                        "新增一个起床提醒技能\n\n"
                        "Additional clarification from the user:\n"
                        "工作日早上 7:30 叫我起床，法定节假日不提醒"
                    ),
                    "allow_clarification": False,
                },
                reply="",
            )

        assert result["status"] == "created"
        analyze_mock.assert_awaited_once()
        assert analyze_mock.await_args.kwargs["allow_clarification"] is False
        generate_package_mock.assert_awaited_once()
        assert (temp_skills / "custom" / "wake_up_reminder" / "SKILL.md").exists()

    async def test_create_custom_skill_returns_structured_error_when_analysis_raises(self, tmp_path: Path):
        temp_skills = tmp_path / "skills"
        shutil.copytree("skills", temp_skills)

        loader = SkillLoader(skills_dir=str(temp_skills))
        loader.discover()
        skill_creator = loader.get_skill("skill_creator")
        assert skill_creator is not None
        actions_module = loader.load_actions(skill_creator)
        assert actions_module is not None

        brain = Brain(bus=EventBus(), skill_loader=loader, memory=MemoryStore(base_dir=str(tmp_path / "memory")))

        with patch("anima_skill_skill_creator._build_llm", return_value=object()), patch(
            "anima_skill_skill_creator._analyze_request_with_llm",
            new_callable=AsyncMock,
            side_effect=RuntimeError("llm upstream 502"),
        ):
            result = await actions_module.create_custom_skill(
                context={"brain": brain, "settings": {}},
                params={"request": "新增一个起床提醒技能"},
                reply="",
            )

        assert result["error"] == "skill_analysis_exception"
        assert "llm upstream 502" in result["reply"]

    async def test_create_custom_skill_accepts_sparse_generated_spec_without_crashing(self, tmp_path: Path):
        temp_skills = tmp_path / "skills"
        shutil.copytree("skills", temp_skills)

        loader = SkillLoader(skills_dir=str(temp_skills))
        loader.discover()
        skill_creator = loader.get_skill("skill_creator")
        assert skill_creator is not None
        actions_module = loader.load_actions(skill_creator)
        assert actions_module is not None

        brain = Brain(bus=EventBus(), skill_loader=loader, memory=MemoryStore(base_dir=str(tmp_path / "memory")))

        with patch("anima_skill_skill_creator._build_llm", return_value=object()), patch(
            "anima_skill_skill_creator._analyze_request_with_llm",
            new_callable=AsyncMock,
            return_value=(fake_request_analysis(clarification=False), []),
        ), patch(
            "anima_skill_skill_creator._generate_skill_spec_with_llm",
            new_callable=AsyncMock,
            return_value=(fake_sparse_generated_spec("wake_up_reminder", "reminder"), []),
        ), patch(
            "anima_skill_skill_creator._generate_file_with_llm",
            new_callable=AsyncMock,
            side_effect=[
                (fake_generated_package("wake_up_reminder", "reminder")["files"]["SKILL.md"], []),
                (fake_generated_package("wake_up_reminder", "reminder")["files"]["references/knowledge.md"], []),
                (fake_generated_package("wake_up_reminder", "reminder")["files"]["references/decide.md"], []),
                (fake_generated_package("wake_up_reminder", "reminder")["files"]["references/learn.md"], []),
                (fake_generated_package("wake_up_reminder", "reminder")["files"]["scripts/actions.py"], []),
            ],
        ):
            result = await actions_module.create_custom_skill(
                context={"brain": brain, "settings": {}},
                params={"request": "新增一个起床提醒技能"},
                reply="",
            )

        assert result["status"] == "created"
        assert (temp_skills / "custom" / "wake_up_reminder" / "SKILL.md").exists()

    async def test_create_custom_skill_simple_scaffold_creates_curtain_skill_without_llm(self, tmp_path: Path):
        temp_skills = tmp_path / "skills"
        shutil.copytree("skills", temp_skills)

        loader = SkillLoader(skills_dir=str(temp_skills))
        loader.discover()
        skill_creator = loader.get_skill("skill_creator")
        assert skill_creator is not None
        actions_module = loader.load_actions(skill_creator)
        assert actions_module is not None

        brain = Brain(bus=EventBus(), skill_loader=loader, memory=MemoryStore(base_dir=str(tmp_path / "memory")))

        result = await actions_module.create_custom_skill(
            context={"brain": brain, "settings": {}},
            params={"request": "帮我新增一个控制窗帘的技能"},
            reply="",
        )

        created_dir = temp_skills / "custom" / "curtain"
        assert result["status"] == "created"
        assert result["creation_mode"] == "simple_scaffold"
        assert result["folder_name"] == "curtain"
        assert created_dir.exists()
        assert (created_dir / "SKILL.md").exists()
        assert (created_dir / "references" / "decide.md").exists()
        assert (created_dir / "scripts" / "actions.py").exists()

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

    async def test_memory_endpoint_returns_normalized_profiles_and_memories(self, tmp_path):
        bus = EventBus()
        adapter = FakeHumidifierAdapter()
        discovery = DiscoveryOrchestrator(bus=bus, adapters=[adapter])
        loader = SkillLoader(skills_dir="skills")
        loader.discover()
        memory = MemoryStore(base_dir=str(tmp_path / "memory"))
        brain = Brain(bus=bus, skill_loader=loader, memory=memory)
        brain.set_environment_provider(discovery.get_all_devices)

        await memory.update_preferences("default", "comfort.temperature", "23°C")
        await memory.update_learned_for_skill(
            "default",
            "light",
            '{"stable_preferences":["Prefer warm dim lights"],"time_based_patterns":[],"seasonal_patterns":[],"weak_signals":[],"confidence_notes":"Consistent evening pattern."}',
        )
        await memory.upsert_extracted_memory(
            "default",
            "evening_lighting_preference",
            {
                "title": "Evening lighting preference",
                "category": "preference",
                "summary": "Warm dim lights are preferred in the evening.",
                "details": ["Observed in repeated light adjustments."],
                "device_types": ["light"],
                "confidence": "high",
                "source_actions": ["set_brightness"],
            },
        )
        await memory.update_memory_extraction_state("default", history_cursor=3, last_batch_size=3)
        await memory.append_history("default", {"action": "set_brightness", "device_type": "light"})

        app = create_app({
            "discovery": discovery,
            "brain": brain,
            "memory": memory,
            "settings": FakeSettings(),
        })
        client = TestClient(app)

        response = client.get("/api/memory")

        assert response.status_code == 200
        data = response.json()
        assert "23°C" in data["preferences"]
        assert data["learned_profiles"]["light"]["stable_preferences"] == ["Prefer warm dim lights"]
        assert data["extracted_memories"]["evening_lighting_preference"]["category"] == "preference"
        assert data["extraction_state"]["history_cursor"] == 3
        assert len(data["recent_history"]) == 1

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

    async def test_skills_endpoint_returns_system_and_custom_skill_inventory(self, tmp_path):
        skills_dir = tmp_path / "skills"
        system_skill_dir = skills_dir / "system" / "humidifier"
        system_skill_dir.mkdir(parents=True)
        (system_skill_dir / "SKILL.md").write_text(
            (
                "---\n"
                "name: humidifier\n"
                "description: system humidifier skill\n"
                "metadata:\n"
                "  device_types:\n"
                "    - humidifier\n"
                "  version: 1.0.0\n"
                "---\n"
            ),
            encoding="utf-8",
        )
        (system_skill_dir / "references").mkdir()
        (system_skill_dir / "references" / "decide.md").write_text("Return none with {current_data}.", encoding="utf-8")
        (system_skill_dir / "scripts").mkdir()
        (system_skill_dir / "scripts" / "actions.py").write_text("pass\n", encoding="utf-8")

        custom_skill_dir = skills_dir / "custom" / "night_curtain"
        custom_skill_dir.mkdir(parents=True)
        (custom_skill_dir / "SKILL.md").write_text(
            (
                "---\n"
                "name: night_curtain\n"
                "description: close curtains at night\n"
                "metadata:\n"
                "  device_types:\n"
                "    - curtain\n"
                "  version: 2.0.0\n"
                "---\n"
            ),
            encoding="utf-8",
        )
        (custom_skill_dir / "references").mkdir()
        (custom_skill_dir / "references" / "decide.md").write_text("Return none with {current_data}.", encoding="utf-8")

        loader = SkillLoader(skills_dir=str(skills_dir))
        loader.discover()
        memory = MemoryStore(base_dir=str(tmp_path / "memory"))
        brain = Brain(bus=EventBus(), skill_loader=loader, memory=memory)

        app = create_app({
            "discovery": DiscoveryOrchestrator(bus=EventBus(), adapters=[]),
            "brain": brain,
            "memory": memory,
            "settings": FakeSettings(),
        })
        client = TestClient(app)

        response = client.get("/api/skills")

        assert response.status_code == 200
        data = response.json()
        assert [item["name"] for item in data["system_skills"]] == ["humidifier"]
        assert data["system_skills"][0]["scope"] == "system"
        assert data["system_skills"][0]["folder_name"] == "humidifier"
        assert data["system_skills"][0]["has_actions"] is True
        assert [item["name"] for item in data["custom_skills"]] == ["night_curtain"]
        assert data["custom_skills"][0]["scope"] == "custom"
        assert data["custom_skills"][0]["folder_name"] == "night_curtain"
        assert data["custom_skills"][0]["has_decide_prompt"] is True

    async def test_audio_file_endpoint_serves_registered_local_audio(self, tmp_path):
        audio_file = tmp_path / "sample.wav"
        audio_file.write_bytes(b"RIFFdemoWAVE")
        registry = LocalAudioRegistry(port=8080)
        token = registry.register_file(audio_file)

        app = create_app({
            "discovery": DiscoveryOrchestrator(bus=EventBus(), adapters=[]),
            "brain": Brain(bus=EventBus(), skill_loader=SkillLoader(skills_dir="skills"), memory=MemoryStore(base_dir=str(tmp_path / "memory"))),
            "memory": MemoryStore(base_dir=str(tmp_path / "memory")),
            "settings": FakeSettings(),
            "audio_registry": registry,
        })
        client = TestClient(app)

        response = client.get(f"/api/audio/{token}")

        assert response.status_code == 200
        assert response.content == b"RIFFdemoWAVE"

    async def test_chat_endpoint_returns_structured_error_when_brain_raises(self, tmp_path):
        app = create_app({
            "discovery": DiscoveryOrchestrator(bus=EventBus(), adapters=[]),
            "brain": type(
                "BrokenBrain",
                (),
                {"handle_chat_message": staticmethod(AsyncMock(side_effect=RuntimeError("boom")))}
            )(),
            "memory": MemoryStore(base_dir=str(tmp_path / "memory")),
            "settings": FakeSettings(),
        })
        client = TestClient(app)

        response = client.post("/api/chat", json={"message": "新增一个技能"})

        assert response.status_code == 200
        data = response.json()
        assert data["error"] == "chat_request_failed"
        assert "boom" in data["reply"]

    async def test_audio_registry_accepts_file_uri_paths(self, tmp_path):
        audio_file = tmp_path / "sample.wav"
        audio_file.write_bytes(b"RIFFdemoWAVE")
        registry = LocalAudioRegistry(port=8080)

        token = registry.register_file(f"file:{audio_file}")
        entry = registry.get(token)

        assert entry is not None
        assert entry.path == audio_file.resolve()
