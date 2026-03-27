from __future__ import annotations

import logging
from typing import Any

from adapters.base import BaseAdapter
from core.events.bus import EventBus
from core.models import Device, Event, EventType, ActionResult

logger = logging.getLogger(__name__)


class DiscoveryOrchestrator:
    def __init__(self, bus: EventBus, adapters: list[BaseAdapter]) -> None:
        self._bus = bus
        self._adapters = adapters
        self.devices: dict[str, Device] = {}
        self._adapter_map: dict[str, BaseAdapter] = {}  # device_id → adapter

    async def scan(self) -> list[Device]:
        newly_found: list[Device] = []

        for adapter in self._adapters:
            try:
                found = await adapter.discover()
                for device in found:
                    if device.device_id not in self.devices:
                        self.devices[device.device_id] = device
                        self._adapter_map[device.device_id] = adapter
                        try:
                            await adapter.subscribe(device)
                        except Exception:
                            logger.exception("Adapter %s subscribe failed for %s", adapter.name, device.device_id)
                        newly_found.append(device)
                        await self._bus.emit(Event(
                            type=EventType.DEVICE_DISCOVERED,
                            device_id=device.device_id,
                            data=device.model_dump(),
                        ))
                        logger.info(
                            "Discovered: %s (%s) via %s",
                            device.name, device.device_id, adapter.name,
                        )
            except Exception:
                logger.exception("Adapter %s scan failed", adapter.name)

        logger.info("Scan complete: %d new, %d total", len(newly_found), len(self.devices))
        return newly_found

    def get_device(self, device_id: str) -> Device | None:
        return self.devices.get(device_id)

    def get_devices_by_type(self, device_type: str) -> list[Device]:
        return [d for d in self.devices.values() if d.type == device_type]

    def get_all_devices(self) -> list[Device]:
        return list(self.devices.values())

    async def refresh_device_states(self, device_ids: list[str] | None = None) -> dict[str, int]:
        target_ids = device_ids or list(self.devices.keys())
        refreshed = 0
        failed = 0

        for device_id in target_ids:
            device = self.devices.get(device_id)
            adapter = self._adapter_map.get(device_id)
            if not device or not adapter:
                continue

            try:
                await adapter.subscribe(device)
                refreshed += 1
            except Exception:
                failed += 1
                logger.exception("Adapter %s refresh failed for %s", adapter.name, device_id)

        return {"refreshed": refreshed, "failed": failed}

    async def execute_command(
        self, device_id: str, action: str, params: dict[str, Any]
    ) -> ActionResult:
        adapter = self._adapter_map.get(device_id)
        if not adapter:
            return ActionResult(
                device_id=device_id, action=action, success=False,
                message=f"No adapter found for device {device_id}",
            )
        try:
            result = await adapter.execute(device_id, action, params)
            await self._bus.emit(Event(
                type=EventType.ACTION_EXECUTED,
                device_id=device_id,
                data={"action": action, "params": params, "success": result.success},
            ))
            return result
        except Exception as e:
            logger.exception("Execute failed: %s.%s", device_id, action)
            return ActionResult(
                device_id=device_id, action=action, success=False, message=str(e),
            )

    def update_device_sensors(self, device_id: str, sensor_data: dict[str, Any]) -> None:
        device = self.devices.get(device_id)
        if not device:
            return
        for sensor in device.sensors:
            if sensor.name in sensor_data:
                sensor.value = sensor_data[sensor.name]
