from __future__ import annotations

import abc
from typing import Any

from core.models import ActionResult, Device


class BaseAdapter(abc.ABC):
    name: str = "base"

    @abc.abstractmethod
    async def discover(self) -> list[Device]:
        """Scan network and return discovered devices."""
        ...

    @abc.abstractmethod
    async def subscribe(self, device: Device) -> None:
        """Start monitoring device state changes. Call on_state_change when state updates."""
        ...

    @abc.abstractmethod
    async def execute(self, device_id: str, action: str, params: dict[str, Any]) -> ActionResult:
        """Execute a control command on a device."""
        ...

    async def start(self) -> None:  # noqa: B027
        """Called once when adapter starts."""

    async def stop(self) -> None:  # noqa: B027
        """Called once when adapter stops."""
