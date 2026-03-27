from unittest.mock import AsyncMock

from core.main import Anima
from core.models import Device, Event, EventType, Sensor


class TestMain:
    async def test_sensor_update_triggers_brain_cycle_without_rules(self):
        anima = Anima.__new__(Anima)
        device = Device(
            device_id="hum_01",
            name="Humidifier",
            adapter="fake",
            type="humidifier",
            sensors=[Sensor(name="humidity", unit="%", value=30)],
        )

        class FakeDiscovery:
            def __init__(self, target):
                self.target = target
                self.executed = []
                self.updated = []

            def get_device(self, device_id):
                return self.target if device_id == self.target.device_id else None

            def update_device_sensors(self, device_id, sensor_data):
                self.updated.append((device_id, sensor_data))

            async def execute_command(self, device_id, action, params):
                self.executed.append((device_id, action, params))

        anima.discovery = FakeDiscovery(device)
        anima.brain = type("Brain", (), {"run_cycle": AsyncMock()})()

        event = Event(
            type=EventType.SENSOR_UPDATED,
            device_id="hum_01",
            data={"humidity": 35},
        )

        await anima._on_sensor_update(event)

        anima.brain.run_cycle.assert_awaited_once()
        assert anima.discovery.updated == [("hum_01", {"humidity": 35})]
