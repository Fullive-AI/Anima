from types import SimpleNamespace
from unittest.mock import patch

import pytest

from core.brain.skill_loader import SkillLoader
from core.chat_agent import ChatAgent


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
        app_state = {
            "discovery": FakeDiscovery(),
            "settings": FakeSettings(),
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
        app_state = {
            "discovery": FakeDiscovery(),
            "settings": FakeSettings(),
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
