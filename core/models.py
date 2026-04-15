from __future__ import annotations

from datetime import UTC, datetime
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
    value: float | int | str | bool | None = None


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
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Event(BaseModel):
    type: EventType
    device_id: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RoomInfo(BaseModel):
    room_id: str
    name: str
    device_ids: list[str] = Field(default_factory=list)


class SkillMeta(BaseModel):
    name: str
    description: str = ""
    device_types: list[str] = Field(default_factory=list)
    version: str = "0.1.0"


class SkillSummary(BaseModel):
    name: str
    description: str = ""
    device_type: str = ""


class SkillPlanItem(BaseModel):
    skill_name: str
    device_type: str
    goal: str = ""
    reason: str = ""
    priority: int = 0


class SkillActionSpec(BaseModel):
    skill_name: str
    device_id: str
    action: str
    params: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""
    expected_state: dict[str, Any] = Field(default_factory=dict)


class ActionVerificationResult(BaseModel):
    device_id: str
    action: str
    verified: bool
    attempts: int = 0
    status: str = ""
    expected_state: dict[str, Any] = Field(default_factory=dict)
    observed_state: dict[str, Any] = Field(default_factory=dict)
    message: str = ""


class SkillExecutionResult(BaseModel):
    plan_item: SkillPlanItem
    actions: list[SkillActionSpec] = Field(default_factory=list)
    verifications: list[ActionVerificationResult] = Field(default_factory=list)


class BrainCycleResult(BaseModel):
    plan_items: list[SkillPlanItem] = Field(default_factory=list)
    task_plan_items: list[TaskPlanItem] = Field(default_factory=list)
    execution_results: list[SkillExecutionResult] = Field(default_factory=list)


class ChatPlan(BaseModel):
    reply: str = ""
    should_execute: bool = False
    system_action: str = "none"
    system_skill: str = ""
    params: dict[str, Any] = Field(default_factory=dict)
    skill_plan_items: list[SkillPlanItem] = Field(default_factory=list)
    task_plan_items: list[TaskPlanItem] = Field(default_factory=list)


class TaskPlanItem(BaseModel):
    kind: str
    goal: str = ""
    reason: str = ""
    priority: int = 0
    skill_name: str = ""
    system_skill: str = ""
    system_action: str = ""
    question: str = ""
    params: dict[str, Any] = Field(default_factory=dict)
    target_device_ids: list[str] = Field(default_factory=list)
    expected_state: dict[str, Any] = Field(default_factory=dict)
