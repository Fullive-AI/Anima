import asyncio

from adapters.virtual.adapter import VIRTUAL_TYPE_CAPABILITIES, VirtualAdapter
from core.events.bus import EventBus
from core.models import Event, EventType


class TestVirtualAdapter:
    async def test_register_device_creates_device_with_chinese_labels(self):
        bus = EventBus()
        adapter = VirtualAdapter(bus=bus)

        device = adapter.register_device("virt_01", "台灯", "light")

        assert device.device_id == "virt_01"
        assert device.adapter == "virtual"
        cap_names = {c.name for c in device.capabilities}
        assert "on" in cap_names
        assert "off" in cap_names
        on_cap = next(c for c in device.capabilities if c.name == "on")
        assert on_cap.params["label"] == "开启"
        off_cap = next(c for c in device.capabilities if c.name == "off")
        assert off_cap.params["label"] == "关闭"

    async def test_execute_on_sets_power_true(self):
        bus = EventBus()
        adapter = VirtualAdapter(bus=bus)
        adapter.register_device("virt_01", "加湿器", "humidifier")

        result = await adapter.execute("virt_01", "on", {})

        assert result.success is True
        assert result.message == "虚拟设备已执行"
        assert adapter._states["virt_01"]["power"] is True

    async def test_execute_off_sets_power_false(self):
        bus = EventBus()
        adapter = VirtualAdapter(bus=bus)
        adapter.register_device("virt_01", "加湿器", "humidifier")
        adapter._states["virt_01"]["power"] = True

        result = await adapter.execute("virt_01", "off", {})

        assert result.success is True
        assert adapter._states["virt_01"]["power"] is False

    async def test_execute_unknown_device_returns_failure(self):
        bus = EventBus()
        adapter = VirtualAdapter(bus=bus)

        result = await adapter.execute("nonexistent", "on", {})

        assert result.success is False
        assert "虚拟设备未找到" in result.message

    async def test_execute_emits_sensor_updated_event(self):
        bus = EventBus()
        events: list[Event] = []

        async def handler(event: Event):
            events.append(event)

        bus.subscribe(EventType.SENSOR_UPDATED, handler)
        adapter = VirtualAdapter(bus=bus)
        adapter.register_device("virt_01", "灯", "light")

        await adapter.execute("virt_01", "on", {})
        await asyncio.sleep(0.2)

        assert len(events) == 1
        assert events[0].type == EventType.SENSOR_UPDATED
        assert events[0].device_id == "virt_01"

    async def test_register_device_with_unknown_type_gets_default_capabilities(self):
        bus = EventBus()
        adapter = VirtualAdapter(bus=bus)

        device = adapter.register_device("virt_01", "未知设备", "unknown_type")

        cap_names = {c.name for c in device.capabilities}
        assert "on" in cap_names
        assert "off" in cap_names
        on_cap = next(c for c in device.capabilities if c.name == "on")
        assert on_cap.params["label"] == "开启"

    def test_virtual_type_capabilities_all_have_chinese_labels(self):
        for device_type, caps in VIRTUAL_TYPE_CAPABILITIES.items():
            for cap in caps:
                assert "label" in cap["params"], f"{device_type}/{cap['name']} missing label"
                label = cap["params"]["label"]
                assert label, f"{device_type}/{cap['name']} has empty label"

    async def test_remove_device(self):
        bus = EventBus()
        adapter = VirtualAdapter(bus=bus)
        adapter.register_device("virt_01", "灯", "light")

        adapter.remove_device("virt_01")

        assert "virt_01" not in adapter._devices
        assert "virt_01" not in adapter._states

    async def test_set_target_humidity_updates_state(self):
        bus = EventBus()
        adapter = VirtualAdapter(bus=bus)
        adapter.register_device("virt_01", "加湿器", "humidifier")

        result = await adapter.execute("virt_01", "set_target_humidity", {"value": 60})

        assert result.success is True
        assert adapter._states["virt_01"]["humidity"] == 60
