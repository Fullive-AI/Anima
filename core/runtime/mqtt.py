from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import aiomqtt

from core.runtime.config import settings

logger = logging.getLogger(__name__)

TOPIC_PREFIX = "anima"

MessageHandler = Callable[[str, dict[str, Any]], Awaitable[None]]


class MQTTClient:
    def __init__(self) -> None:
        self._client: aiomqtt.Client | None = None
        self._handlers: dict[str, MessageHandler] = {}

    # ── Topic builders ──

    @staticmethod
    def _device_state_topic(device_id: str) -> str:
        return f"{TOPIC_PREFIX}/devices/{device_id}/state"

    @staticmethod
    def _device_command_topic(device_id: str) -> str:
        return f"{TOPIC_PREFIX}/devices/{device_id}/command"

    @staticmethod
    def _device_online_topic(device_id: str) -> str:
        return f"{TOPIC_PREFIX}/devices/{device_id}/online"

    @staticmethod
    def _discovery_topic() -> str:
        return f"{TOPIC_PREFIX}/discovery/announce"

    @staticmethod
    def _scan_topic() -> str:
        return f"{TOPIC_PREFIX}/discovery/scan"

    @staticmethod
    def _decision_topic() -> str:
        return f"{TOPIC_PREFIX}/system/brain/decisions"

    @staticmethod
    def _parse_device_id(topic: str) -> str | None:
        parts = topic.split("/")
        if len(parts) >= 4 and parts[1] == "devices":
            return parts[2]
        return None

    # ── Connection ──

    async def connect(self) -> aiomqtt.Client:
        self._client = aiomqtt.Client(
            hostname=settings.mqtt_host,
            port=settings.mqtt_port,
        )
        await self._client.__aenter__()
        logger.info("MQTT connected to %s:%d", settings.mqtt_host, settings.mqtt_port)
        return self._client

    async def disconnect(self) -> None:
        if self._client:
            await self._client.__aexit__(None, None, None)
            self._client = None

    # ── Publish ──

    async def publish(self, topic: str, payload: dict[str, Any]) -> None:
        if not self._client:
            raise RuntimeError("MQTT client not connected")
        await self._client.publish(topic, json.dumps(payload))

    async def publish_device_state(self, device_id: str, state: dict[str, Any]) -> None:
        await self.publish(self._device_state_topic(device_id), state)

    async def publish_command(self, device_id: str, command: dict[str, Any]) -> None:
        await self.publish(self._device_command_topic(device_id), command)

    async def publish_discovery(self, device_data: dict[str, Any]) -> None:
        await self.publish(self._discovery_topic(), device_data)

    async def publish_decision(self, decision: dict[str, Any]) -> None:
        await self.publish(self._decision_topic(), decision)

    # ── Subscribe ──

    async def subscribe(self, topic: str, handler: MessageHandler) -> None:
        if not self._client:
            raise RuntimeError("MQTT client not connected")
        self._handlers[topic] = handler
        await self._client.subscribe(topic)

    async def listen(self) -> None:
        if not self._client:
            raise RuntimeError("MQTT client not connected")
        async for message in self._client.messages:
            topic = str(message.topic)
            try:
                payload = json.loads(message.payload)
            except (json.JSONDecodeError, TypeError):
                logger.warning("Invalid JSON on topic %s", topic)
                continue

            for pattern, handler in self._handlers.items():
                if aiomqtt.Topic(pattern).matches(topic):
                    try:
                        await handler(topic, payload)
                    except Exception:
                        logger.exception("MQTT handler error for topic %s", topic)
