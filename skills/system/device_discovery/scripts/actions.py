from __future__ import annotations

from typing import Any

from adapters.miot.xiaomi_cloud import QrLoginFlow


async def scan_local_devices(
    context: dict[str, Any],
    params: dict[str, Any] | None = None,
    reply: str = "",
) -> dict[str, Any]:
    discovery = context["discovery"]
    new_devices = await discovery.scan()
    return {
        "reply": reply or f"扫描完成，新增 {len(new_devices)} 台设备，当前共 {len(discovery.devices)} 台。",
        "new_devices": len(new_devices),
        "total": len(discovery.devices),
        "refresh_devices": True,
    }


async def start_xiaomi_qr_scan(
    context: dict[str, Any],
    params: dict[str, Any] | None = None,
    reply: str = "",
) -> dict[str, Any]:
    flow = QrLoginFlow()
    result = flow.start()
    if result["status"] == "error":
        return {
            "reply": result["error"],
            "error": result["error"],
        }

    context["_xiaomi_qr_flow"] = flow
    country = (params or {}).get("country", "cn") or "cn"
    qr_image_b64 = result.get("qr_image_b64", "")
    context["_xiaomi_qr_image_b64"] = qr_image_b64
    return {
        "reply": reply or "二维码已生成，请用米家 App 扫码。",
        "status": "qr_required",
        "country": country,
        "qr_image_b64": qr_image_b64,
    }
