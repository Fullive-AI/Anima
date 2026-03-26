import pytest
from datetime import datetime
from core.models import (
    Device, Capability, Sensor, DeviceCommand, Event, EventType,
    SkillMeta, RoomInfo, ActionResult,
)


class TestDevice:
    def test_create_device(self):
        device = Device(
            device_id="miot_humidifier_01",
            name="Bedroom Humidifier",
            adapter="miot",
            type="humidifier",
            capabilities=[
                Capability(name="set_humidity", params={"min": 30, "max": 80, "step": 10}),
                Capability(name="turn_on"),
                Capability(name="turn_off"),
            ],
            sensors=[
                Sensor(name="humidity", unit="%", value=45.0),
                Sensor(name="water_level", unit="%", value=60.0),
            ],
        )
        assert device.device_id == "miot_humidifier_01"
        assert device.adapter == "miot"
        assert device.room is None
        assert device.online is True
        assert len(device.capabilities) == 3
        assert len(device.sensors) == 2

    def test_device_assign_room(self):
        device = Device(
            device_id="miot_light_01",
            name="Desk Lamp",
            adapter="miot",
            type="light",
        )
        device.room = "bedroom"
        assert device.room == "bedroom"

    def test_device_get_sensor_value(self):
        device = Device(
            device_id="miot_humidifier_01",
            name="Humidifier",
            adapter="miot",
            type="humidifier",
            sensors=[Sensor(name="humidity", unit="%", value=45.0)],
        )
        assert device.get_sensor("humidity").value == 45.0
        assert device.get_sensor("nonexistent") is None


class TestDeviceCommand:
    def test_create_command(self):
        cmd = DeviceCommand(
            device_id="miot_humidifier_01",
            action="set_humidity",
            params={"value": 55},
            source="brain",
            reason="User prefers 55%, currently 45%",
            confidence=0.9,
            expected_outcome="raise humidity",
            should_wait_seconds=900,
        )
        assert cmd.action == "set_humidity"
        assert cmd.params["value"] == 55
        assert cmd.source == "brain"
        assert cmd.confidence == 0.9
        assert cmd.expected_outcome == "raise humidity"
        assert cmd.should_wait_seconds == 900


class TestEvent:
    def test_create_event(self):
        event = Event(
            type=EventType.SENSOR_UPDATED,
            device_id="miot_humidifier_01",
            data={"humidity": 45.0},
        )
        assert event.type == EventType.SENSOR_UPDATED
        assert event.timestamp is not None

    def test_event_types(self):
        assert EventType.DEVICE_DISCOVERED == "device.discovered"
        assert EventType.SENSOR_UPDATED == "sensor.updated"
        assert EventType.RULE_TRIGGERED == "rule.triggered"
        assert EventType.ACTION_EXECUTED == "action.executed"
        assert EventType.USER_COMMAND == "user.command"


class TestRoomInfo:
    def test_create_room(self):
        room = RoomInfo(room_id="bedroom", name="Bedroom")
        assert room.device_ids == []

    def test_room_add_device(self):
        room = RoomInfo(room_id="bedroom", name="Bedroom")
        room.device_ids.append("miot_humidifier_01")
        assert len(room.device_ids) == 1
