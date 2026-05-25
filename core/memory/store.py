from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.memory.history_filter import HistoryFilter
from core.memory.memory_merge import merge_extracted_memory

logger = logging.getLogger(__name__)

DEFAULT_PREFERENCES = """# 用户偏好

## 舒适度
- 温度: 24°C（夏天制冷目标温度，冬天可适当调高）
- 湿度: 50%（舒适湿度范围 45-55%）
- 亮度: 白天适中，晚上温暖偏暗

## 作息时间
- 起床: 07:00-08:00
- 睡觉: 22:30-00:00

## 在家状态
- 默认在家

## 备注
（AI 会根据使用习惯自动学习并更新此部分）
"""

COLD_START_COMFORT_DEFAULTS = {
    "temperature": "24°C（夏天制冷，冬天可调高至26°C）",
    "humidity": "50%（舒适范围 45-55%）",
    "brightness": "白天适中亮度，晚上温暖偏暗",
}

LEARNED_PROFILE_KEYS = (
    "stable_preferences",
    "time_based_patterns",
    "seasonal_patterns",
    "weak_signals",
    "confidence_notes",
)


def _device_type_sort_key(device_type: str) -> tuple[int, str]:
    preferred = ["air_conditioner", "humidifier", "air_purifier", "light", "speaker"]
    try:
        return preferred.index(device_type), device_type
    except ValueError:
        return len(preferred), device_type


class MemoryStore:
    def __init__(self, base_dir: str = "data/memory") -> None:
        self._base = Path(base_dir)
        self._history_filter = HistoryFilter()

    def _user_dir(self, user_id: str) -> Path:
        d = self._base / "users" / user_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _preferences_path(self, user_id: str) -> Path:
        return self._user_dir(user_id) / "preferences.md"

    def _history_path(self, user_id: str) -> Path:
        return self._user_dir(user_id) / "history.json"

    def _memory_state_path(self, user_id: str) -> Path:
        return self._user_dir(user_id) / "memory_state.json"

    def _memories_dir(self, user_id: str) -> Path:
        path = self._user_dir(user_id) / "memories"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _slugify_topic(topic: str) -> str:
        slug = re.sub(r"[^a-z0-9_]+", "_", topic.lower()).strip("_")
        return slug[:64] or "memory"

    # ── Preferences (Markdown) ──

    async def get_preferences(self, user_id: str = "default") -> str:
        path = self._preferences_path(user_id)
        if not path.exists():
            path.write_text(DEFAULT_PREFERENCES, encoding="utf-8")
        return path.read_text(encoding="utf-8")

    async def update_preferences(self, user_id: str, key: str, value: str) -> None:
        prefs = await self.get_preferences(user_id)
        path = self._user_dir(user_id) / "preferences.md"

        # Simple key replacement: find "- {key}: ..." and replace value
        lines = prefs.splitlines()
        updated = False
        for i, line in enumerate(lines):
            if line.strip().startswith(f"- {key.split('.')[-1]}:"):
                lines[i] = f"- {key.split('.')[-1]}: {value}"
                updated = True
                break
        if not updated:
            lines.append(f"- {key}: {value}")
        path.write_text("\n".join(lines), encoding="utf-8")

    async def ensure_cold_start_profiles(
        self,
        *,
        device_types: list[str],
        user_id: str = "default",
        style: str = "comfort_first",
        force: bool = False,
    ) -> dict[str, Any]:
        normalized_device_types = sorted(
            {
                str(device_type).strip()
                for device_type in device_types
                if isinstance(device_type, str) and device_type.strip()
            },
            key=_device_type_sort_key,
        )

        preferences_created = await self._ensure_cold_start_preferences(
            user_id=user_id,
            device_types=normalized_device_types,
            style=style,
            force=force,
        )

        profiles_created = await self._ensure_cold_start_learned_profiles(
            user_id=user_id,
            device_types=normalized_device_types,
            style=style,
            force=force,
        )

        existing_profiles = await self.get_learned_profiles(user_id)
        return {
            "preferences_created": preferences_created,
            "profiles_created": profiles_created,
            "profiles_skipped": sorted(
                [
                    device_type
                    for device_type in normalized_device_types
                    if device_type not in profiles_created and device_type in existing_profiles
                ],
                key=_device_type_sort_key,
            ),
        }

    async def _ensure_cold_start_preferences(
        self,
        *,
        user_id: str,
        device_types: list[str],
        style: str,
        force: bool,
    ) -> bool:
        path = self._preferences_path(user_id)
        current = await self.get_preferences(user_id)
        if not force and current.strip() and current.strip() != DEFAULT_PREFERENCES.strip():
            return False

        generated = self._build_cold_start_preferences(device_types=device_types, style=style)
        path.write_text(generated, encoding="utf-8")
        return True

    async def _ensure_cold_start_learned_profiles(
        self,
        *,
        user_id: str,
        device_types: list[str],
        style: str,
        force: bool,
    ) -> list[str]:
        profiles = self._load_learned_profiles(user_id)
        created: list[str] = []
        for device_type in device_types:
            if not force and profiles.get(device_type):
                continue
            profiles[device_type] = json.dumps(
                self._build_cold_start_profile(device_type=device_type, style=style),
                ensure_ascii=False,
                indent=2,
            )
            created.append(device_type)

        if created:
            self._learned_json_path(user_id).write_text(
                json.dumps(profiles, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        return created

    def _build_cold_start_preferences(self, *, device_types: list[str], style: str) -> str:
        lines = [
            "# 用户偏好",
            "",
            "> 根据当前已连接设备类型自动生成的初始偏好配置。",
            "> 这是舒适导向的基础默认值，会随实际使用习惯自动更新。",
            "",
            "## 舒适度",
            f"- 温度: {COLD_START_COMFORT_DEFAULTS['temperature'] if 'air_conditioner' in device_types else '未设置'}",
            f"- 湿度: {COLD_START_COMFORT_DEFAULTS['humidity'] if {'humidifier', 'air_purifier'} & set(device_types) else '未设置'}",
            f"- 亮度: {COLD_START_COMFORT_DEFAULTS['brightness'] if 'light' in device_types else '未设置'}",
            "",
            "## 作息时间",
            "- 起床: 07:00-08:00",
            "- 睡觉: 22:30-00:00",
            "",
            "## 在家状态",
            "- 默认在家",
            "",
            "## 设备偏好",
        ]

        if "air_conditioner" in device_types:
            lines.append("- 空调: 优先舒适，活跃时段温度保持在24°C左右，睡前避免剧烈温度变化。")
        if "humidifier" in device_types:
            lines.append("- 加湿器: 湿度低于45%时主动加湿，保持室内不干燥。")
        if "air_purifier" in device_types:
            lines.append("- 空气净化器: 有人在家时保持空气清新，睡眠时段优先安静模式。")
        if "light" in device_types:
            lines.append("- 灯光: 白天中性亮光，晚上暖色调偏暗，睡前自动调暗。")
        if "speaker" in device_types:
            lines.append("- 音箱: 仅在用户明确要求时播报，默认保持安静。")
        if not device_types:
            lines.append("- 暂无设备特定偏好，等待设备接入后自动生成。")

        lines.extend(
            [
                "",
                "## 初始化说明",
                f"- 风格: {style}",
                "- 来源: 根据当前已连接设备类型生成，非学习行为。",
                "- 更新策略: 用户明确设置和学习到的行为偏好优先级更高。",
            ]
        )
        return "\n".join(lines) + "\n"

    def _build_cold_start_profile(self, *, device_type: str, style: str) -> dict[str, Any]:
        profile: dict[str, Any] = {
            "stable_preferences": [],
            "time_based_patterns": [],
            "seasonal_patterns": [],
            "weak_signals": [],
            "confidence_notes": (
                "Cold-start default profile generated from connected device types. "
                "Treat as low-confidence initialization until reinforced by real history."
            ),
        }

        if device_type == "air_conditioner":
            profile["stable_preferences"] = [
                "Prefer keeping occupied rooms around 22-24°C.",
                "Prefer comfort-first adjustment during active hours.",
            ]
            profile["time_based_patterns"] = [
                "Daytime: allow neutral comfort cooling/heating when temperature drifts clearly outside the comfort band.",
                "Night: avoid aggressive temperature swings close to sleep hours.",
            ]
            profile["seasonal_patterns"] = [
                "Warm seasons: bias toward cooling when rooms become clearly warm.",
                "Cold seasons: bias toward gentle heating when rooms become clearly cold.",
            ]
            profile["weak_signals"] = [
                "Recent occupancy-like activity can justify comfort adjustment during active hours.",
            ]
        elif device_type == "humidifier":
            profile["stable_preferences"] = [
                "Prefer keeping indoor humidity around 45-55%.",
                "Act before the room feels obviously dry.",
            ]
            profile["time_based_patterns"] = [
                "Evening and sleep hours: slightly stronger preference for comfortable humidity.",
            ]
            profile["seasonal_patterns"] = [
                "Dry seasons: maintain a more proactive humidity baseline.",
            ]
            profile["weak_signals"] = [
                "Low humidity readings below the comfort band justify intervention even without explicit user input.",
            ]
        elif device_type == "air_purifier":
            profile["stable_preferences"] = [
                "Prefer cleaner air during occupied periods.",
                "Bias toward enabling purification when air quality looks poor rather than waiting too long.",
            ]
            profile["time_based_patterns"] = [
                "Sleep hours: prefer quieter or less disruptive purification if available.",
            ]
            profile["seasonal_patterns"] = [
                "Dusty or allergy-prone periods may justify more proactive purification.",
            ]
            profile["weak_signals"] = [
                "Air-quality degradation plus likely occupancy should increase confidence in turning purification on.",
            ]
        elif device_type == "light":
            profile["stable_preferences"] = [
                "Prefer brighter neutral light in daytime.",
                "Prefer warmer dimmer light in evening and before sleep.",
            ]
            profile["time_based_patterns"] = [
                "Morning: light can ramp up toward a clearer, more alert ambience.",
                "Night: avoid harsh brightness and cool color temperature.",
            ]
            profile["seasonal_patterns"] = [
                "Short daylight periods may justify earlier lighting support in the afternoon or evening.",
            ]
            profile["weak_signals"] = [
                "Low ambient brightness during active hours can justify light adjustment.",
            ]
        elif device_type == "speaker":
            profile["stable_preferences"] = [
                "Use the speaker primarily for explicit user requests.",
                "Prefer concise voice feedback instead of proactive announcements.",
            ]
            profile["time_based_patterns"] = [
                "Late-night hours: avoid unsolicited speaker output.",
            ]
            profile["seasonal_patterns"] = [
                "No strong seasonal pattern assumed at cold start.",
            ]
            profile["weak_signals"] = [
                "Only explicit user intent should trigger spoken output at cold start.",
            ]
        else:
            profile["stable_preferences"] = [
                f"Maintain a safe, comfort-oriented baseline for {device_type} until real usage history accumulates.",
            ]
            profile["time_based_patterns"] = [
                "Prefer minimal disruption during sleep hours.",
            ]
            profile["seasonal_patterns"] = [
                "No strong seasonal pattern assumed at cold start.",
            ]
            profile["weak_signals"] = [
                "Use only clear sensor signals and explicit requests until more evidence is learned.",
            ]

        profile["bootstrap_style"] = style
        profile["bootstrap_source"] = "current_device_types"
        return profile

    # ── History (JSON) ──

    async def get_history(self, user_id: str = "default", limit: int = 50) -> list[dict]:
        path = self._history_path(user_id)
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        return data[-limit:]

    async def get_history_slice(
        self,
        user_id: str = "default",
        *,
        start_index: int = 0,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        path = self._history_path(user_id)
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            return []
        sliced = data[max(start_index, 0) :]
        if limit is not None:
            sliced = sliced[:limit]
        return [item for item in sliced if isinstance(item, dict)]

    async def get_history_count(self, user_id: str = "default") -> int:
        path = self._history_path(user_id)
        if not path.exists():
            return 0
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            return 0
        return len(data)

    async def append_history(self, user_id: str, entry: dict[str, Any]) -> None:
        path = self._history_path(user_id)
        data = []
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            data = []

        now = datetime.now(UTC)
        recent_entries = [item for item in data[-30:] if isinstance(item, dict)]
        # 写入前统一交给 history_filter 判断；当前只过滤重复 refresh_environment。
        filter_result = self._history_filter.should_write(
            entry=entry,
            recent_entries=recent_entries,
            now=now,
        )
        if not filter_result.should_write:
            logger.debug("Skipped history entry: %s", filter_result.reason)
            return

        entry.setdefault("event_id", uuid.uuid4().hex)
        entry["timestamp"] = now.isoformat()
        data.append(entry)
        # Keep last 1000 entries
        if len(data) > 1000:
            data = data[-1000:]
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── Learned Profile (Markdown) ──

    def _learned_json_path(self, user_id: str) -> Path:
        return self._user_dir(user_id) / "learned.json"

    def _load_learned_profiles(self, user_id: str) -> dict[str, str]:
        path = self._learned_json_path(user_id)
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                normalized: dict[str, str] = {}
                for key, value in data.items():
                    parsed = self.parse_learned_profile(value)
                    normalized[str(key)] = json.dumps(parsed, ensure_ascii=False, indent=2)
                return normalized

        legacy_path = self._user_dir(user_id) / "learned.md"
        if legacy_path.exists():
            legacy = legacy_path.read_text(encoding="utf-8").strip()
            if legacy:
                return {"global": legacy}

        return {}

    async def get_learned(self, user_id: str = "default") -> str:
        path = self._user_dir(user_id) / "learned.md"
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    async def update_learned(self, user_id: str, content: str) -> None:
        path = self._user_dir(user_id) / "learned.md"
        path.write_text(content, encoding="utf-8")

    async def get_learned_profiles(self, user_id: str = "default") -> dict[str, str]:
        return self._load_learned_profiles(user_id)

    async def get_learned_for_skill(self, user_id: str = "default", skill_type: str = "") -> str:
        profiles = self._load_learned_profiles(user_id)
        return profiles.get(skill_type, "")

    async def update_learned_for_skill(self, user_id: str, skill_type: str, content: str) -> None:
        profiles = self._load_learned_profiles(user_id)
        profiles[skill_type] = json.dumps(self.parse_learned_profile(content), ensure_ascii=False, indent=2)
        path = self._learned_json_path(user_id)
        path.write_text(json.dumps(profiles, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _normalize_learned_list(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, dict):
            parts: list[str] = []
            for key, item in value.items():
                key_text = str(key).strip()
                item_text = str(item).strip()
                if key_text and item_text:
                    parts.append(f"{key_text}: {item_text}")
            return parts
        text = str(value).strip()
        return [text] if text and text not in {"{}", "[]", "null"} else []

    @classmethod
    def parse_learned_profile(cls, raw: Any) -> dict[str, Any]:
        data: Any = raw
        if isinstance(raw, str):
            stripped = raw.strip()
            if stripped:
                try:
                    data = json.loads(stripped)
                except json.JSONDecodeError:
                    data = {"confidence_notes": stripped}
            else:
                data = {}

        if not isinstance(data, dict):
            data = {}

        # confidence_notes may itself be a JSON string (double-serialized) — unwrap it
        raw_notes = data.get("confidence_notes", "")
        if isinstance(raw_notes, str):
            stripped_notes = raw_notes.strip()
            # Strip markdown code fences if present
            if stripped_notes.startswith("```"):
                stripped_notes = re.sub(r"^```[a-z]*\n?", "", stripped_notes).rstrip("`").strip()
            try:
                parsed_notes = json.loads(stripped_notes)
                if isinstance(parsed_notes, dict):
                    # Merge unwrapped fields back, confidence_notes becomes a plain string summary
                    for field in ("stable_preferences", "time_based_patterns", "seasonal_patterns", "weak_signals"):
                        if field in parsed_notes and not data.get(field):
                            data[field] = parsed_notes[field]
                    raw_notes = str(parsed_notes.get("confidence_notes", stripped_notes)).strip()
            except (json.JSONDecodeError, ValueError):
                raw_notes = stripped_notes
        confidence_notes = str(raw_notes).strip()

        profile = {
            "stable_preferences": cls._normalize_learned_list(data.get("stable_preferences")),
            "time_based_patterns": cls._normalize_learned_list(data.get("time_based_patterns")),
            "seasonal_patterns": cls._normalize_learned_list(data.get("seasonal_patterns")),
            "weak_signals": cls._normalize_learned_list(data.get("weak_signals")),
            "confidence_notes": confidence_notes,
        }

        metadata = data.get("metadata", {})
        if isinstance(metadata, dict):
            normalized_metadata = {str(key): value for key, value in metadata.items() if str(key).strip()}
        else:
            normalized_metadata = {}

        for legacy_key in ("bootstrap_style", "bootstrap_source"):
            if legacy_key in data and legacy_key not in normalized_metadata:
                normalized_metadata[legacy_key] = data[legacy_key]

        if normalized_metadata:
            profile["metadata"] = normalized_metadata

        return profile

    # ── Extracted Memories (per-topic JSON) ──

    async def get_memory_extraction_state(self, user_id: str = "default") -> dict[str, Any]:
        path = self._memory_state_path(user_id)
        if not path.exists():
            return {"history_cursor": 0}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"history_cursor": 0}
        if not isinstance(data, dict):
            return {"history_cursor": 0}
        history_cursor = data.get("history_cursor", 0)
        return {
            "history_cursor": history_cursor if isinstance(history_cursor, int) and history_cursor >= 0 else 0,
            "last_extracted_at": data.get("last_extracted_at", ""),
            "last_batch_size": data.get("last_batch_size", 0),
        }

    async def update_memory_extraction_state(
        self,
        user_id: str,
        *,
        history_cursor: int,
        last_batch_size: int,
    ) -> None:
        path = self._memory_state_path(user_id)
        payload = {
            "history_cursor": max(history_cursor, 0),
            "last_batch_size": max(last_batch_size, 0),
            "last_extracted_at": datetime.now(UTC).isoformat(),
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    async def get_extracted_memories(self, user_id: str = "default") -> dict[str, dict[str, Any]]:
        memories: dict[str, dict[str, Any]] = {}
        for path in sorted(self._memories_dir(user_id).glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                memories[path.stem] = data
        return memories

    async def get_memory_manifest(self, user_id: str = "default") -> list[dict[str, Any]]:
        memories = await self.get_extracted_memories(user_id)
        manifest: list[dict[str, Any]] = []
        for topic, data in memories.items():
            manifest.append(
                {
                    "topic": topic,
                    "title": str(data.get("title", topic)),
                    "category": str(data.get("category", "context")),
                    "summary": str(data.get("summary", "")),
                    "updated_at": str(data.get("updated_at", "")),
                }
            )
        return sorted(manifest, key=lambda item: (item["category"], item["topic"]))

    async def upsert_extracted_memory(
        self,
        user_id: str,
        topic: str,
        content: dict[str, Any],
    ) -> str:
        slug = self._slugify_topic(topic)
        path = self._memories_dir(user_id) / f"{slug}.json"
        existing: dict[str, Any] | None = None
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                data = None
            if isinstance(data, dict):
                existing = data

        incoming = dict(content)
        incoming["topic"] = slug
        payload = merge_extracted_memory(existing, incoming, now=datetime.now(UTC).isoformat())
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return slug

    async def delete_extracted_memory(self, user_id: str, topic: str) -> None:
        slug = self._slugify_topic(topic)
        path = self._memories_dir(user_id) / f"{slug}.json"
        if path.exists():
            path.unlink()

    async def search_memory_details(
        self,
        user_id: str = "default",
        *,
        device_type: str = "",
        device_id: str = "",
        query: str = "",
        statuses: set[str] | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        statuses = statuses or {"confirmed"}
        memories = await self.get_extracted_memories(user_id)
        query_tokens = self._memory_query_tokens(query)
        scored: list[tuple[float, str, dict[str, Any]]] = []

        for topic, memory in memories.items():
            if not self._is_complete_memory(memory):
                continue
            if str(memory.get("status", "")).strip() not in statuses:
                continue

            memory_device_types = [str(item).strip() for item in memory.get("device_types", [])]
            memory_device_ids = [str(item).strip() for item in memory.get("device_ids", [])]
            if device_type and memory_device_types and device_type not in memory_device_types:
                continue
            if device_id and memory_device_ids and device_id not in memory_device_ids:
                continue

            score = 0.0
            if device_id and device_id in memory_device_ids:
                score += 8.0
            if device_type and device_type in memory_device_types:
                score += 5.0
            elif device_type and not memory_device_types:
                score += 1.0

            category = str(memory.get("category", "")).strip()
            if category in {"preference", "routine", "constraint"}:
                score += 2.0

            confidence = str(memory.get("confidence", "")).strip()
            if confidence == "high":
                score += 1.0
            elif confidence == "medium":
                score += 0.5

            searchable_text = self._memory_search_text(memory)
            for token in query_tokens:
                if token and token in searchable_text:
                    score += 1.5

            if score <= 0:
                continue
            scored.append((score, topic, memory))

        scored.sort(key=lambda item: (-item[0], item[1]))
        return [memory for _, _, memory in scored[: max(limit, 0)]]

    # ── Three-Layer Memory Context (for LLM) ──
    #
    # L1 常驻层: 每次请求必带，极度精简 (~200 tokens)
    #   - 偏好摘要（一句话版）、在家状态、最近1条历史
    # L2 摘要层: 放在初始上下文，agent 可按需深入
    #   - 学习档案目录（仅名称列表）+ 记忆清单（仅 topic/title）
    # L3 按需层: 仅在 agent 调用工具时才加载
    #   - 完整学习档案、历史记录、记忆详情

    async def get_core_identity(self, user_id: str = "default") -> dict[str, Any]:
        """L1 常驻层: 每次必带的极致精简上下文。"""
        prefs = await self.get_preferences(user_id)
        # 压缩偏好为关键参数摘要
        compact_prefs = self._compress_preferences(prefs)
        # 仅最近1条历史给出对话延续感
        history = await self.get_history(user_id, limit=1)
        return {
            "preferences_summary": compact_prefs,
            "last_interaction": history[0] if history else None,
        }

    async def get_memory_directory(self, user_id: str = "default") -> dict[str, Any]:
        """L2 摘要层: 供 agent 了解有哪些记忆可用，按需深入。"""
        profiles = self._load_learned_profiles(user_id)
        profile_index = list(profiles.keys())  # 仅设备类型名列表
        manifest = await self.get_memory_manifest(user_id)
        # 极度压缩: 仅 topic + title
        memory_index = [
            {"topic": m["topic"], "title": m["title"]}
            for m in manifest
        ]
        return {
            "learned_profile_types": profile_index,
            "memory_topics": memory_index,
        }

    async def get_memory_detail(
        self,
        user_id: str = "default",
        *,
        profile_type: str = "",
        memory_topic: str = "",
        history_limit: int = 10,
    ) -> dict[str, Any]:
        """L3 按需层: agent 主动调用才加载的完整记忆详情。"""
        result: dict[str, Any] = {}
        if profile_type:
            result["learned_profile"] = await self.get_learned_for_skill(user_id, profile_type)
        if memory_topic:
            memories = await self.get_extracted_memories(user_id)
            slug = self._slugify_topic(memory_topic)
            result["memory_detail"] = memories.get(slug, {})
        if history_limit > 0:
            result["history"] = await self.get_history(user_id, limit=history_limit)
        return result

    @staticmethod
    def _compress_preferences(prefs_md: str) -> str:
        """将 Markdown 偏好压缩为单行关键参数。"""
        key_lines: list[str] = []
        for line in prefs_md.splitlines():
            stripped = line.strip()
            if stripped.startswith("- ") and ":" in stripped:
                # "- 温度: 24°C（...）" → "温度:24°C"
                key, _, val = stripped[2:].partition(":")
                val = val.strip()
                # 截取括号前的核心值
                for sep in ("（", "(", "，", ","):
                    if sep in val:
                        val = val[:val.index(sep)]
                        break
                if val and val != "未设置":
                    key_lines.append(f"{key.strip()}:{val.strip()}")
        return "; ".join(key_lines) if key_lines else "无特殊偏好"

    # ── Legacy & Compatibility Contexts ──

    async def get_full_context(self, user_id: str = "default") -> dict[str, Any]:
        """完整版上下文(仅供后台任务/偏好学习/测试使用，禁止在 LLM 对话中直接调用)。"""
        learned_profiles = await self.get_learned_profiles(user_id)
        return {
            "preferences": await self.get_preferences(user_id),
            "history": await self.get_history(user_id, limit=10),
            "learned": learned_profiles,
            "learned_profiles": learned_profiles,
            "memory_manifest": await self.get_memory_manifest(user_id),
            "extracted_memories": await self.get_extracted_memories(user_id),
        }

    async def get_planner_context(self, user_id: str = "default") -> dict[str, Any]:
        """供定时调度器/chat planner 使用: L1 常驻 + L2 目录。"""
        core = await self.get_core_identity(user_id)
        directory = await self.get_memory_directory(user_id)
        return {
            **core,
            **directory,
        }

    async def get_skill_context(
        self,
        user_id: str = "default",
        device_type: str = "",
        *,
        device_id: str = "",
        query: str = "",
    ) -> dict[str, Any]:
        """供 skill 决策使用: L1 常驻 + 该设备的 L3 学习档案（按需加载）。"""
        core = await self.get_core_identity(user_id)

        learned_profile = ""
        if device_type:
            learned_profile = await self.get_learned_for_skill(user_id, device_type)

        relevant_memories = await self.search_memory_details(
            user_id,
            device_type=device_type,
            device_id=device_id,
            query=query,
            statuses={"confirmed"},
            limit=5,
        )

        return {
            **core,
            "learned_profile": learned_profile,
            "relevant_memories": relevant_memories,
        }

    @staticmethod
    def _is_complete_memory(memory: dict[str, Any]) -> bool:
        required = {
            "topic",
            "title",
            "category",
            "claim_type",
            "status",
            "summary",
            "details",
            "device_types",
            "device_ids",
            "scenes",
            "confidence",
            "evidence_count",
            "positive_evidence",
            "negative_evidence",
            "source_actions",
            "created_at",
            "updated_at",
        }
        return required.issubset(memory.keys())

    @staticmethod
    def _memory_search_text(memory: dict[str, Any]) -> str:
        details = memory.get("details", [])
        scenes = memory.get("scenes", [])
        parts = [
            str(memory.get("topic", "")),
            str(memory.get("title", "")),
            str(memory.get("summary", "")),
            *[str(item) for item in details if str(item).strip()],
            *[str(item) for item in scenes if str(item).strip()],
        ]
        return " ".join(parts).lower().replace("_", " ")

    @staticmethod
    def _memory_query_tokens(query: str) -> list[str]:
        normalized = str(query or "").strip().lower().replace("_", " ")
        if not normalized:
            return []
        tokens = re.findall(r"[a-z]+|\d+|[\u4e00-\u9fff]+", normalized)
        unique: list[str] = []
        seen: set[str] = set()
        for token in [normalized, *tokens]:
            token = token.strip()
            if not token or token in seen:
                continue
            seen.add(token)
            unique.append(token)
        return unique
