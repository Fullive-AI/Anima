from __future__ import annotations

import json
import logging
import math
import re
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph
from openai import AsyncOpenAI

from core.brain.skill_loader import LoadedSkill, SkillLoader
from core.events.bus import EventBus
from core.memory.store import MemoryStore
from core.models import (
    ActionVerificationResult,
    BrainCycleResult,
    ChatPlan,
    Device,
    DeviceCommand,
    SkillActionSpec,
    SkillExecutionResult,
    SkillPlanItem,
    SkillSummary,
)
from core.runtime.config import settings

logger = logging.getLogger(__name__)
PLANNER_HINTS_PATH = Path(__file__).with_name("prompts") / "planner_hints.md"


class BrainCycleState(TypedDict, total=False):
    user_memory: dict[str, Any]
    devices: list[Device]
    environment_state: dict[str, Any]
    lightweight_skills: list[SkillSummary]
    planner_prompt: str
    planner_output: str
    plan_items: list[SkillPlanItem]
    execution_results: list[SkillExecutionResult]


class ChatState(TypedDict, total=False):
    message: str
    app_state: dict[str, Any]
    planner_prompt: str
    planner_output: str
    plan: ChatPlan
    result: dict[str, Any]


class Brain:
    def __init__(
        self,
        bus: EventBus,
        skill_loader: SkillLoader,
        memory: MemoryStore,
    ) -> None:
        self._bus = bus
        self._skill_loader = skill_loader
        self._memory = memory
        self._environment_provider: Callable[[], list[Device]] | None = None
        self._llm = AsyncOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url or None,
        )
        self._llm_model = settings.llm_model
        self._llm_disable_thinking = settings.llm_disable_thinking
        self._cycle_graph = self._build_cycle_graph()
        self._chat_graph = self._build_chat_graph()

    def set_environment_provider(self, provider: Callable[[], list[Device]]) -> None:
        self._environment_provider = provider

    async def run_cycle(self) -> BrainCycleResult:
        user_memory = await self._memory.get_full_context()
        devices = self._get_environment_devices(None)
        environment_state = self.get_environment_state()
        lightweight_skills = self._skill_loader.list_system_device_skill_summaries()

        if not devices or not lightweight_skills:
            return BrainCycleResult()

        result = await self._cycle_graph.ainvoke(
            {
                "user_memory": user_memory,
                "devices": devices,
                "environment_state": environment_state,
                "lightweight_skills": lightweight_skills,
            }
        )
        return BrainCycleResult(
            plan_items=result.get("plan_items", []),
            execution_results=result.get("execution_results", []),
        )

    async def handle_chat_message(self, message: str, app_state: dict[str, Any]) -> dict[str, Any]:
        text = message.strip()
        if not text:
            return {"reply": "请先输入你的需求。"}

        if not settings.llm_api_key and not app_state["settings"].get("llm_api_key", ""):
            return {"reply": "聊天入口现在统一走模型决策，请先配置可用的 LLM。", "error": "llm_required"}

        result = await self._chat_graph.ainvoke({"message": text, "app_state": app_state})
        return result.get("result", {"reply": "我暂时没有需要执行的操作。"})

    async def execute_device_skill(
        self,
        skill_name: str,
        context: dict[str, Any],
        plan_item: SkillPlanItem,
    ) -> list[SkillActionSpec]:
        loaded_skill = context.get("_loaded_skill")
        if not isinstance(loaded_skill, LoadedSkill):
            loaded_skill = self._skill_loader.get_skill(skill_name)
        if not loaded_skill or not loaded_skill.decide_prompt:
            return []

        discovery = context["discovery"]
        devices = [
            device for device in discovery.get_devices_by_type(plan_item.device_type)
            if device.online
        ]
        if not devices:
            devices = discovery.get_devices_by_type(plan_item.device_type)

        user_memory = context.get("user_memory")
        if not isinstance(user_memory, dict):
            user_memory = await self._memory.get_full_context()

        actions: list[SkillActionSpec] = []
        for device in devices:
            prompt = self._build_prompt_context(
                skill=loaded_skill,
                device=device,
                user_memory=user_memory,
                planner_goal=plan_item.goal,
                planner_reason=plan_item.reason,
            )
            content = await self._invoke_llm_text(prompt, temperature=0.2, max_tokens=900)
            command = self._parse_llm_response(content, device.device_id)
            if not command:
                continue
            command = self._sanitize_command_for_device(command, device)
            if not command:
                continue
            actions.append(
                SkillActionSpec(
                    skill_name=skill_name,
                    device_id=command.device_id,
                    action=command.action,
                    params=command.params,
                    reason=command.reason,
                    expected_state=self._derive_expected_state(command),
                )
            )

        return actions

    async def learn_preferences(self, user_id: str = "default") -> None:
        skill_types = ["humidifier", "air_conditioner", "light", "air_purifier", "speaker"]

        for skill_type in skill_types:
            skill = self._skill_loader.get_skill_for_device(skill_type)
            if not skill or not skill.learn_prompt:
                continue

            try:
                history = await self._memory.get_history(user_id, limit=100)
                relevant = [h for h in history if h.get("device_type") == skill_type]
                if len(relevant) < 5:
                    continue

                current_profile = await self._memory.get_learned(user_id)
                current_skill_profile = await self._memory.get_learned_for_skill(user_id, skill_type)
                prompt = skill.learn_prompt.format(
                    history=json.dumps(relevant[-50:], indent=2),
                    current_profile=current_skill_profile or current_profile or "(no profile yet)",
                )
                content = await self._invoke_llm_text(prompt, temperature=0.2, max_tokens=900)
                await self._memory.update_learned_for_skill(user_id, skill_type, content)
                logger.info("Updated learned profile for %s/%s", user_id, skill_type)
            except Exception:
                logger.exception("Learning failed for skill %s", skill_type)

    def get_environment_state(self) -> dict[str, Any]:
        devices = self._get_environment_devices(None)
        return self._summarize_environment_state(
            devices=devices,
            current_device_id=None,
            current_device_type=None,
        )

    def _build_cycle_graph(self) -> Any:
        graph = StateGraph(BrainCycleState)
        graph.add_node("planner", self._graph_planner)
        graph.add_node("executor", self._graph_executor)
        graph.set_entry_point("planner")
        graph.add_edge("planner", "executor")
        graph.add_edge("executor", END)
        logger.info("Brain cycle graph ready (langgraph)")
        return graph.compile()

    def _build_chat_graph(self) -> Any:
        graph = StateGraph(ChatState)
        graph.add_node("planner", self._graph_chat_planner)
        graph.add_node("executor", self._graph_chat_executor)
        graph.set_entry_point("planner")
        graph.add_edge("planner", "executor")
        graph.add_edge("executor", END)
        logger.info("Brain chat graph ready (langgraph)")
        return graph.compile()

    async def _graph_planner(self, state: dict[str, Any]) -> dict[str, Any]:
        prompt = self._build_planner_prompt(
            devices=state.get("devices", []),
            environment_state=state.get("environment_state", {}),
            user_memory=state.get("user_memory", {}),
            lightweight_skills=state.get("lightweight_skills", []),
        )
        content = await self._invoke_llm_text(prompt, temperature=0.1, max_tokens=900)
        plan_items = self._parse_planner_response(content, state.get("lightweight_skills", []))
        return {
            "planner_prompt": prompt,
            "planner_output": content,
            "plan_items": plan_items,
        }

    async def _graph_executor(self, state: dict[str, Any]) -> dict[str, Any]:
        plan_items: list[SkillPlanItem] = state.get("plan_items", [])
        if not plan_items:
            return {"execution_results": []}

        context = {
            "brain": self,
            "memory": self._memory,
            "user_memory": state.get("user_memory", {}),
            "environment_state": state.get("environment_state", {}),
            "discovery": self._build_discovery_proxy(),
        }

        execution_results: list[SkillExecutionResult] = []
        for plan_item in sorted(plan_items, key=lambda item: item.priority):
            execution_results.append(await self._execute_skill_plan_item(plan_item, context))

        return {"execution_results": execution_results}

    async def _graph_chat_planner(self, state: dict[str, Any]) -> dict[str, Any]:
        app_state = state["app_state"]
        discovery = app_state["discovery"]
        user_memory = await self._memory.get_full_context()
        environment_state = self.get_environment_state()
        skills = self._skill_loader.list_system_skill_summaries()
        prompt = self._build_chat_planner_prompt(
            message=state["message"],
            devices=discovery.get_all_devices(),
            environment_state=environment_state,
            user_memory=user_memory,
            skill_summaries=skills,
        )
        content = await self._invoke_llm_text(prompt, temperature=0.1, max_tokens=900)
        plan = self._parse_chat_plan(content, skills)
        return {
            "planner_prompt": prompt,
            "planner_output": content,
            "plan": plan,
        }

    async def _graph_chat_executor(self, state: dict[str, Any]) -> dict[str, Any]:
        plan: ChatPlan = state.get("plan", ChatPlan())
        app_state = state["app_state"]

        result: dict[str, Any] = {"reply": plan.reply or "我暂时没有需要执行的操作。"}
        if not plan.should_execute:
            return {"result": result}

        if plan.system_action != "none":
            if plan.system_action == "create_custom_skill":
                plan.params.setdefault("request", state.get("message", ""))
            system_result = await self._execute_system_chat_action(plan, app_state)
            if plan.reply and "reply" not in system_result:
                system_result["reply"] = plan.reply
            return {"result": system_result}

        if not plan.skill_plan_items:
            return {"result": result}

        context = {
            "brain": self,
            "memory": self._memory,
            "user_memory": await self._memory.get_full_context(),
            "environment_state": self.get_environment_state(),
            "discovery": app_state["discovery"],
            "settings": app_state["settings"],
        }
        execution_results: list[SkillExecutionResult] = []
        for plan_item in sorted(plan.skill_plan_items, key=lambda item: item.priority):
            execution_results.append(await self._execute_skill_plan_item(plan_item, context))

        result["execution_results"] = [item.model_dump() for item in execution_results]
        result["executed"] = True
        failure_message = self._summarize_chat_execution_failure(execution_results)
        if failure_message:
            result["reply"] = failure_message
            result["executed"] = False
        return {"result": result}

    async def _execute_skill_plan_item(
        self,
        plan_item: SkillPlanItem,
        context: dict[str, Any],
    ) -> SkillExecutionResult:
        skill = self._skill_loader.get_skill(plan_item.skill_name)
        if not skill:
            return SkillExecutionResult(plan_item=plan_item)

        actions_module = self._skill_loader.load_actions(skill)
        handler = getattr(actions_module, "execute", None) if actions_module else None
        if not handler:
            return SkillExecutionResult(plan_item=plan_item)

        skill_context = dict(context)
        skill_context["_loaded_skill"] = skill
        raw_actions = await handler(context=skill_context, plan_item=plan_item)
        actions = self._normalize_action_specs(raw_actions)

        result = SkillExecutionResult(plan_item=plan_item, actions=actions)
        for action_spec in actions:
            verification = await self._execute_action_with_retry(action_spec, context["discovery"])
            result.verifications.append(verification)
            await self._record_execution_history(plan_item, action_spec, verification)
        return result

    async def _execute_action_with_retry(
        self,
        action_spec: SkillActionSpec,
        discovery: Any,
    ) -> ActionVerificationResult:
        attempts = 0
        last_message = ""
        last_observed: dict[str, Any] = {}

        while attempts < 3:
            attempts += 1
            result = await discovery.execute_command(
                action_spec.device_id,
                action_spec.action,
                action_spec.params,
            )
            last_message = result.message
            if not getattr(result, "success", False):
                continue
            verification = await self._verify_action(action_spec, discovery, attempts)
            last_observed = verification.observed_state
            if verification.verified:
                verification.message = result.message
                return verification

        return ActionVerificationResult(
            device_id=action_spec.device_id,
            action=action_spec.action,
            verified=False,
            attempts=attempts,
            status="verification_failed",
            expected_state=action_spec.expected_state,
            observed_state=last_observed,
            message=last_message or "state did not converge after retries",
        )

    async def _verify_action(
        self,
        action_spec: SkillActionSpec,
        discovery: Any,
        attempts: int,
    ) -> ActionVerificationResult:
        await discovery.refresh_device_states([action_spec.device_id])
        device = discovery.get_device(action_spec.device_id)
        if not device:
            return ActionVerificationResult(
                device_id=action_spec.device_id,
                action=action_spec.action,
                verified=False,
                attempts=attempts,
                status="device_missing_after_refresh",
                expected_state=action_spec.expected_state,
                message="device missing after refresh",
            )

        if not action_spec.expected_state:
            return ActionVerificationResult(
                device_id=action_spec.device_id,
                action=action_spec.action,
                verified=True,
                attempts=attempts,
                status="unverifiable_but_executed",
                expected_state={},
                observed_state=self._snapshot_device_sensors(device),
            )

        observed = self._observe_expected_state(device, action_spec.expected_state)
        verified = observed == action_spec.expected_state
        return ActionVerificationResult(
            device_id=action_spec.device_id,
            action=action_spec.action,
            verified=verified,
            attempts=attempts,
            status="verified" if verified else "mismatch",
            expected_state=action_spec.expected_state,
            observed_state=observed,
        )

    async def _record_execution_history(
        self,
        plan_item: SkillPlanItem,
        action_spec: SkillActionSpec,
        verification: ActionVerificationResult,
    ) -> None:
        await self._memory.append_history(
            "default",
            {
                "skill_name": plan_item.skill_name,
                "plan_goal": plan_item.goal,
                "device_id": action_spec.device_id,
                "device_type": plan_item.device_type,
                "action": action_spec.action,
                "params": action_spec.params,
                "reason": action_spec.reason,
                "attempt": verification.attempts,
                "verification_passed": verification.verified,
                "final_status": verification.status,
                "expected_state": verification.expected_state,
                "observed_state": verification.observed_state,
            },
        )

    @staticmethod
    def _summarize_chat_execution_failure(execution_results: list[SkillExecutionResult]) -> str:
        if not execution_results:
            return "我理解了你的请求，但这次没有生成可执行动作。"

        if all(not item.actions for item in execution_results):
            return "我理解了你的请求，但当前没有生成可执行动作。"

        for item in execution_results:
            for verification in item.verifications:
                if not verification.verified:
                    detail = verification.message or verification.status or "执行失败"
                    return f"我尝试执行了，但没有成功：{detail}"

        return ""

    def _build_discovery_proxy(self) -> Any:
        provider = self._environment_provider
        if provider and hasattr(provider, "__self__") and provider.__self__ is not None:
            return provider.__self__
        raise RuntimeError("Brain environment provider must be bound to discovery")

    def _build_planner_prompt(
        self,
        *,
        devices: list[Device],
        environment_state: dict[str, Any],
        user_memory: dict[str, Any],
        lightweight_skills: list[SkillSummary],
    ) -> str:
        device_summaries = [
            {
                "device_id": device.device_id,
                "name": device.name,
                "type": device.type,
                "room": device.room,
                "online": device.online,
                "sensors": {
                    sensor.name: {"value": sensor.value, "unit": sensor.unit}
                    for sensor in device.sensors
                    if sensor.value is not None
                },
            }
            for device in devices
        ]
        skill_summaries = [
            {"name": skill.name, "description": skill.description}
            for skill in lightweight_skills
        ]
        planner_hints = self._load_planner_hints()
        return (
            "You are Anima's scheduler-driven planner.\n"
            "Inspect the current device state, environment, user memory, and available skills.\n"
            "Select zero or more skills that should run in this cycle.\n\n"
            "Available skill summaries:\n"
            f"{json.dumps(skill_summaries, ensure_ascii=False, indent=2)}\n\n"
            "Planner hints:\n"
            f"{planner_hints}\n\n"
            "Current devices:\n"
            f"{json.dumps(device_summaries, ensure_ascii=False, indent=2)}\n\n"
            "Environment snapshot:\n"
            f"{json.dumps(environment_state, ensure_ascii=False, indent=2)}\n\n"
            "User memory:\n"
            f"{json.dumps(user_memory, ensure_ascii=False, indent=2)}\n\n"
            "Return JSON only. Use this schema:\n"
            "[\n"
            '  {"skill_name": "humidifier", "goal": "raise humidity", "reason": "why now", "priority": 10}\n'
            "]\n"
            "Rules:\n"
            "- Only choose skill_name values from the available skill summaries.\n"
            "- Prefer no output over redundant actions.\n"
            "- Keep the list short and conservative.\n"
            "- Priority uses lower numbers first.\n"
        )

    def _build_chat_planner_prompt(
        self,
        *,
        message: str,
        devices: list[Device],
        environment_state: dict[str, Any],
        user_memory: dict[str, Any],
        skill_summaries: list[SkillSummary],
    ) -> str:
        device_summaries = [
            {
                "device_id": device.device_id,
                "name": device.name,
                "type": device.type,
                "online": device.online,
            }
            for device in devices
        ]
        skills = [
            {"name": skill.name, "description": skill.description, "device_type": skill.device_type}
            for skill in skill_summaries
        ]
        return (
            "You are Anima's unified chat planner running inside LangGraph.\n"
            "Decide whether to reply only, execute a system skill, or execute one or more device skills.\n\n"
            f"User message:\n{message}\n\n"
            "Available system skills:\n"
            f"{json.dumps(skills, ensure_ascii=False, indent=2)}\n\n"
            "Current devices:\n"
            f"{json.dumps(device_summaries, ensure_ascii=False, indent=2)}\n\n"
            "Environment snapshot:\n"
            f"{json.dumps(environment_state, ensure_ascii=False, indent=2)}\n\n"
            "User memory:\n"
            f"{json.dumps(user_memory, ensure_ascii=False, indent=2)}\n\n"
            "Output JSON only with this schema:\n"
            "{\n"
            '  "reply": "string",\n'
            '  "should_execute": true,\n'
            '  "system_action": "none | scan_local_devices | start_xiaomi_qr_scan | create_custom_skill",\n'
            '  "system_skill": "device_discovery | skill_creator |",\n'
            '  "params": {},\n'
            '  "skill_plan_items": [\n'
            '    {"skill_name": "humidifier", "goal": "raise humidity", "reason": "why", "priority": 10}\n'
            "  ]\n"
            "}\n"
            "Rules:\n"
            "- If this is a system operation such as Xiaomi QR onboarding, LAN scan, or creating a custom skill, use system_action.\n"
            "- If this is device control or home intelligence, use skill_plan_items.\n"
            "- If the user asks to play music or audio on a speaker, use the `speaker` skill.\n"
            "- If the user asks to play something without giving a specific path or URL, set the speaker goal to random local playback.\n"
            "- If the user asks to stop speaker playback, use the `speaker` skill with a stop-oriented goal.\n"
            "- For general Q&A, set should_execute to false.\n"
            "- Do not use regex or heuristics; infer intent from the message and context.\n"
        )

    def _load_planner_hints(self) -> str:
        try:
            return PLANNER_HINTS_PATH.read_text(encoding="utf-8").strip()
        except OSError:
            logger.warning("Planner hints file not found: %s", PLANNER_HINTS_PATH)
            return (
                "- Call `humidifier` when current humidity is below 50% and the environment is not already comfortable.\n"
                "- Call `air_conditioner` when temperature is clearly outside the comfortable range and the change is meaningful.\n"
                "- Call `light` when brightness or color temperature is mismatched with time of day or user preference.\n"
                "- Prefer no action when the current state is already acceptable."
            )

    def _build_prompt_context(
        self,
        skill: LoadedSkill,
        device: Device,
        user_memory: dict[str, Any],
        *,
        planner_goal: str = "",
        planner_reason: str = "",
    ) -> str:
        sensor_summary = {
            sensor.name: {"value": sensor.value, "unit": sensor.unit}
            for sensor in device.sensors
            if sensor.value is not None
        }
        caps_summary = [{"name": cap.name, **cap.params} for cap in device.capabilities]
        learned_profiles = user_memory.get("learned_profiles", {})
        learned_profile = learned_profiles.get(device.type) or user_memory.get("learned", "")
        environment_state = self._build_environment_state(device)
        base_prompt = skill.decide_prompt.format(
            current_data=json.dumps(sensor_summary, indent=2),
            capabilities=json.dumps(caps_summary, indent=2),
            environment_state=json.dumps(environment_state, ensure_ascii=False, indent=2),
            user_preferences=user_memory.get("preferences", ""),
            recent_history=json.dumps(user_memory.get("history", [])[-5:], indent=2),
            learned_profile=learned_profile or "(none)",
            knowledge=skill.knowledge,
        )
        if not planner_goal and not planner_reason:
            return base_prompt
        return (
            f"{base_prompt}\n\n"
            "## Planner Intent\n"
            f"Goal: {planner_goal or '(none)'}\n"
            f"Reason: {planner_reason or '(none)'}\n"
        )

    def _parse_planner_response(
        self,
        content: str,
        lightweight_skills: list[SkillSummary],
    ) -> list[SkillPlanItem]:
        json_str = self._extract_json(content)
        if not json_str:
            return []

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            return []

        if not isinstance(data, list):
            return []

        skill_map = {skill.name: skill for skill in lightweight_skills}
        items: list[SkillPlanItem] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            skill_name = str(item.get("skill_name", "")).strip()
            summary = skill_map.get(skill_name)
            if not summary:
                continue
            items.append(
                SkillPlanItem(
                    skill_name=skill_name,
                    device_type=summary.device_type,
                    goal=str(item.get("goal", "")),
                    reason=str(item.get("reason", "")),
                    priority=self._coerce_priority(item.get("priority")),
                )
            )
        return items

    def _normalize_action_specs(self, raw_actions: Any) -> list[SkillActionSpec]:
        if raw_actions is None:
            return []
        if isinstance(raw_actions, list):
            actions = raw_actions
        else:
            actions = [raw_actions]

        normalized: list[SkillActionSpec] = []
        for action in actions:
            if isinstance(action, SkillActionSpec):
                normalized.append(action)
                continue
            if not isinstance(action, dict):
                continue
            skill_name = str(action.get("skill_name", "")).strip()
            device_id = str(action.get("device_id", "")).strip()
            command_action = str(action.get("action", "")).strip()
            if not skill_name or not device_id or not command_action:
                continue
            normalized.append(
                SkillActionSpec(
                    skill_name=skill_name,
                    device_id=device_id,
                    action=command_action,
                    params=action.get("params", {}) if isinstance(action.get("params"), dict) else {},
                    reason=str(action.get("reason", "")),
                    expected_state=action.get("expected_state", {}) if isinstance(action.get("expected_state"), dict) else {},
                )
            )
        return normalized

    async def _execute_system_chat_action(self, plan: ChatPlan, app_state: dict[str, Any]) -> dict[str, Any]:
        skill = self._skill_loader.get_skill(plan.system_skill)
        if not skill:
            return {"reply": plan.reply or f"{plan.system_skill} skill 尚未加载。"}

        actions_module = self._skill_loader.load_actions(skill)
        handler = getattr(actions_module, plan.system_action, None) if actions_module else None
        if not handler:
            return {"reply": plan.reply or f"{plan.system_skill} skill 不支持动作: {plan.system_action}"}

        params = dict(plan.params)
        result = await handler(context=app_state, params=params, reply=plan.reply)
        if "reply" not in result and plan.reply:
            result["reply"] = plan.reply
        result["action"] = plan.system_action
        return result

    def _parse_chat_plan(self, content: str, skill_summaries: list[SkillSummary]) -> ChatPlan:
        json_str = self._extract_json(content)
        if not json_str:
            return ChatPlan(reply="我暂时无法判断要执行什么。", should_execute=False)

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            return ChatPlan(reply="我暂时无法判断要执行什么。", should_execute=False)

        if not isinstance(data, dict):
            return ChatPlan(reply="我暂时无法判断要执行什么。", should_execute=False)

        skill_map = {skill.name: skill for skill in skill_summaries}
        plan_items: list[SkillPlanItem] = []
        raw_items = data.get("skill_plan_items", [])
        if isinstance(raw_items, list):
            for item in raw_items:
                if not isinstance(item, dict):
                    continue
                skill_name = str(item.get("skill_name", "")).strip()
                summary = skill_map.get(skill_name)
                if not summary or not summary.device_type:
                    continue
                plan_items.append(
                    SkillPlanItem(
                        skill_name=skill_name,
                        device_type=summary.device_type,
                        goal=str(item.get("goal", "")),
                        reason=str(item.get("reason", "")),
                        priority=self._coerce_priority(item.get("priority")),
                    )
                )

        return ChatPlan(
            reply=str(data.get("reply", "")),
            should_execute=bool(data.get("should_execute")),
            system_action=str(data.get("system_action", "none")),
            system_skill=str(data.get("system_skill", "")),
            params=data.get("params", {}) if isinstance(data.get("params"), dict) else {},
            skill_plan_items=plan_items,
        )

    def _build_environment_state(self, current_device: Device) -> dict[str, Any]:
        devices = self._get_environment_devices(current_device)
        return self._summarize_environment_state(
            devices=devices,
            current_device_id=current_device.device_id,
            current_device_type=current_device.type,
        )

    def _summarize_environment_state(
        self,
        *,
        devices: list[Device],
        current_device_id: str | None,
        current_device_type: str | None,
    ) -> dict[str, Any]:
        device_snapshots: list[dict[str, Any]] = []
        signals: dict[str, list[dict[str, Any]]] = {}

        for device in devices:
            sensors = {
                sensor.name: {"value": sensor.value, "unit": sensor.unit}
                for sensor in device.sensors
                if sensor.value is not None
            }
            if not sensors:
                continue

            device_snapshots.append(
                {
                    "device_id": device.device_id,
                    "name": device.name,
                    "type": device.type,
                    "room": device.room,
                    "online": device.online,
                    "sensors": sensors,
                }
            )

            for sensor_name, payload in sensors.items():
                signals.setdefault(sensor_name, []).append(
                    {
                        "device_id": device.device_id,
                        "device_type": device.type,
                        "room": device.room,
                        "value": payload["value"],
                        "unit": payload["unit"],
                    }
                )

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "current_device_id": current_device_id,
            "current_device_type": current_device_type,
            "devices": device_snapshots,
            "signals": signals,
        }

    def _get_environment_devices(self, current_device: Device | None) -> list[Device]:
        devices: list[Device] = []
        provider = self._environment_provider
        if callable(provider):
            try:
                provided = provider()
                if isinstance(provided, list):
                    devices = [device for device in provided if isinstance(device, Device)]
            except Exception:
                logger.exception("Failed to read environment devices")

        if current_device and not any(device.device_id == current_device.device_id for device in devices):
            devices.append(current_device)

        return devices

    async def _invoke_llm_text(self, prompt: str, *, temperature: float, max_tokens: int) -> str:
        extra_body: dict[str, Any] = {}
        if self._llm_disable_thinking:
            extra_body["thinking"] = {"type": "disabled"}

        response = await self._llm.chat.completions.create(
            model=self._llm_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
            extra_body=extra_body or None,
        )
        if not response.choices:
            return ""

        content = response.choices[0].message.content
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            chunks: list[str] = []
            for item in content:
                text = getattr(item, "text", None)
                if isinstance(text, str):
                    chunks.append(text)
                elif isinstance(item, dict) and isinstance(item.get("text"), str):
                    chunks.append(item["text"])
            return "\n".join(chunks)
        return ""

    def _parse_llm_response(self, content: str, device_id: str) -> DeviceCommand | None:
        json_str = self._extract_json(content)
        if not json_str:
            logger.warning("Could not extract JSON from LLM response")
            return None

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            logger.warning("Invalid JSON in LLM response: %s", json_str[:200])
            return None

        action = data.get("action", "none")
        if not isinstance(action, str):
            logger.warning("Invalid action field in LLM response: %r", action)
            return None

        action = action.strip()
        if action == "none":
            return None

        params = data.get("params", {})
        if not isinstance(params, dict):
            params = {}

        return DeviceCommand(
            device_id=device_id,
            action=action,
            params=params,
            source="brain",
            reason=str(data.get("reason", "")),
            confidence=self._parse_confidence(data.get("confidence")),
            expected_outcome=str(data.get("expected_outcome", "")),
            should_wait_seconds=self._parse_wait_seconds(data.get("should_wait_seconds")),
        )

    def _sanitize_command_for_device(self, command: DeviceCommand, device: Device) -> DeviceCommand | None:
        capability = self._find_matching_capability(device, command.action)
        if capability is None:
            if device.capabilities:
                logger.warning("Unsupported action for %s: %s", device.device_id, command.action)
                return None
            return command

        sanitized = command.model_copy(deep=True)
        sanitized.params = self._sanitize_params_with_capability(sanitized.params, capability)
        return sanitized

    @staticmethod
    def _find_matching_capability(device: Device, action: str) -> Any | None:
        aliases = {
            action,
            {"turn_on": "on", "turn_off": "off", "on": "turn_on", "off": "turn_off"}.get(action, action),
        }
        for capability in device.capabilities:
            if capability.name in aliases:
                return capability
        return None

    def _sanitize_params_with_capability(self, params: dict[str, Any], capability: Any) -> dict[str, Any]:
        sanitized = dict(params)
        inputs = capability.params.get("inputs", []) if isinstance(capability.params, dict) else []

        if inputs:
            for input_meta in inputs:
                name = input_meta.get("name")
                if not isinstance(name, str):
                    continue
                if name not in sanitized and "default" in input_meta:
                    sanitized[name] = input_meta["default"]
                if name in sanitized:
                    sanitized[name] = self._sanitize_value(sanitized[name], input_meta)
        elif "value" in sanitized:
            sanitized["value"] = self._sanitize_value(sanitized["value"], capability.params)

        return sanitized

    def _sanitize_value(self, value: Any, meta: dict[str, Any]) -> Any:
        value_type = meta.get("type")
        if value_type == "number" or any(key in meta for key in ("min", "max", "step")):
            return self._sanitize_numeric_value(value, meta)
        if value_type == "boolean":
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                return value.lower() in {"1", "true", "on", "yes"}
            return bool(value)
        if value_type == "enum":
            options = meta.get("options", [])
            if value in options:
                return value
            stringified = str(value)
            for option in options:
                if str(option).lower() == stringified.lower():
                    return option
            if "default" in meta:
                return meta["default"]
            return options[0] if options else value
        return value

    @staticmethod
    def _sanitize_numeric_value(value: Any, meta: dict[str, Any]) -> int | float | Any:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            default = meta.get("default")
            if default is not None:
                return default
            return value

        minimum = meta.get("min")
        maximum = meta.get("max")
        step = meta.get("step")

        if isinstance(minimum, (int, float)):
            numeric = max(numeric, float(minimum))
        if isinstance(maximum, (int, float)):
            numeric = min(numeric, float(maximum))
        if isinstance(step, (int, float)) and step not in (0, 0.0):
            base = float(minimum) if isinstance(minimum, (int, float)) else 0.0
            numeric = base + round((numeric - base) / float(step)) * float(step)
            if isinstance(minimum, (int, float)):
                numeric = max(numeric, float(minimum))
            if isinstance(maximum, (int, float)):
                numeric = min(numeric, float(maximum))

        if all(isinstance(meta.get(key), int) for key in ("min", "max", "step") if key in meta):
            return int(round(numeric))
        if math.isclose(numeric, round(numeric)):
            return int(round(numeric))
        return numeric

    def _derive_expected_state(self, command: DeviceCommand) -> dict[str, Any]:
        action = command.action
        if action in {"turn_on", "on"}:
            return {"power": True}
        if action in {"turn_off", "off"}:
            return {"power": False}
        if action == "set_brightness" and "value" in command.params:
            return {"brightness": command.params["value"]}
        if action == "set_color_temp" and "kelvin" in command.params:
            return {"color_temp": command.params["kelvin"]}
        return {}

    def _observe_expected_state(self, device: Device, expected_state: dict[str, Any]) -> dict[str, Any]:
        observed: dict[str, Any] = {}
        for sensor_name in expected_state:
            sensor = device.get_sensor(sensor_name)
            observed[sensor_name] = sensor.value if sensor else None
        return observed

    def _snapshot_device_sensors(self, device: Device) -> dict[str, Any]:
        return {
            sensor.name: sensor.value
            for sensor in device.sensors
            if sensor.value is not None
        }

    @staticmethod
    def _coerce_priority(value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 100

    @staticmethod
    def _parse_confidence(value: Any) -> float | None:
        if value is None:
            return None
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            return None
        return max(0.0, min(1.0, confidence))

    @staticmethod
    def _parse_wait_seconds(value: Any) -> int | None:
        if value is None:
            return None
        try:
            wait_seconds = int(value)
        except (TypeError, ValueError):
            return None
        return max(0, wait_seconds)

    @staticmethod
    def _extract_json(text: str) -> str | None:
        stripped = text.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            return stripped

        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if match:
            return match.group(1).strip()

        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return match.group(0)

        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            return match.group(0)

        return None
