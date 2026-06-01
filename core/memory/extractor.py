from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from core.brain.skill_loader import SkillLoader
from core.llm.runtime import LLMRuntime, LLMSnapshot
from core.memory.memory_merge import normalize_memory_for_storage
from core.memory.store import MemoryStore
from core.runtime.config import settings

logger = logging.getLogger(__name__)

MAX_HISTORY_BATCH = 50
CUSTOM_SKILL_MEMORY_HINTS = (
    "custom skill",
    "custom skills",
    "自定义技能",
    "新增技能",
    "新增 skill",
    "created skill",
    "created and activated",
    "skill request",
)
CUSTOM_SKILL_TOKEN_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "at",
    "by",
    "connected",
    "created",
    "current",
    "custom",
    "has",
    "have",
    "immediately",
    "is",
    "of",
    "on",
    "or",
    "remains",
    "requested",
    "skill",
    "successfully",
    "the",
    "to",
    "user",
    "via",
    "working",
}


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
    def __init__(self, memory: MemoryStore, *, skills_dir: str | None = None) -> None:
        self._memory = memory
        self._llm_runtime = LLMRuntime(
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            base_url=settings.llm_base_url,
            disable_thinking=settings.llm_disable_thinking,
        )
        self._skills_dir = skills_dir or settings.skills_dir
        self._lock = asyncio.Lock()
        self._pending: set[str] = set()
        self._tasks: dict[str, asyncio.Task[None]] = {}

    async def reload_llm_config(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str,
        disable_thinking: bool,
    ) -> bool:
        return await self._llm_runtime.reload(
            api_key=api_key,
            model=model,
            base_url=base_url,
            disable_thinking=disable_thinking,
        )

    async def close(self) -> None:
        await self._llm_runtime.close()

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
        custom_skills = self._load_custom_skill_inventory()
        existing_memories = await self._memory.get_extracted_memories(user_id)
        writes = await self._cleanup_invalid_custom_skill_memories(
            user_id,
            existing_memories=existing_memories,
            custom_skills=custom_skills,
        )

        state = await self._memory.get_memory_extraction_state(user_id)
        start_index = int(state.get("history_cursor", 0) or 0)
        history_batch = await self._memory.get_history_slice(
            user_id,
            start_index=start_index,
            limit=MAX_HISTORY_BATCH,
        )
        if not history_batch:
            return writes > 0
        recent_history = [item for item in history_batch if item.get("learnable", True) is not False]
        if not recent_history:
            await self._memory.update_memory_extraction_state(
                user_id,
                history_cursor=start_index + len(history_batch),
                last_batch_size=len(history_batch),
            )
            return writes > 0
        snapshot = self._llm_runtime.snapshot()
        if not snapshot.configured:
            return writes > 0

        manifest = await self._memory.get_memory_manifest(user_id)
        prompt = self._build_prompt(
            recent_history=recent_history,
            manifest=manifest,
            custom_skills=custom_skills,
        )
        content = await self._invoke_llm_text(
            prompt,
            temperature=0.1,
            max_tokens=1800,
            snapshot=snapshot,
        )
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

        for topic in forget_topics:
            if isinstance(topic, str) and topic.strip():
                await self._memory.delete_extracted_memory(user_id, topic)
                writes += 1

        for item in memories:
            normalized = self._normalize_memory_item(item)
            if not normalized:
                continue
            linked_custom_skill_name = self._resolve_custom_skill_link(normalized, custom_skills)
            if self._is_custom_skill_related(normalized) and not linked_custom_skill_name:
                continue
            if linked_custom_skill_name:
                normalized["linked_custom_skill_name"] = linked_custom_skill_name
            await self._memory.upsert_extracted_memory(user_id, normalized["topic"], normalized)
            writes += 1

        await self._memory.update_memory_extraction_state(
            user_id,
            history_cursor=start_index + len(history_batch),
            last_batch_size=len(history_batch),
        )
        return writes > 0

    def _build_prompt(
        self,
        *,
        recent_history: list[dict[str, Any]],
        manifest: list[dict[str, Any]],
        custom_skills: list[dict[str, Any]],
    ) -> str:
        return (
            "You are Anima's background memory extraction worker.\n"
            "This worker runs independently from the main planner so it must only propose evidence-backed long-term memory candidates.\n\n"
            "Analyze only the recent history batch below. Do not infer beyond the evidence.\n"
            "Prefer updating an existing topic rather than inventing duplicates.\n"
            "Ignore one-off execution noise.\n\n"
            "Existing memory manifest:\n"
            f"{json.dumps(manifest, ensure_ascii=False, indent=2)}\n\n"
            "Existing real custom skill inventory from skills/custom:\n"
            f"{json.dumps(custom_skills, ensure_ascii=False, indent=2)}\n\n"
            "Recent history batch:\n"
            f"{json.dumps(recent_history, ensure_ascii=False, indent=2)}\n\n"
            "Return JSON only with this schema:\n"
            "{\n"
            '  "memories": [\n'
            "    {\n"
            '      "topic": "stable_snake_case_topic",\n'
            '      "title": "Short title",\n'
            '      "category": "preference | routine | constraint | context",\n'
            '      "claim_type": "explicit_preference | implicit_preference | routine | device_alias | constraint | home_context",\n'
            '      "status": "candidate | confirmed",\n'
            '      "summary": "one sentence summary",\n'
            '      "details": ["fact", "fact"],\n'
            '      "device_types": ["light"],\n'
            '      "device_ids": ["device id from history when known"],\n'
            '      "scenes": ["night", "bedroom"],\n'
            '      "confidence": "low | medium | high",\n'
            '      "positive_evidence": [\n'
            '        {"event_id": "history event_id", "timestamp": "history timestamp", "source": "chat", "action": "set_brightness", "device_type": "light", "device_id": "device id", "summary": "short evidence summary"}\n'
            "      ],\n"
            '      "negative_evidence": [],\n'
            '      "source_actions": ["turn_on", "plan.ask_user"],\n'
            '      "linked_custom_skill_name": "exact existing custom skill name or empty string"\n'
            "    }\n"
            "  ],\n"
            '  "forget_topics": ["obsolete_topic"]\n'
            "}\n"
            "Rules:\n"
            "- Save only durable user preferences, routines, constraints, device aliases, or home context.\n"
            "- Use event_id from history entries in positive_evidence or negative_evidence.\n"
            "- Evidence must refer only to events in the provided recent history batch.\n"
            "- Status is advisory. The system will recalculate final status using evidence rules.\n"
            "- Do not mark implicit preferences or routines as confirmed from a single event.\n"
            "- Explicit user preferences or constraints may be proposed as confirmed, but the system will verify.\n"
            "- Do not infer durable preferences from one device action.\n"
            "- Do not save ephemeral failures, transient sensor values, or obvious duplicates.\n"
            "- For memories about created, activated, or available custom skills, only save them when they match one real skill from the custom skill inventory.\n"
            "- When a memory refers to a real custom skill, set linked_custom_skill_name exactly to the inventory name.\n"
            "- Do not save pending or vague custom skill requests as long-term memory.\n"
            "- If nothing is worth saving, return an empty memories list.\n"
            "- Use snake_case topics.\n"
        )

    async def _invoke_llm_text(
        self,
        prompt: str,
        *,
        temperature: float,
        max_tokens: int,
        snapshot: LLMSnapshot | None = None,
    ) -> str:
        snapshot = snapshot or self._llm_runtime.snapshot()
        extra_body: dict[str, Any] = {}
        if snapshot.disable_thinking:
            extra_body["thinking"] = {"type": "disabled"}

        response = await snapshot.client.chat.completions.create(
            model=snapshot.model,
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
        return normalize_memory_for_storage(item)

    def _load_custom_skill_inventory(self) -> list[dict[str, Any]]:
        loader = SkillLoader(skills_dir=self._skills_dir)
        skills = loader.discover()
        inventory: list[dict[str, Any]] = []
        for skill in skills:
            if "custom" not in skill.path.parts:
                continue
            inventory.append(
                {
                    "name": skill.meta.name,
                    "folder_name": skill.path.name,
                    "description": skill.meta.description,
                    "device_types": list(skill.meta.device_types),
                }
            )
        return sorted(inventory, key=lambda item: item["name"])

    async def _cleanup_invalid_custom_skill_memories(
        self,
        user_id: str,
        *,
        existing_memories: dict[str, dict[str, Any]],
        custom_skills: list[dict[str, Any]],
    ) -> int:
        writes = 0
        for topic, memory in existing_memories.items():
            if not self._is_custom_skill_related(memory):
                continue

            linked_custom_skill_name = self._resolve_custom_skill_link(memory, custom_skills)
            if not linked_custom_skill_name:
                await self._memory.delete_extracted_memory(user_id, topic)
                writes += 1
                continue

            current_link = str(memory.get("linked_custom_skill_name", "")).strip()
            if current_link == linked_custom_skill_name:
                continue

            updated_memory = dict(memory)
            updated_memory["linked_custom_skill_name"] = linked_custom_skill_name
            await self._memory.upsert_extracted_memory(user_id, topic, updated_memory)
            writes += 1
        return writes

    @staticmethod
    def _is_custom_skill_related(item: dict[str, Any]) -> bool:
        topic = str(item.get("topic", "")).strip().lower()
        if topic.startswith("user_custom_") or "linked_custom_skill_name" in item:
            return True

        text = MemoryExtractionService._memory_text(item).lower()
        return any(hint in text for hint in CUSTOM_SKILL_MEMORY_HINTS)

    @staticmethod
    def _memory_text(item: dict[str, Any]) -> str:
        details = item.get("details", [])
        if not isinstance(details, list):
            details = []
        parts = [
            str(item.get("topic", "")).strip(),
            str(item.get("title", "")).strip(),
            str(item.get("summary", "")).strip(),
            *[str(detail).strip() for detail in details if str(detail).strip()],
        ]
        return " ".join(part for part in parts if part)

    @staticmethod
    def _tokenize_text(text: str) -> set[str]:
        normalized = text.lower().replace("_", " ")
        tokens = re.findall(r"[a-z]+|\d+|[\u4e00-\u9fff]+", normalized)
        return {token for token in tokens if token and token not in CUSTOM_SKILL_TOKEN_STOPWORDS}

    def _resolve_custom_skill_link(
        self,
        item: dict[str, Any],
        custom_skills: list[dict[str, Any]],
    ) -> str:
        if not custom_skills:
            return ""

        explicit_name = str(item.get("linked_custom_skill_name", "")).strip()
        if explicit_name and any(skill["name"] == explicit_name for skill in custom_skills):
            return explicit_name

        text = self._memory_text(item)
        normalized_text = text.lower().replace("_", " ")
        memory_tokens = self._tokenize_text(text)

        best_name = ""
        best_score = 0
        for skill in custom_skills:
            name = str(skill.get("name", "")).strip()
            folder_name = str(skill.get("folder_name", "")).strip()
            description = str(skill.get("description", "")).strip()
            if not name:
                continue

            name_variants = [
                name.lower(),
                name.lower().replace("_", " "),
                folder_name.lower(),
                folder_name.lower().replace("_", " "),
            ]
            if any(variant and variant in normalized_text for variant in name_variants):
                return name

            skill_tokens = self._tokenize_text(
                " ".join(
                    [
                        name,
                        folder_name,
                        description,
                        " ".join(str(device_type) for device_type in skill.get("device_types", [])),
                    ]
                )
            )
            if not skill_tokens:
                continue

            numeric_tokens = {token for token in skill_tokens if token.isdigit()}
            if numeric_tokens and not (numeric_tokens & memory_tokens):
                continue

            score = len(skill_tokens & memory_tokens)
            if score > best_score:
                best_score = score
                best_name = name

        return best_name if best_score >= 4 else ""
