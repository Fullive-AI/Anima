from core.models import DeviceCommand

def turn_on() -> DeviceCommand:
    return DeviceCommand(action="turn_on", params={})

def turn_off() -> DeviceCommand:
    return DeviceCommand(action="turn_off", params={})