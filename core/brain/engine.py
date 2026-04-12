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
from core.memory.extractor import MemoryExtractionService
from core.memory.learning import PreferenceLearningService
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
    TaskPlanItem,
)
from core.runtime.config import settings

logger = logging.getLogger(__name__)
PLANNER_HINTS_PATH = Path(__file__).with_name("prompts") / "planner_hints.md"
SYSTEM_ACTION_ALIASES = {
    "generate_new_skill_package": "create_custom_skill",
}
PENDING_SKILL_CANCEL_TOKENS = ("取消", "算了", "不用了", "停止", "cancel", "never mind")
AIR_PURIFIER_AQI_THRESHOLD = 5.0
AC_HIGH_TEMP_THRESHOLD = 28.0
AC_LOW_TEMP_THRESHOLD = 16.0
HUMIDIFIER_LOW_HUMIDITY_THRESHOLD = 35.0
HUMIDIFIER_HIGH_HUMIDITY_THRESHOLD = 70.0
SKILL_CREATION_INTENT_PATTERNS = (
    r"(新增|创建|生成|做|写|开发|定制|自定义).{0,12}(技能|skill)",
    r"(技能|skill).{0,12}(新增|创建|生成|定制|自定义|开发)",
    r"\b(create|add|generate|build|make|scaffold|customi[sz]e)\b.{0,20}\b(skill|custom skill)\b",
    r"\b(skill|custom skill)\b.{0,20}\b(create|add|generate|build|customi[sz]e)\b",
)
ENVIRONMENT_QUERY_HINTS = (
    "现在",
    "当前",
    "屋内",
    "室内",
    "房间",
    "状态",
    "温度",
    "湿度",
    "空气质量",
    "空气",
    "pm2.5",
    "pm10",
    "co2",
    "二氧化碳",
    "环境",
    "情况",
    "怎么样",
    "如何",
    "多少",
    "查询",
    "看下",
    "看看",
    "what's",
    "what is",
    "status",
    "temperature",
    "humidity",
    "air quality",
    "indoor",
    "room",
)


class BrainCycleState(TypedDict, total=False):
    user_memory: dict[str, Any]
    devices: list[Device]
    environment_state: dict[str, Any]
    lightweight_skills: list[SkillSummary]
    planner_prompt: str
    planner_output: str
    plan_items: list[SkillPlanItem]
    task_plan_items: list[TaskPlanItem]
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
        self._memory_extractor: MemoryExtractionService | None = None
        self._preference_learner: PreferenceLearningService | None = None
        self._llm = AsyncOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url or None,
        )
        self._llm_model = settings.llm_model
        self._llm_disable_thinking = settings.llm_disable_thinking
        self._pending_skill_creation: dict[str, Any] | None = None
        self._air_purifier_startup_bootstrap_pending = True
        self._cycle_graph = self._build_cycle_graph()
        self._chat_graph = self._build_chat_graph()

    def set_environment_provider(self, provider: Callable[[], list[Device]]) -> None:
        self._environment_provider = provider

    def set_memory_extractor(self, extractor: MemoryExtractionService) -> None:
        self._memory_extractor = extractor

    def set_preference_learner(self, learner: PreferenceLearningService) -> None:
        self._preference_learner = learner

    def schedule_preference_learning(self, user_id: str = "default") -> None:
        if self._preference_learner is not None:
            self._preference_learner.schedule(user_id)
            return
        if self._memory_extractor is None:
            return
        self._memory_extractor.schedule(user_id)

    async def run_cycle(self) -> BrainCycleResult:
        user_memory = await self._memory.get_full_context()
        devices = self._get_environment_devices(None)
        environment_state = self.get_environment_state()
        lightweight_skills = self._skill_loader.list_executable_skill_summaries()

        if not devices or not lightweight_skills:
            return BrainCycleResult()

        deterministic_tasks = self._build_deterministic_cycle_tasks(
            devices=devices,
            lightweight_skills=lightweight_skills,
        )
        if deterministic_tasks:
            result = await self._graph_executor(
                {
                    "user_memory": user_memory,
                    "environment_state": environment_state,
                    "task_plan_items": deterministic_tasks,
                }
            )
            return BrainCycleResult(
                plan_items=self._cycle_tasks_to_skill_plan_items(deterministic_tasks, lightweight_skills),
                task_plan_items=deterministic_tasks,
                execution_results=result.get("execution_results", []),
            )

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
            task_plan_items=result.get("task_plan_items", []),
            execution_results=result.get("execution_results", []),
        )

    def _build_deterministic_cycle_tasks(
        self,
        *,
        devices: list[Device],
        lightweight_skills: list[SkillSummary],
    ) -> list[TaskPlanItem]:
        skill_names = {skill.name for skill in lightweight_skills}
        tasks: list[TaskPlanItem] = []

        # ── Air purifier automation ──────────────────────────────────────────
        if "air_purifier" in skill_names:
            purifier_devices = [d for d in devices if d.type == "air_purifier"]
            if purifier_devices:
                device = purifier_devices[0]
                power_sensor = device.get_sensor("power")
                power_value = self._coerce_sensor_bool(power_sensor.value if power_sensor else None)
                aqi_value = self._read_air_purifier_aqi(device)

                if self._air_purifier_startup_bootstrap_pending:
                    self._air_purifier_startup_bootstrap_pending = False
                    if power_value is not True:
                        tasks.append(TaskPlanItem(
                            kind="execute_skill",
                            skill_name="air_purifier",
                            goal="系统启动，已帮主人开启空气净化器，保持室内空气清新",
                            reason="启动自动化：空气净化器开机引导",
                            priority=1,
                        ))
                elif aqi_value is not None:
                    if aqi_value > AIR_PURIFIER_AQI_THRESHOLD and power_value is not True:
                        tasks.append(TaskPlanItem(
                            kind="execute_skill",
                            skill_name="air_purifier",
                            goal=f"室内 AQI 已达 {aqi_value}，空气有点差，已帮主人开启净化器",
                            reason=f"空气质量自动化：AQI {aqi_value} > 阈值 {AIR_PURIFIER_AQI_THRESHOLD}",
                            priority=1,
                        ))
                    elif aqi_value <= AIR_PURIFIER_AQI_THRESHOLD and power_value is True:
                        tasks.append(TaskPlanItem(
                            kind="execute_skill",
                            skill_name="air_purifier",
                            goal=f"室内空气已恢复清新（AQI {aqi_value}），已帮主人关闭净化器",
                            reason=f"空气质量自动化：AQI {aqi_value} ≤ 阈值 {AIR_PURIFIER_AQI_THRESHOLD}",
                            priority=1,
                        ))
            else:
                self._air_purifier_startup_bootstrap_pending = False

        # ── Air conditioner temperature automation ───────────────────────────
        if "air_conditioner" in skill_names:
            ac_devices = [d for d in devices if d.type == "air_conditioner"]
            for ac in ac_devices:
                power_sensor = ac.get_sensor("power")
                power_value = self._coerce_sensor_bool(power_sensor.value if power_sensor else None)
                # Try both "temperature" and "current_temperature" sensor names
                temp_sensor = ac.get_sensor("temperature") or ac.get_sensor("current_temperature")
                temp_value = self._coerce_sensor_number(temp_sensor.value if temp_sensor else None)
                if temp_value is None:
                    continue
                if temp_value >= AC_HIGH_TEMP_THRESHOLD and power_value is not True:
                    tasks.append(TaskPlanItem(
                        kind="execute_skill",
                        skill_name="air_conditioner",
                        goal=f"室内温度已达 {temp_value}°C，有点热了，帮主人开启空调降温到舒适温度（约24°C）",
                        reason=f"温度自动化：当前 {temp_value}°C ≥ 阈值 {AC_HIGH_TEMP_THRESHOLD}°C",
                        priority=2,
                    ))
                elif temp_value <= AC_LOW_TEMP_THRESHOLD and power_value is True:
                    tasks.append(TaskPlanItem(
                        kind="execute_skill",
                        skill_name="air_conditioner",
                        goal=f"室内温度已降至 {temp_value}°C，已帮主人关闭空调",
                        reason=f"温度自动化：当前 {temp_value}°C ≤ 阈值 {AC_LOW_TEMP_THRESHOLD}°C",
                        priority=2,
                    ))

        # ── Humidifier humidity automation ───────────────────────────────────
        if "humidifier" in skill_names:
            humidifier_devices = [d for d in devices if d.type == "humidifier"]
            for hum in humidifier_devices:
                power_sensor = hum.get_sensor("power")
                power_value = self._coerce_sensor_bool(power_sensor.value if power_sensor else None)
                hum_sensor = hum.get_sensor("humidity")
                hum_value = self._coerce_sensor_number(hum_sensor.value if hum_sensor else None)
                if hum_value is None:
                    continue
                if hum_value < HUMIDIFIER_LOW_HUMIDITY_THRESHOLD and power_value is not True:
                    tasks.append(TaskPlanItem(
                        kind="execute_skill",
                        skill_name="humidifier",
                        goal=f"室内湿度只有 {hum_value}%，有点干燥，已帮主人开启加湿器",
                        reason=f"湿度自动化：当前 {hum_value}% < 阈值 {HUMIDIFIER_LOW_HUMIDITY_THRESHOLD}%",
                        priority=2,
                    ))
                elif hum_value > HUMIDIFIER_HIGH_HUMIDITY_THRESHOLD and power_value is True:
                    tasks.append(TaskPlanItem(
                        kind="execute_skill",
                        skill_name="humidifier",
                        goal=f"室内湿度已达 {hum_value}%，湿度够了，已帮主人关闭加湿器",
                        reason=f"湿度自动化：当前 {hum_value}% > 阈值 {HUMIDIFIER_HIGH_HUMIDITY_THRESHOLD}%",
                        priority=2,
                    ))

        return tasks

    @staticmethod
    def _coerce_sensor_bool(value: Any) -> bool | None:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.lower()
            if lowered in {"on", "true", "1"}:
                return True
            if lowered in {"off", "false", "0"}:
                return False
        return None

    @staticmethod
    def _coerce_sensor_number(value: Any) -> float | None:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                return None
        return None

    def _read_air_purifier_aqi(self, device: Device) -> float | None:
        for sensor_name in ("aqi", "pm2_5", "average_aqi"):
            sensor = device.get_sensor(sensor_name)
            if sensor is None:
                continue
            numeric = self._coerce_sensor_number(sensor.value)
            if numeric is not None:
                return numeric
        return None

    async def handle_chat_message(self, message: str, app_state: dict[str, Any]) -> dict[str, Any]:
        text = message.strip()
        if not text:
            return {"reply": "请先输入你的需求。"}

        if not settings.llm_api_key and not app_state["settings"].get("llm_api_key", ""):
            return {"reply": "聊天入口现在统一走模型决策，请先配置可用的 LLM。", "error": "llm_required"}

        result = await self._chat_graph.ainvoke({"message": text, "app_state": app_state})
        return result.get("result", {"reply": "我暂时没有需要执行的操作。"})

    async def handle_chat_message_stream(self, message: str, app_state: dict[str, Any]):
        """Streaming variant: yields SSE chunks via ReAct agentic loop."""
        from core.brain.react_agent import ReActAgent
        text = message.strip()
        if not text:
            yield 'data: {"reply":"请先输入你的需求。","done":true}\n\n'
            return

        if not settings.llm_api_key and not app_state["settings"].get("llm_api_key", ""):
            yield 'data: {"reply":"聊天入口现在统一走模型决策，请先配置可用的 LLM。","error":"llm_required","done":true}\n\n'
            return

        intent = self._classify_intent(text)
        if intent == "chitchat":
            # Fast path: direct streaming, no tool loop
            reply_text = ""
            async for chunk in self._stream_chitchat_reply(text):
                reply_text += chunk
                yield f"data: {json.dumps({'type': 'chunk', 'content': chunk}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'reply', 'content': reply_text, 'done': True}, ensure_ascii=False)}\n\n"
            return

        # ReAct agentic loop for all other intents
        agent = ReActAgent(
            llm=self._llm,
            model=self._llm_model,
            disable_thinking=self._llm_disable_thinking,
            skill_loader=self._skill_loader,
            memory=self._memory,
        )
        app_state_with_brain = dict(app_state)
        app_state_with_brain["brain"] = self

        async for event in agent.run(text, app_state_with_brain):
            yield event.to_sse()

    async def _stream_chitchat_reply(self, message: str):
        """Stream a direct chitchat reply without full planner overhead."""
        extra_body: dict[str, Any] = {}
        if self._llm_disable_thinking:
            extra_body["thinking"] = {"type": "disabled"}
        prompt = (
            "你是 Anima，一个智能家居助手。用简短友好的中文回复用户。\n"
            f"用户说：{message}"
        )
        stream = await self._llm.chat.completions.create(
            model=self._llm_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=200,
            stream=True,
            extra_body=extra_body or None,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                yield delta

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
        if self._preference_learner is not None:
            await self._preference_learner.run_now(user_id)
            return

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
        task_plan_items, plan_items = self._parse_cycle_plan(content, state.get("lightweight_skills", []))
        return {
            "planner_prompt": prompt,
            "planner_output": content,
            "plan_items": plan_items,
            "task_plan_items": task_plan_items,
        }

    async def _graph_executor(self, state: dict[str, Any]) -> dict[str, Any]:
        task_plan_items: list[TaskPlanItem] = state.get("task_plan_items", [])
        if not task_plan_items:
            return {"execution_results": []}

        await self._record_task_plan_history(task_plan_items, source="scheduler")

        context = {
            "brain": self,
            "memory": self._memory,
            "user_memory": state.get("user_memory", {}),
            "environment_state": state.get("environment_state", {}),
            "discovery": self._build_discovery_proxy(),
        }

        execution_results: list[SkillExecutionResult] = []
        for task in sorted(task_plan_items, key=lambda item: item.priority):
            execution_result = await self._execute_cycle_task(task, context)
            if execution_result is not None:
                execution_results.append(execution_result)

        return {"execution_results": execution_results}

    async def _graph_chat_planner(self, state: dict[str, Any]) -> dict[str, Any]:
        app_state = state["app_state"]
        discovery = app_state["discovery"]
        user_memory = await self._memory.get_planner_context()
        environment_state = self.get_environment_state()
        pending = self._route_pending_skill_creation(state["message"])
        if pending is not None:
            return {
                "planner_prompt": pending["prompt"],
                "planner_output": pending["output"],
                "plan": pending["plan"],
            }

        routed = await self._route_system_chat_message(
            message=state["message"],
            app_state=app_state,
        )
        if routed is not None:
            return {
                "planner_prompt": routed["prompt"],
                "planner_output": routed["output"],
                "plan": routed["plan"],
            }

        intent = self._classify_intent(state["message"])
        skills = self._skill_loader.list_chat_skill_summaries()
        prompt = self._build_chat_planner_prompt(
            message=state["message"],
            devices=discovery.get_all_devices(),
            environment_state=environment_state,
            user_memory=user_memory,
            skill_summaries=skills,
            intent=intent,
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
        task_plan_items = self._normalize_chat_tasks(plan)

        result: dict[str, Any] = {"reply": plan.reply or "我暂时没有需要执行的操作。"}
        if task_plan_items:
            result["task_plan_items"] = [item.model_dump() for item in task_plan_items]
        if not plan.should_execute:
            return {"result": result}

        if not task_plan_items:
            return {"result": result}

        await self._record_task_plan_history(
            task_plan_items,
            source="chat",
            message=state.get("message", ""),
        )

        context = {
            "brain": self,
            "memory": self._memory,
            "user_memory": await self._memory.get_full_context(),
            "environment_state": self.get_environment_state(),
            "discovery": app_state["discovery"],
            "settings": app_state["settings"],
        }
        execution_results: list[SkillExecutionResult] = []
        task_results: list[dict[str, Any]] = []
        result["executed"] = False

        for task in sorted(task_plan_items, key=lambda item: item.priority):
            task_result = await self._execute_chat_task(task, context, state.get("message", ""))
            task_results.append(task_result)

            reply = str(task_result.get("reply", "")).strip()
            if reply:
                result["reply"] = reply

            for key, value in task_result.items():
                if key in {"execution_result", "stop", "kind", "reason"}:
                    continue
                result[key] = value

            if task_result.get("execution_result") is not None:
                execution_result = task_result["execution_result"]
                if isinstance(execution_result, SkillExecutionResult):
                    execution_results.append(execution_result)
                    result["executed"] = True

            if task_result.get("stop"):
                break

        if task_results:
            result["task_results"] = task_results
        if execution_results:
            result["execution_results"] = [item.model_dump() for item in execution_results]
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
        skill_context = dict(context)
        skill_context["_loaded_skill"] = skill
        if handler:
            raw_actions = await handler(context=skill_context, plan_item=plan_item)
        elif skill.decide_prompt:
            # Older custom skills may only provide DeviceCommand helpers and rely on
            # the shared Brain decision path instead of defining execute().
            raw_actions = await self.execute_device_skill(plan_item.skill_name, skill_context, plan_item)
        else:
            return SkillExecutionResult(plan_item=plan_item)
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
        self.schedule_preference_learning("default")

    async def _record_task_plan_history(
        self,
        task_plan_items: list[TaskPlanItem],
        *,
        source: str,
        message: str = "",
    ) -> None:
        for task in sorted(task_plan_items, key=lambda item: item.priority):
            entry = {
                "record_type": "planner_task",
                "source": source,
                "task_kind": task.kind,
                "action": f"plan.{task.kind}",
                "reason": task.reason or task.goal or task.question,
                "priority": task.priority,
                "skill_name": task.skill_name,
                "system_skill": task.system_skill,
                "system_action": task.system_action,
                "goal": task.goal,
                "question": task.question,
                "params": task.params,
            }
            if message:
                entry["message"] = message
            await self._memory.append_history("default", entry)
        if task_plan_items:
            self.schedule_preference_learning("default")

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
        _j = lambda o: json.dumps(o, ensure_ascii=False, separators=(",", ":"))
        planner_hints = self._load_planner_hints()
        return (
            "You are Anima's scheduler-driven planner.\n"
            "Inspect the current device state, environment, user memory, and available skills.\n"
            "Break the cycle into small tasks. Tasks may refresh environment state, execute a device skill, or reply with no-op reasoning.\n\n"
            f"Available skill summaries:\n{_j(skill_summaries)}\n\n"
            f"Planner hints:\n{planner_hints}\n\n"
            f"Current devices:\n{_j(device_summaries)}\n\n"
            f"Environment signals:\n{_j(environment_state.get('signals', {}))}\n\n"
            f"User memory:\n{_j(user_memory)}\n\n"
            "Return JSON only. Preferred schema:\n"
            "{\n"
            '  "task_plan_items": [\n'
            '    {"kind": "refresh_environment", "reason": "need latest sensor state", "priority": 5},\n'
            '    {"kind": "execute_skill", "skill_name": "humidifier", "goal": "raise humidity", "reason": "why now", "priority": 10},\n'
            '    {"kind": "reply", "reply": "No action needed because the environment is already comfortable.", "priority": 20}\n'
            "  ]\n"
            "}\n"
            "Legacy schema is still accepted:\n"
            "[\n"
            '  {"skill_name": "humidifier", "goal": "raise humidity", "reason": "why now", "priority": 10}\n'
            "]\n"
            "Rules:\n"
            "- Allowed task kinds for scheduler are refresh_environment, execute_skill, and reply.\n"
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
        intent: str = "general",
    ) -> str:
        _j = lambda o: json.dumps(o, ensure_ascii=False, separators=(",", ":"))
        skills = [{"name": s.name, "description": s.description} for s in skill_summaries]

        parts = [
            "You are Anima's unified chat planner running inside LangGraph.\n"
            "Break the user's request into small actionable tasks.\n"
            "A task may ask the user for clarification, refresh the environment, execute a system action, execute one or more device skills, or reply only.\n\n"
            f"User message:\n{message}\n\n"
            f"Available skills:\n{_j(skills)}\n\n",
        ]

        if intent in ("device_control", "env_query", "general"):
            device_summaries = [
                {"id": d.device_id, "name": d.name, "type": d.type, "online": d.online}
                for d in devices
            ]
            # Compact environment: only signal values
            env_signals = environment_state.get("signals", {})
            parts.append(f"Devices:\n{_j(device_summaries)}\n\nEnvironment signals:\n{_j(env_signals)}\n\n")

        prefs = user_memory.get("preferences", "")
        history = user_memory.get("history", [])
        if isinstance(history, list):
            history = history[-3:]
        parts.append(f"User preferences:\n{prefs}\n\nRecent history:\n{_j(history)}\n\n")

        return "".join(parts) + (
            "Output JSON only with this schema:\n"
            "{\n"
            '  "reply": "string",\n'
            '  "should_execute": true,\n'
            '  "task_plan_items": [\n'
            '    {"kind": "ask_user", "question": "你想调节哪个房间？", "reason": "scope ambiguous", "priority": 5},\n'
            '    {"kind": "refresh_environment", "reason": "need latest state before acting", "priority": 8},\n'
            '    {"kind": "system_action", "system_skill": "device_discovery", "system_action": "scan_local_devices", "params": {}, "reason": "user asked to scan", "priority": 10},\n'
            '    {"kind": "execute_skill", "skill_name": "humidifier", "goal": "raise humidity", "reason": "why", "priority": 20},\n'
            '    {"kind": "reply", "reply": "我已经处理完成。", "priority": 30}\n'
            "  ]\n"
            "}\n"
            "Rules:\n"
            "- Use task_plan_items for multi-step planning.\n"
            "- Use ask_user when the request is ambiguous or missing critical information.\n"
            "- Use refresh_environment before acting when current state may be stale or must be confirmed.\n"
            "- Use system_action for Xiaomi QR onboarding, LAN scan, or creating a custom skill.\n"
            "- For `system_skill: \"skill_creator\"`, the only valid creation action is `create_custom_skill`.\n"
            "- Never invent action names such as `generate_new_skill_package`.\n"
            "- Use execute_skill for device control or home intelligence actions.\n"
            "- If the user asks to play music or audio on a speaker, use the `speaker` skill.\n"
            "- If the user asks to play something without giving a specific path or URL, set the speaker goal to random local playback.\n"
            "- If the user asks to stop speaker playback, use the `speaker` skill with a stop-oriented goal.\n"
            "- For general Q&A, set should_execute to false.\n"
            "- Do not use regex or heuristics; infer intent from the message and context.\n"
        )

    async def _route_system_chat_message(
        self,
        *,
        message: str,
        app_state: dict[str, Any],
    ) -> dict[str, Any] | None:
        for skill_name in ("skill_creator", "device_discovery"):
            if skill_name == "skill_creator" and not self._looks_like_skill_creation_request(message):
                continue
            skill = self._skill_loader.get_skill(skill_name)
            if not skill or not skill.chat_prompt:
                continue

            prompt = self._build_system_chat_route_prompt(
                skill=skill,
                message=message,
                app_state=app_state,
            )
            content = await self._invoke_llm_text(prompt, temperature=0.0, max_tokens=300)
            plan = self._parse_system_chat_route(content, skill_name=skill.meta.name)
            if plan is None:
                continue
            return {
                "prompt": prompt,
                "output": content,
                "plan": plan,
            }

        return None

    _CHITCHAT_PATTERNS = (
        r"^(你好|hi|hello|嗨|哈喽|早|晚安|早安|谢谢|谢了|感谢|好的|好|ok|okay|嗯|哦|明白|知道了|没事|不用了|再见)[\s!！。.]*$",
    )
    _HOME_AWAY_PATTERNS = (
        r"(我走了|拜拜|出门了|我要出门|我不在了|我离开了|我出去了)",
        r"(我回来了|我到家了|我回家了|我在家了|到家了|回来了)",
    )
    _DEVICE_KEYWORDS = (
        "开", "关", "调", "设置", "控制", "打开", "关闭", "启动", "停止",
        "温度", "湿度", "亮度", "音量", "模式", "净化", "加湿", "空调", "灯",
        "turn", "set", "control", "adjust", "switch",
    )

    def _classify_intent(self, message: str) -> str:
        """Classify message intent without LLM. Returns: chitchat | home_away | device_control | env_query | general."""
        text = message.strip()
        lowered = text.lower()
        if any(re.search(p, text, re.IGNORECASE) for p in self._CHITCHAT_PATTERNS):
            return "chitchat"
        if any(re.search(p, text, re.IGNORECASE) for p in self._HOME_AWAY_PATTERNS):
            return "home_away"
        if any(kw in text or kw in lowered for kw in self._DEVICE_KEYWORDS):
            return "device_control"
        if any(hint in text or hint in lowered for hint in ENVIRONMENT_QUERY_HINTS):
            return "env_query"
        return "general"

    @staticmethod
    def _looks_like_skill_creation_request(message: str) -> bool:
        text = message.strip()
        if not text:
            return False

        lowered = text.lower()
        if any(re.search(pattern, text, re.IGNORECASE) for pattern in SKILL_CREATION_INTENT_PATTERNS):
            return True

        has_skill_word = "技能" in text or "skill" in lowered
        if not has_skill_word:
            return False

        if any(hint in text or hint in lowered for hint in ENVIRONMENT_QUERY_HINTS):
            return False

        return False

    def _route_pending_skill_creation(self, message: str) -> dict[str, Any] | None:
        pending = self._pending_skill_creation
        if not pending:
            return None

        stripped = message.strip()
        lowered = stripped.lower()
        if any(token in stripped or token in lowered for token in PENDING_SKILL_CANCEL_TOKENS):
            self._pending_skill_creation = None
            return {
                "prompt": "pending skill creation cancel",
                "output": "",
                "plan": ChatPlan(
                    reply="已取消上一次技能创建请求。",
                    should_execute=False,
                ),
            }

        merged_request = self._merge_pending_skill_creation_request(
            base_request=str(pending.get("request", "")).strip(),
            follow_up_message=stripped,
        )
        task = TaskPlanItem(
            kind="system_action",
            system_skill="skill_creator",
            system_action="create_custom_skill",
            params={
                "request": merged_request,
                "allow_clarification": False,
            },
            reason="continue pending custom skill clarification",
            priority=5,
        )
        return {
            "prompt": "pending skill creation resume",
            "output": "",
            "plan": ChatPlan(
                reply="",
                should_execute=True,
                task_plan_items=[task],
            ),
        }

    @staticmethod
    def _merge_pending_skill_creation_request(base_request: str, follow_up_message: str) -> str:
        if not base_request:
            return follow_up_message
        if not follow_up_message:
            return base_request
        return (
            f"{base_request}\n\n"
            "Additional clarification from the user:\n"
            f"{follow_up_message}"
        )

    def _build_system_chat_route_prompt(
        self,
        *,
        skill: LoadedSkill,
        message: str,
        app_state: dict[str, Any],
    ) -> str:
        discovery = app_state.get("discovery")
        settings_store = app_state.get("settings")
        devices = discovery.get_all_devices() if discovery is not None and hasattr(discovery, "get_all_devices") else []
        current_devices = [
            {
                "device_id": device.device_id,
                "name": device.name,
                "type": device.type,
                "online": device.online,
            }
            for device in devices
            if isinstance(device, Device)
        ]
        existing_custom_skills = self._skill_loader.list_custom_skill_names()
        xiaomi_connected = bool(settings_store.get("xiaomi_cloud_devices", [])) if settings_store is not None and hasattr(settings_store, "get") else False

        return skill.chat_prompt.format(
            user_message=message,
            existing_custom_skills=json.dumps(existing_custom_skills, ensure_ascii=False, indent=2),
            current_devices=json.dumps(current_devices, ensure_ascii=False, indent=2),
            xiaomi_connected=json.dumps(xiaomi_connected, ensure_ascii=False),
            knowledge=skill.knowledge,
        )

    def _parse_system_chat_route(self, content: str, *, skill_name: str) -> ChatPlan | None:
        allowed_actions = {
            "skill_creator": {"create_custom_skill"},
            "device_discovery": {"scan_local_devices", "start_xiaomi_qr_scan"},
        }.get(skill_name, set())

        json_str = self._extract_json(content)
        if not json_str:
            return None

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            return None

        if not isinstance(data, dict):
            return None

        action = str(data.get("action", "")).strip()
        if not action or action == "none":
            return None
        if allowed_actions and action not in allowed_actions:
            return None

        params = data.get("params", {})
        if not isinstance(params, dict):
            params = {}

        reply = str(data.get("reply", "")).strip()
        task = TaskPlanItem(
            kind="system_action",
            system_skill=skill_name,
            system_action=action,
            params=params,
            reason=reply or f"chat router chose {action}",
            priority=5,
        )
        return ChatPlan(
            reply=reply,
            should_execute=True,
            task_plan_items=[task],
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

    def _parse_cycle_plan(
        self,
        content: str,
        lightweight_skills: list[SkillSummary],
    ) -> tuple[list[TaskPlanItem], list[SkillPlanItem]]:
        json_str = self._extract_json(content)
        if not json_str:
            return [], []

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            return [], []

        if isinstance(data, list):
            plan_items = self._parse_planner_response(content, lightweight_skills)
            return self._skill_plan_items_to_cycle_tasks(plan_items), plan_items

        if not isinstance(data, dict):
            return [], []

        task_items: list[TaskPlanItem] = []
        skill_map = {skill.name: skill for skill in lightweight_skills}
        raw_tasks = data.get("task_plan_items", [])
        if isinstance(raw_tasks, list):
            for item in raw_tasks:
                if not isinstance(item, dict):
                    continue

                kind = str(item.get("kind", "")).strip()
                if kind not in {"refresh_environment", "execute_skill", "reply"}:
                    continue

                skill_name = str(item.get("skill_name", "")).strip()
                if kind == "execute_skill":
                    summary = skill_map.get(skill_name)
                    if not summary or not summary.device_type:
                        continue

                params = item.get("params", {})
                if not isinstance(params, dict):
                    params = {}

                reply_text = str(item.get("reply", "")).strip()
                if kind == "reply" and reply_text:
                    params = {**params, "reply": reply_text}

                task_items.append(
                    TaskPlanItem(
                        kind=kind,
                        goal=str(item.get("goal", "")),
                        reason=str(item.get("reason", "")),
                        priority=self._coerce_priority(item.get("priority")),
                        skill_name=skill_name,
                        params=params,
                    )
                )

        if not task_items:
            return [], []

        plan_items = self._cycle_tasks_to_skill_plan_items(task_items, lightweight_skills)
        return task_items, plan_items

    def _skill_plan_items_to_cycle_tasks(self, plan_items: list[SkillPlanItem]) -> list[TaskPlanItem]:
        return [
            TaskPlanItem(
                kind="execute_skill",
                skill_name=item.skill_name,
                goal=item.goal,
                reason=item.reason,
                priority=item.priority,
            )
            for item in plan_items
        ]

    def _cycle_tasks_to_skill_plan_items(
        self,
        task_items: list[TaskPlanItem],
        lightweight_skills: list[SkillSummary],
    ) -> list[SkillPlanItem]:
        skill_map = {skill.name: skill for skill in lightweight_skills}
        return [
            SkillPlanItem(
                skill_name=item.skill_name,
                device_type=skill_map[item.skill_name].device_type,
                goal=item.goal,
                reason=item.reason,
                priority=item.priority,
            )
            for item in task_items
            if item.kind == "execute_skill" and item.skill_name in skill_map and skill_map[item.skill_name].device_type
        ]

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
        normalized_action = SYSTEM_ACTION_ALIASES.get(plan.system_action, plan.system_action)
        handler = getattr(actions_module, normalized_action, None) if actions_module else None
        if not handler:
            return {"reply": plan.reply or f"{plan.system_skill} skill 不支持动作: {plan.system_action}"}

        params = dict(plan.params)
        result = await handler(context=app_state, params=params, reply=plan.reply)
        if "reply" not in result and plan.reply:
            result["reply"] = plan.reply
        result["action"] = normalized_action
        if normalized_action != plan.system_action:
            result["requested_action"] = plan.system_action
        return result

    def _normalize_chat_tasks(self, plan: ChatPlan) -> list[TaskPlanItem]:
        if plan.task_plan_items:
            return plan.task_plan_items

        tasks: list[TaskPlanItem] = []
        if plan.system_action != "none":
            tasks.append(
                TaskPlanItem(
                    kind="system_action",
                    system_skill=plan.system_skill,
                    system_action=plan.system_action,
                    params=plan.params,
                    reason=plan.reply,
                    priority=10,
                )
            )

        for item in plan.skill_plan_items:
            tasks.append(
                TaskPlanItem(
                    kind="execute_skill",
                    skill_name=item.skill_name,
                    goal=item.goal,
                    reason=item.reason,
                    priority=item.priority,
                )
            )

        return tasks

    async def _execute_chat_task(
        self,
        task: TaskPlanItem,
        context: dict[str, Any],
        user_message: str,
    ) -> dict[str, Any]:
        if task.kind == "ask_user":
            question = task.question.strip() or "我需要先确认一些信息。"
            return {
                "kind": task.kind,
                "question": question,
                "reason": task.reason,
                "reply": question,
                "stop": True,
            }

        if task.kind == "refresh_environment":
            discovery = context["discovery"]
            refresh_result = await discovery.refresh_device_states(task.target_device_ids or None)
            context["environment_state"] = self.get_environment_state()
            return {
                "kind": task.kind,
                "reason": task.reason,
                "refresh_result": {
                    **refresh_result,
                    "environment": context["environment_state"],
                },
            }

        if task.kind == "system_action":
            plan = ChatPlan(
                reply="",
                should_execute=True,
                system_action=task.system_action or "none",
                system_skill=task.system_skill,
                params=dict(task.params),
            )
            if plan.system_action == "create_custom_skill":
                plan.params.setdefault("request", user_message)
            system_result = await self._execute_system_chat_action(plan, context)
            self._update_pending_skill_creation_state(
                plan=plan,
                system_result=system_result,
            )
            system_result["kind"] = task.kind
            system_result["stop"] = True
            return system_result

        if task.kind == "execute_skill":
            summary = next(
                (
                    item for item in self._skill_loader.list_executable_skill_summaries()
                    if item.name == task.skill_name
                ),
                None,
            )
            if not summary or not summary.device_type:
                return {
                    "kind": task.kind,
                    "reason": task.reason,
                    "reply": f"我理解了你的请求，但没有找到可执行的 skill: {task.skill_name or '(unknown)'}",
                    "stop": True,
                }

            plan_item = SkillPlanItem(
                skill_name=task.skill_name,
                device_type=summary.device_type,
                goal=task.goal,
                reason=task.reason,
                priority=task.priority,
            )
            execution_result = await self._execute_skill_plan_item(plan_item, context)
            return {
                "kind": task.kind,
                "reason": task.reason,
                "execution_result": execution_result,
            }

        if task.kind == "reply":
            reply = str(task.params.get("reply", "")).strip()
            return {
                "kind": task.kind,
                "reply": reply or "我已经处理完当前步骤。",
                "stop": True,
            }

        return {
            "kind": task.kind,
            "reason": task.reason,
            "reply": f"我规划了一个暂不支持的任务类型: {task.kind}",
            "stop": True,
        }

    def _update_pending_skill_creation_state(
        self,
        *,
        plan: ChatPlan,
        system_result: dict[str, Any],
    ) -> None:
        normalized_action = SYSTEM_ACTION_ALIASES.get(plan.system_action, plan.system_action)
        result_action = str(system_result.get("action", "")).strip()
        if normalized_action != "create_custom_skill" and result_action != "create_custom_skill":
            return

        status = str(system_result.get("status", "")).strip()
        request = str(plan.params.get("request", "")).strip()
        if status == "needs_clarification":
            questions = system_result.get("questions", [])
            if not isinstance(questions, list):
                questions = []
            self._pending_skill_creation = {
                "request": request,
                "questions": [str(item).strip() for item in questions if str(item).strip()],
            }
            return

        self._pending_skill_creation = None

    async def _execute_cycle_task(
        self,
        task: TaskPlanItem,
        context: dict[str, Any],
    ) -> SkillExecutionResult | None:
        if task.kind == "refresh_environment":
            discovery = context["discovery"]
            await discovery.refresh_device_states(task.target_device_ids or None)
            context["environment_state"] = self.get_environment_state()
            return None

        if task.kind == "execute_skill":
            summary = next(
                (
                    item for item in self._skill_loader.list_executable_skill_summaries()
                    if item.name == task.skill_name
                ),
                None,
            )
            if not summary or not summary.device_type:
                return None

            plan_item = SkillPlanItem(
                skill_name=task.skill_name,
                device_type=summary.device_type,
                goal=task.goal,
                reason=task.reason,
                priority=task.priority,
            )
            return await self._execute_skill_plan_item(plan_item, context)

        if task.kind == "reply":
            return None

        return None

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
        task_items: list[TaskPlanItem] = []
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

        raw_tasks = data.get("task_plan_items", [])
        if isinstance(raw_tasks, list):
            for item in raw_tasks:
                if not isinstance(item, dict):
                    continue

                kind = str(item.get("kind", "")).strip()
                if kind not in {"execute_skill", "system_action", "ask_user", "refresh_environment", "reply"}:
                    continue

                skill_name = str(item.get("skill_name", "")).strip()
                if kind == "execute_skill":
                    summary = skill_map.get(skill_name)
                    if not summary or not summary.device_type:
                        continue

                params = item.get("params", {})
                if not isinstance(params, dict):
                    params = {}

                target_device_ids = item.get("target_device_ids", [])
                if not isinstance(target_device_ids, list):
                    target_device_ids = []

                reply_text = str(item.get("reply", "")).strip()
                question = str(item.get("question", "")).strip()
                if kind == "reply" and reply_text:
                    params = {**params, "reply": reply_text}

                task_items.append(
                    TaskPlanItem(
                        kind=kind,
                        goal=str(item.get("goal", "")),
                        reason=str(item.get("reason", "")),
                        priority=self._coerce_priority(item.get("priority")),
                        skill_name=skill_name,
                        system_skill=str(item.get("system_skill", "")),
                        system_action=str(item.get("system_action", "")),
                        question=question,
                        params=params,
                        target_device_ids=[str(device_id) for device_id in target_device_ids if isinstance(device_id, str)],
                        expected_state=item.get("expected_state", {}) if isinstance(item.get("expected_state"), dict) else {},
                    )
                )

        return ChatPlan(
            reply=str(data.get("reply", "")),
            should_execute=bool(data.get("should_execute")),
            system_action=str(data.get("system_action", "none")),
            system_skill=str(data.get("system_skill", "")),
            params=data.get("params", {}) if isinstance(data.get("params"), dict) else {},
            skill_plan_items=plan_items,
            task_plan_items=task_items,
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
