from __future__ import annotations

import logging
import operator
import time
from typing import Any

from pydantic import BaseModel

from core.models import DeviceCommand

logger = logging.getLogger(__name__)

OPERATORS = {
    ">": operator.gt,
    "<": operator.lt,
    ">=": operator.ge,
    "<=": operator.le,
    "==": operator.eq,
}


class Condition(BaseModel):
    sensor: str
    operator: str  # >, <, >=, <=, ==
    threshold: float


class Rule(BaseModel):
    name: str
    condition: Condition
    action: DeviceCommand
    device_type: str
    cooldown_seconds: int = 0


class RulesEngine:
    def __init__(self) -> None:
        self.rules: list[Rule] = []
        self._last_triggered: dict[str, float] = {}

    def add_rule(self, rule: Rule) -> None:
        self.rules.append(rule)

    def load_defaults(self) -> None:
        defaults = [
            Rule(
                name="emergency_high_temp",
                condition=Condition(sensor="temperature", operator=">", threshold=35),
                action=DeviceCommand(
                    device_id="*", action="turn_on", source="rules", reason="Emergency: temperature > 35°C"
                ),
                device_type="air_conditioner",
                cooldown_seconds=300,
            ),
            Rule(
                name="emergency_low_humidity",
                condition=Condition(sensor="humidity", operator="<", threshold=20),
                action=DeviceCommand(
                    device_id="*", action="turn_on", source="rules", reason="Emergency: humidity < 20%"
                ),
                device_type="humidifier",
                cooldown_seconds=300,
            ),
        ]
        for rule in defaults:
            self.add_rule(rule)

    async def evaluate(
        self,
        device_type: str,
        sensor_data: dict[str, Any],
        device_id: str,
    ) -> list[DeviceCommand]:
        triggered: list[DeviceCommand] = []

        for rule in self.rules:
            if rule.device_type != device_type:
                continue

            sensor_value = sensor_data.get(rule.condition.sensor)
            if sensor_value is None:
                continue

            op_func = OPERATORS.get(rule.condition.operator)
            if op_func is None:
                continue

            if not op_func(sensor_value, rule.condition.threshold):
                continue

            # Cooldown check
            now = time.monotonic()
            last = self._last_triggered.get(rule.name, 0)
            if rule.cooldown_seconds > 0 and (now - last) < rule.cooldown_seconds:
                continue

            self._last_triggered[rule.name] = now
            command = rule.action.model_copy()
            if command.device_id == "*":
                command.device_id = device_id
            triggered.append(command)
            logger.info("Rule triggered: %s → %s on %s", rule.name, command.action, device_id)

        return triggered
