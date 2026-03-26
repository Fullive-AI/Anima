import pytest
from unittest.mock import AsyncMock
from core.discovery import DiscoveryOrchestrator
from core.events.bus import EventBus
from core.models import Device, Event, EventType
from adapters.base import BaseAdapter


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
