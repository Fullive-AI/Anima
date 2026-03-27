from core.models import DeviceCommand, SkillPlanItem


async def execute(context: dict, plan_item: SkillPlanItem):
    discovery = context.get("discovery")
    if discovery is not None:
        action_name = _resolve_intent_action(plan_item)
        if action_name:
            devices = [
                device for device in discovery.get_devices_by_type("speaker")
                if getattr(device, "online", True)
            ] or discovery.get_devices_by_type("speaker")

            actions = []
            for device in devices:
                capabilities = {cap.name for cap in getattr(device, "capabilities", [])}
                if action_name not in capabilities:
                    continue
                actions.append(
                    {
                        "skill_name": "speaker",
                        "device_id": device.device_id,
                        "action": action_name,
                        "params": {},
                        "reason": plan_item.reason or plan_item.goal,
                        "expected_state": {},
                    }
                )
            if actions:
                return actions

    return await context["brain"].execute_device_skill("speaker", context, plan_item)


def _resolve_intent_action(plan_item: SkillPlanItem) -> str:
    text = f"{plan_item.goal} {plan_item.reason}".lower()
    if any(token in text for token in ("stop", "pause", "停止", "暂停")):
        return "stop_audio"
    if any(token in text for token in ("random", "music", "audio", "song", "播放", "音乐", "歌曲", "来一首")):
        return "play_random_audio"
    return ""


def turn_on(device_id: str, reason: str = "") -> DeviceCommand:
    return DeviceCommand(device_id=device_id, action="turn_on", params={}, source="brain", reason=reason)


def turn_off(device_id: str, reason: str = "") -> DeviceCommand:
    return DeviceCommand(device_id=device_id, action="turn_off", params={}, source="brain", reason=reason)


def play_random_audio(device_id: str, reason: str = "") -> DeviceCommand:
    return DeviceCommand(device_id=device_id, action="play_random_audio", params={}, source="brain", reason=reason)


def stop_audio(device_id: str, reason: str = "") -> DeviceCommand:
    return DeviceCommand(device_id=device_id, action="stop_audio", params={}, source="brain", reason=reason)


def play_audio_file(device_id: str, path: str, reason: str = "") -> DeviceCommand:
    return DeviceCommand(
        device_id=device_id,
        action="play_audio_file",
        params={"path": path},
        source="brain",
        reason=reason,
    )


def play_audio_url(device_id: str, url: str, reason: str = "") -> DeviceCommand:
    return DeviceCommand(
        device_id=device_id,
        action="play_audio_url",
        params={"url": url},
        source="brain",
        reason=reason,
    )
