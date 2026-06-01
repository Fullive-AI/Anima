from __future__ import annotations

import asyncio
import logging
from typing import Any

from adapters.base import BaseAdapter
from core.events.bus import EventBus
from core.models import ActionResult, Capability, Device, Event, EventType, Sensor

logger = logging.getLogger(__name__)

VIRTUAL_TYPE_CAPABILITIES: dict[str, list[dict[str, Any]]] = {
    "light": [
        {"name": "on", "params": {"label": "开启"}},
        {"name": "off", "params": {"label": "关闭"}},
        {
            "name": "set_brightness",
            "params": {"label": "亮度", "inputs": [{"name": "value", "type": "number", "required": True}]},
        },
        {
            "name": "set_color_temp",
            "params": {"label": "色温", "inputs": [{"name": "kelvin", "type": "number", "required": True}]},
        },
    ],
    "humidifier": [
        {"name": "on", "params": {"label": "开启"}},
        {"name": "off", "params": {"label": "关闭"}},
        {
            "name": "set_target_humidity",
            "params": {"label": "目标湿度", "inputs": [{"name": "value", "type": "number", "required": True}]},
        },
    ],
    "air_conditioner": [
        {"name": "on", "params": {"label": "开启"}},
        {"name": "off", "params": {"label": "关闭"}},
        {
            "name": "set_target_temperature",
            "params": {"label": "目标温度", "inputs": [{"name": "value", "type": "number", "required": True}]},
        },
        {
            "name": "set_mode",
            "params": {"label": "模式", "inputs": [{"name": "mode", "type": "string", "required": True}]},
        },
    ],
    "air_purifier": [
        {"name": "on", "params": {"label": "开启"}},
        {"name": "off", "params": {"label": "关闭"}},
        {
            "name": "set_mode",
            "params": {"label": "模式", "inputs": [{"name": "mode", "type": "string", "required": True}]},
        },
    ],
}

VIRTUAL_TYPE_SENSORS: dict[str, list[tuple[str, str, Any]]] = {
    "light": [("power", "on/off", False), ("brightness", "%", 80), ("color_temp", "K", 4000)],
    "humidifier": [
        ("power", "on/off", False),
        ("humidity", "%", 50),
        ("temperature", "°C", 22.0),
        ("water_level", "%", 80),
    ],
    "air_conditioner": [("power", "on/off", False), ("temperature", "°C", 26.0)],
    "air_purifier": [
        ("power", "on/off", False),
        ("pm2_5", "µg/m3", 12),
        ("aqi", "AQI", 12),
        ("temperature", "°C", 22.0),
        ("humidity", "%", 50),
    ],
}


class VirtualAdapter(BaseAdapter):
    """Adapter for virtual (simulated) devices."""

    name = "virtual"

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self._states: dict[str, dict[str, Any]] = {}
        self._devices: dict[str, Device] = {}

    async def discover(self) -> list[Device]:
        return list(self._devices.values())

    async def subscribe(self, device: Device) -> None:
        # Virtual devices always have fresh state — nothing to poll
        state = self._states.get(device.device_id, {})
        for sensor in device.sensors:
            if sensor.name in state:
                sensor.value = state[sensor.name]

    async def execute(self, device_id: str, action: str, params: dict[str, Any]) -> ActionResult:
        device = self._devices.get(device_id)
        if not device:
            return ActionResult(device_id=device_id, action=action, success=False, message="虚拟设备未找到")

        state = self._states.setdefault(device_id, {})

        if action in ("on", "turn_on"):
            state["power"] = True
        elif action in ("off", "turn_off"):
            state["power"] = False
        elif action == "set_brightness":
            state["brightness"] = params.get("value", params.get("brightness", 80))
        elif action == "set_color_temp":
            state["color_temp"] = params.get("kelvin", params.get("value", 4000))
        elif action in ("set_target_humidity", "set_humidity"):
            state["humidity"] = params.get("value", 50)
        elif action in ("set_target_temperature", "set_temperature"):
            state["temperature"] = params.get("value", 26.0)
        elif action == "set_mode":
            state["mode"] = params.get("mode", "auto")
        else:
            state.update(params)

        # Update device sensors in-memory
        for sensor in device.sensors:
            if sensor.name in state:
                sensor.value = state[sensor.name]

        # Emit sensor update (simulates real device callback)
        asyncio.create_task(self._emit_state_update(device_id, state))

        return ActionResult(device_id=device_id, action=action, success=True, message="虚拟设备已执行")

    async def _emit_state_update(self, device_id: str, state: dict[str, Any]) -> None:
        await asyncio.sleep(0.1)
        await self._bus.emit(
            Event(
                type=EventType.SENSOR_UPDATED,
                device_id=device_id,
                data=dict(state),
            )
        )

    def register_device(self, device_id: str, name: str, device_type: str) -> Device:
        caps = [
            Capability(name=c["name"], params=c["params"])
            for c in VIRTUAL_TYPE_CAPABILITIES.get(
                device_type,
                [
                    {"name": "on", "params": {"label": "开启"}},
                    {"name": "off", "params": {"label": "关闭"}},
                ],
            )
        ]
        sensor_defs = VIRTUAL_TYPE_SENSORS.get(device_type, [("power", "on/off", False)])
        sensors = [Sensor(name=s[0], unit=s[1], value=s[2]) for s in sensor_defs]
        self._states[device_id] = {s[0]: s[2] for s in sensor_defs}

        device = Device(
            device_id=device_id,
            name=name,
            adapter="virtual",
            type=device_type,
            online=True,
            capabilities=caps,
            sensors=sensors,
        )
        self._devices[device_id] = device
        return device

    def remove_device(self, device_id: str) -> None:
        self._devices.pop(device_id, None)
        self._states.pop(device_id, None)
