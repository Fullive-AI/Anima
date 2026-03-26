from __future__ import annotations

import json
import logging
import re
import math
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph
from openai import AsyncOpenAI
from core.brain.skill_loader import SkillLoader, LoadedSkill
from core.config import settings
from core.events.bus import EventBus
from core.memory.store import MemoryStore
from core.models import Device, DeviceCommand, Event, EventType

logger = logging.getLogger(__name__)


class DecisionState(TypedDict, total=False):
    device: Device
    sensor_data: dict[str, Any]
    skill: LoadedSkill
    user_memory: dict[str, Any]
    decision_prompt: str
    supported_actions: list[dict[str, Any]]
    planner_prompt: str
    planner_output: str
    plan: dict[str, Any]
    feasible_actions: list[dict[str, Any]]
    rejected_actions: list[dict[str, Any]]
    graph_next: str
    generator_prompt: str
    generator_output: str
    command: DeviceCommand | None


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
        self._decision_graph = self._build_decision_graph()

    def set_environment_provider(self, provider: Callable[[], list[Device]]) -> None:
        self._environment_provider = provider

    async def decide(self, device: Device, sensor_data: dict[str, Any]) -> DeviceCommand | None:
        skill = self._skill_loader.get_skill_for_device(device.type)
        if not skill or not skill.decide_prompt:
            logger.debug("No skill found for device type: %s", device.type)
            return None

        try:
            user_memory = await self._memory.get_full_context()
            result = await self._decision_graph.ainvoke({
                "device": device,
                "sensor_data": sensor_data,
                "skill": skill,
                "user_memory": user_memory,
            })
            command = result.get("command")
            if command:
                logger.info(
                    "Brain decision: %s → %s (reason: %s)",
                    device.device_id, command.action, command.reason,
                )
                # Record to history
                await self._memory.append_history("default", {
                    "device_id": device.device_id,
                    "device_type": device.type,
                    "sensor_data": sensor_data,
                    "action": command.action,
                    "params": command.params,
                    "reason": command.reason,
                    "confidence": command.confidence,
                    "expected_outcome": command.expected_outcome,
                    "should_wait_seconds": command.should_wait_seconds,
                })
            return command

        except Exception:
            logger.exception("Brain decision failed for %s", device.device_id)
            return None

    async def coordinate(self, devices: list[Device], environment: dict) -> list[DeviceCommand]:
        skill = self._skill_loader.get_skill_for_device("coordinator")
        if not skill or not skill.orchestrate_prompt:
            return []

        try:
            user_memory = await self._memory.get_full_context()
            prompt = skill.orchestrate_prompt.format(
                devices=json.dumps([d.model_dump() for d in devices], default=str, indent=2),
                environment=json.dumps(environment, indent=2),
                recent_actions=json.dumps(user_memory.get("history", [])[-10:], indent=2),
                user_preferences=user_memory.get("preferences", ""),
                knowledge=skill.knowledge,
            )

            content = await self._invoke_llm_text(prompt, temperature=0.2, max_tokens=900)

            # Parse array of actions
            json_str = self._extract_json(content)
            if not json_str:
                return []
            actions = json.loads(json_str)
            if not isinstance(actions, list):
                return []

            commands = []
            for a in actions:
                cmd = DeviceCommand(
                    device_id=a["device_id"],
                    action=a["action"],
                    params=a.get("params", {}),
                    source="brain",
                    reason=a.get("reason", "coordinator"),
                )
                commands.append(cmd)
            return commands

        except Exception:
            logger.exception("Coordination failed")
            return []

    async def learn_preferences(self, user_id: str = "default") -> None:
        """Periodic learning: review history and update user profile."""
        skill_types = ["humidifier", "air_conditioner", "light"]

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

    def _build_prompt_context(
        self,
        skill: LoadedSkill,
        device: Device,
        user_memory: dict[str, Any],
    ) -> str:
        sensor_summary = {
            s.name: {"value": s.value, "unit": s.unit}
            for s in device.sensors
            if s.value is not None
        }
        caps_summary = [
            {"name": c.name, **c.params} for c in device.capabilities
        ]
        learned_profiles = user_memory.get("learned_profiles", {})
        learned_profile = learned_profiles.get(device.type) or user_memory.get("learned", "")
        environment_state = self._build_environment_state(device)

        return skill.decide_prompt.format(
            current_data=json.dumps(sensor_summary, indent=2),
            capabilities=json.dumps(caps_summary, indent=2),
            environment_state=json.dumps(environment_state, ensure_ascii=False, indent=2),
            user_preferences=user_memory.get("preferences", ""),
            recent_history=json.dumps(user_memory.get("history", [])[-5:], indent=2),
            learned_profile=learned_profile or "(none)",
            knowledge=skill.knowledge,
        )

    def _build_decision_graph(self) -> Any:
        graph = StateGraph(DecisionState)
        graph.add_node("prepare", self._graph_prepare)
        graph.add_node("planner", self._graph_planner)
        graph.add_node("executor", self._graph_executor)
        graph.add_node("generator", self._graph_generator)
        graph.set_entry_point("prepare")
        graph.add_edge("prepare", "planner")
        graph.add_edge("planner", "executor")
        graph.add_conditional_edges(
            "executor",
            self._graph_route_after_executor,
            {
                "generator": "generator",
                "end": END,
            },
        )
        graph.add_edge("generator", END)
        logger.info("Brain decision graph ready (langgraph)")
        return graph.compile()

    async def _graph_prepare(self, state: dict[str, Any]) -> dict[str, Any]:
        device: Device = state["device"]
        skill: LoadedSkill = state["skill"]
        user_memory: dict[str, Any] = state["user_memory"]
        prompt = self._build_prompt_context(skill, device, user_memory)
        supported_actions = self._describe_supported_actions(device)
        return {
            "decision_prompt": prompt,
            "supported_actions": supported_actions,
        }

    async def _graph_planner(self, state: dict[str, Any]) -> dict[str, Any]:
        device: Device = state["device"]
        prompt = self._build_planner_prompt(
            device=device,
            skill=state["skill"],
            decision_prompt=state["decision_prompt"],
            supported_actions=state["supported_actions"],
        )
        content = await self._invoke_llm_text(prompt, temperature=0.1, max_tokens=700)
        plan = self._parse_plan_response(content, device.device_id)
        return {
            "planner_prompt": prompt,
            "planner_output": content,
            "plan": plan,
        }

    async def _graph_executor(self, state: dict[str, Any]) -> dict[str, Any]:
        device: Device = state["device"]
        plan = state.get("plan") or {}
        candidates = plan.get("candidate_actions", [])
        feasible: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []

        for candidate in candidates:
            command = DeviceCommand(
                device_id=device.device_id,
                action=str(candidate.get("action", "")).strip(),
                params=candidate.get("params", {}) if isinstance(candidate.get("params"), dict) else {},
                source="brain",
                reason=str(candidate.get("reason", "")),
            )
            if not command.action or command.action == "none":
                continue
            sanitized = self._sanitize_command_for_device(command, device)
            if sanitized is None:
                rejected.append({
                    "action": command.action,
                    "params": command.params,
                    "reason": "unsupported_or_invalid_for_capabilities",
                })
                continue
            feasible.append({
                "action": sanitized.action,
                "params": sanitized.params,
                "reason": command.reason,
            })

        should_generate = bool(plan.get("should_act")) and bool(feasible)
        return {
            "feasible_actions": feasible,
            "rejected_actions": rejected,
            "graph_next": "generator" if should_generate else "end",
        }

    async def _graph_generator(self, state: dict[str, Any]) -> dict[str, Any]:
        device: Device = state["device"]
        prompt = self._build_generator_prompt(
            decision_prompt=state["decision_prompt"],
            planner_output=state.get("planner_output", ""),
            feasible_actions=state.get("feasible_actions", []),
            rejected_actions=state.get("rejected_actions", []),
        )
        content = await self._invoke_llm_text(prompt, temperature=0.2, max_tokens=900)
        command = self._parse_llm_response(content, device.device_id)
        if command:
            command = self._sanitize_command_for_device(command, device)
        return {
            "generator_prompt": prompt,
            "generator_output": content,
            "command": command,
        }

    @staticmethod
    def _graph_route_after_executor(state: dict[str, Any]) -> str:
        return state.get("graph_next", "end")

    def _build_planner_prompt(
        self,
        *,
        device: Device,
        skill: LoadedSkill,
        decision_prompt: str,
        supported_actions: list[dict[str, Any]],
    ) -> str:
        return (
            "You are the planner node in Anima's LangGraph decision pipeline.\n"
            "Your job is to inspect the device context and produce a small candidate action plan.\n\n"
            f"Device ID: {device.device_id}\n"
            f"Device type: {device.type}\n"
            f"Skill: {skill.meta.name}\n"
            f"Supported actions: {json.dumps(supported_actions, ensure_ascii=False, indent=2)}\n\n"
            "Base decision context:\n"
            f"{decision_prompt}\n\n"
            "Return exactly one JSON object with this schema:\n"
            "{\n"
            '  "should_act": true,\n'
            '  "goal": "short goal",\n'
            '  "candidate_actions": [\n'
            '    {"action": "turn_on", "params": {}, "reason": "why"}\n'
            "  ],\n"
            '  "notes": "short notes"\n'
            "}\n"
            "Rules:\n"
            "- Return JSON only.\n"
            "- If no action is needed, set should_act to false and return an empty candidate_actions array.\n"
            "- Only propose actions from the supported actions list.\n"
            "- Keep candidate_actions short, conservative, and capability-aware.\n"
        )

    def _build_generator_prompt(
        self,
        *,
        decision_prompt: str,
        planner_output: str,
        feasible_actions: list[dict[str, Any]],
        rejected_actions: list[dict[str, Any]],
    ) -> str:
        return (
            f"{decision_prompt}\n\n"
            "## Planner Output\n"
            f"{planner_output}\n\n"
            "## Executor Feasible Actions\n"
            f"{json.dumps(feasible_actions, ensure_ascii=False, indent=2)}\n\n"
            "## Executor Rejected Actions\n"
            f"{json.dumps(rejected_actions, ensure_ascii=False, indent=2)}\n\n"
            "Use the feasible actions list as the hard boundary.\n"
            "If there is no safe feasible action, return `none`.\n"
            "Choose one final action or `none` and respond with the JSON schema defined above.\n"
        )

    def _parse_plan_response(self, content: str, device_id: str) -> dict[str, Any]:
        json_str = self._extract_json(content)
        if not json_str:
            return {"should_act": False, "candidate_actions": [], "notes": "planner_invalid_json"}

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            return {"should_act": False, "candidate_actions": [], "notes": "planner_invalid_json"}

        if isinstance(data, dict) and isinstance(data.get("action"), str):
            action = data.get("action", "").strip()
            if not action or action == "none":
                return {"should_act": False, "candidate_actions": [], "notes": "planner_direct_none"}
            return {
                "should_act": True,
                "goal": str(data.get("reason", "")),
                "candidate_actions": [{
                    "action": action,
                    "params": data.get("params", {}) if isinstance(data.get("params"), dict) else {},
                    "reason": str(data.get("reason", "")),
                }],
                "notes": "planner_direct_command",
            }

        if not isinstance(data, dict):
            return {"should_act": False, "candidate_actions": [], "notes": "planner_invalid_shape"}

        candidate_actions = data.get("candidate_actions", [])
        if not isinstance(candidate_actions, list):
            candidate_actions = []

        normalized_candidates = []
        for candidate in candidate_actions:
            if not isinstance(candidate, dict):
                continue
            action = str(candidate.get("action", "")).strip()
            if not action:
                continue
            normalized_candidates.append({
                "action": action,
                "params": candidate.get("params", {}) if isinstance(candidate.get("params"), dict) else {},
                "reason": str(candidate.get("reason", "")),
            })

        return {
            "should_act": bool(data.get("should_act")) and bool(normalized_candidates),
            "goal": str(data.get("goal", "")),
            "candidate_actions": normalized_candidates,
            "notes": str(data.get("notes", "")),
        }

    def _describe_supported_actions(self, device: Device) -> list[dict[str, Any]]:
        actions = []
        for capability in device.capabilities:
            params = capability.params if isinstance(capability.params, dict) else {}
            inputs = params.get("inputs", []) if isinstance(params.get("inputs", []), list) else []
            normalized_inputs = []
            for item in inputs:
                if not isinstance(item, dict):
                    continue
                normalized_inputs.append({
                    "name": item.get("name", ""),
                    "type": item.get("type", "string"),
                    "required": bool(item.get("required", False)),
                    "default": item.get("default"),
                    "options": item.get("options", []),
                    "min": item.get("min"),
                    "max": item.get("max"),
                    "step": item.get("step"),
                })
            actions.append({
                "name": capability.name,
                "inputs": normalized_inputs,
                "min": params.get("min"),
                "max": params.get("max"),
                "step": params.get("step"),
            })
        return actions

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

    def _build_environment_state(self, current_device: Device) -> dict[str, Any]:
        devices = self._get_environment_devices(current_device)
        return self._summarize_environment_state(
            devices=devices,
            current_device_id=current_device.device_id,
            current_device_type=current_device.type,
        )

    def get_environment_state(self) -> dict[str, Any]:
        devices = self._get_environment_devices(None)
        return self._summarize_environment_state(
            devices=devices,
            current_device_id=None,
            current_device_type=None,
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

            device_snapshots.append({
                "device_id": device.device_id,
                "name": device.name,
                "type": device.type,
                "room": device.room,
                "online": device.online,
                "sensors": sensors,
            })

            for sensor_name, payload in sensors.items():
                signals.setdefault(sensor_name, []).append({
                    "device_id": device.device_id,
                    "device_type": device.type,
                    "room": device.room,
                    "value": payload["value"],
                    "unit": payload["unit"],
                })

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
            logger.warning("Invalid params field in LLM response: %r", params)
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
        # Try to find JSON in markdown code fence
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if match:
            return match.group(1).strip()

        # Try to find raw JSON object
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return match.group(0)

        # Try to find raw JSON array
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            return match.group(0)

        return None
