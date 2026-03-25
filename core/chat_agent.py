from __future__ import annotations

import json
import logging
import re
from typing import Any

from langchain_openai import ChatOpenAI

from core.brain.skill_loader import SkillLoader
from core.config import settings as env_settings

logger = logging.getLogger(__name__)


class ChatAgent:
    def __init__(self, skill_loader: SkillLoader) -> None:
        self._skill_loader = skill_loader

    async def handle_message(self, message: str, app_state: dict[str, Any]) -> dict[str, Any]:
        text = message.strip()
        if not text:
            return {"reply": "请先输入你的需求。"}

        skill = self._skill_loader.get_skill("device_discovery")
        if not skill:
            return {"reply": "设备扫描能力尚未加载。"}

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

        result = await handler(
            context=app_state,
            params=plan.get("params", {}),
            reply=reply,
        )
        result.setdefault("reply", reply)
        result["action"] = action
        return result

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

    def _build_llm(self, app_state: dict[str, Any]) -> ChatOpenAI | None:
        store = app_state["settings"]
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
            temperature=0.1,
            max_tokens=512,
            extra_body=extra_body or None,
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
