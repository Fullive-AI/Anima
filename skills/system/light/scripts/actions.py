from core.models import DeviceCommand


def set_brightness(device_id: str, value: int, reason: str = "") -> DeviceCommand:
    return DeviceCommand(
        device_id=device_id,
        action="set_brightness",
        params={"value": value},
        source="brain",
        reason=reason,
    )


def set_color_temp(device_id: str, kelvin: int, reason: str = "") -> DeviceCommand:
    return DeviceCommand(
        device_id=device_id,
        action="set_color_temp",
        params={"kelvin": kelvin},
        source="brain",
        reason=reason,
    )


def turn_on(device_id: str, reason: str = "") -> DeviceCommand:
    return DeviceCommand(device_id=device_id, action="turn_on", source="brain", reason=reason)


def turn_off(device_id: str, reason: str = "") -> DeviceCommand:
    return DeviceCommand(device_id=device_id, action="turn_off", source="brain", reason=reason)
