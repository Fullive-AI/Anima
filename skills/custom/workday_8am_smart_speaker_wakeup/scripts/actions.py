from core.models import DeviceCommand


def activate_wakeup_alarm(alarm_time: str) -> DeviceCommand:
    return DeviceCommand(
        device_type="smart_speaker",
        command="play_wakeup_alarm",
        payload={"alarm_time": alarm_time, "trigger_source": "workday_alarm_skill"},
    )


def skip_scheduled_alarm() -> DeviceCommand:
    return DeviceCommand(device_type="smart_speaker", command="skip_scheduled_alarm", payload={})
