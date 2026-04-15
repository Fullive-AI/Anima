from __future__ import annotations

import json
from typing import Any

try:
    import miio
    from miio.integrations.airpurifier.zhimi.airpurifier_miot import AirPurifierMiot
except ImportError:
    miio = None  # type: ignore[assignment]
    AirPurifierMiot = None  # type: ignore[assignment]

from .reflection import coerce_command_value, extract_command_inputs


def execute_action(dev: miio.Device, action: str, params: dict[str, Any]) -> None:
    if isinstance(dev, AirPurifierMiot) and getattr(dev, "model", "") == "xiaomi.airp.mp5":
        if _execute_mp5_command(dev, action, params):
            return

    if action in {"miot_get_property", "miot_set_property", "miot_call_action"}:
        _execute_generic_reflection(dev, action, params)
        return

    aliased = {
        "turn_on": "on",
        "turn_off": "off",
        "set_humidity": "set_target_humidity",
        "set_temperature": "set_target_temperature",
    }.get(action, action)

    if _execute_dynamic_command(dev, aliased, params):
        return

    if aliased == "turn_on" or aliased == "on":
        if hasattr(dev, "on"):
            dev.on()
            return
        _send_with_fallbacks(dev, [("set_power", ["on"]), ("power", ["on"])])
        return

    if aliased == "turn_off" or aliased == "off":
        if hasattr(dev, "off"):
            dev.off()
            return
        _send_with_fallbacks(dev, [("set_power", ["off"]), ("power", ["off"])])
        return

    if aliased in {"set_humidity", "set_target_humidity"}:
        value = _first_present(params, ("value", "humidity", "target_humidity", "relative_humidity"))
        if hasattr(dev, "set_target_humidity"):
            dev.set_target_humidity(value)
            return
        _send_with_fallbacks(
            dev, [("set_target_humidity", [value]), ("set_humidity", [value]), ("set_limit_hum", [value])]
        )
        return

    if aliased in {"set_temperature", "set_target_temperature"}:
        value = _first_present(params, ("value", "temperature", "target_temperature"))
        if hasattr(dev, "set_target_temperature"):
            dev.set_target_temperature(value)
            return
        _send_with_fallbacks(dev, [("set_target_temperature", [value]), ("set_temperature", [value])])
        return

    if aliased == "set_brightness":
        value = params.get("value")
        if hasattr(dev, "set_brightness"):
            dev.set_brightness(value)
            return
        _send_with_fallbacks(dev, [("set_bright", [value]), ("set_brightness", [value])])
        return

    if aliased == "set_color_temp":
        kelvin = params.get("kelvin")
        if hasattr(dev, "set_color_temp"):
            dev.set_color_temp(kelvin)
            return
        _send_with_fallbacks(dev, [("set_ct_abx", [kelvin, "smooth", 500])])
        return

    if aliased == "set_mode":
        mode = params.get("mode")
        if hasattr(dev, "set_mode"):
            dev.set_mode(mode)
            return
        _send_with_fallbacks(dev, [("set_mode", [mode])])
        return

    dev.send(aliased, list(params.values()) if params else [])


def _first_present(params: dict[str, Any], names: tuple[str, ...]) -> Any:
    for name in names:
        if name in params:
            return params[name]
    return None


def _execute_mp5_command(dev: AirPurifierMiot, action: str, params: dict[str, Any]) -> bool:
    if action in {"on", "turn_on"}:
        dev.set_property("power", True)
        return True
    if action in {"off", "turn_off"}:
        dev.set_property("power", False)
        return True
    if action == "set_mode":
        dev.set_property("mode", int(params.get("mode")))
        return True
    if action == "set_fan_level":
        dev.set_property("fan_level", int(params.get("level")))
        return True
    return False


def _execute_dynamic_command(dev: miio.Device, action: str, params: dict[str, Any]) -> bool:
    commands = getattr(dev.__class__, "_device_group_commands", {})
    command = commands.get(action)
    if not command:
        return False

    import inspect

    signature = inspect.signature(command.func)
    call_args: dict[str, Any] = {}
    for input_meta in extract_command_inputs(command):
        name = input_meta["name"]
        sig_param = signature.parameters.get(name)
        annotation = sig_param.annotation if sig_param else inspect._empty

        if name in params:
            call_args[name] = coerce_command_value(params[name], annotation)
        elif "default" in input_meta:
            call_args[name] = coerce_command_value(input_meta["default"], annotation)
        else:
            raise ValueError(f"Missing required parameter: {name}")

    command.call(dev, **call_args)
    return True


def _execute_generic_reflection(dev: miio.Device, action: str, params: dict[str, Any]) -> None:
    if action == "miot_get_property":
        dev.get_property_by(int(params["siid"]), int(params["piid"]))
        return
    if action == "miot_set_property":
        value_type = params.get("value_type")
        dev.set_property_by(
            int(params["siid"]),
            int(params["piid"]),
            params.get("value"),
            value_type=value_type,
        )
        return
    if action == "miot_call_action":
        raw_in = params.get("in", [])
        if isinstance(raw_in, str) and raw_in.strip():
            try:
                raw_in = json.loads(raw_in)
            except json.JSONDecodeError:
                raw_in = [raw_in]
        if not isinstance(raw_in, list):
            raw_in = [raw_in]
        dev.call_action_by(int(params["siid"]), int(params["aiid"]), raw_in)


def _send_with_fallbacks(dev: miio.Device, commands: list[tuple[str, list[Any]]]) -> None:
    last_error: Exception | None = None
    for method, args in commands:
        try:
            dev.send(method, args)
            return
        except Exception as exc:
            last_error = exc
    if last_error:
        raise last_error
