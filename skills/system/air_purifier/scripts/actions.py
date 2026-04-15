from core.models import DeviceCommand, SkillPlanItem


async def execute(context: dict, plan_item: SkillPlanItem):
    discovery = context.get("discovery")
    if discovery is not None:
        action_name = _resolve_intent_action(plan_item)
        if action_name:
            devices = [
                device for device in discovery.get_devices_by_type("air_purifier") if getattr(device, "online", True)
            ] or discovery.get_devices_by_type("air_purifier")

            actions = []
            for device in devices:
                capabilities = {cap.name for cap in getattr(device, "capabilities", [])}
                if action_name not in capabilities:
                    continue
                actions.append(
                    {
                        "skill_name": "air_purifier",
                        "device_id": device.device_id,
                        "action": action_name,
                        "params": {},
                        "reason": plan_item.reason or plan_item.goal,
                        "expected_state": {"power": action_name == "on"},
                    }
                )
            if actions:
                return actions

    return await context["brain"].execute_device_skill("air_purifier", context, plan_item)


def _resolve_intent_action(plan_item: SkillPlanItem) -> str:
    text = f"{plan_item.goal} {plan_item.reason}".lower()
    if any(token in text for token in ("turn off", "power off", "stop", "关闭", "关掉")):
        return "off"
    if any(token in text for token in ("turn on", "power on", "start", "开启", "打开")):
        return "on"
    return ""


def on(device_id: str, reason: str = "") -> DeviceCommand:
    return DeviceCommand(device_id=device_id, action="on", params={}, source="brain", reason=reason)


def off(device_id: str, reason: str = "") -> DeviceCommand:
    return DeviceCommand(device_id=device_id, action="off", params={}, source="brain", reason=reason)


def set_mode(device_id: str, mode: str, reason: str = "") -> DeviceCommand:
    return DeviceCommand(
        device_id=device_id,
        action="set_mode",
        params={"mode": mode},
        source="brain",
        reason=reason,
    )


def set_fan_level(device_id: str, level: int | float, reason: str = "") -> DeviceCommand:
    return DeviceCommand(
        device_id=device_id,
        action="set_fan_level",
        params={"level": level},
        source="brain",
        reason=reason,
    )
