from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from core.brain.skill_loader import SkillLoader
from core.memory.extractor import MemoryExtractionService
from core.memory.store import MemoryStore

logger = logging.getLogger(__name__)


class PreferenceLearningService:
    def __init__(
        self,
        memory: MemoryStore,
        *,
        extractor: MemoryExtractionService,
        skill_loader: SkillLoader,
        invoke_llm_text,
    ) -> None:
        self._memory = memory
        self._extractor = extractor
        self._skill_loader = skill_loader
        self._invoke_llm_text = invoke_llm_text
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
        changed = False
        async with self._lock:
            while user_id in self._pending:
                self._pending.discard(user_id)
                updated = await self._run_once(user_id)
                changed = changed or updated
        return changed

    async def _run_once(self, user_id: str) -> bool:
        state_before = await self._memory.get_memory_extraction_state(user_id)
        start_index = int(state_before.get("history_cursor", 0) or 0)
        recent_history = await self._memory.get_history_slice(user_id, start_index=start_index, limit=50)
        if not recent_history:
            return False

        await self._extractor.run_now(user_id)

        affected_device_types = sorted(
            {
                str(item.get("device_type")).strip()
                for item in recent_history
                if isinstance(item, dict) and str(item.get("device_type", "")).strip()
            }
        )
        if not affected_device_types:
            return False

        extracted_memories = await self._memory.get_extracted_memories(user_id)
        updated = False
        for device_type in affected_device_types:
            skill = self._skill_loader.get_skill_for_device(device_type)
            if not skill or not skill.learn_prompt:
                continue

            relevant_history = [
                item for item in recent_history if str(item.get("device_type", "")).strip() == device_type
            ]
            relevant_memories = [
                memory
                for memory in extracted_memories.values()
                if device_type in memory.get("device_types", []) or not memory.get("device_types")
            ]
            if len(relevant_history) < 3 and not relevant_memories:
                continue

            current_profile = await self._memory.get_learned_for_skill(user_id, device_type)
            prompt = self._build_profile_prompt(
                base_prompt=skill.learn_prompt,
                relevant_history=relevant_history,
                current_profile=current_profile
                or json.dumps(
                    MemoryStore.parse_learned_profile(""),
                    ensure_ascii=False,
                    indent=2,
                ),
                relevant_memories=relevant_memories,
                device_type=device_type,
            )
            try:
                content = await self._invoke_llm_text(prompt, temperature=0.2, max_tokens=900)
            except Exception:
                logger.exception("Preference learning failed for %s/%s", user_id, device_type)
                continue
            if not content.strip():
                continue
            normalized_profile = MemoryStore.parse_learned_profile(content)
            metadata = normalized_profile.setdefault("metadata", {})
            if isinstance(metadata, dict):
                metadata.update(
                    {
                        "device_type": device_type,
                        "history_samples": len(relevant_history),
                        "memory_topics": sorted(
                            {
                                str(memory.get("topic", "")).strip()
                                for memory in relevant_memories
                                if str(memory.get("topic", "")).strip()
                            }
                        ),
                    }
                )
            await self._memory.update_learned_for_skill(
                user_id,
                device_type,
                json.dumps(normalized_profile, ensure_ascii=False, indent=2),
            )
            updated = True
        return updated

    @staticmethod
    def _build_profile_prompt(
        *,
        base_prompt: str,
        relevant_history: list[dict[str, Any]],
        current_profile: str,
        relevant_memories: list[dict[str, Any]],
        device_type: str,
    ) -> str:
        memory_block = json.dumps(relevant_memories, ensure_ascii=False, indent=2) if relevant_memories else "[]"
        return (
            base_prompt.format(
                history=json.dumps(relevant_history[-50:], ensure_ascii=False, indent=2),
                current_profile=current_profile,
            )
            + "\n\n## Extracted Long-Term Memories\n"
            + memory_block
            + "\n\n## Output Contract\n"
            + "Return JSON only.\n"
            + "Always use this schema exactly:\n"
            + "{\n"
            + '  "stable_preferences": ["string"],\n'
            + '  "time_based_patterns": ["string"],\n'
            + '  "seasonal_patterns": ["string"],\n'
            + '  "weak_signals": ["string"],\n'
            + '  "confidence_notes": "string"\n'
            + "}\n"
            + f"Focus only on durable {device_type} preferences. Prefer durable patterns over one-off events and use the extracted long-term memories as supporting evidence."
        )
