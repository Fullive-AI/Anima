from __future__ import annotations

import ast
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from core.runtime.config import settings as env_settings
from core.llm.openai_text_client import OpenAITextClient


def _build_llm(context: dict[str, Any]) -> OpenAITextClient | None:
    store = context["settings"]
    api_key = store.get("llm_api_key", "") or env_settings.llm_api_key
    if not api_key or api_key.strip() in {"your-api-key-here", "sk-xxx"}:
        return None

    disable_thinking = store.get("llm_disable_thinking", env_settings.llm_disable_thinking)
    return OpenAITextClient(
        api_key=api_key,
        model=store.get("llm_model", "") or env_settings.llm_model,
        base_url=store.get("llm_base_url", "") or env_settings.llm_base_url or None,
        temperature=0.2,
        max_tokens=1800,
        disable_thinking=disable_thinking,
    )


def _extract_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
            else:
                text = getattr(item, "text", None)
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(part for part in parts if part)
    return str(content or "")


def _strip_code_fence(text: str) -> str:
    match = re.match(r"^\s*```(?:[a-zA-Z0-9_+-]+)?\s*\n(.*)\n```\s*$", text, re.DOTALL)
    return match.group(1).strip() if match else text.strip()


def _extract_json(text: str) -> dict[str, Any] | None:
    candidates = [_strip_code_fence(text), text.strip()]
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        candidates.append(match.group(0))

    for candidate in candidates:
        if not candidate:
            continue
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    return None


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

REQUIRED_FILES = [
    "SKILL.md",
    "references/knowledge.md",
    "references/decide.md",
    "references/learn.md",
    "scripts/actions.py",
]

FILE_REQUIREMENTS = {
    "SKILL.md": [
        "Return raw markdown only. Do not wrap it in JSON or code fences.",
        "Start with valid YAML frontmatter delimited by ---.",
        "Frontmatter must include `name`, `description`, and metadata.device_types.",
        "The body should include a short Goal section, a Load These Resources section, and concise Working Rules.",
        "Mention when the skill should trigger and what success looks like.",
    ],
    "references/knowledge.md": [
        "Return raw markdown only.",
        "Describe domain knowledge, safe operating goals, and important context.",
        "Do not include placeholders unrelated to this skill.",
    ],
    "references/decide.md": [
        "Return raw markdown only.",
        "Use the prompt variables {current_data}, {capabilities}, {user_preferences}, {learned_profile}, {recent_history}, and {knowledge}.",
        "The output schema must explicitly allow the action `none`.",
        "Only mention actions that exist in scripts/actions.py.",
    ],
    "references/learn.md": [
        "Return raw markdown only.",
        "Use the prompt variables {history} and {current_profile}.",
        "Require structured JSON output with fields like stable_preferences, time_based_patterns, seasonal_patterns, weak_signals, and confidence_notes.",
    ],
    "scripts/actions.py": [
        "Return raw Python source only. No markdown fences.",
        "Import DeviceCommand from core.models.",
        "Define helper functions only for supported actions.",
        "Each helper must return a DeviceCommand.",
    ],
}

ANALYSIS_REQUIRED_LIST_FIELDS = (
    "primary_steps",
    "success_criteria",
    "constraints",
    "needed_inputs",
    "assumptions",
    "clarification_questions",
)


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _default_request_analysis(request: str, *, mode: str, device_context: dict[str, Any] | None = None) -> dict[str, Any]:
    device_context = device_context or {}
    device_types = _string_list(device_context.get("device_types"))
    target_name = device_types[0] if device_types else "device"
    supported_actions = _normalize_supported_actions(device_context.get("supported_actions"))
    action_names = [item["name"] for item in supported_actions] or ["turn_on", "turn_off"]
    summary = request.strip() or f"Generate a {mode} skill."

    if mode == "system":
        primary_steps = [
            f"Read the current `{target_name}` device state and relevant sensors.",
            f"Choose one of the supported actions: {', '.join(action_names)}.",
            "Return a safe no-op when the context is insufficient or the current state is already appropriate.",
        ]
        success_criteria = [
            "The generated skill only references supported actions and parameters.",
            "The decision prompt makes `none` an explicit valid outcome.",
            "The generated package matches the repository skill layout.",
        ]
    else:
        primary_steps = [
            "Infer the trigger condition and target device types from the request.",
            "Define the smallest safe action set needed to satisfy the request.",
            "Generate a skill package that keeps decisions conservative and explicit.",
        ]
        success_criteria = [
            "The generated skill is specific enough to trigger from a clear user or environment signal.",
            "The package defines safe no-op behavior instead of over-automating.",
            "All generated files stay consistent with the same scope and action set.",
        ]

    constraints = _string_list(device_context.get("hard_rules")) or [
        "Keep the generated skill narrow and filesystem-safe.",
        "Do not invent actions outside scripts/actions.py.",
    ]
    assumptions = _string_list(device_context.get("knowledge_points"))
    needed_inputs = device_types or [target_name]

    return {
        "summary": summary,
        "goal": device_context.get("domain_summary", "") or f"Create a reusable {mode} skill from the user's request.",
        "trigger_description": f"Use when the user or runtime needs this {target_name}-related workflow." if target_name else "Use when this workflow is needed.",
        "primary_steps": primary_steps,
        "success_criteria": success_criteria,
        "constraints": constraints,
        "needed_inputs": needed_inputs,
        "assumptions": assumptions,
        "should_ask_clarification": False,
        "clarification_questions": [],
    }


def _validate_request_analysis(data: dict[str, Any], *, request: str, mode: str) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    summary = str(data.get("summary", "")).strip() or request.strip()
    goal = str(data.get("goal", "")).strip()
    trigger_description = str(data.get("trigger_description", "")).strip()
    should_ask_clarification = bool(data.get("should_ask_clarification", False))

    normalized = {
        "summary": summary,
        "goal": goal,
        "trigger_description": trigger_description,
        "should_ask_clarification": should_ask_clarification,
    }

    for field in ANALYSIS_REQUIRED_LIST_FIELDS:
        normalized[field] = _string_list(data.get(field))

    if not normalized["summary"]:
        errors.append("Analysis must include a non-empty `summary`.")
    if not normalized["goal"]:
        errors.append("Analysis must include a non-empty `goal`.")
    if not normalized["trigger_description"]:
        errors.append("Analysis must include a non-empty `trigger_description`.")
    if not normalized["primary_steps"]:
        errors.append("Analysis must include at least one `primary_steps` item.")
    if not normalized["success_criteria"]:
        errors.append("Analysis must include at least one `success_criteria` item.")
    if should_ask_clarification and not normalized["clarification_questions"]:
        errors.append("Analysis marked clarification as required but provided no `clarification_questions`.")
    if mode == "custom" and len(request.strip()) < 8 and not should_ask_clarification:
        errors.append("Very short custom requests must ask for clarification.")

    if errors:
        return None, errors
    return normalized, []


async def _analyze_request_with_llm(
    llm: OpenAITextClient,
    *,
    mode: str,
    request: str,
    device_context: dict[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, list[str]]:
    device_context_json = json.dumps(device_context or {}, ensure_ascii=False, indent=2)
    base_prompt = f"""
You are planning an Anima skill before any files are generated.

Mode: {mode}
User request:
{request}

Device context:
{device_context_json}

Return exactly one compact JSON object with this schema:
{{
  "summary": "one sentence summary of the reusable workflow",
  "goal": "what the skill should accomplish",
  "trigger_description": "when this skill should be used",
  "primary_steps": ["ordered step", "ordered step"],
  "success_criteria": ["observable outcome", "observable outcome"],
  "constraints": ["hard rule", "hard rule"],
  "needed_inputs": ["input or signal", "input or signal"],
  "assumptions": ["assumption", "assumption"],
  "should_ask_clarification": true,
  "clarification_questions": ["question", "question"]
}}

Hard constraints:
- Return JSON only. No markdown fences. No explanation.
- Think like a skill designer: extract repeatable triggers, steps, and success criteria before generation.
- Set should_ask_clarification to true when the request is too vague to generate a narrow safe skill.
- When clarification is not required, return an empty clarification_questions list.
- Keep the skill narrow. Prefer concrete triggers over generic "smart automation" wording.
"""

    prompt = base_prompt
    last_errors: list[str] = []
    for _attempt in range(3):
        response = await llm.ainvoke(prompt)
        data = _extract_json(_extract_text(response.content))
        if not data:
            last_errors = ["The model response was not valid JSON."]
            prompt = base_prompt + "\nYour previous response was not valid JSON. Return one JSON object only."
            continue

        analysis, errors = _validate_request_analysis(data, request=request, mode=mode)
        if analysis:
            return analysis, []

        last_errors = errors
        prompt = (
            base_prompt
            + "\nThe previous response was invalid. Fix these issues:\n- "
            + "\n- ".join(errors)
            + "\nReturn one corrected JSON object only."
        )

    return None, last_errors


def _normalize_supported_actions(raw_actions: Any) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    if not isinstance(raw_actions, list):
        return normalized

    for action in raw_actions:
        if not isinstance(action, dict):
            continue
        name = _normalize_slug(str(action.get("name", "")), "action")
        if not name:
            continue
        params: list[dict[str, str]] = []
        raw_params = action.get("params", [])
        if isinstance(raw_params, list):
            for param in raw_params:
                if not isinstance(param, dict):
                    continue
                param_name = _normalize_slug(str(param.get("name", "")), "value")
                if not param_name:
                    continue
                param_type = str(param.get("type", "string"))
                if param_type not in {"string", "number", "boolean"}:
                    param_type = "string"
                params.append({"name": param_name, "type": param_type})
        normalized.append({"name": name, "params": params})
    return normalized


def _default_supported_actions() -> list[dict[str, Any]]:
    return [{"name": "turn_on", "params": []}, {"name": "turn_off", "params": []}]


def _validate_generated_spec(
    data: dict[str, Any],
    *,
    request: str,
    analysis: dict[str, Any],
    skill_name_hint: str,
    existing_names: list[str],
    device_context: dict[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    device_context = device_context or {}

    folder_name = _normalize_slug(str(data.get("folder_name", skill_name_hint)), request)
    skill_name = _normalize_slug(str(data.get("skill_name", folder_name)), request)
    description = str(data.get("description", "")).strip()

    raw_device_types = data.get("device_types")
    if not isinstance(raw_device_types, list):
        raw_device_types = device_context.get("device_types", [])
    device_types = [
        _normalize_slug(str(item), str(item))
        for item in raw_device_types
        if isinstance(item, str) and item.strip()
    ]
    device_types = [item for item in device_types if item]

    if not folder_name:
        errors.append("Spec must include a valid `folder_name`.")
    if folder_name in existing_names:
        errors.append(f"Spec folder_name `{folder_name}` already exists.")
    if not skill_name:
        errors.append("Spec must include a valid `skill_name`.")
    if not description:
        errors.append("Spec must include a non-empty `description`.")
    if not device_types:
        errors.append("Spec must include at least one `device_types` entry.")

    domain_summary = str(data.get("domain_summary", "")).strip() or str(device_context.get("domain_summary", "")).strip()
    if not domain_summary:
        domain_summary = f"This skill handles the automation request: {request}"

    def _string_list(value: Any, fallback: list[str]) -> list[str]:
        if not isinstance(value, list):
            return fallback
        result = [str(item).strip() for item in value if str(item).strip()]
        return result or fallback

    knowledge_points = _string_list(data.get("knowledge_points"), list(device_context.get("knowledge_points", [])))
    hard_rules = _string_list(data.get("hard_rules"), list(device_context.get("hard_rules", [])))
    learning_focus = _string_list(data.get("learning_focus"), list(device_context.get("learning_focus", [])))
    supported_actions = _normalize_supported_actions(data.get("supported_actions"))
    if not supported_actions:
        supported_actions = _normalize_supported_actions(device_context.get("supported_actions"))
    if not supported_actions:
        supported_actions = _default_supported_actions()

    if errors:
        return None, errors

    return {
        "folder_name": folder_name,
        "skill_name": skill_name,
        "description": description,
        "device_types": device_types,
        "goal": str(data.get("goal", "")).strip() or str(analysis.get("goal", "")).strip(),
        "trigger_description": str(data.get("trigger_description", "")).strip()
        or str(analysis.get("trigger_description", "")).strip(),
        "primary_steps": _string_list(data.get("primary_steps")) or list(analysis.get("primary_steps", [])),
        "success_criteria": _string_list(data.get("success_criteria")) or list(analysis.get("success_criteria", [])),
        "constraints": _string_list(data.get("constraints")) or list(analysis.get("constraints", [])),
        "needed_inputs": _string_list(data.get("needed_inputs")) or list(analysis.get("needed_inputs", [])),
        "assumptions": _string_list(data.get("assumptions")) or list(analysis.get("assumptions", [])),
        "domain_summary": domain_summary,
        "knowledge_points": knowledge_points,
        "hard_rules": hard_rules,
        "supported_actions": supported_actions,
        "learning_focus": learning_focus,
    }, []


async def _generate_skill_spec_with_llm(
    llm: OpenAITextClient,
    *,
    mode: str,
    request: str,
    analysis: dict[str, Any],
    skill_name_hint: str,
    existing_names: list[str],
    device_context: dict[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, list[str]]:
    device_context_json = json.dumps(device_context or {}, ensure_ascii=False, indent=2)
    analysis_json = json.dumps(analysis, ensure_ascii=False, indent=2)
    base_prompt = f"""
You are designing an Anima skill package.

Mode: {mode}
User request:
{request}

Request analysis:
{analysis_json}

Skill name hint:
{skill_name_hint}

Existing skill names in the target directory:
{json.dumps(existing_names, ensure_ascii=False, indent=2)}

Device context:
{device_context_json}

Return exactly one compact JSON object with this schema:
{{
  "folder_name": "filesystem-safe lower_snake_case name",
  "skill_name": "stable skill id",
  "description": "one sentence summary",
  "device_types": ["device_type"],
  "goal": "what success looks like",
  "trigger_description": "when this skill should trigger",
  "primary_steps": ["ordered step", "ordered step"],
  "success_criteria": ["observable outcome", "observable outcome"],
  "constraints": ["hard rule", "hard rule"],
  "needed_inputs": ["signal", "signal"],
  "assumptions": ["assumption", "assumption"],
  "domain_summary": "brief domain summary",
  "knowledge_points": ["bullet", "bullet"],
  "hard_rules": ["rule", "rule"],
  "supported_actions": [
    {{"name": "turn_on", "params": []}},
    {{"name": "set_mode", "params": [{{"name": "mode", "type": "string"}}]}}
  ],
  "learning_focus": ["signal", "signal"]
}}

Hard constraints:
- Return JSON only. No markdown fences. No explanation.
- Do not reuse an existing skill folder name.
- Keep the skill specific to the request or device type.
- supported_actions must stay compatible with the device context when provided.
- Use the request analysis to keep the generated skill trigger, scope, and success criteria coherent.
"""

    prompt = base_prompt
    last_errors: list[str] = []
    for _attempt in range(3):
        response = await llm.ainvoke(prompt)
        data = _extract_json(_extract_text(response.content))
        if not data:
            last_errors = ["The model response was not valid JSON."]
            prompt = base_prompt + "\nYour previous response was not valid JSON. Return one JSON object only."
            continue

        spec, errors = _validate_generated_spec(
            data,
            request=request,
            analysis=analysis,
            skill_name_hint=skill_name_hint,
            existing_names=existing_names,
            device_context=device_context,
        )
        if spec:
            return spec, []

        last_errors = errors
        prompt = (
            base_prompt
            + "\nThe previous response was invalid. Fix these issues:\n- "
            + "\n- ".join(errors)
            + "\nReturn one corrected JSON object only."
        )

    return None, last_errors


def _validate_generated_file(file_path: str, content: str) -> list[str]:
    errors: list[str] = []
    stripped = content.strip()
    if not stripped:
        return [f"`{file_path}` was empty."]

    if file_path == "SKILL.md":
        if not re.match(r"^---\n.*?\n---\n", stripped, re.DOTALL):
            errors.append("`SKILL.md` must start with valid YAML frontmatter delimited by `---`.")
        for heading in ("## Goal", "## Load These Resources", "## Working Rules"):
            if heading not in stripped:
                errors.append(f"`SKILL.md` must include a `{heading}` section.")
    elif file_path == "references/decide.md":
        lowered = stripped.lower()
        if "`none`" not in stripped and '"none"' not in lowered and " none" not in lowered:
            errors.append("`references/decide.md` must explicitly allow `none`.")
        for placeholder in ("{current_data}", "{capabilities}", "{user_preferences}", "{learned_profile}", "{recent_history}", "{knowledge}"):
            if placeholder not in stripped:
                errors.append(f"`references/decide.md` must include `{placeholder}`.")
    elif file_path == "references/learn.md":
        lowered = stripped.lower()
        if "{history}" not in stripped or "{current_profile}" not in stripped:
            errors.append("`references/learn.md` must include `{history}` and `{current_profile}`.")
        if "json" not in lowered:
            errors.append("`references/learn.md` must require structured JSON output.")
    elif file_path == "scripts/actions.py":
        if "DeviceCommand" not in stripped:
            errors.append("`scripts/actions.py` must reference `DeviceCommand`.")
        try:
            ast.parse(stripped)
        except SyntaxError as exc:
            errors.append(f"`scripts/actions.py` must be valid Python: {exc.msg}.")
    return errors


async def _generate_file_with_llm(
    llm: OpenAITextClient,
    *,
    mode: str,
    request: str,
    spec: dict[str, Any],
    file_path: str,
) -> tuple[str | None, list[str]]:
    requirements = "\n".join(f"- {item}" for item in FILE_REQUIREMENTS[file_path])
    spec_json = json.dumps(spec, ensure_ascii=False, indent=2)
    base_prompt = f"""
You are generating one file for an Anima skill package.

Mode: {mode}
User request:
{request}

Skill spec:
{spec_json}

Target file:
{file_path}

Requirements:
{requirements}

Return only the raw file content for `{file_path}`. Do not wrap it in JSON. Do not add commentary.
"""

    prompt = base_prompt
    last_errors: list[str] = []
    for _attempt in range(3):
        response = await llm.ainvoke(prompt)
        content = _strip_code_fence(_extract_text(response.content))
        errors = _validate_generated_file(file_path, content)
        if not errors:
            return content, []

        last_errors = errors
        prompt = (
            base_prompt
            + "\nThe previous file content was invalid. Fix these issues:\n- "
            + "\n- ".join(errors)
            + "\nReturn only the corrected raw file content."
        )

    return None, last_errors


def _validate_generated_package(data: dict[str, Any], *, request: str, skill_name_hint: str) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    files = data.get("files")
    if not isinstance(files, dict):
        return None, ["Top-level `files` must be a JSON object."]

    missing = [path for path in REQUIRED_FILES if not isinstance(files.get(path), str) or not files.get(path).strip()]
    if missing:
        errors.append(f"Missing or empty required files: {', '.join(missing)}.")

    folder_name = _normalize_slug(str(data.get("folder_name", skill_name_hint)), request)
    skill_name = _normalize_slug(str(data.get("skill_name", folder_name)), request)

    skill_md = files.get("SKILL.md", "")
    if not isinstance(skill_md, str) or not re.match(r"^---\n.*?\n---\n", skill_md, re.DOTALL):
        errors.append("`SKILL.md` must start with valid YAML frontmatter delimited by `---`.")

    decide_md = files.get("references/decide.md", "")
    if isinstance(decide_md, str):
        lowered_decide = decide_md.lower()
        if "`none`" not in decide_md and "| none" not in lowered_decide and '"none"' not in lowered_decide and " none" not in lowered_decide:
            errors.append("`references/decide.md` must explicitly allow `none`.")

    actions_py = files.get("scripts/actions.py", "")
    if isinstance(actions_py, str) and "DeviceCommand" not in actions_py:
        errors.append("`scripts/actions.py` must return `DeviceCommand` helpers.")

    if errors:
        return None, errors

    return {
        "folder_name": folder_name,
        "skill_name": skill_name,
        "files": {path: files[path] for path in REQUIRED_FILES},
    }, []


async def _generate_package_with_llm(
    llm: OpenAITextClient,
    *,
    mode: str,
    request: str,
    skill_name_hint: str,
    existing_names: list[str],
    device_context: dict[str, Any] | None = None,
    analysis: dict[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, list[str]]:
    normalized_analysis = analysis or _default_request_analysis(request, mode=mode, device_context=device_context)
    if analysis is None and mode == "custom":
        analyzed, analysis_errors = await _analyze_request_with_llm(
            llm,
            mode=mode,
            request=request,
            device_context=device_context,
        )
        if not analyzed:
            return None, analysis_errors
        normalized_analysis = analyzed

    spec, spec_errors = await _generate_skill_spec_with_llm(
        llm,
        mode=mode,
        request=request,
        analysis=normalized_analysis,
        skill_name_hint=skill_name_hint,
        existing_names=existing_names,
        device_context=device_context,
    )
    if not spec:
        return None, spec_errors

    files: dict[str, str] = {}
    last_errors: list[str] = []
    for file_path in REQUIRED_FILES:
        content, file_errors = await _generate_file_with_llm(
            llm,
            mode=mode,
            request=request,
            spec=spec,
            file_path=file_path,
        )
        if content is None:
            return None, file_errors
        files[file_path] = content
        last_errors = file_errors

    package, package_errors = _validate_generated_package(
        {
            "folder_name": spec["folder_name"],
            "skill_name": spec["skill_name"],
            "files": files,
        },
        request=request,
        skill_name_hint=skill_name_hint,
    )
    if not package:
        return None, package_errors or last_errors
    return package, []


def _write_generated_package(target_dir: Path, package: dict[str, Any]) -> None:
    for relative_path, content in package["files"].items():
        file_path = target_dir / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")


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
    if not llm:
        return {
            "reply": "创建 skill 需要先配置可用的 LLM。",
            "error": "llm_required",
        }

    analysis, analysis_errors = await _analyze_request_with_llm(
        llm,
        mode="custom",
        request=request,
    )
    if not analysis:
        detail = f" 失败原因：{'；'.join(analysis_errors[:3])}" if analysis_errors else ""
        return {
            "reply": f"我没能完成需求分析，请把要自动化的触发条件和目标动作说得更具体一些。{detail}",
            "error": "skill_analysis_failed",
            "details": analysis_errors,
        }
    if analysis.get("should_ask_clarification"):
        questions = _string_list(analysis.get("clarification_questions"))[:3]
        question_block = "\n".join(f"{idx}. {item}" for idx, item in enumerate(questions, start=1))
        return {
            "reply": "我需要先确认几件事，避免生成一个过于宽泛的 skill：\n" + question_block,
            "action": "create_custom_skill",
            "status": "needs_clarification",
            "questions": questions,
        }

    package, errors = await _generate_package_with_llm(
        llm,
        mode="custom",
        request=request,
        skill_name_hint=_normalize_slug("", request),
        existing_names=existing_custom_skills,
        analysis=analysis,
    )
    if not package:
        detail = f" 失败原因：{'；'.join(errors[:3])}" if errors else ""
        return {
            "reply": f"我没能生成有效的 skill 文件，请调整需求后再试一次。{detail}",
            "error": "skill_generation_failed",
            "details": errors,
        }

    target_dir = _unique_dir(base_dir, package["folder_name"])
    _write_generated_package(target_dir, package)

    skill_loader.discover()

    created_name = target_dir.name
    return {
        "reply": reply or f"已创建自定义 skill：{created_name}",
        "action": "create_custom_skill",
        "status": "created",
        "skill_name": package["skill_name"],
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
    llm = _build_llm(context)
    if not llm:
        return {
            "reply": reply or "未配置 LLM，跳过自动生成 system skill。",
            "action": "ensure_system_skills_for_devices",
            "status": "noop",
            "created_skills": [],
            "refresh_skills": False,
        }

    for device in devices:
        device_type = getattr(device, "type", "") or ""
        if not isinstance(device_type, str) or not device_type or device_type == "unknown":
            continue
        if skill_loader.get_system_skill_for_device(device_type):
            continue

        system_spec = _system_spec_from_device(device)
        target_dir = target_root / system_spec["folder_name"]
        if target_dir.exists():
            continue

        package, _errors = await _generate_package_with_llm(
            llm,
            mode="system",
            request=f"Auto-generated system skill for discovered device type `{device_type}`.",
            skill_name_hint=system_spec["skill_name"],
            existing_names=[path.name for path in target_root.iterdir() if path.is_dir() and not path.name.startswith((".", "_"))],
            device_context=system_spec,
        )
        if not package:
            continue

        target_dir = target_root / package["folder_name"]
        if target_dir.exists():
            continue

        _write_generated_package(target_dir, package)
        created.append(package["folder_name"])

    if created:
        skill_loader.discover()

    return {
        "reply": reply or (f"已自动补齐 system skill：{', '.join(created)}" if created else "没有需要补齐的 system skill。"),
        "action": "ensure_system_skills_for_devices",
        "status": "created" if created else "noop",
        "created_skills": created,
        "refresh_skills": bool(created),
    }
