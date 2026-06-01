from core.models import DeviceCommand

# Replace these helpers with the exact actions your adapter supports.
# Keep parameter names aligned with the capability schema exposed by the device.
# Delete helpers you do not need.


def set_target(device_id: str, value: int, reason: str = "") -> DeviceCommand:
    return DeviceCommand(
        device_id=device_id,
        action="set_target",
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
