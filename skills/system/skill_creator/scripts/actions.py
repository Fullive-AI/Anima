from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from langchain_openai import ChatOpenAI
import yaml

from core.config import settings as env_settings


def _build_llm(context: dict[str, Any]) -> ChatOpenAI | None:
    store = context["settings"]
    api_key = store.get("llm_api_key", "") or env_settings.llm_api_key
    if not api_key:
        return None

    extra_body = {}
    disable_thinking = store.get("llm_disable_thinking", env_settings.llm_disable_thinking)
    if disable_thinking:
        extra_body["thinking"] = {"type": "disabled"}

    return ChatOpenAI(
        api_key=api_key,
        model=store.get("llm_model", "") or env_settings.llm_model,
        base_url=store.get("llm_base_url", "") or env_settings.llm_base_url or None,
        temperature=0.2,
        max_tokens=1800,
        extra_body=extra_body or None,
    )


def _extract_json(text: str) -> dict[str, Any] | None:
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    json_str = match.group(1).strip() if match else None
    if not json_str:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        json_str = match.group(0) if match else None
    if not json_str:
        return None

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _normalize_slug(raw: str, fallback_seed: str) -> str:
    slug = re.sub(r"[^a-z0-9_]+", "_", raw.lower()).strip("_")
    if slug:
        return slug[:48]
    digest = hashlib.sha1(fallback_seed.encode("utf-8")).hexdigest()[:8]
    return f"custom_skill_{digest}"


def _unique_dir(base_dir: Path, folder_name: str) -> Path:
    candidate = base_dir / folder_name
    if not candidate.exists():
        return candidate

    index = 2
    while True:
        next_candidate = base_dir / f"{folder_name}_{index}"
        if not next_candidate.exists():
            return next_candidate
        index += 1


def _custom_root(skill_loader: Any) -> Path:
    return skill_loader._dir / "custom"


def _system_root(skill_loader: Any) -> Path:
    return skill_loader._dir / "system"


def _device_capability_spec(device: Any) -> list[dict[str, Any]]:
    supported_actions: list[dict[str, Any]] = []
    for capability in getattr(device, "capabilities", []):
        name = getattr(capability, "name", "")
        if not isinstance(name, str) or not name:
            continue

        params_meta = getattr(capability, "params", {}) if hasattr(capability, "params") else {}
        inputs = params_meta.get("inputs", []) if isinstance(params_meta, dict) else []
        action_params = []
        for item in inputs:
            param_name = item.get("name")
            if not isinstance(param_name, str) or not param_name:
                continue
            param_type = item.get("type", "string")
            if param_type not in {"string", "number", "boolean"}:
                param_type = "string"
            action_params.append({"name": _normalize_slug(param_name, param_name), "type": param_type})

        if not inputs and isinstance(params_meta, dict) and any(key in params_meta for key in ("min", "max", "step")):
            action_params.append({"name": "value", "type": "number"})

        supported_actions.append({"name": _normalize_slug(name, name), "params": action_params})

    if not supported_actions:
        supported_actions = [
            {"name": "turn_on", "params": []},
            {"name": "turn_off", "params": []},
        ]

    return supported_actions


def _system_spec_from_device(device: Any) -> dict[str, Any]:
    device_type = _normalize_slug(getattr(device, "type", "") or "", "device")
    device_name = str(getattr(device, "name", device_type))
    supported_actions = _device_capability_spec(device)
    capability_names = ", ".join(action["name"] for action in supported_actions)
    return {
        "folder_name": device_type,
        "skill_name": device_type,
        "description": f"Use when reasoning about {device_type} devices in Anima.",
        "device_types": [device_type],
        "domain_summary": f"This system skill was auto-generated for discovered `{device_type}` devices such as `{device_name}`.",
        "knowledge_points": [
            f"The device type is `{device_type}` and should only use supported actions: {capability_names}.",
            "Prefer safe no-op behavior when the current context is insufficient.",
            "Avoid redundant commands when recent history shows the device was just adjusted.",
            "Use device capabilities as the hard boundary for all emitted actions and params.",
        ],
        "hard_rules": [
            "Return none if the current context is missing or ambiguous.",
            "Do not invent actions outside the generated scripts/actions.py file.",
            "Do not repeat materially identical commands when recent history shows a recent adjustment.",
            "Respect the capability list and parameter bounds exposed by the device.",
        ],
        "supported_actions": supported_actions,
        "learning_focus": [
            "Which actions are repeatedly preferred by the user",
            "Whether behavior changes by time of day or occupancy pattern",
            "Whether some modes or targets are consistently favored over others",
        ],
    }


def _fallback_spec(request: str) -> dict[str, Any]:
    folder_name = _normalize_slug("", request)
    return {
        "folder_name": folder_name,
        "skill_name": folder_name,
        "description": f"Use when handling this custom user requirement in Anima: {request}",
        "device_types": [folder_name],
        "domain_summary": request,
        "knowledge_points": [
            "Capture the user's routine, preferred timing, and desired device behavior.",
            "Translate the request into clear on/off or mode-change rules.",
            "Prefer safe no-op decisions when context is incomplete.",
        ],
        "hard_rules": [
            "Return none if the triggering context is missing.",
            "Do not invent actions outside scripts/actions.py.",
            "Avoid repeating identical commands when recent history already shows an adjustment.",
        ],
        "supported_actions": [
            {"name": "activate_routine", "params": [{"name": "routine_name", "type": "string"}]},
            {"name": "turn_on", "params": []},
            {"name": "turn_off", "params": []},
            {"name": "set_mode", "params": [{"name": "mode", "type": "string"}]},
        ],
        "learning_focus": [
            "What time the user usually wants this routine to trigger",
            "Which actions are consistently preferred",
            "Whether the routine changes by weekday, season, or occupancy pattern",
        ],
    }


async def _generate_spec_with_llm(request: str, existing_custom_skills: list[str], llm: ChatOpenAI) -> dict[str, Any] | None:
    prompt = f"""
You are generating a custom Anima skill package specification.

User request:
{request}

Existing custom skills:
{json.dumps(existing_custom_skills, ensure_ascii=False, indent=2)}

Return one JSON object with this schema:
{{
  "folder_name": "filesystem-safe lower_snake_case name",
  "skill_name": "same as folder_name unless you have a strong reason",
  "description": "one sentence saying when this skill should be used",
  "device_types": ["custom device types this skill should map to"],
  "domain_summary": "one short paragraph",
  "knowledge_points": ["3 to 6 bullet-like statements"],
  "hard_rules": ["3 to 6 concrete guardrails"],
  "supported_actions": [
    {{
      "name": "action_name",
      "params": [
        {{"name": "param_name", "type": "string | number | boolean"}}
      ]
    }}
  ],
  "learning_focus": ["2 to 5 things this skill should learn over time"]
}}

Constraints:
- Keep names stable and filesystem-safe.
- Do not reuse an existing custom skill name.
- Include `none` handling in hard rules implicitly; do not list it as an action.
- Prefer 2 to 5 concrete actions.
- Keep the skill specific to the user's requirement.
"""
    response = await llm.ainvoke(prompt)
    data = _extract_json(response.content)
    if not data:
        return None
    return data


def _param_type_hint(param_type: str) -> str:
    return {"number": "int | float", "boolean": "bool"}.get(param_type, "str")


def _example_param_value(param_type: str) -> str:
    return {"number": "0", "boolean": "False"}.get(param_type, '""')


def _render_skill_md(spec: dict[str, Any]) -> str:
    actions = ", ".join(action["name"] for action in spec["supported_actions"])
    frontmatter = {
        "name": spec["skill_name"],
        "description": spec["description"],
        "metadata": {
            "device_types": spec["device_types"],
            "version": "0.1.0",
        },
    }
    frontmatter_text = yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False).strip()
    return f"""---
{frontmatter_text}
---

# {spec["skill_name"].replace("_", " ").title()}

This custom skill was generated from a user request.

## Scope

{spec["domain_summary"]}

## Load These Resources

- `references/knowledge.md` for the domain rules and constraints.
- `references/decide.md` when generating a single-device or routine decision.
- `references/learn.md` when updating the learned profile from usage history.
- `scripts/actions.py` for the structured action helpers exposed to Anima.

## Supported Actions

- {actions}
"""


def _render_knowledge_md(spec: dict[str, Any], request: str) -> str:
    points = "\n".join(f"- {item}" for item in spec["knowledge_points"])
    return f"""# {spec["skill_name"].replace("_", " ").title()} — Domain Knowledge

## Original User Request

- {request}

## Operating Knowledge

{points}
"""


def _render_decide_md(spec: dict[str, Any]) -> str:
    hard_rules = "\n".join(f"- {rule}" for rule in spec["hard_rules"])
    action_names = " | ".join(action["name"] for action in spec["supported_actions"])
    return f"""You are Anima's decision module for `{spec["skill_name"]}`. Produce one conservative, structured control decision for a single device or routine instance.

## Current Data
{{current_data}}

## Device Capabilities
{{capabilities}}

## User Preferences
{{user_preferences}}

## Learned Profile
{{learned_profile}}

## Recent Decision History
{{recent_history}}

## Domain Knowledge
{{knowledge}}

## Decision Priority

1. Safety and device protection
2. Avoid oscillation and redundant commands
3. Match the user's stated routine or preference
4. Energy and resource efficiency

## Hard Rules

{hard_rules}

## Instructions

1. Compare the current context against the user's intended behavior.
2. Prefer explicit user intent first, then learned profile if it is consistent.
3. If there is not enough context to act safely, return `none`.

Respond with a JSON object:

```json
{{
  "action": "{action_names} | none",
  "params": {{}},
  "reason": "brief explanation",
  "confidence": 0.0,
  "expected_outcome": "what should improve",
  "should_wait_seconds": 0
}}
```
"""


def _render_learn_md(spec: dict[str, Any]) -> str:
    focus = "\n".join(f"- {item}" for item in spec["learning_focus"])
    return f"""Analyze the user's history for `{spec["skill_name"]}` and update the learned profile.

## History
{{history}}

## Current Learned Profile
{{current_profile}}

## Focus Areas

{focus}

Respond with a JSON object:

```json
{{
  "stable_preferences": [
    "clear preference statements backed by repeated history"
  ],
  "time_based_patterns": [
    "patterns tied to time of day or routines"
  ],
  "seasonal_patterns": [
    "patterns tied to season, weekday, or longer cycles"
  ],
  "weak_signals": [
    "possible preferences that need more evidence"
  ],
  "confidence_notes": "short note about certainty and data quality"
}}
```
"""


def _render_actions_py(spec: dict[str, Any]) -> str:
    blocks: list[str] = ["from core.models import DeviceCommand", ""]
    for action in spec["supported_actions"]:
        func_name = action["name"]
        params = action.get("params", [])
        signature = ", ".join(
            [f'{param["name"]}: {_param_type_hint(param.get("type", "string"))}' for param in params]
        )
        if signature:
            signature = f"{signature}, "
        params_dict = ", ".join(
            [f'"{param["name"]}": {param["name"]}' for param in params]
        )
        params_literal = "{" + params_dict + "}" if params_dict else "{}"
        blocks.append(
            f"""def {func_name}(device_id: str, {signature}reason: str = "") -> DeviceCommand:
    return DeviceCommand(
        device_id=device_id,
        action="{func_name}",
        params={params_literal},
        source="brain",
        reason=reason,
    )
"""
        )
    return "\n".join(blocks).strip() + "\n"


def _write_skill_package(target_dir: Path, spec: dict[str, Any], request: str) -> None:
    (target_dir / "references").mkdir(parents=True)
    (target_dir / "scripts").mkdir(parents=True)

    (target_dir / "SKILL.md").write_text(_render_skill_md(spec), encoding="utf-8")
    (target_dir / "references" / "knowledge.md").write_text(_render_knowledge_md(spec, request), encoding="utf-8")
    (target_dir / "references" / "decide.md").write_text(_render_decide_md(spec), encoding="utf-8")
    (target_dir / "references" / "learn.md").write_text(_render_learn_md(spec), encoding="utf-8")
    (target_dir / "scripts" / "actions.py").write_text(_render_actions_py(spec), encoding="utf-8")


async def create_custom_skill(
    context: dict[str, Any],
    params: dict[str, Any] | None = None,
    reply: str = "",
) -> dict[str, Any]:
    request = ((params or {}).get("request") or "").strip()
    if not request:
        return {"reply": "请先告诉我这个 skill 要解决什么问题。", "error": "missing_request"}

    skill_loader = context["brain"]._skill_loader
    base_dir = _custom_root(skill_loader)
    base_dir.mkdir(parents=True, exist_ok=True)

    existing_custom_skills = [path.name for path in base_dir.iterdir() if path.is_dir() and not path.name.startswith((".", "_"))]
    llm = _build_llm(context)
    spec = None
    if llm:
        try:
            spec = await _generate_spec_with_llm(request, existing_custom_skills, llm)
        except Exception:
            spec = None

    if not spec:
        spec = _fallback_spec(request)

    folder_name = _normalize_slug(str(spec.get("folder_name", spec.get("skill_name", ""))), request)
    skill_name = _normalize_slug(str(spec.get("skill_name", folder_name)), request)
    spec["folder_name"] = folder_name
    spec["skill_name"] = skill_name
    spec["device_types"] = [item for item in spec.get("device_types", [folder_name]) if isinstance(item, str) and item] or [folder_name]
    spec["knowledge_points"] = [item for item in spec.get("knowledge_points", []) if isinstance(item, str) and item] or _fallback_spec(request)["knowledge_points"]
    spec["hard_rules"] = [item for item in spec.get("hard_rules", []) if isinstance(item, str) and item] or _fallback_spec(request)["hard_rules"]
    spec["learning_focus"] = [item for item in spec.get("learning_focus", []) if isinstance(item, str) and item] or _fallback_spec(request)["learning_focus"]
    supported_actions = []
    for action in spec.get("supported_actions", []):
        if not isinstance(action, dict):
            continue
        name = action.get("name")
        if not isinstance(name, str) or not name:
            continue
        normalized_name = _normalize_slug(name, name)
        params_list = []
        for param in action.get("params", []):
            if not isinstance(param, dict):
                continue
            param_name = param.get("name")
            if not isinstance(param_name, str) or not param_name:
                continue
            param_type = param.get("type", "string")
            if param_type not in {"string", "number", "boolean"}:
                param_type = "string"
            params_list.append({"name": _normalize_slug(param_name, param_name), "type": param_type})
        supported_actions.append({"name": normalized_name, "params": params_list})
    spec["supported_actions"] = supported_actions or _fallback_spec(request)["supported_actions"]
    spec["description"] = str(spec.get("description", f"Use when handling this custom requirement: {request}"))
    spec["domain_summary"] = str(spec.get("domain_summary", request))

    target_dir = _unique_dir(base_dir, folder_name)
    _write_skill_package(target_dir, spec, request)

    skill_loader.discover()

    created_name = target_dir.name
    return {
        "reply": reply or f"已创建自定义 skill：{created_name}",
        "action": "create_custom_skill",
        "status": "created",
        "skill_name": spec["skill_name"],
        "folder_name": created_name,
        "path": str(target_dir),
        "refresh_skills": True,
    }


async def ensure_system_skills_for_devices(
    context: dict[str, Any],
    params: dict[str, Any] | None = None,
    reply: str = "",
) -> dict[str, Any]:
    skill_loader = context["brain"]._skill_loader
    target_root = _system_root(skill_loader)
    target_root.mkdir(parents=True, exist_ok=True)

    devices = (params or {}).get("devices")
    if not isinstance(devices, list):
        discovery = context["discovery"]
        devices = discovery.get_all_devices()

    created: list[str] = []
    for device in devices:
        device_type = getattr(device, "type", "") or ""
        if not isinstance(device_type, str) or not device_type or device_type == "unknown":
            continue
        if skill_loader.get_system_skill_for_device(device_type):
            continue

        spec = _system_spec_from_device(device)
        target_dir = target_root / spec["folder_name"]
        if target_dir.exists():
            continue

        _write_skill_package(
            target_dir,
            spec,
            request=f"Auto-generated system skill for discovered device type `{device_type}`.",
        )
        created.append(spec["folder_name"])

    if created:
        skill_loader.discover()

    return {
        "reply": reply or (f"已自动补齐 system skill：{', '.join(created)}" if created else "没有需要补齐的 system skill。"),
        "action": "ensure_system_skills_for_devices",
        "status": "created" if created else "noop",
        "created_skills": created,
        "refresh_skills": bool(created),
    }

