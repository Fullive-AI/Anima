from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.runtime.config import settings as env_settings


@dataclass(frozen=True)
class RuntimeLLMConfig:
    api_key: str
    model: str
    base_url: str
    disable_thinking: bool
    source: str


def resolve_llm_config(store: Any | None = None) -> RuntimeLLMConfig:
    dashboard_key = store.get("llm_api_key", "") if store else ""
    dashboard_model = store.get("llm_model", "") if store else ""
    dashboard_base_url = store.get("llm_base_url", "") if store else ""
    dashboard_disable_thinking = store.get("llm_disable_thinking", None) if store else None

    api_key = dashboard_key or env_settings.llm_api_key
    model = dashboard_model or env_settings.llm_model
    base_url = dashboard_base_url or env_settings.llm_base_url or ""
    disable_thinking = (
        dashboard_disable_thinking
        if dashboard_disable_thinking is not None
        else env_settings.llm_disable_thinking
    )

    return RuntimeLLMConfig(
        api_key=api_key,
        model=model,
        base_url=base_url,
        disable_thinking=bool(disable_thinking),
        source="dashboard" if dashboard_key else "env",
    )
