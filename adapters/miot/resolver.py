from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:
    import miio
    from miio.airconditioner_miot import AirConditionerMiot
    from miio.integrations.airpurifier.zhimi.airpurifier_miot import AirPurifierMiot
    from miio.integrations.humidifier.deerma.airhumidifier_jsqs import AirHumidifierJsqs
    from miio.integrations.humidifier.deerma.airhumidifier_mjjsq import AirHumidifierMjjsq
    from miio.integrations.humidifier.zhimi.airhumidifier import AirHumidifier
    from miio.integrations.light.yeelight.yeelight import Yeelight
except ImportError:
    miio = None  # type: ignore[assignment]
    AirConditionerMiot = None  # type: ignore[assignment]
    AirPurifierMiot = None  # type: ignore[assignment]
    AirHumidifierJsqs = None  # type: ignore[assignment]
    AirHumidifierMjjsq = None  # type: ignore[assignment]
    AirHumidifier = None  # type: ignore[assignment]
    Yeelight = None  # type: ignore[assignment]


@dataclass(frozen=True)
class DevicePath:
    kind: str
    device_class: type[miio.Device]


KNOWN_MODEL_CLASS_MAP: list[tuple[tuple[str, ...], type[miio.Device], str]] = [
    (("zhimi.humidifier",), AirHumidifier, "known"),
    (("deerma.humidifier.jsqs", "deerma.humidifier.jsq5", "deerma.humidifier.jsq2g"), AirHumidifierJsqs, "known"),
    (("deerma.humidifier.mjjsq", "deerma.humidifier.jsq", "deerma.humidifier.jsq1"), AirHumidifierMjjsq, "known"),
    (("xiaomi.aircondition", "midea.aircondition"), AirConditionerMiot, "known"),
    (("zhimi.airpurifier", "xiaomi.airp"), AirPurifierMiot, "known"),
    (("yeelink.light", "xiaomi.light", "philips.light"), Yeelight, "known"),
]


def resolve_device_path(model: str) -> DevicePath:
    for prefixes, device_class, kind in KNOWN_MODEL_CLASS_MAP:
        if model.startswith(prefixes):
            return DevicePath(kind=kind, device_class=device_class)
    return DevicePath(kind="generic", device_class=miio.Device)


def create_device_instance(info: dict[str, Any]) -> miio.Device:
    model = info.get("model", "")
    ip = info["ip"]
    token = info["token"]
    path = resolve_device_path(model)
    if path.device_class is miio.Device:
        return miio.Device(ip=ip, token=token, model=model or None)
    return path.device_class(ip=ip, token=token, model=model)
