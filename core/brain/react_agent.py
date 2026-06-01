from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

MAX_STEPS = 8

SYSTEM_PROMPT = """You are Anima, a smart home assistant. Complete user requests by calling tools when needed.

Rules:
- Think step by step internally, then call one tool when a tool is needed.
- For device control, use get_devices first to find the target device, then execute_skill.
- For environment information, use get_environment to fetch sensor data.
- If you are unsure which skill can handle the request, use get_skill.
- After all tool calls are complete, output the final reply text directly without calling another tool.
- The final reply language must follow the user's latest message.

Home/away detection:
- If the user says phrases like "我走了", "拜拜", "出门了", "我要出门", "我不在了", or equivalent English expressions, treat it as leaving home and turn off devices as appropriate.
- If the user says phrases like "我回来了", "我到家了", "我回家了", "我在家", or equivalent English expressions, treat it as returning home and restore preferred device settings as appropriate.
- Voice input may contain recognition errors. Ask for confirmation when intent is unclear.
- Messages marked with [语音输入] come from speech recognition and may contain transcription errors.
"""

def _preferred_language(message: str) -> str:
    if any("\u4e00" <= ch <= "\u9fff" for ch in message):
        return "zh"
    if any(ch.isalpha() for ch in message):
        return "en"
    return "zh"


def _language_instruction(language: str) -> str:
    if language == "en":
        return (
            "Language rule: the user's latest message is English. "
            "All user-visible replies, questions, explanations, and final status text MUST be in English. "
            "Do not switch to Chinese because tool descriptions, device names, memories, or observations contain Chinese."
        )
    return "语言规则：用户最近一条消息是中文。所有面向用户的回复、问题、解释和最终状态文字必须使用简体中文。"


def _localized(language: str, zh: str, en: str) -> str:
    return en if language == "en" else zh


TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_devices",
            "description": "Get the device list, optionally filtered by type. Returns device id, name, online status, and sensor data.",
            "parameters": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "description": "Device type, such as light, air_conditioner, humidifier, air_purifier, or speaker. Leave empty to return all devices.",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_skill",
            "description": "Get a skill's capability description and available actions by name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Skill name, such as light, humidifier, air_conditioner, air_purifier, or speaker.",
                    }
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "execute_skill",
            "description": "Execute a skill action on a specified device.",
            "parameters": {
                "type": "object",
                "properties": {
                    "skill_name": {"type": "string", "description": "Skill name."},
                    "device_id": {"type": "string", "description": "Target device ID."},
                    "goal": {"type": "string", "description": "Goal description in the user's language, such as turn on the device or set brightness to 50%."},
                },
                "required": ["skill_name", "device_id", "goal"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_environment",
            "description": "Get a snapshot of current indoor environment sensors, including temperature, humidity, and air quality.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    # reply tool removed — agent now streams the final answer directly
]


@dataclass
class AgentEvent:
    type: str  # thought | action | observation | reply | error
    content: str = ""
    tool: str = ""
    args: dict[str, Any] = field(default_factory=dict)
    result: str = ""
    step: int = 0
    done: bool = False
    execution_results: list[dict[str, Any]] = field(default_factory=list)

    def to_sse(self) -> str:
        return f"data: {json.dumps(self.__dict__, ensure_ascii=False)}\n\n"


class ReActAgent:
    def __init__(
        self,
        *,
        llm: AsyncOpenAI,
        model: str,
        disable_thinking: bool = False,
        skill_loader: Any,
        memory: Any,
        environment_provider: Any = None,
    ) -> None:
        self._llm = llm
        self._model = model
        self._disable_thinking = disable_thinking
        self._skill_loader = skill_loader
        self._memory = memory
        self._environment_provider = environment_provider

    async def run(self, message: str, app_state: dict[str, Any]) -> AsyncGenerator[AgentEvent, None]:
        language = _preferred_language(message)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "system", "content": _language_instruction(language)},
            {"role": "user", "content": message},
        ]
        execution_results: list[dict[str, Any]] = []

        for step in range(MAX_STEPS):
            extra_body: dict[str, Any] = {}
            if self._disable_thinking:
                extra_body["thinking"] = {"type": "disabled"}

            try:
                stream = await self._llm.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    tools=TOOLS,
                    tool_choice="auto",
                    temperature=0.1,
                    max_tokens=600,
                    stream=True,
                    extra_body=extra_body or None,
                )
            except Exception as exc:
                yield AgentEvent(type="error", content=str(exc), step=step, done=True)
                return

            # Accumulate streaming response
            collected_content = ""
            collected_tool_calls: dict[int, dict[str, Any]] = {}
            has_tool_calls = False

            try:
                async for chunk in stream:
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta

                    # Stream content tokens — only when no tool calls have started yet
                    if delta.content:
                        collected_content += delta.content
                        # Hold partial text until we know whether this turn uses tools.
                        # Some models emit a preamble before tool calls; showing it leaks
                        # intermediate reasoning and can use the wrong language.

                    # Accumulate tool call deltas
                    if delta.tool_calls:
                        has_tool_calls = True
                        for tc_delta in delta.tool_calls:
                            idx = tc_delta.index
                            if idx not in collected_tool_calls:
                                collected_tool_calls[idx] = {
                                    "id": tc_delta.id or "",
                                    "type": "function",
                                    "function": {
                                        "name": tc_delta.function.name or "" if tc_delta.function else "",
                                        "arguments": tc_delta.function.arguments or "" if tc_delta.function else "",
                                    },
                                }
                            else:
                                if tc_delta.id:
                                    collected_tool_calls[idx]["id"] = tc_delta.id
                                if tc_delta.function:
                                    if tc_delta.function.name:
                                        collected_tool_calls[idx]["function"]["name"] += tc_delta.function.name
                                    if tc_delta.function.arguments:
                                        collected_tool_calls[idx]["function"]["arguments"] += tc_delta.function.arguments
            except Exception as exc:
                yield AgentEvent(type="error", content=str(exc), step=step, done=True)
                return

            # No tool calls -> final text reply.
            if not has_tool_calls:
                reply_text = collected_content or _localized(
                    language,
                    "我暂时没有需要执行的操作。",
                    "I do not have any action to perform right now.",
                )
                yield AgentEvent(
                    type="reply",
                    content=reply_text,
                    step=step,
                    done=True,
                    execution_results=execution_results,
                )
                return

            # Process tool calls
            tool_calls_list = [collected_tool_calls[i] for i in sorted(collected_tool_calls.keys())]
            messages.append(
                {
                    "role": "assistant",
                    "content": collected_content or None,
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {"name": tc["function"]["name"], "arguments": tc["function"]["arguments"]},
                        }
                        for tc in tool_calls_list
                    ],
                }
            )

            for tc in tool_calls_list:
                tool_name = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"]["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {}

                yield AgentEvent(type="action", tool=tool_name, args=args, step=step)

                obs, exec_result = await self._execute_tool(tool_name, args, app_state, language)

                if exec_result:
                    execution_results.append(exec_result)

                yield AgentEvent(type="observation", tool=tool_name, result=obs, step=step)

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": f"{obs}\n\n{_language_instruction(language)}",
                    }
                )

        # Max steps reached
        yield AgentEvent(
            type="reply",
            content=_localized(
                language,
                "已达到最大推理步数，请重新描述你的需求。",
                "I reached the maximum reasoning steps. Please rephrase your request.",
            ),
            step=MAX_STEPS,
            done=True,
            execution_results=execution_results,
        )

    async def _execute_tool(
        self, name: str, args: dict[str, Any], app_state: dict[str, Any], language: str
    ) -> tuple[str, dict[str, Any] | None]:
        try:
            if name == "get_devices":
                return self._tool_get_devices(args, app_state, language), None
            if name == "get_skill":
                return self._tool_get_skill(args, language), None
            if name == "get_environment":
                return self._tool_get_environment(app_state, language), None
            if name == "execute_skill":
                return await self._tool_execute_skill(args, app_state, language)
            return _localized(language, f"未知工具: {name}", f"Unknown tool: {name}"), None
        except Exception as exc:
            logger.exception("Tool %s failed", name)
            return _localized(language, f"工具执行失败: {exc}", f"Tool execution failed: {exc}"), None

    def _tool_get_devices(self, args: dict[str, Any], app_state: dict[str, Any], language: str) -> str:
        discovery = app_state["discovery"]
        device_type = args.get("type", "").strip()
        if device_type:
            devices = discovery.get_devices_by_type(device_type)
        else:
            devices = discovery.get_all_devices()

        if not devices:
            if language == "en":
                return f"No devices found{f' for type {device_type}' if device_type else ''}."
            return f"没有找到{'类型为 ' + device_type + ' 的' if device_type else ''}设备。"

        result = []
        for d in devices:
            sensors = {s.name: s.value for s in d.sensors if s.value is not None}
            result.append(
                {
                    "device_id": d.device_id,
                    "name": d.name,
                    "type": d.type,
                    "online": d.online,
                    "sensors": sensors,
                }
            )
        return json.dumps(result, ensure_ascii=False)

    def _tool_get_skill(self, args: dict[str, Any], language: str) -> str:
        name = args.get("name", "").strip()
        if not name:
            skills = self._skill_loader.list_chat_skill_summaries()
            names = [s.name for s in skills]
            prefix = _localized(language, "可用 skill 列表", "Available skills")
            return f"{prefix}: {json.dumps(names, ensure_ascii=False)}"

        skill = self._skill_loader.get_skill(name)
        if not skill:
            return _localized(language, f"未找到 skill: {name}", f"Skill not found: {name}")

        info: dict[str, Any] = {
            "name": skill.meta.name,
            "description": skill.meta.description,
            "device_types": list(skill.meta.device_types),
        }
        if skill.knowledge:
            info["knowledge"] = skill.knowledge[:500]
        return json.dumps(info, ensure_ascii=False)

    def _tool_get_environment(self, app_state: dict[str, Any], language: str) -> str:
        brain = app_state.get("brain")
        if brain and hasattr(brain, "get_environment_state"):
            env = brain.get_environment_state()
            signals = env.get("signals", {})
            compact: dict[str, Any] = {}
            for sig_name, readings in signals.items():
                if readings:
                    compact[sig_name] = (
                        readings[0].get("value")
                        if isinstance(readings[0], dict)
                        else getattr(readings[0], "value", None)
                    )
            return json.dumps(compact, ensure_ascii=False) if compact else _localized(language, "暂无环境数据", "No environment data available")
        return _localized(language, "暂无环境数据", "No environment data available")

    async def _tool_execute_skill(
        self, args: dict[str, Any], app_state: dict[str, Any], language: str
    ) -> tuple[str, dict[str, Any] | None]:
        from core.models import SkillPlanItem

        skill_name = args.get("skill_name", "").strip()
        device_id = args.get("device_id", "").strip()
        goal = args.get("goal", "").strip()

        if not skill_name or not device_id:
            return _localized(language, "缺少 skill_name 或 device_id 参数", "Missing skill_name or device_id."), None

        brain = app_state.get("brain")
        if not brain:
            return _localized(language, "brain 未初始化", "Brain is not initialized."), None

        skill = self._skill_loader.get_skill(skill_name)
        if not skill:
            return _localized(language, f"未找到 skill: {skill_name}", f"Skill not found: {skill_name}"), None

        device_type = list(skill.meta.device_types)[0] if skill.meta.device_types else ""
        plan_item = SkillPlanItem(
            skill_name=skill_name,
            device_type=device_type,
            goal=goal,
            reason="ReAct agent decision",
            priority=10,
        )

        user_memory = await self._memory.get_full_context()
        context = {
            "brain": brain,
            "memory": self._memory,
            "user_memory": user_memory,
            "environment_state": brain.get_environment_state(),
            "discovery": app_state["discovery"],
            "settings": app_state["settings"],
            "_loaded_skill": skill,
            "_history_source": "chat",
            "_history_learnable": True,
        }

        try:
            result = await brain._execute_skill_plan_item(plan_item, context)
            actions = [a.__dict__ if hasattr(a, "__dict__") else dict(a) for a in result.actions]
            verifications = [v.__dict__ if hasattr(v, "__dict__") else dict(v) for v in result.verifications]
            success = (
                any(v.get("verified") or v.get("success") for v in verifications) if verifications else bool(actions)
            )
            obs = _localized(
                language,
                "执行成功" if success else "执行失败或无法验证",
                "Execution succeeded" if success else "Execution failed or could not be verified",
            )
            exec_result = {
                "plan_item": plan_item.model_dump(),
                "actions": actions,
                "verifications": verifications,
            }
            return obs, exec_result
        except Exception as exc:
            logger.exception("execute_skill failed for %s", skill_name)
            return _localized(language, f"执行失败: {exc}", f"Execution failed: {exc}"), None
