from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from openai import AsyncOpenAI

from core.memory.store import MemoryStore
from core.runtime.config import settings

logger = logging.getLogger(__name__)

MAX_HISTORY_BATCH = 50


def _extract_json(text: str) -> dict[str, Any] | None:
    content = text.strip()
    if not content:
        return None
    candidates = [content]
    match = re.search(r"\{.*\}", content, re.DOTALL)
    if match:
        candidates.append(match.group(0))
    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    return None


class MemoryExtractionService:
    def __init__(self, memory: MemoryStore) -> None:
        self._memory = memory
        self._llm = AsyncOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url or None,
        )
        self._model = settings.llm_model
        self._disable_thinking = settings.llm_disable_thinking
        self._lock = asyncio.Lock()
        self._pending: set[str] = set()
        self._tasks: dict[str, asyncio.Task[None]] = {}

    def schedule(self, user_id: str = "default") -> None:
        self._pending.add(user_id)
        task = self._tasks.get(user_id)
        if task and not task.done():
            return
        self._tasks[user_id] = asyncio.create_task(self._drain(user_id))

    async def run_now(self, user_id: str = "default") -> bool:
        self._pending.add(user_id)
        return await self._drain(user_id)

    async def _drain(self, user_id: str) -> bool:
        extracted = False
        async with self._lock:
            while user_id in self._pending:
                self._pending.discard(user_id)
                changed = await self._extract_once(user_id)
                extracted = extracted or changed
        return extracted

    async def _extract_once(self, user_id: str) -> bool:
        if not settings.llm_api_key:
            return False

        state = await self._memory.get_memory_extraction_state(user_id)
        start_index = int(state.get("history_cursor", 0) or 0)
        recent_history = await self._memory.get_history_slice(
            user_id,
            start_index=start_index,
            limit=MAX_HISTORY_BATCH,
        )
        if not recent_history:
            return False

        manifest = await self._memory.get_memory_manifest(user_id)
        prompt = self._build_prompt(recent_history=recent_history, manifest=manifest)
        content = await self._invoke_llm_text(prompt, temperature=0.1, max_tokens=1400)
        payload = _extract_json(content)
        if not payload:
            logger.warning("Memory extraction returned invalid JSON")
            return False

        memories = payload.get("memories", [])
        forget_topics = payload.get("forget_topics", [])
        if not isinstance(memories, list):
            memories = []
        if not isinstance(forget_topics, list):
            forget_topics = []

        writes = 0
        for topic in forget_topics:
            if isinstance(topic, str) and topic.strip():
                await self._memory.delete_extracted_memory(user_id, topic)
                writes += 1

        for item in memories:
            normalized = self._normalize_memory_item(item)
            if not normalized:
                continue
            await self._memory.upsert_extracted_memory(user_id, normalized["topic"], normalized)
            writes += 1

        await self._memory.update_memory_extraction_state(
            user_id,
            history_cursor=start_index + len(recent_history),
            last_batch_size=len(recent_history),
        )
        return writes > 0

    def _build_prompt(
        self,
        *,
        recent_history: list[dict[str, Any]],
        manifest: list[dict[str, Any]],
    ) -> str:
        return (
            "You are Anima's background memory extraction worker.\n"
            "This worker runs independently from the main planner so it must only summarize stable, reusable memory.\n\n"
            "Analyze only the recent history batch below. Do not infer beyond the evidence.\n"
            "Prefer updating an existing topic rather than inventing duplicates.\n"
            "Ignore one-off execution noise.\n\n"
            "Existing memory manifest:\n"
            f"{json.dumps(manifest, ensure_ascii=False, indent=2)}\n\n"
            "Recent history batch:\n"
            f"{json.dumps(recent_history, ensure_ascii=False, indent=2)}\n\n"
            "Return JSON only with this schema:\n"
            "{\n"
            '  "memories": [\n'
            '    {\n'
            '      "topic": "stable_snake_case_topic",\n'
            '      "title": "Short title",\n'
            '      "category": "preference | routine | constraint | context",\n'
            '      "summary": "one sentence summary",\n'
            '      "details": ["fact", "fact"],\n'
            '      "device_types": ["light"],\n'
            '      "confidence": "low | medium | high",\n'
            '      "source_actions": ["turn_on", "plan.ask_user"]\n'
            "    }\n"
            "  ],\n"
            '  "forget_topics": ["obsolete_topic"]\n'
            "}\n"
            "Rules:\n"
            "- Save only durable user preferences, routines, constraints, or home context.\n"
            "- Do not save ephemeral failures, transient sensor values, or obvious duplicates.\n"
            "- If nothing is worth saving, return an empty memories list.\n"
            "- Use snake_case topics.\n"
        )

    async def _invoke_llm_text(self, prompt: str, *, temperature: float, max_tokens: int) -> str:
        extra_body: dict[str, Any] = {}
        if self._disable_thinking:
            extra_body["thinking"] = {"type": "disabled"}

        response = await self._llm.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
            extra_body=extra_body or None,
        )
        if not response.choices:
            return ""
        content = response.choices[0].message.content
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            chunks: list[str] = []
            for item in content:
                text = getattr(item, "text", None)
                if isinstance(text, str):
                    chunks.append(text)
                elif isinstance(item, dict) and isinstance(item.get("text"), str):
                    chunks.append(item["text"])
            return "\n".join(chunks)
        return ""

    @staticmethod
    def _normalize_memory_item(item: Any) -> dict[str, Any] | None:
        if not isinstance(item, dict):
            return None
        topic_raw = str(item.get("topic", "")).strip().lower()
        topic = re.sub(r"[^a-z0-9_]+", "_", topic_raw).strip("_")
        if not topic:
            return None
        title = str(item.get("title", topic)).strip() or topic
        category = str(item.get("category", "context")).strip().lower() or "context"
        if category not in {"preference", "routine", "constraint", "context"}:
            category = "context"
        summary = str(item.get("summary", "")).strip()
        if not summary:
            return None
        details = item.get("details", [])
        if not isinstance(details, list):
            details = []
        device_types = item.get("device_types", [])
        if not isinstance(device_types, list):
            device_types = []
        source_actions = item.get("source_actions", [])
        if not isinstance(source_actions, list):
            source_actions = []
        confidence = str(item.get("confidence", "medium")).strip().lower() or "medium"
        if confidence not in {"low", "medium", "high"}:
            confidence = "medium"
        return {
            "topic": topic,
            "title": title,
            "category": category,
            "summary": summary,
            "details": [str(detail).strip() for detail in details if str(detail).strip()],
            "device_types": [str(name).strip() for name in device_types if str(name).strip()],
            "confidence": confidence,
            "source_actions": [str(name).strip() for name in source_actions if str(name).strip()],
        }
