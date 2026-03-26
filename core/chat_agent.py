from __future__ import annotations

import json
import logging
import re
from typing import Any

from core.brain.skill_loader import SkillLoader
from core.config import settings as env_settings
from core.llm.openai_text_client import OpenAITextClient

logger = logging.getLogger(__name__)


class ChatAgent:
    def __init__(self, skill_loader: SkillLoader) -> None:
        self._skill_loader = skill_loader

    async def handle_message(self, message: str, app_state: dict[str, Any]) -> dict[str, Any]:
        text = message.strip()
        if not text:
            return {"reply": "请先输入你的需求。"}

        skill_name = self._select_chat_skill(text)
        skill = self._skill_loader.get_skill(skill_name)
        if not skill:
            return {"reply": f"{skill_name} skill 尚未加载。"}

        if skill_name == "skill_creator":
            plan = await self._plan_skill_creation(text, skill, app_state)
        else:
            plan = await self._plan_device_discovery(text, skill, app_state)
        action = plan.get("action", "none")
        reply = plan.get("reply", "") or "我暂时没有需要执行的操作。"

        if action == "none":
            return {"reply": reply}

        actions_module = self._skill_loader.load_actions(skill)
        if not actions_module:
            return {"reply": "设备扫描 skill 已加载，但 actions.py 不可用。"}

        handler = getattr(actions_module, action, None)
        if not handler:
            return {"reply": f"设备扫描 skill 不支持动作: {action}"}

        try:
            result = await handler(
                context=app_state,
                params=plan.get("params", {}),
                reply=reply,
            )
        except Exception:
            logger.exception("ChatAgent action execution failed: %s.%s", skill_name, action)
            return {"reply": "处理这条请求时后端出错了，请检查 LLM 配置或稍后重试。", "error": "action_execution_failed"}
        result.setdefault("reply", reply)
        result["action"] = action
        return result

    def _select_chat_skill(self, message: str) -> str:
        text = message.lower()
        skill_creation_verbs = (
            "新增", "创建", "新建", "生成", "定制", "做一个", "写一个", "create", "generate", "build",
        )
        skill_nouns = ("技能", "skill")
        if any(noun in text for noun in skill_nouns) and any(verb in text for verb in skill_creation_verbs):
            return "skill_creator"
        return "device_discovery"

    async def _plan_device_discovery(
        self,
        message: str,
        skill: Any,
        app_state: dict[str, Any],
    ) -> dict[str, Any]:
        heuristic = self._heuristic_plan(message, app_state)
        llm = self._build_llm(app_state)
        if not llm or not skill.chat_prompt:
            return heuristic

        discovery = app_state["discovery"]
        store = app_state["settings"]
        devices = [
            {
                "device_id": d.device_id,
                "name": d.name,
                "type": d.type,
                "online": d.online,
            }
            for d in discovery.get_all_devices()
        ]

        prompt = skill.chat_prompt.format(
            user_message=message,
            current_devices=json.dumps(devices, ensure_ascii=False, indent=2),
            xiaomi_connected=json.dumps(
                {
                    "configured": len(store.get("xiaomi_cloud_devices", [])) > 0,
                    "country": store.get("xiaomi_cloud_country", "cn"),
                },
                ensure_ascii=False,
                indent=2,
            ),
            knowledge=skill.knowledge,
        )

        try:
            response = await llm.ainvoke(prompt)
            parsed = self._extract_action_plan(response.content)
            if parsed:
                return parsed
        except Exception:
            logger.exception("ChatAgent LLM planning failed")

        return heuristic

    async def _plan_skill_creation(
        self,
        message: str,
        skill: Any,
        app_state: dict[str, Any],
    ) -> dict[str, Any]:
        heuristic = self._heuristic_skill_creation_plan(message)
        llm = self._build_llm(app_state)
        if not llm or not skill.chat_prompt:
            return heuristic

        custom_root = self._skill_loader._dir / "custom"
        existing_custom_skills = [
            path.name for path in sorted(custom_root.iterdir())
            if path.is_dir() and not path.name.startswith((".", "_"))
        ] if custom_root.exists() else []

        prompt = skill.chat_prompt.format(
            user_message=message,
            existing_custom_skills=json.dumps(existing_custom_skills, ensure_ascii=False, indent=2),
            knowledge=skill.knowledge,
        )

        try:
            response = await llm.ainvoke(prompt)
            parsed = self._extract_action_plan(response.content)
            if parsed:
                parsed.setdefault("params", {})
                parsed["params"].setdefault("request", message)
                return parsed
        except Exception:
            logger.exception("ChatAgent skill creation planning failed")

        return heuristic

    def _build_llm(self, app_state: dict[str, Any]) -> OpenAITextClient | None:
        store = app_state["settings"]
        api_key = store.get("llm_api_key", "") or env_settings.llm_api_key
        if not api_key or api_key.strip() in {"your-api-key-here", "sk-xxx"}:
            return None

        disable_thinking = store.get("llm_disable_thinking", env_settings.llm_disable_thinking)
        return OpenAITextClient(
            api_key=api_key,
            model=store.get("llm_model", "") or env_settings.llm_model,
            base_url=store.get("llm_base_url", "") or env_settings.llm_base_url or None,
            temperature=0.1,
            max_tokens=512,
            disable_thinking=disable_thinking,
        )

    def _heuristic_plan(self, message: str, app_state: dict[str, Any]) -> dict[str, Any]:
        text = message.lower()
        store = app_state["settings"]
        country = store.get("xiaomi_cloud_country", "cn")

        qr_keywords = (
            "二维码", "扫码", "米家", "小米", "qr", "xiaomi", "mi home", "mihome",
        )
        scan_keywords = (
            "扫描设备", "扫描屋内", "发现设备", "搜索设备", "scan", "discover",
        )

        if any(k in text for k in qr_keywords):
            return {
                "action": "start_xiaomi_qr_scan",
                "params": {"country": country},
                "reply": "我来生成米家扫码二维码。请让客户用米家 App 扫码，完成后我会继续拉取屋内设备。",
            }

        if any(k in text for k in scan_keywords):
            return {
                "action": "scan_local_devices",
                "params": {},
                "reply": "我先执行一次局域网设备扫描，看看当前能直接发现哪些设备。",
            }

        return {
            "action": "none",
            "params": {},
            "reply": "如果你要我帮你发现屋内设备，可以直接说“扫描设备”或“生成小米扫码二维码”。",
        }

    def _heuristic_skill_creation_plan(self, message: str) -> dict[str, Any]:
        text = message.lower()
        if "技能" in text or "skill" in text:
            return {
                "action": "create_custom_skill",
                "params": {"request": message},
                "reply": "我会根据你的描述生成一个自定义 skill，放到 `skills/custom/` 下面。",
            }

        return {
            "action": "none",
            "params": {},
            "reply": "如果你要我帮你新增 skill，可以直接描述这个 skill 要解决什么问题。",
        }

    def _extract_action_plan(self, text: str) -> dict[str, Any] | None:
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

        action = data.get("action")
        if not isinstance(action, str):
            return None

        return {
            "action": action,
            "params": data.get("params", {}) if isinstance(data.get("params", {}), dict) else {},
            "reply": data.get("reply", "") if isinstance(data.get("reply", ""), str) else "",
        }
