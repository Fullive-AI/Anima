from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from core.models import DeviceCommand

logger = logging.getLogger(__name__)


class XiaomiLoginRequest(BaseModel):
    username: str
    password: str
    country: str = "cn"


class LLMConfigRequest(BaseModel):
    api_key: str
    model: str = "gpt-4o"
    base_url: str = ""
    disable_thinking: bool = False


class ManualDeviceRequest(BaseModel):
    ip: str
    token: str
    name: str = ""
    device_type: str = "unknown"


class ActivateDeviceRequest(BaseModel):
    token: str


def create_app(app_state: dict[str, Any]) -> FastAPI:
    app = FastAPI(title="Anima", description="Make Every Hardware Intelligent", version="0.1.0")

    def has_devices_needing_token() -> bool:
        discovery = app_state["discovery"]
        for adapter in discovery._adapters:
            infos = getattr(adapter, "_device_infos", {})
            for info in infos.values():
                if info.get("needs_token"):
                    return True
        return False

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health():
        return {"status": "ok", "version": "0.1.0"}

    @app.get("/api/devices")
    async def list_devices():
        from adapters.miot.adapter import MIoTAdapter
        discovery = app_state["discovery"]
        miot = next((a for a in discovery._adapters if isinstance(a, MIoTAdapter)), None)

        result = []
        for d in discovery.get_all_devices():
            data = d.model_dump()
            # Check if device needs token activation
            if miot:
                info = miot._device_infos.get(d.device_id, {})
                data["needs_token"] = info.get("needs_token", False)
                data["ip"] = info.get("ip", "")
            result.append(data)
        return result

    @app.get("/api/audio/{token}")
    async def get_audio_file(token: str):
        registry = app_state.get("audio_registry")
        if registry is None:
            raise HTTPException(status_code=404, detail="Audio registry not configured")

        entry = registry.get(token)
        if entry is None:
            raise HTTPException(status_code=404, detail="Audio file not found")

        return FileResponse(entry.path, media_type=entry.media_type, filename=entry.filename)

    @app.get("/api/devices/{device_id}")
    async def get_device(device_id: str):
        discovery = app_state["discovery"]
        device = discovery.get_device(device_id)
        if not device:
            return {"error": "Device not found"}, 404
        return device.model_dump()

    @app.post("/api/devices/{device_id}/command")
    async def send_command(device_id: str, command: DeviceCommand):
        discovery = app_state["discovery"]
        result = await discovery.execute_command(
            device_id, command.action, command.params,
        )
        return result.model_dump()

    @app.get("/api/rooms")
    async def list_rooms():
        return app_state.get("rooms", [])

    @app.post("/api/chat")
    async def chat(body: dict):
        message = body.get("message", "")
        return await app_state["brain"].handle_chat_message(message, app_state)

    @app.get("/api/onboarding/status")
    async def onboarding_status():
        store = app_state["settings"]
        flow = app_state.get("_xiaomi_qr_flow")
        qr_image_b64 = app_state.get("_xiaomi_qr_image_b64", "")
        if flow and qr_image_b64:
            return {
                "status": "qr_required",
                "qr_image_b64": qr_image_b64,
                "country": store.get("xiaomi_cloud_country", "cn"),
            }

        if not has_devices_needing_token() and len(store.get("xiaomi_cloud_devices", [])) > 0:
            return {"status": "connected"}

        return {"status": "idle"}

    @app.get("/api/decisions")
    async def list_decisions():
        memory = app_state["memory"]
        history = await memory.get_history("default", limit=50)
        return history

    @app.get("/api/environment")
    async def get_environment():
        brain = app_state["brain"]
        return brain.get_environment_state()

    @app.post("/api/environment/refresh")
    async def refresh_environment():
        discovery = app_state["discovery"]
        result = await discovery.refresh_device_states()
        brain = app_state["brain"]
        return {
            **result,
            "environment": brain.get_environment_state(),
        }

    @app.post("/api/scan")
    async def trigger_scan():
        discovery = app_state["discovery"]
        new_devices = await discovery.scan()
        ensure_system_skills = app_state.get("ensure_system_skills")
        if ensure_system_skills:
            await ensure_system_skills(app_state)
        return {"new_devices": len(new_devices), "total": len(discovery.devices)}

    @app.post("/api/devices/add")
    async def add_manual_device(req: ManualDeviceRequest):
        """Manually add a device by IP + token."""
        from adapters.miot.adapter import MIoTAdapter
        from core.models import Device, Event, EventType

        discovery = app_state["discovery"]
        store = app_state["settings"]

        # Find the MIoT adapter
        miot = next((a for a in discovery._adapters if isinstance(a, MIoTAdapter)), None)
        if not miot:
            return {"success": False, "error": "MIoT adapter not found"}

        # Try to probe the device to get model info
        model = "manual"
        try:
            import miio
            dev = miio.Device(ip=req.ip, token=req.token)
            info = dev.info()
            model = info.model or "manual"
        except Exception:
            pass  # probe failed, use manual defaults

        device_type = req.device_type if req.device_type != "unknown" else miot._guess_device_type(model)
        device_id = miot._build_device_id(req.ip, model)
        name = req.name or f"{model} ({req.ip})"

        device = Device(
            device_id=device_id,
            name=name,
            adapter="miot",
            type=device_type,
            online=True,
            capabilities=miot._build_capabilities(model, has_token=True),
            sensors=miot._default_sensors(device_type),
        )

        # Register in discovery + adapter
        miot._device_infos[device_id] = {"ip": req.ip, "token": req.token, "model": model}
        if device_id not in discovery.devices:
            discovery.devices[device_id] = device
            discovery._adapter_map[device_id] = miot
            await discovery._bus.emit(Event(
                type=EventType.DEVICE_DISCOVERED,
                device_id=device_id,
                data=device.model_dump(),
            ))

        # Save to persistent config
        manual_devices = store.get("manual_devices", [])
        # Avoid duplicates
        manual_devices = [d for d in manual_devices if d.get("ip") != req.ip]
        manual_devices.append({
            "ip": req.ip, "token": req.token, "name": name,
            "device_type": device_type, "model": model,
        })
        store.set("manual_devices", manual_devices)

        ensure_system_skills = app_state.get("ensure_system_skills")
        if ensure_system_skills:
            await ensure_system_skills(app_state, [device])

        return {
            "success": True,
            "device_id": device_id,
            "name": name,
            "type": device_type,
            "model": model,
        }

    @app.post("/api/devices/{device_id}/activate")
    async def activate_device(device_id: str, req: ActivateDeviceRequest):
        """Activate a discovered device by providing its token."""
        from adapters.miot.adapter import MIoTAdapter
        import miio as miio_lib

        discovery = app_state["discovery"]
        store = app_state["settings"]

        device = discovery.get_device(device_id)
        if not device:
            return {"success": False, "error": "设备未找到"}

        miot = next((a for a in discovery._adapters if isinstance(a, MIoTAdapter)), None)
        if not miot:
            return {"success": False, "error": "MIoT adapter not found"}

        info = miot._device_infos.get(device_id, {})
        ip = info.get("ip", "")
        if not ip:
            return {"success": False, "error": "设备 IP 未知"}

        # Try to probe device with the provided token
        model = "xiaomi.device"
        device_type = "unknown"
        try:
            dev = miio_lib.Device(ip=ip, token=req.token)
            dev_info = dev.info()
            model = dev_info.model or model
            device_type = miot._guess_device_type(model)
        except Exception as e:
            return {"success": False, "error": f"Token 验证失败: {e}"}

        # Update device info
        miot._device_infos[device_id] = {
            "ip": ip, "token": req.token, "model": model,
            "did": info.get("did", ""),
        }

        # Update device object
        device.name = f"{model} ({ip})"
        device.type = device_type
        device.capabilities = miot._build_capabilities(model, has_token=True)
        device.sensors = miot._default_sensors(device_type)

        # Save as manual device for persistence
        manual_devices = store.get("manual_devices", [])
        manual_devices = [d for d in manual_devices if d.get("ip") != ip]
        manual_devices.append({
            "ip": ip, "token": req.token, "name": device.name,
            "device_type": device_type, "model": model,
        })
        store.set("manual_devices", manual_devices)

        ensure_system_skills = app_state.get("ensure_system_skills")
        if ensure_system_skills:
            await ensure_system_skills(app_state, [device])

        return {
            "success": True,
            "device_id": device_id,
            "name": device.name,
            "type": device_type,
            "model": model,
        }

    # ── Settings API ──

    @app.get("/api/settings")
    async def get_settings():
        store = app_state["settings"]
        data = store.get_all()
        # Mask sensitive fields
        safe = dict(data)
        if "xiaomi_cloud_pass" in safe:
            safe["xiaomi_cloud_pass"] = "***"
        if "llm_api_key" in safe:
            safe["llm_api_key"] = safe["llm_api_key"][:8] + "***"
        return safe

    @app.get("/api/settings/xiaomi/status")
    async def xiaomi_status():
        store = app_state["settings"]
        device_count = len(store.get("xiaomi_cloud_devices", []))
        return {
            "configured": device_count > 0,
            "device_count": device_count,
            "country": store.get("xiaomi_cloud_country", "cn"),
        }

    @app.post("/api/settings/xiaomi/qr/start")
    async def xiaomi_qr_start():
        """Start QR code login flow."""
        from adapters.miot.xiaomi_cloud import QrLoginFlow
        flow = QrLoginFlow()
        result = flow.start()
        if result["status"] == "error":
            return {"success": False, "error": result["error"]}
        app_state["_xiaomi_qr_flow"] = flow
        app_state["_xiaomi_qr_image_b64"] = result.get("qr_image_b64", "")
        return {
            "success": True,
            "status": "qr_required",
            "qr_image_b64": result.get("qr_image_b64", ""),
        }

    @app.post("/api/settings/xiaomi/qr/poll")
    async def xiaomi_qr_poll(body: dict = {}):
        """Poll QR login status."""
        from adapters.miot.xiaomi_cloud import fetch_all_devices
        from adapters.miot.adapter import MIoTAdapter
        from core.models import Device, Event, EventType

        flow = app_state.get("_xiaomi_qr_flow")
        if not flow:
            return {"status": "error", "error": "没有进行中的扫码登录"}

        region = body.get("country", "cn") or "cn"
        result = flow.poll()

        if result["status"] == "qr_pending":
            return {"status": "qr_pending"}
        if result["status"] in ("error", "qr_expired"):
            app_state.pop("_xiaomi_qr_flow", None)
            app_state.pop("_xiaomi_qr_image_b64", None)
            return {"status": "error", "error": result.get("error", "登录失败")}
        if result["status"] != "ok":
            return {"status": "error", "error": "未知状态"}

        # Login OK — fetch devices
        try:
            cloud_devices = fetch_all_devices(flow.connector, region)
        except Exception as e:
            logger.exception("Failed to fetch devices after QR login")
            app_state.pop("_xiaomi_qr_flow", None)
            app_state.pop("_xiaomi_qr_image_b64", None)
            return {"status": "error", "error": f"获取设备列表失败: {e}"}

        app_state.pop("_xiaomi_qr_flow", None)
        app_state.pop("_xiaomi_qr_image_b64", None)
        store = app_state["settings"]
        store.set("xiaomi_cloud_devices", cloud_devices)
        store.set("xiaomi_cloud_country", region)

        # Register devices — merge with existing local-discovered devices by IP
        discovery = app_state["discovery"]
        miot = next((a for a in discovery._adapters if isinstance(a, MIoTAdapter)), None)
        registered = 0
        updated = 0
        if miot:
            # Build IP → existing device_id lookup
            ip_to_existing: dict[str, str] = {}
            for did_key, info in miot._device_infos.items():
                if info.get("ip"):
                    ip_to_existing[info["ip"]] = did_key

            for cd in cloud_devices:
                did = cd.get("did", "")
                if not did:
                    continue
                ip = cd.get("localip", "")
                token = cd.get("token", "")
                model = cd.get("model", "unknown")
                name = cd.get("name", model)
                device_type = miot._guess_device_type(model)
                has_token = bool(token) and token != "0" * 32

                # Check if this device already exists (matched by IP)
                existing_id = ip_to_existing.get(ip) if ip else None

                if existing_id and existing_id in discovery.devices:
                    # Update existing device with cloud data
                    device = discovery.devices[existing_id]
                    device.name = name
                    device.type = device_type
                    device.online = bool(cd.get("isOnline", False))
                    if has_token:
                        device.capabilities = miot._build_capabilities(model, has_token=True)
                        device.sensors = miot._default_sensors(device_type)
                    miot._device_infos[existing_id] = {
                        "ip": ip, "token": token, "model": model, "did": did,
                        "needs_token": not has_token,
                    }
                    updated += 1
                else:
                    # New device from cloud
                    device_id = f"miot_cloud_{did}"
                    device = Device(
                        device_id=device_id,
                        name=name,
                        adapter="miot",
                        type=device_type,
                        online=bool(cd.get("isOnline", False)),
                        capabilities=miot._build_capabilities(model, has_token=has_token),
                        sensors=miot._default_sensors(device_type) if has_token else [],
                    )
                    miot._device_infos[device_id] = {
                        "ip": ip, "token": token, "model": model, "did": did,
                        "needs_token": not has_token,
                    }
                    if device_id not in discovery.devices:
                        discovery.devices[device_id] = device
                        discovery._adapter_map[device_id] = miot
                        registered += 1

        ensure_system_skills = app_state.get("ensure_system_skills")
        if ensure_system_skills:
            await ensure_system_skills(app_state)

        return {
            "status": "ok",
            "cloud_devices": len(cloud_devices),
            "updated": updated,
            "registered": registered,
            "total": len(discovery.devices),
        }

    @app.post("/api/settings/xiaomi/disconnect")
    async def xiaomi_disconnect():
        store = app_state["settings"]
        store.delete("xiaomi_cloud_devices")
        store.delete("xiaomi_cloud_country")
        return {"success": True}

    @app.get("/api/settings/llm/status")
    async def llm_status():
        from core.runtime.config import settings as env_settings
        store = app_state["settings"]
        api_key = store.get("llm_api_key", "") or env_settings.llm_api_key
        # Mask key for display: show first 8 chars + ***
        masked_key = (api_key[:8] + "***") if api_key else ""
        disable_thinking = store.get("llm_disable_thinking", env_settings.llm_disable_thinking)
        return {
            "configured": bool(api_key),
            "masked_key": masked_key,
            "model": store.get("llm_model", "") or env_settings.llm_model,
            "base_url": store.get("llm_base_url", "") or env_settings.llm_base_url or "",
            "disable_thinking": disable_thinking,
            "source": "dashboard" if store.get("llm_api_key") else "env",
        }

    @app.post("/api/settings/llm/configure")
    async def llm_configure(req: LLMConfigRequest):
        store = app_state["settings"]
        store.update({
            "llm_api_key": req.api_key,
            "llm_model": req.model,
            "llm_base_url": req.base_url,
            "llm_disable_thinking": req.disable_thinking,
        })
        return {"success": True, "model": req.model}

    return app
