from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable

from core.models import Event, EventType

logger = logging.getLogger(__name__)

EventHandler = Callable[[Event], Awaitable[None]]


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)

    def subscribe(self, event_type: str | EventType, handler: EventHandler) -> None:
        self._handlers[str(event_type)].append(handler)

    def unsubscribe(self, event_type: str | EventType, handler: EventHandler) -> None:
        handlers = self._handlers[str(event_type)]
        if handler in handlers:
            handlers.remove(handler)

    async def emit(self, event: Event) -> None:
        handlers = list(self._handlers.get(str(event.type), []))
        handlers += list(self._handlers.get("*", []))

        for handler in handlers:
            try:
                await handler(event)
            except Exception:
                logger.exception("EventBus handler error for %s", event.type)
