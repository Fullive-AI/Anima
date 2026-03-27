"""Runtime settings store — persists user config to data/config.json.

Supports both Dashboard UI writes and .env fallback.
Settings saved here take precedence over .env values.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from core.runtime.config import settings as env_settings

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = "data/config.json"


class SettingsStore:
    def __init__(self, path: str = DEFAULT_CONFIG_PATH) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._data: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            try:
                self._data = json.loads(self._path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                logger.warning("Failed to load config from %s, starting fresh", self._path)
                self._data = {}

    def _save(self) -> None:
        self._path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        self._save()

    def delete(self, key: str) -> None:
        self._data.pop(key, None)
        self._save()

    def get_all(self) -> dict[str, Any]:
        return dict(self._data)

    def update(self, data: dict[str, Any]) -> None:
        self._data.update(data)
        self._save()

    # ── Convenience accessors ──

    def get_xiaomi_credentials(self) -> tuple[str, str] | None:
        user = self.get("xiaomi_cloud_user", "") or env_settings.xiaomi_cloud_user
        pwd = self.get("xiaomi_cloud_pass", "") or env_settings.xiaomi_cloud_pass
        if user and pwd:
            return user, pwd
        return None

    def get_xiaomi_country(self) -> str:
        return self.get("xiaomi_cloud_country", "cn")

    def is_xiaomi_configured(self) -> bool:
        return self.get_xiaomi_credentials() is not None

    def get_audio_library_dir(self) -> str:
        return self.get("audio_library_dir", "") or env_settings.audio_library_dir
