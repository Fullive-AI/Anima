from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class EventType(StrEnum):
    DEVICE_DISCOVERED = "device.discovered"
    DEVICE_OFFLINE = "device.offline"
    SENSOR_UPDATED = "sensor.updated"
    RULE_TRIGGERED = "rule.triggered"
    ACTION_EXECUTED = "action.executed"
    USER_COMMAND = "user.command"


class Capability(BaseModel):
    name: str
    params: dict[str, Any] = Field(default_factory=dict)


class Sensor(BaseModel):
    name: str
    unit: str = ""
    value: float | str | bool | None = None


class Device(BaseModel):
    device_id: str
    name: str
    adapter: str
    type: str
    room: str | None = None
    online: bool = True
    capabilities: list[Capability] = Field(default_factory=list)
    sensors: list[Sensor] = Field(default_factory=list)

    def get_sensor(self, name: str) -> Sensor | None:
        return next((s for s in self.sensors if s.name == name), None)


class DeviceCommand(BaseModel):
    device_id: str
    action: str
    params: dict[str, Any] = Field(default_factory=dict)
    source: str = "brain"  # brain / rules / user
    reason: str = ""
    confidence: float | None = None
    expected_outcome: str = ""
    should_wait_seconds: int | None = None


class ActionResult(BaseModel):
    device_id: str
    action: str
    success: bool
    message: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Event(BaseModel):
    type: EventType
    device_id: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RoomInfo(BaseModel):
    room_id: str
    name: str
    device_ids: list[str] = Field(default_factory=list)


class SkillMeta(BaseModel):
    name: str
    description: str = ""
    device_types: list[str] = Field(default_factory=list)
    version: str = "0.1.0"
