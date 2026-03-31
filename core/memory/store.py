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

COLD_START_COMFORT_DEFAULTS = {
    "temperature": "22-24°C",
    "humidity": "45-55%",
    "brightness": "daytime moderate, evening warm and dim",
}


def _device_type_sort_key(device_type: str) -> tuple[int, str]:
    preferred = ["air_conditioner", "humidifier", "air_purifier", "light", "speaker"]
    try:
        return preferred.index(device_type), device_type
    except ValueError:
        return len(preferred), device_type


class MemoryStore:
    def __init__(self, base_dir: str = "data/memory") -> None:
        self._base = Path(base_dir)

    def _user_dir(self, user_id: str) -> Path:
        d = self._base / "users" / user_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _preferences_path(self, user_id: str) -> Path:
        return self._user_dir(user_id) / "preferences.md"

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
            "# User Preferences",
            "",
            "> Cold-start defaults generated from currently connected device types.",
            "> These values are an initial comfort-oriented baseline and should evolve from real usage history.",
            "",
            "## Comfort",
            f"- temperature: {COLD_START_COMFORT_DEFAULTS['temperature'] if 'air_conditioner' in device_types else 'not set'}",
            f"- humidity: {COLD_START_COMFORT_DEFAULTS['humidity'] if {'humidifier', 'air_purifier'} & set(device_types) else 'not set'}",
            f"- brightness: {COLD_START_COMFORT_DEFAULTS['brightness'] if 'light' in device_types else 'not set'}",
            "",
            "## Schedule",
            "- wake_up: 07:00-08:00",
            "- sleep: 22:30-00:00",
            "",
            "## Device Notes",
        ]

        if "air_conditioner" in device_types:
            lines.append("- air_conditioner: prioritize comfort over energy savings during active hours.")
        if "humidifier" in device_types:
            lines.append("- humidifier: prefer keeping rooms in a comfortable humidity band before they feel dry.")
        if "air_purifier" in device_types:
            lines.append("- air_purifier: prefer cleaner air during occupied periods and sleep hours.")
        if "light" in device_types:
            lines.append("- light: prefer brighter neutral light in daytime and warmer dimmer light at night.")
        if "speaker" in device_types:
            lines.append("- speaker: keep voice interactions low-noise by default; only speak aloud for explicit requests.")
        if not device_types:
            lines.append("- home: no active device-specific preferences have been inferred yet.")

        lines.extend(
            [
                "",
                "## Cold-Start Notes",
                f"- style: {style}",
                "- source: generated from currently available device types, not from learned behavior.",
                "- overwrite_policy: later explicit user edits and learned profiles should take precedence.",
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
