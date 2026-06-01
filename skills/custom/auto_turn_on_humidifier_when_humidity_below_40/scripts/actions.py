from core.models import DeviceCommand


def turn_on() -> DeviceCommand:
    return DeviceCommand(name="turn_on", params={})


def set_target_humidity(target_humidity: float) -> DeviceCommand:
    return DeviceCommand(name="set_target_humidity", params={"target_humidity": target_humidity})
