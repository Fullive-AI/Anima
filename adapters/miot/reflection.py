from __future__ import annotations

import enum
import inspect
from typing import Any

try:
    import miio
except ImportError:
    miio = None  # type: ignore[assignment]

from core.models import Capability

from .resolver import resolve_device_path


GENERIC_REFLECTION_CAPABILITIES = [
    Capability(
        name="miot_get_property",
        params={
            "label": "读取属性",
            "help": "通过 siid/piid 读取原始 MIoT 属性。",
            "inputs": [
                {"name": "siid", "required": True, "type": "number"},
                {"name": "piid", "required": True, "type": "number"},
            ],
        },
    ),
    Capability(
        name="miot_set_property",
        params={
            "label": "设置属性",
            "help": "通过 siid/piid/value 设置原始 MIoT 属性。",
            "inputs": [
                {"name": "siid", "required": True, "type": "number"},
                {"name": "piid", "required": True, "type": "number"},
                {"name": "value", "required": True, "type": "string"},
                {"name": "value_type", "required": False, "type": "enum", "options": ["int", "float", "bool", "str"]},
            ],
        },
    ),
    Capability(
        name="miot_call_action",
        params={
            "label": "调用动作",
            "help": "通过 siid/aiid/in 调用原始 MIoT 动作。",
            "inputs": [
                {"name": "siid", "required": True, "type": "number"},
                {"name": "aiid", "required": True, "type": "number"},
                {"name": "in", "required": False, "type": "string"},
            ],
        },
    ),
]


def build_capabilities(model: str, *, has_token: bool, mp5_factory: callable) -> list[Capability]:
    if not has_token:
        return []

    if model == "xiaomi.airp.mp5":
        return mp5_factory()

    path = resolve_device_path(model)
    if path.kind == "generic":
        return list(GENERIC_REFLECTION_CAPABILITIES)

    commands = getattr(path.device_class, "_device_group_commands", {})
    capabilities: list[Capability] = []
    for name, command in commands.items():
        if name in {"status", "info", "set_property_by", "get_property_by", "call_action", "call_action_by"}:
            continue
        if name.startswith("set_") or name in {"on", "off"}:
            capabilities.append(
                Capability(
                    name=name,
                    params={
                        "label": _format_capability_label(name),
                        "help": command.kwargs.get("help", ""),
                        "inputs": _extract_command_inputs(command),
                    },
                )
            )

    return capabilities or list(GENERIC_REFLECTION_CAPABILITIES)


def extract_command_inputs(command: Any) -> list[dict[str, Any]]:
    return _extract_command_inputs(command)


def coerce_command_value(value: Any, annotation: Any) -> Any:
    return _coerce_command_value(value, annotation)


def _extract_command_inputs(command: Any) -> list[dict[str, Any]]:
    decorated = _apply_click_decorators(command)
    click_params = getattr(decorated, "__click_params__", [])
    signature = inspect.signature(command.func)
    inputs: list[dict[str, Any]] = []

    for param in reversed(click_params):
        name = param.name
        if name == "self":
            continue

        sig_param = signature.parameters.get(name)
        annotation = sig_param.annotation if sig_param else inspect._empty
        input_meta: dict[str, Any] = {
            "name": name,
            "required": getattr(param, "required", False),
        }

        if annotation is not inspect._empty and inspect.isclass(annotation) and hasattr(annotation, "__members__"):
            input_meta["type"] = "enum"
            input_meta["options"] = [member.name.lower() for member in annotation]
        elif annotation in {int, float}:
            input_meta["type"] = "number"
        elif annotation is bool:
            input_meta["type"] = "boolean"
        elif getattr(param.type, "name", "") in {"int", "integer", "float"}:
            input_meta["type"] = "number"
        elif getattr(param.type, "name", "") in {"bool", "boolean"}:
            input_meta["type"] = "boolean"
        else:
            input_meta["type"] = "string"

        default = getattr(param, "default", inspect._empty)
        if default is not inspect._empty and str(default) != "Sentinel.UNSET":
            input_meta["default"] = default

        inputs.append(input_meta)

    return [item for item in inputs if item.get("required", False)]


def _coerce_command_value(value: Any, annotation: Any) -> Any:
    if annotation is inspect._empty:
        return value

    if inspect.isclass(annotation) and issubclass(annotation, enum.Enum):
        if isinstance(value, annotation):
            return value
        if isinstance(value, str):
            for member in annotation:
                if member.name.lower() == value.lower():
                    return member
                if str(member.value).lower() == value.lower():
                    return member
        return annotation(value)

    if annotation is bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in {"1", "true", "on", "yes"}
        return bool(value)

    if annotation is int:
        return int(value)

    if annotation is float:
        return float(value)

    return value


def _apply_click_decorators(command: Any) -> Any:
    def dummy():
        pass

    fn = dummy
    for decorator in command.decorators:
        fn = decorator(fn)
    return fn


def _format_capability_label(name: str) -> str:
    if name == "on":
        return "开启"
    if name == "off":
        return "关闭"
    return name.removeprefix("set_").replace("_", " ").title()
