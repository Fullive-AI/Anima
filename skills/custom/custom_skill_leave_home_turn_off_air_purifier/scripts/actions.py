from core.models import DeviceCommand

def turn_off(device_id: str) -> DeviceCommand:
    return DeviceCommand(
        action="turn_off",
        params={},
        device_id=device_id
    )