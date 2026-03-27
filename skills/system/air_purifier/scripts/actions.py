from core.models import DeviceCommand, SkillPlanItem


async def execute(context: dict, plan_item: SkillPlanItem):
    return await context["brain"].execute_device_skill("air_purifier", context, plan_item)


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
