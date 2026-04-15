from core.events.bus import EventBus
from core.models import Event, EventType


class TestEventBus:
    async def test_subscribe_and_emit(self):
        bus = EventBus()
        received = []

        async def handler(event: Event):
            received.append(event)

        bus.subscribe(EventType.SENSOR_UPDATED, handler)
        event = Event(type=EventType.SENSOR_UPDATED, device_id="d1", data={"temp": 26})
        await bus.emit(event)

        assert len(received) == 1
        assert received[0].data["temp"] == 26

    async def test_multiple_subscribers(self):
        bus = EventBus()
        count = {"a": 0, "b": 0}

        async def handler_a(event: Event):
            count["a"] += 1

        async def handler_b(event: Event):
            count["b"] += 1

        bus.subscribe(EventType.DEVICE_DISCOVERED, handler_a)
        bus.subscribe(EventType.DEVICE_DISCOVERED, handler_b)
        await bus.emit(Event(type=EventType.DEVICE_DISCOVERED, device_id="d1"))

        assert count["a"] == 1
        assert count["b"] == 1

    async def test_wildcard_subscriber(self):
        bus = EventBus()
        received = []

        async def handler(event: Event):
            received.append(event)

        bus.subscribe("*", handler)
        await bus.emit(Event(type=EventType.SENSOR_UPDATED, device_id="d1"))
        await bus.emit(Event(type=EventType.DEVICE_DISCOVERED, device_id="d2"))

        assert len(received) == 2

    async def test_unsubscribe(self):
        bus = EventBus()
        received = []

        async def handler(event: Event):
            received.append(event)

        bus.subscribe(EventType.SENSOR_UPDATED, handler)
        bus.unsubscribe(EventType.SENSOR_UPDATED, handler)
        await bus.emit(Event(type=EventType.SENSOR_UPDATED, device_id="d1"))

        assert len(received) == 0

    async def test_handler_error_does_not_crash_bus(self):
        bus = EventBus()
        results = []

        async def bad_handler(event: Event):
            raise ValueError("boom")

        async def good_handler(event: Event):
            results.append("ok")

        bus.subscribe(EventType.SENSOR_UPDATED, bad_handler)
        bus.subscribe(EventType.SENSOR_UPDATED, good_handler)
        await bus.emit(Event(type=EventType.SENSOR_UPDATED, device_id="d1"))

        assert results == ["ok"]
