from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

REFRESH_ENVIRONMENT_ACTIONS = {
    "refresh_environment",
    "plan.refresh_environment",
    "environment_refresh",
}
# 过滤写入history文件中的refresh_environment操作
# 减少memory读取的token消耗


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
        # 环境刷新是系统内部状态同步，不直接代表用户偏好；当前版本全部跳过写入 history。
        if self._is_refresh_environment_history(entry):
            return HistoryFilterResult(
                should_write=False,
                reason="refresh_environment_filtered",
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
