from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_PREFERENCES = """# User Preferences

## Comfort
- temperature: not set
- humidity: not set
- brightness: not set

## Schedule
- wake_up: not set
- sleep: not set

## Notes
(AI will learn and update this section)
"""


class MemoryStore:
    def __init__(self, base_dir: str = "data/memory") -> None:
        self._base = Path(base_dir)

    def _user_dir(self, user_id: str) -> Path:
        d = self._base / "users" / user_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ── Preferences (Markdown) ──

    async def get_preferences(self, user_id: str = "default") -> str:
        path = self._user_dir(user_id) / "preferences.md"
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

    # ── History (JSON) ──

    async def get_history(self, user_id: str = "default", limit: int = 50) -> list[dict]:
        path = self._user_dir(user_id) / "history.json"
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        return data[-limit:]

    async def append_history(self, user_id: str, entry: dict[str, Any]) -> None:
        path = self._user_dir(user_id) / "history.json"
        data = []
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
        entry["timestamp"] = datetime.now(timezone.utc).isoformat()
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
                return {str(k): str(v) for k, v in data.items()}

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
        profiles[skill_type] = content
        path = self._learned_json_path(user_id)
        path.write_text(json.dumps(profiles, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── Full Context (for LLM) ──

    async def get_full_context(self, user_id: str = "default") -> dict[str, Any]:
        return {
            "preferences": await self.get_preferences(user_id),
            "history": await self.get_history(user_id, limit=20),
            "learned": await self.get_learned(user_id),
            "learned_profiles": await self.get_learned_profiles(user_id),
        }
