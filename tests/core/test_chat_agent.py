from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path
import shutil

import pytest

from core.brain.skill_loader import SkillLoader
from core.chat_agent import ChatAgent


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
        "knowledge_points": ["Keep the behavior safe."],
        "hard_rules": ["Return none when context is unclear."],
        "supported_actions": [{"name": "turn_on", "params": []}],
        "learning_focus": ["Which actions the user repeats most often"],
    }


def fake_generated_files(name: str, device_type: str) -> dict[str, str]:
    return fake_generated_package(name, device_type)["files"]


class FakeDiscovery:
    def __init__(self):
        self.devices = {}

    def get_all_devices(self):
        return list(self.devices.values())

    async def scan(self):
        self.devices["dev1"] = SimpleNamespace(
            device_id="dev1",
            name="Lamp",
            type="light",
            online=True,
        )
        return [self.devices["dev1"]]


class FakeSettings:
    def __init__(self):
        self._data = {}

    def get(self, key, default=None):
        return self._data.get(key, default)


class TestChatAgent:
    @pytest.mark.asyncio
    async def test_scan_local_devices_with_heuristic(self):
        loader = SkillLoader(skills_dir="skills")
        loader.discover()
        agent = ChatAgent(loader)
        settings = FakeSettings()
        settings._data["llm_api_key"] = "your-api-key-here"
        app_state = {
            "discovery": FakeDiscovery(),
            "settings": settings,
        }

        result = await agent.handle_message("帮我扫描屋内设备", app_state)

        assert result["action"] == "scan_local_devices"
        assert result["new_devices"] == 1
        assert result["total"] == 1

    @pytest.mark.asyncio
    async def test_start_qr_scan_with_heuristic(self):
        loader = SkillLoader(skills_dir="skills")
        loader.discover()
        loader.load_actions(loader.get_skill("device_discovery"))
        agent = ChatAgent(loader)
        settings = FakeSettings()
        settings._data["llm_api_key"] = "your-api-key-here"
        app_state = {
            "discovery": FakeDiscovery(),
            "settings": settings,
        }

        with patch("anima_skill_device_discovery.QrLoginFlow") as qr_cls:
            qr_cls.return_value.start.return_value = {
                "status": "ok",
                "qr_image_b64": "base64-image",
            }
            result = await agent.handle_message("扫码连接米家设备", app_state)

        assert result["action"] == "start_xiaomi_qr_scan"
        assert result["status"] == "qr_required"
        assert result["qr_image_b64"] == "base64-image"

    @pytest.mark.asyncio
    async def test_create_custom_skill_with_heuristic(self, tmp_path: Path):
        temp_skills = tmp_path / "skills"
        shutil.copytree("skills", temp_skills)

        loader = SkillLoader(skills_dir=str(temp_skills))
        loader.discover()
        loader.load_actions(loader.get_skill("skill_creator"))
        agent = ChatAgent(loader)
        app_state = {
            "discovery": FakeDiscovery(),
            "settings": FakeSettings(),
            "brain": SimpleNamespace(_skill_loader=loader),
        }

        with patch("anima_skill_skill_creator._build_llm", return_value=object()), patch(
            "anima_skill_skill_creator._generate_skill_spec_with_llm",
            return_value=(fake_generated_spec("morning_departure", "morning_departure"), []),
        ), patch(
            "anima_skill_skill_creator._generate_file_with_llm",
            side_effect=[
                (fake_generated_files("morning_departure", "morning_departure")["SKILL.md"], []),
                (fake_generated_files("morning_departure", "morning_departure")["references/knowledge.md"], []),
                (fake_generated_files("morning_departure", "morning_departure")["references/decide.md"], []),
                (fake_generated_files("morning_departure", "morning_departure")["references/learn.md"], []),
                (fake_generated_files("morning_departure", "morning_departure")["scripts/actions.py"], []),
            ],
        ):
            result = await agent.handle_message("帮我新增一个技能，早上7点起床后离家时自动关闭家里的电器", app_state)

        assert result["action"] == "create_custom_skill"
        assert result["status"] == "created"
        created_path = Path(result["path"])
        assert created_path.exists()
        assert (created_path / "SKILL.md").exists()
        assert (created_path / "references" / "decide.md").exists()
        assert (created_path / "scripts" / "actions.py").exists()
        assert loader.get_skill(result["skill_name"]) is not None

    @pytest.mark.asyncio
    async def test_create_custom_skill_with_placeholder_key_returns_reply(self):
        loader = SkillLoader(skills_dir="skills")
        loader.discover()
        agent = ChatAgent(loader)
        settings = FakeSettings()
        settings._data["llm_api_key"] = "your-api-key-here"
        app_state = {
            "discovery": FakeDiscovery(),
            "settings": settings,
            "brain": SimpleNamespace(_skill_loader=loader),
        }

        result = await agent.handle_message("帮我新增一个技能，晚上回家时自动开灯", app_state)

        assert result["reply"] == "创建 skill 需要先配置可用的 LLM。"
        assert result["error"] == "llm_required"

    @pytest.mark.asyncio
    async def test_chat_action_exception_returns_safe_reply(self):
        loader = SkillLoader(skills_dir="skills")
        loader.discover()
        agent = ChatAgent(loader)
        settings = FakeSettings()
        settings._data["llm_api_key"] = "your-api-key-here"
        app_state = {
            "discovery": FakeDiscovery(),
            "settings": settings,
            "brain": SimpleNamespace(_skill_loader=loader),
        }

        async def broken_handler(*args, **kwargs):
            raise RuntimeError("boom")

        with patch.object(loader, "load_actions", return_value=SimpleNamespace(scan_local_devices=broken_handler)):
            result = await agent.handle_message("帮我扫描设备", app_state)

        assert result["error"] == "action_execution_failed"
        assert "后端出错" in result["reply"]

    @pytest.mark.asyncio
    async def test_create_custom_skill_retries_invalid_llm_output(self, tmp_path: Path):
        temp_skills = tmp_path / "skills"
        shutil.copytree("skills", temp_skills)

        loader = SkillLoader(skills_dir=str(temp_skills))
        loader.discover()
        loader.load_actions(loader.get_skill("skill_creator"))
        agent = ChatAgent(loader)
        app_state = {
            "discovery": FakeDiscovery(),
            "settings": FakeSettings(),
            "brain": SimpleNamespace(_skill_loader=loader),
        }

        class FakeLLM:
            def __init__(self):
                self.calls = 0

            async def ainvoke(self, prompt: str):
                self.calls += 1
                if "Return exactly one compact JSON object" in prompt:
                    if self.calls == 1:
                        return SimpleNamespace(content="not-json")
                    return SimpleNamespace(
                        content='{"folder_name":"retry_skill","skill_name":"retry_skill","description":"ok","device_types":["retry_skill"],"domain_summary":"Retry skill","knowledge_points":["Prefer safe behavior"],"hard_rules":["Return none when unsure"],"supported_actions":[{"name":"turn_on","params":[]}],"learning_focus":["Observe repeated actions"]}'
                    )

                file_map = fake_generated_files("retry_skill", "retry_skill")
                for path, content in file_map.items():
                    if path in prompt:
                        return SimpleNamespace(content=content)
                return SimpleNamespace(content="")

        with patch("anima_skill_skill_creator._build_llm", return_value=FakeLLM()):
            result = await agent.handle_message("帮我新增一个技能，回家时自动开灯", app_state)

        assert result["status"] == "created"
        assert result["folder_name"] == "retry_skill"

    @pytest.mark.asyncio
    async def test_create_custom_skill_returns_validation_details_on_failure(self):
        loader = SkillLoader(skills_dir="skills")
        loader.discover()
        loader.load_actions(loader.get_skill("skill_creator"))
        agent = ChatAgent(loader)
        app_state = {
            "discovery": FakeDiscovery(),
            "settings": FakeSettings(),
            "brain": SimpleNamespace(_skill_loader=loader),
        }

        class BadLLM:
            async def ainvoke(self, prompt: str):
                if "Return exactly one compact JSON object" in prompt:
                    return SimpleNamespace(
                        content='{"folder_name":"bad","skill_name":"bad","description":"bad","device_types":["bad"],"domain_summary":"bad","knowledge_points":["x"],"hard_rules":["y"],"supported_actions":[{"name":"turn_on","params":[]}],"learning_focus":["z"]}'
                    )
                if "references/decide.md" in prompt:
                    return SimpleNamespace(content="missing placeholders and no action none")
                file_map = fake_generated_files("bad", "bad")
                if "SKILL.md" in prompt:
                    return SimpleNamespace(content=file_map["SKILL.md"])
                if "references/knowledge.md" in prompt:
                    return SimpleNamespace(content=file_map["references/knowledge.md"])
                if "references/learn.md" in prompt:
                    return SimpleNamespace(content=file_map["references/learn.md"])
                if "scripts/actions.py" in prompt:
                    return SimpleNamespace(content=file_map["scripts/actions.py"])
                return SimpleNamespace(content="")

        with patch("anima_skill_skill_creator._build_llm", return_value=BadLLM()):
            result = await agent.handle_message("帮我新增一个技能，离家后自动关闭空调", app_state)

        assert result["error"] == "skill_generation_failed"
        assert "失败原因" in result["reply"]
        assert result["details"]
