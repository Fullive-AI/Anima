from __future__ import annotations

from typing import Any

import miio


def default_sensors(device_type: str, *, include_generic: bool = False) -> list[tuple[str, str]]:
    type_sensors = {
        "humidifier": [("humidity", "%"), ("temperature", "°C"), ("water_level", "%")],
        "air_conditioner": [("temperature", "°C")],
        "light": [("brightness", "%"), ("color_temp", "K")],
    }
    sensors = [("power", "on/off"), *type_sensors.get(device_type, [])]
    if include_generic and device_type == "unknown":
        sensors.extend([("miot_online", "bool")])
    return sensors


def read_sensor_snapshot(device_type: str, dev: miio.Device) -> dict[str, Any]:
    if not hasattr(dev, "status"):
        return {}

    status = dev.status()
    if device_type == "humidifier":
        return _filter_none(_read_humidifier_status(status))
    if device_type == "air_conditioner":
        return _filter_none(_read_air_conditioner_status(status))
    if device_type == "light":
        return _filter_none(_read_light_status(status))
    return _filter_none(_read_generic_status(status))


def _read_humidifier_status(status: Any) -> dict[str, Any]:
    snapshot: dict[str, Any] = {"power": _extract_power_status(status)}

    humidity = _read_status_field(status, "relative_humidity")
    if humidity is None:
        humidity = _read_status_field(status, "humidity")
    snapshot["humidity"] = humidity
    snapshot["temperature"] = _read_status_field(status, "temperature")

    water_level = _read_status_field(status, "water_level")
    if water_level is not None:
        snapshot["water_level"] = water_level
        return snapshot

    tank_filed = _read_status_field(status, "tank_filed")
    water_shortage = _read_status_field(status, "water_shortage_fault")
    no_water = _read_status_field(status, "no_water")
    tank_detached = _read_status_field(status, "water_tank_detached")

    if tank_filed is True:
        snapshot["water_level"] = 100
    elif water_shortage is True or no_water is True or tank_detached is True:
        snapshot["water_level"] = 0
    return snapshot


def _read_air_conditioner_status(status: Any) -> dict[str, Any]:
    return {
        "power": _extract_power_status(status),
        "temperature": _read_status_field(status, "temperature"),
    }


def _read_light_status(status: Any) -> dict[str, Any]:
    return {
        "power": _extract_power_status(status),
        "brightness": _read_status_field(status, "brightness"),
        "color_temp": _read_status_field(status, "color_temp"),
    }


def _read_generic_status(status: Any) -> dict[str, Any]:
    return {
        "power": _extract_power_status(status),
        "miot_online": True,
    }


def _extract_power_status(status: Any) -> bool | None:
    for field in ("is_on", "power"):
        value = _read_status_field(status, field)
        if value is not None:
            return _normalize_power_value(value)
    return None


def _read_status_field(status: Any, name: str) -> Any:
    if isinstance(status, dict) and name in status:
        return status[name]
    if hasattr(status, name):
        value = getattr(status, name)
        if callable(value):
            try:
                return value()
            except TypeError:
                return None
        return value
    return None


def _normalize_power_value(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.lower()
        if lowered in {"on", "true", "1"}:
            return True
        if lowered in {"off", "false", "0"}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return None


def _filter_none(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in snapshot.items() if value is not None}
