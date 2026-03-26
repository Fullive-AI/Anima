import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from adapters.miot.adapter import MIoTAdapter
from core.models import Device, Sensor


class TestMIoTAdapter:
    def test_adapter_name(self):
        adapter = MIoTAdapter()
        assert adapter.name == "miot"

    @patch("adapters.miot.adapter.miio.Discovery")
    async def test_discover_returns_devices(self, mock_discovery_cls):
        mock_listener = MagicMock()
        mock_info = MagicMock()
        mock_info.ip = "192.168.1.100"
        mock_info.token = "aabbccdd" * 4
        mock_info.model = "zhimi.humidifier.v1"
        mock_info.name = "Humidifier"

        adapter = MIoTAdapter()
        # Test device type mapping
        assert adapter._guess_device_type("zhimi.humidifier.v1") == "humidifier"
        assert adapter._guess_device_type("xiaomi.aircondition.mc5") == "air_conditioner"
        assert adapter._guess_device_type("yeelink.light.lamp1") == "light"
        assert adapter._guess_device_type("unknown.model.x1") == "unknown"

    def test_build_device_id(self):
        adapter = MIoTAdapter()
        did = adapter._build_device_id("192.168.1.100", "zhimi.humidifier.v1")
        assert did == "miot_192_168_1_100_zhimi_humidifier_v1"

    async def test_execute_calls_device(self):
        adapter = MIoTAdapter()
        # Without real device, execute should return failure
        result = await adapter.execute("nonexistent", "turn_on", {})
        assert result.success is False

    async def test_subscribe_refreshes_sensor_values(self):
        adapter = MIoTAdapter()
        device = Device(
            device_id="miot_1",
            name="Humidifier",
            adapter="miot",
            type="humidifier",
            sensors=[
                Sensor(name="power", unit="on/off"),
                Sensor(name="humidity", unit="%"),
                Sensor(name="water_level", unit="%"),
            ],
        )

        status = SimpleNamespace(is_on=True, humidity=48, water_level=75)
        miio_device = SimpleNamespace(status=lambda: status)

        with patch.object(adapter, "_get_miio_device", return_value=miio_device):
            await adapter.subscribe(device)

        assert device.get_sensor("power").value is True
        assert device.get_sensor("humidity").value == 48
        assert device.get_sensor("water_level").value == 75

    def test_unknown_model_gets_generic_reflection_capabilities(self):
        adapter = MIoTAdapter()

        capabilities = adapter._build_capabilities("unknown.vendor.device", has_token=True)
        capability_names = {capability.name for capability in capabilities}

        assert capability_names == {
            "miot_get_property",
            "miot_set_property",
            "miot_call_action",
        }

    async def test_subscribe_refreshes_generic_device_status(self):
        adapter = MIoTAdapter()
        device = Device(
            device_id="miot_generic",
            name="Unknown Device",
            adapter="miot",
            type="unknown",
            sensors=[
                Sensor(name="power", unit="on/off"),
                Sensor(name="miot_online", unit="bool"),
            ],
        )

        status = SimpleNamespace(power="on")
        miio_device = SimpleNamespace(status=lambda: status)

        with patch.object(adapter, "_get_miio_device", return_value=miio_device):
            await adapter.subscribe(device)

        assert device.get_sensor("power").value is True
        assert device.get_sensor("miot_online").value is True
