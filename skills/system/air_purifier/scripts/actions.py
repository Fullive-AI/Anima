from core.models import DeviceCommand

def on() -> DeviceCommand:
    return DeviceCommand(action="on", params={})

def off() -> DeviceCommand:
    return DeviceCommand(action="off", params={})

def set_mode(mode: str) -> DeviceCommand:
    return DeviceCommand(action="set_mode", params={"mode": mode})

def set_fan_level(level: int | float) -> DeviceCommand:
    return DeviceCommand(action="set_fan_level", params={"level": level})