from core.models import DeviceCommand, SkillPlanItem


async def execute(context: dict, plan_item: SkillPlanItem):
    return await context["brain"].execute_device_skill("speaker", context, plan_item)


def turn_on(device_id: str, reason: str = "") -> DeviceCommand:
    return DeviceCommand(device_id=device_id, action="turn_on", params={}, source="brain", reason=reason)


def turn_off(device_id: str, reason: str = "") -> DeviceCommand:
    return DeviceCommand(device_id=device_id, action="turn_off", params={}, source="brain", reason=reason)
