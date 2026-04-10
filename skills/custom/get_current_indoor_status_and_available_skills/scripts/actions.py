from core.models import DeviceCommand


def retrieve_available_skills() -> DeviceCommand:
    return DeviceCommand(
        name="retrieve_available_skills",
        params={}
    )


def collect_indoor_sensor_data() -> DeviceCommand:
    return DeviceCommand(
        name="collect_indoor_sensor_data",
        params={}
    )


def present_compiled_information() -> DeviceCommand:
    return DeviceCommand(
        name="present_compiled_information",
        params={}
    )