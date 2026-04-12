from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

MAX_STEPS = 8

SYSTEM_PROMPT = """你是 Anima，一个智能家居助手。通过调用工具完成用户请求。

规则：
- 每步先思考（Thought），再调用一个工具
- 需要控制设备时，先用 get_devices 找到设备，再用 execute_skill 执行
- 需要了解环境时，用 get_environment 获取传感器数据
- 不确定有哪些 skill 能力时，用 get_skill 按需查询
- 任务完成后调用 reply 输出最终回复
- 回复使用中文，简洁友好

在家/离家检测：
- 如果用户说"我走了"、"拜拜"、"出门了"、"我要出门"、"我不在了"等，说明用户离家，应关闭所有设备，回复温馨提示
- 如果用户说"我回来了"、"我到家了"、"我回家了"、"我在家"等，说明用户回家，应按用户偏好开启设备（如空调调到舒适温度、开灯等），回复欢迎语
- 语音输入可能有识别误差，遇到不确定的指令先反问用户确认，不要盲目执行
- 标记为 [语音输入] 的消息来自语音识别，可能有错别字，请联想判断用户真实意图
"""

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_devices",
            "description": "获取设备列表，可按类型过滤。返回设备 id、名称、在线状态和传感器数据。",
            "parameters": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "description": "设备类型，如 light、air_conditioner、humidifier、air_purifier、speaker。不填则返回所有设备。",
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
            "description": "按名称获取 skill 的能力描述和可用动作列表。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "skill 名称，如 light、humidifier、air_conditioner、air_purifier、speaker。",
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
            "description": "在指定设备上执行 skill 动作。",
            "parameters": {
                "type": "object",
                "properties": {
                    "skill_name": {"type": "string", "description": "skill 名称"},
                    "device_id": {"type": "string", "description": "目标设备 ID"},
                    "goal": {"type": "string", "description": "目标描述，如 turn on、set brightness to 50%"},
                },
                "required": ["skill_name", "device_id", "goal"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_environment",
            "description": "获取当前室内环境传感器快照，包括温度、湿度、空气质量等。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reply",
            "description": "向用户发送最终回复并结束对话。",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "回复内容"}
                },
                "required": ["text"],
            },
        },
    },
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
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": message},
        ]
        execution_results: list[dict[str, Any]] = []

        for step in range(MAX_STEPS):
            extra_body: dict[str, Any] = {}
            if self._disable_thinking:
                extra_body["thinking"] = {"type": "disabled"}

            try:
                response = await self._llm.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    tools=TOOLS,
                    tool_choice="auto",
                    temperature=0.1,
                    max_tokens=600,
                    extra_body=extra_body or None,
                )
            except Exception as exc:
                yield AgentEvent(type="error", content=str(exc), step=step, done=True)
                return

            choice = response.choices[0] if response.choices else None
            if not choice:
                yield AgentEvent(type="error", content="LLM 返回空响应", step=step, done=True)
                return

            msg = choice.message

            # No tool call → final text reply
            if not msg.tool_calls:
                reply_text = msg.content or "我暂时没有需要执行的操作。"
                yield AgentEvent(
                    type="reply",
                    content=reply_text,
                    step=step,
                    done=True,
                    execution_results=execution_results,
                )
                return

            # Process tool calls
            messages.append({"role": "assistant", "content": msg.content, "tool_calls": [
                {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in msg.tool_calls
            ]})

            for tc in msg.tool_calls:
                tool_name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}

                yield AgentEvent(type="action", tool=tool_name, args=args, step=step)

                if tool_name == "reply":
                    reply_text = args.get("text", "")
                    yield AgentEvent(
                        type="reply",
                        content=reply_text,
                        step=step,
                        done=True,
                        execution_results=execution_results,
                    )
                    return

                obs, exec_result = await self._execute_tool(tool_name, args, app_state)

                if exec_result:
                    execution_results.append(exec_result)

                yield AgentEvent(type="observation", tool=tool_name, result=obs, step=step)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": obs,
                })

        # Max steps reached
        yield AgentEvent(
            type="reply",
            content="已达到最大推理步数，请重新描述你的需求。",
            step=MAX_STEPS,
            done=True,
            execution_results=execution_results,
        )

    async def _execute_tool(
        self, name: str, args: dict[str, Any], app_state: dict[str, Any]
    ) -> tuple[str, dict[str, Any] | None]:
        try:
            if name == "get_devices":
                return self._tool_get_devices(args, app_state), None
            if name == "get_skill":
                return self._tool_get_skill(args), None
            if name == "get_environment":
                return self._tool_get_environment(app_state), None
            if name == "execute_skill":
                return await self._tool_execute_skill(args, app_state)
            return f"未知工具: {name}", None
        except Exception as exc:
            logger.exception("Tool %s failed", name)
            return f"工具执行失败: {exc}", None

    def _tool_get_devices(self, args: dict[str, Any], app_state: dict[str, Any]) -> str:
        discovery = app_state["discovery"]
        device_type = args.get("type", "").strip()
        if device_type:
            devices = discovery.get_devices_by_type(device_type)
        else:
            devices = discovery.get_all_devices()

        if not devices:
            return f"没有找到{'类型为 ' + device_type + ' 的' if device_type else ''}设备。"

        result = []
        for d in devices:
            sensors = {s.name: s.value for s in d.sensors if s.value is not None}
            result.append({
                "device_id": d.device_id,
                "name": d.name,
                "type": d.type,
                "online": d.online,
                "sensors": sensors,
            })
        return json.dumps(result, ensure_ascii=False)

    def _tool_get_skill(self, args: dict[str, Any]) -> str:
        name = args.get("name", "").strip()
        if not name:
            skills = self._skill_loader.list_chat_skill_summaries()
            names = [s.name for s in skills]
            return f"可用 skill 列表: {json.dumps(names, ensure_ascii=False)}"

        skill = self._skill_loader.get_skill(name)
        if not skill:
            return f"未找到 skill: {name}"

        info: dict[str, Any] = {
            "name": skill.meta.name,
            "description": skill.meta.description,
            "device_types": list(skill.meta.device_types),
        }
        if skill.knowledge:
            info["knowledge"] = skill.knowledge[:500]
        return json.dumps(info, ensure_ascii=False)

    def _tool_get_environment(self, app_state: dict[str, Any]) -> str:
        brain = app_state.get("brain")
        if brain and hasattr(brain, "get_environment_state"):
            env = brain.get_environment_state()
            signals = env.get("signals", {})
            compact: dict[str, Any] = {}
            for sig_name, readings in signals.items():
                if readings:
                    compact[sig_name] = readings[0].get("value") if isinstance(readings[0], dict) else getattr(readings[0], "value", None)
            return json.dumps(compact, ensure_ascii=False) if compact else "暂无环境数据"
        return "暂无环境数据"

    async def _tool_execute_skill(
        self, args: dict[str, Any], app_state: dict[str, Any]
    ) -> tuple[str, dict[str, Any] | None]:
        from core.models import SkillPlanItem

        skill_name = args.get("skill_name", "").strip()
        device_id = args.get("device_id", "").strip()
        goal = args.get("goal", "").strip()

        if not skill_name or not device_id:
            return "缺少 skill_name 或 device_id 参数", None

        brain = app_state.get("brain")
        if not brain:
            return "brain 未初始化", None

        skill = self._skill_loader.get_skill(skill_name)
        if not skill:
            return f"未找到 skill: {skill_name}", None

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
        }

        try:
            result = await brain._execute_skill_plan_item(plan_item, context)
            actions = [a.__dict__ if hasattr(a, "__dict__") else dict(a) for a in result.actions]
            verifications = [v.__dict__ if hasattr(v, "__dict__") else dict(v) for v in result.verifications]
            success = any(v.get("verified") or v.get("success") for v in verifications) if verifications else bool(actions)
            obs = "执行成功" if success else "执行失败或无法验证"
            exec_result = {
                "plan_item": plan_item.model_dump(),
                "actions": actions,
                "verifications": verifications,
            }
            return obs, exec_result
        except Exception as exc:
            logger.exception("execute_skill failed for %s", skill_name)
            return f"执行失败: {exc}", None
