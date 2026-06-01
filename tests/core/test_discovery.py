from adapters.base import BaseAdapter
from core.devices.discovery import DiscoveryOrchestrator
from core.events.bus import EventBus
from core.models import Device, Event, EventType, Sensor


class MockAdapter(BaseAdapter):
    name = "mock"

    def __init__(self):
        self.subscribed = []

    async def discover(self) -> list[Device]:
        return [
            Device(device_id="mock_01", name="Mock Light", adapter="mock", type="light"),
            Device(device_id="mock_02", name="Mock Humidifier", adapter="mock", type="humidifier"),
        ]

    async def subscribe(self, device) -> None:
        self.subscribed.append(device.device_id)

    async def execute(self, device_id, action, params):
        pass


class TestDiscoveryOrchestrator:
    async def test_scan_discovers_devices(self):
        bus = EventBus()
        disco = DiscoveryOrchestrator(bus=bus, adapters=[MockAdapter()])
        devices = await disco.scan()
        assert len(devices) == 2
        assert "mock_01" in disco.devices
        assert "mock_02" in disco.devices

    async def test_scan_emits_events(self):
        bus = EventBus()
        events = []

        async def handler(event: Event):
            events.append(event)

        bus.subscribe(EventType.DEVICE_DISCOVERED, handler)
        disco = DiscoveryOrchestrator(bus=bus, adapters=[MockAdapter()])
        await disco.scan()

        assert len(events) == 2
        assert events[0].type == EventType.DEVICE_DISCOVERED

    async def test_get_device(self):
        bus = EventBus()
        disco = DiscoveryOrchestrator(bus=bus, adapters=[MockAdapter()])
        await disco.scan()
        device = disco.get_device("mock_01")
        assert device is not None
        assert device.name == "Mock Light"

    async def test_get_devices_by_type(self):
        bus = EventBus()
        disco = DiscoveryOrchestrator(bus=bus, adapters=[MockAdapter()])
        await disco.scan()
        lights = disco.get_devices_by_type("light")
        assert len(lights) == 1

    async def test_duplicate_device_not_re_announced(self):
        bus = EventBus()
        events = []

        async def handler(event: Event):
            events.append(event)

        bus.subscribe(EventType.DEVICE_DISCOVERED, handler)
        disco = DiscoveryOrchestrator(bus=bus, adapters=[MockAdapter()])
        await disco.scan()
        await disco.scan()  # second scan

        assert len(events) == 2  # only first scan emits events

    async def test_scan_subscribes_new_devices(self):
        bus = EventBus()
        adapter = MockAdapter()
        disco = DiscoveryOrchestrator(bus=bus, adapters=[adapter])

        await disco.scan()

        assert adapter.subscribed == ["mock_01", "mock_02"]

    async def test_scan_emits_sensor_updated_after_initial_subscribe(self):
        bus = EventBus()
        events = []

        class SensorAdapter(BaseAdapter):
            name = "sensor-mock"

            async def discover(self) -> list[Device]:
                return [
                    Device(
                        device_id="sensor_01",
                        name="Sensor Humidifier",
                        adapter="mock",
                        type="humidifier",
                        sensors=[Sensor(name="humidity", unit="%", value=None)],
                    )
                ]

            async def subscribe(self, device) -> None:
                device.get_sensor("humidity").value = 45

            async def execute(self, device_id, action, params):
                pass

        async def handler(event: Event):
            events.append(event)

        bus.subscribe(EventType.SENSOR_UPDATED, handler)
        disco = DiscoveryOrchestrator(bus=bus, adapters=[SensorAdapter()])

        await disco.scan()

        assert len(events) == 1
        assert events[0].type == EventType.SENSOR_UPDATED
        assert events[0].device_id == "sensor_01"
        assert events[0].data == {"humidity": 45}

    async def test_refresh_device_states_emits_sensor_updated_only_when_value_changes(self):
        bus = EventBus()
        events = []

        class RefreshingAdapter(BaseAdapter):
            name = "refresh-mock"

            def __init__(self):
                self.values = [40, 40, 55]

            async def discover(self) -> list[Device]:
                return [
                    Device(
                        device_id="sensor_01",
                        name="Sensor Humidifier",
                        adapter="mock",
                        type="humidifier",
                        sensors=[Sensor(name="humidity", unit="%", value=None)],
                    )
                ]

            async def subscribe(self, device) -> None:
                device.get_sensor("humidity").value = self.values.pop(0)

            async def execute(self, device_id, action, params):
                pass

        async def handler(event: Event):
            events.append(event)

        adapter = RefreshingAdapter()
        bus.subscribe(EventType.SENSOR_UPDATED, handler)
        disco = DiscoveryOrchestrator(bus=bus, adapters=[adapter])

        await disco.scan()
        events.clear()

        result_no_change = await disco.refresh_device_states(["sensor_01"])
        result_changed = await disco.refresh_device_states(["sensor_01"])

        assert result_no_change == {"refreshed": 1, "failed": 0}
        assert result_changed == {"refreshed": 1, "failed": 0}
        assert len(events) == 1
        assert events[0].data == {"humidity": 55}
