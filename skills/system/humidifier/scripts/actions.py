from core.models import DeviceCommand


def set_humidity(device_id: str, value: int, reason: str = "") -> DeviceCommand:
    return DeviceCommand(
        device_id=device_id,
        action="set_humidity",
        params={"value": value},
        source="brain",
        reason=reason,
    )


def set_mode(device_id: str, mode: str, reason: str = "") -> DeviceCommand:
    return DeviceCommand(
        device_id=device_id,
        action="set_mode",
        params={"mode": mode},
        source="brain",
        reason=reason,
    )


def turn_on(device_id: str, reason: str = "") -> DeviceCommand:
    return DeviceCommand(device_id=device_id, action="turn_on", source="brain", reason=reason)


def turn_off(device_id: str, reason: str = "") -> DeviceCommand:
    return DeviceCommand(device_id=device_id, action="turn_off", source="brain", reason=reason)
