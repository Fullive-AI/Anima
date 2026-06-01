from core.models import DeviceCommand


def activate_wakeup_alarm(device_id: str, alarm_time: str) -> DeviceCommand:
    return DeviceCommand(
        device_id=device_id,
        action="play_wakeup_alarm",
        params={"alarm_time": alarm_time, "trigger_source": "workday_alarm_skill"},
    )


def skip_scheduled_alarm(device_id: str) -> DeviceCommand:
    return DeviceCommand(device_id=device_id, action="skip_scheduled_alarm", params={})
