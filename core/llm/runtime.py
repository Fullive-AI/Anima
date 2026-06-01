from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LLMSnapshot:
    client: AsyncOpenAI
    model: str
    disable_thinking: bool
    configured: bool


@dataclass(frozen=True)
class _LLMRuntimeState:
    client: AsyncOpenAI
    api_key: str
    model: str
    base_url: str
    disable_thinking: bool


class LLMRuntime:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str,
        disable_thinking: bool,
        close_delay_seconds: float = 300.0,
    ) -> None:
        self._state = self._build_state(
            api_key=api_key,
            model=model,
            base_url=base_url,
            disable_thinking=disable_thinking,
        )
        self._close_delay_seconds = close_delay_seconds
        self._lock = asyncio.Lock()
        self._close_tasks: set[asyncio.Task[None]] = set()

    def snapshot(self) -> LLMSnapshot:
        # 一轮 LLM 任务开始时只拿一次快照，保证该轮任务不会中途切换 client/model。
        state = self._state
        return LLMSnapshot(
            client=state.client,
            model=state.model,
            disable_thinking=state.disable_thinking,
            configured=bool(state.api_key),
        )

    async def reload(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str,
        disable_thinking: bool,
    ) -> bool:
        new_state = self._build_state(
            api_key=api_key,
            model=model,
            base_url=base_url,
            disable_thinking=disable_thinking,
        )

        async with self._lock:
            old_state = self._state
            if self._same_config(old_state, new_state):
                await self._close_client(new_state.client)
                return False
            self._state = new_state

        # 旧 client 不立即关闭，避免打断正在流式输出或正在执行的任务。
        self._schedule_delayed_close(old_state.client)
        return True

    async def close(self) -> None:
        for task in list(self._close_tasks):
            task.cancel()
        for task in list(self._close_tasks):
            with contextlib.suppress(asyncio.CancelledError):
                await task
        await self._close_client(self._state.client)

    def _build_state(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str,
        disable_thinking: bool,
    ) -> _LLMRuntimeState:
        return _LLMRuntimeState(
            client=AsyncOpenAI(api_key=api_key, base_url=base_url or None),
            api_key=api_key,
            model=model,
            base_url=base_url,
            disable_thinking=disable_thinking,
        )

    def _same_config(self, left: _LLMRuntimeState, right: _LLMRuntimeState) -> bool:
        return (
            left.api_key == right.api_key
            and left.model == right.model
            and left.base_url == right.base_url
            and left.disable_thinking == right.disable_thinking
        )

    def _schedule_delayed_close(self, client: AsyncOpenAI) -> None:
        task = asyncio.create_task(self._delayed_close(client), name="llm-client-delayed-close")
        self._close_tasks.add(task)
        task.add_done_callback(self._close_tasks.discard)
        logger.info("Scheduled old LLM client close in %.1f seconds", self._close_delay_seconds)

    async def _delayed_close(self, client: AsyncOpenAI) -> None:
        try:
            await asyncio.sleep(self._close_delay_seconds)
            await self._close_client(client)
            logger.info("Closed old LLM client after delayed close window")
        except asyncio.CancelledError:
            raise

    async def _close_client(self, client: AsyncOpenAI) -> None:
        with contextlib.suppress(Exception):
            await client.close()
