from core.models import DeviceCommand
from core.rules.engine import Condition, Rule, RulesEngine


class TestRulesEngine:
    def test_add_rule(self):
        engine = RulesEngine()
        rule = Rule(
            name="high_temp_ac",
            condition=Condition(sensor="temperature", operator=">", threshold=35),
            action=DeviceCommand(
                device_id="*",  # any AC device
                action="turn_on",
                source="rules",
                reason="Emergency: temperature > 35°C",
            ),
            device_type="air_conditioner",
            cooldown_seconds=300,
        )
        engine.add_rule(rule)
        assert len(engine.rules) == 1

    async def test_evaluate_triggers_rule(self):
        engine = RulesEngine()
        engine.add_rule(
            Rule(
                name="low_humidity",
                condition=Condition(sensor="humidity", operator="<", threshold=30),
                action=DeviceCommand(
                    device_id="*",
                    action="turn_on",
                    source="rules",
                    reason="Humidity below 30%",
                ),
                device_type="humidifier",
            )
        )

        commands = await engine.evaluate(
            device_type="humidifier",
            sensor_data={"humidity": 25.0},
            device_id="miot_hum_01",
        )
        assert len(commands) == 1
        assert commands[0].action == "turn_on"
        assert commands[0].device_id == "miot_hum_01"

    async def test_evaluate_no_trigger(self):
        engine = RulesEngine()
        engine.add_rule(
            Rule(
                name="low_humidity",
                condition=Condition(sensor="humidity", operator="<", threshold=30),
                action=DeviceCommand(device_id="*", action="turn_on", source="rules"),
                device_type="humidifier",
            )
        )

        commands = await engine.evaluate(
            device_type="humidifier",
            sensor_data={"humidity": 50.0},
            device_id="miot_hum_01",
        )
        assert len(commands) == 0

    async def test_cooldown_prevents_repeat(self):
        engine = RulesEngine()
        engine.add_rule(
            Rule(
                name="low_humidity",
                condition=Condition(sensor="humidity", operator="<", threshold=30),
                action=DeviceCommand(device_id="*", action="turn_on", source="rules"),
                device_type="humidifier",
                cooldown_seconds=600,
            )
        )

        cmds1 = await engine.evaluate("humidifier", {"humidity": 20}, "d1")
        cmds2 = await engine.evaluate("humidifier", {"humidity": 20}, "d1")
        assert len(cmds1) == 1
        assert len(cmds2) == 0  # cooldown active

    async def test_condition_operators(self):
        engine = RulesEngine()
        for op, val, expected in [
            (">", 36, True),
            (">", 34, False),
            ("<", 20, True),
            ("<", 40, False),
            (">=", 35, True),
            (">=", 34, False),
            ("<=", 35, True),
            ("<=", 36, False),
            ("==", 35, True),
            ("==", 34, False),
        ]:
            engine.rules.clear()
            engine._last_triggered.clear()
            engine.add_rule(
                Rule(
                    name="test",
                    condition=Condition(sensor="temp", operator=op, threshold=35),
                    action=DeviceCommand(device_id="*", action="turn_on", source="rules"),
                    device_type="ac",
                )
            )
            cmds = await engine.evaluate("ac", {"temp": val}, "d1")
            assert len(cmds) == (1 if expected else 0), f"op={op}, val={val}"
