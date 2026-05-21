from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

REFRESH_ENVIRONMENT_ACTIONS = {
    "refresh_environment",
    "plan.refresh_environment",
    "environment_refresh",
}


@dataclass(frozen=True)
class HistoryFilterResult:
    should_write: bool
    reason: str | None = None


class HistoryFilter:
    def __init__(self, *, refresh_window_seconds: int = 60) -> None:
        self.refresh_window_seconds = refresh_window_seconds

    def should_write(
        self,
        *,
        entry: dict[str, Any],
        recent_entries: list[dict[str, Any]],
        now: datetime,
    ) -> HistoryFilterResult:
        # 当前第一版只过滤重复的环境刷新记录，避免影响真实设备动作和用户指令。
        if self._is_refresh_environment_history(entry) and self._has_recent_refresh_environment_history(
            recent_entries,
            now=now,
        ):
            return HistoryFilterResult(
                should_write=False,
                reason="duplicate_refresh_environment",
            )
        return HistoryFilterResult(should_write=True)

    def _is_refresh_environment_history(self, entry: dict[str, Any]) -> bool:
        action = str(entry.get("action", "")).strip()
        return action in REFRESH_ENVIRONMENT_ACTIONS

    def _has_recent_refresh_environment_history(
        self,
        recent_entries: list[dict[str, Any]],
        *,
        now: datetime,
    ) -> bool:
        for item in reversed(recent_entries):
            if not self._is_refresh_environment_history(item):
                continue
            seen_at = self._parse_timestamp(item.get("timestamp"))
            if seen_at is None:
                continue
            if (now - seen_at).total_seconds() <= self.refresh_window_seconds:
                return True
        return False

    def _parse_timestamp(self, value: Any) -> datetime | None:
        if not value:
            return None
        try:
            timestamp = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        except ValueError:
            return None
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        return timestamp
