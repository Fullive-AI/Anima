from __future__ import annotations

import logging
import re
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
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


class RoomRequest(BaseModel):
    name: str


class DeviceRoomRequest(BaseModel):
    room_id: str | None = None


class VirtualDeviceRequest(BaseModel):
    name: str
    device_type: str = "light"


class VirtualSensorUpdateRequest(BaseModel):
    sensors: dict[str, float | int | bool | str]


class DeviceRenameRequest(BaseModel):
    name: str


class UpdateCustomSkillRequest(BaseModel):
    mode: str = "structured"
    name: str
    description: str
    device_types: list[str]
    trigger_text: str = ""
    action_text: str = ""
    knowledge_md: str = ""
    decide_md: str = ""


SKILL_FOLDER_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")


def _validate_custom_skill_folder_name(folder_name: str) -> str:
    if not SKILL_FOLDER_RE.match(folder_name):
        raise HTTPException(status_code=400, detail="Invalid custom skill folder name")
    return folder_name


def _extract_markdown_section(body: str, heading: str) -> str:
    pattern = rf"(?ms)^##\s+{re.escape(heading)}\s*\n(.*?)(?=^##\s+|\Z)"
    match = re.search(pattern, body)
    return match.group(1).strip() if match else ""


def _render_custom_skill_md(
    *,
    name: str,
    description: str,
    device_types: list[str],
    version: str,
    trigger_text: str,
    action_text: str,
) -> str:
    frontmatter = [
        "---",
        f"name: {name}",
        f"description: {description}",
        "metadata:",
        "  device_types:",
        *[f"    - {device_type}" for device_type in device_types],
        f"  version: {version}",
        "---",
        "",
        f"# {name}",
        "",
        "## Trigger",
        trigger_text.strip() or "Describe when this custom skill should be triggered.",
        "",
        "## Action",
        action_text.strip() or "Describe what this custom skill should do when triggered.",
        "",
        "## Working Rules",
        "- Keep this skill narrowly scoped to the device types above.",
        "- Prefer safe no-op behaviour when required context is missing.",
        "",
        "## Success Criteria",
        "- The skill triggers under the intended conditions.",
        "- The skill performs the intended action safely and predictably.",
        "",
    ]
    return "\n".join(frontmatter)


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

        store = app_state["settings"]
        device_rooms = store.get("device_rooms", {})
        result = []
        for d in discovery.get_all_devices():
            data = d.model_dump()
            # Check if device needs token activation
            if miot:
                info = miot._device_infos.get(d.device_id, {})
                data["needs_token"] = info.get("needs_token", False)
                data["ip"] = info.get("ip", "")
            # Fill room from persistent store
            data["room"] = device_rooms.get(d.device_id, d.room)
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
            device_id,
            command.action,
            command.params,
        )
        return result.model_dump()

    @app.get("/api/rooms")
    async def list_rooms():
        store = app_state["settings"]
        return store.get("rooms", [])

    @app.post("/api/rooms")
    async def create_room(req: RoomRequest):
        store = app_state["settings"]
        import uuid

        rooms = store.get("rooms", [])
        room = {"room_id": str(uuid.uuid4()), "name": req.name.strip()}
        rooms.append(room)
        store.set("rooms", rooms)
        return room

    @app.put("/api/rooms/{room_id}")
    async def rename_room(room_id: str, req: RoomRequest):
        store = app_state["settings"]
        rooms = store.get("rooms", [])
        for r in rooms:
            if r["room_id"] == room_id:
                r["name"] = req.name.strip()
                store.set("rooms", rooms)
                return r
        raise HTTPException(status_code=404, detail="Room not found")

    @app.delete("/api/rooms/{room_id}")
    async def delete_room(room_id: str):
        store = app_state["settings"]
        rooms = [r for r in store.get("rooms", []) if r["room_id"] != room_id]
        store.set("rooms", rooms)
        # Clear room assignment from devices
        device_rooms = store.get("device_rooms", {})
        device_rooms = {k: v for k, v in device_rooms.items() if v != room_id}
        store.set("device_rooms", device_rooms)
        return {"success": True}

    @app.put("/api/devices/{device_id}/room")
    async def set_device_room(device_id: str, req: DeviceRoomRequest):
        store = app_state["settings"]
        device_rooms = store.get("device_rooms", {})
        if req.room_id is None:
            device_rooms.pop(device_id, None)
        else:
            device_rooms[device_id] = req.room_id
        store.set("device_rooms", device_rooms)
        # Update in-memory device object
        discovery = app_state["discovery"]
        device = discovery.get_device(device_id)
        if device:
            device.room = req.room_id
        return {"success": True}

    @app.post("/api/admin/virtual-devices")
    async def create_virtual_device(req: VirtualDeviceRequest):
        import uuid

        from adapters.virtual.adapter import VirtualAdapter
        from core.models import Event, EventType

        discovery = app_state["discovery"]
        store = app_state["settings"]

        virtual = next((a for a in discovery._adapters if isinstance(a, VirtualAdapter)), None)
        if not virtual:
            raise HTTPException(status_code=500, detail="Virtual adapter not available")

        device_id = f"virtual_{uuid.uuid4().hex[:8]}"
        name = req.name.strip() or f"虚拟{req.device_type}"
        device = virtual.register_device(device_id=device_id, name=name, device_type=req.device_type)

        discovery.devices[device_id] = device
        discovery._adapter_map[device_id] = virtual

        await discovery._bus.emit(
            Event(
                type=EventType.DEVICE_DISCOVERED,
                device_id=device_id,
                data=device.model_dump(),
            )
        )

        # Persist
        virtual_devices = store.get("virtual_devices", [])
        virtual_devices.append({"device_id": device_id, "name": name, "device_type": req.device_type})
        store.set("virtual_devices", virtual_devices)

        return {"success": True, "device_id": device_id, "name": name, "type": req.device_type}

    @app.delete("/api/admin/virtual-devices/{device_id}")
    async def delete_virtual_device(device_id: str):
        from adapters.virtual.adapter import VirtualAdapter

        discovery = app_state["discovery"]
        store = app_state["settings"]

        virtual = next((a for a in discovery._adapters if isinstance(a, VirtualAdapter)), None)
        if virtual:
            virtual.remove_device(device_id)

        discovery.devices.pop(device_id, None)
        discovery._adapter_map.pop(device_id, None)

        virtual_devices = [v for v in store.get("virtual_devices", []) if v["device_id"] != device_id]
        store.set("virtual_devices", virtual_devices)

        return {"success": True}

    @app.post("/api/devices/{device_id}/sensors")
    async def update_virtual_sensors(device_id: str, req: VirtualSensorUpdateRequest):
        """Manually update sensor values for a virtual device, triggering SENSOR_UPDATED."""
        from adapters.virtual.adapter import VirtualAdapter
        from core.models import Event, EventType

        discovery = app_state["discovery"]
        device = discovery.get_device(device_id)
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")

        virtual = next((a for a in discovery._adapters if isinstance(a, VirtualAdapter)), None)
        if not virtual or device_id not in virtual._devices:
            raise HTTPException(status_code=400, detail="Not a virtual device")

        state = virtual._states.setdefault(device_id, {})
        state.update(req.sensors)

        # Sync into device sensor objects
        for sensor in device.sensors:
            if sensor.name in req.sensors:
                sensor.value = req.sensors[sensor.name]

        # Emit SENSOR_UPDATED to trigger brain cycle
        await discovery._bus.emit(
            Event(
                type=EventType.SENSOR_UPDATED,
                device_id=device_id,
                data=dict(state),
            )
        )

        return {"success": True, "device_id": device_id, "updated": req.sensors}

    @app.patch("/api/devices/{device_id}/rename")
    async def rename_device(device_id: str, req: DeviceRenameRequest):
        discovery = app_state["discovery"]
        store = app_state["settings"]
        device = discovery.get_device(device_id)
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")
        device.name = req.name.strip()
        # Persist for virtual devices
        virtual_devices = store.get("virtual_devices", [])
        for v in virtual_devices:
            if v["device_id"] == device_id:
                v["name"] = device.name
        store.set("virtual_devices", virtual_devices)
        return {"success": True, "device_id": device_id, "name": device.name}

    @app.delete("/api/devices/{device_id}")
    async def delete_device(device_id: str):
        from adapters.virtual.adapter import VirtualAdapter

        discovery = app_state["discovery"]
        store = app_state["settings"]
        device = discovery.get_device(device_id)
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")
        # Remove from virtual adapter if applicable
        virtual = next((a for a in discovery._adapters if isinstance(a, VirtualAdapter)), None)
        if virtual and device_id in virtual._devices:
            virtual.remove_device(device_id)
            virtual_devices = [v for v in store.get("virtual_devices", []) if v["device_id"] != device_id]
            store.set("virtual_devices", virtual_devices)
        # Remove from discovery
        discovery.devices.pop(device_id, None)
        discovery._adapter_map.pop(device_id, None)
        # Remove room assignment
        device_rooms = store.get("device_rooms", {})
        device_rooms.pop(device_id, None)
        store.set("device_rooms", device_rooms)
        return {"success": True}

    @app.get("/api/brain/events")
    async def brain_events():
        """SSE stream for proactive brain notifications."""
        import asyncio

        queue: asyncio.Queue[str] = asyncio.Queue()
        app_state.setdefault("_brain_event_queues", []).append(queue)

        async def generate():
            try:
                yield 'data: {"type":"connected"}\n\n'
                while True:
                    try:
                        msg = await asyncio.wait_for(queue.get(), timeout=25.0)
                        yield f"data: {msg}\n\n"
                    except TimeoutError:
                        yield 'data: {"type":"ping"}\n\n'
            finally:
                queues = app_state.get("_brain_event_queues", [])
                if queue in queues:
                    queues.remove(queue)

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/api/chat")
    async def chat(body: dict):
        message = body.get("message", "")
        stream = body.get("stream", False)
        try:
            if stream:
                return StreamingResponse(
                    app_state["brain"].handle_chat_message_stream(message, app_state),
                    media_type="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
                )
            return await app_state["brain"].handle_chat_message(message, app_state)
        except Exception as exc:
            logger.exception("Chat request failed")
            return {
                "reply": f"聊天请求执行失败：{exc}",
                "error": "chat_request_failed",
            }

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

    @app.get("/api/memory")
    async def get_memory_debug():
        memory = app_state["memory"]
        preferences = await memory.get_preferences("default")
        learned_profiles_raw = await memory.get_learned_profiles("default")
        learned_profiles = {
            skill_type: memory.parse_learned_profile(content) for skill_type, content in learned_profiles_raw.items()
        }
        extracted_memories = await memory.get_extracted_memories("default")
        extraction_state = await memory.get_memory_extraction_state("default")
        history = await memory.get_history("default", limit=20)
        return {
            "preferences": preferences,
            "learned_profiles": learned_profiles,
            "memory_manifest": await memory.get_memory_manifest("default"),
            "extracted_memories": extracted_memories,
            "extraction_state": extraction_state,
            "recent_history": history,
        }

    @app.get("/api/skills")
    async def list_skills():
        skill_loader = app_state["brain"]._skill_loader
        skill_loader.discover()
        return {
            "system_skills": [item.__dict__ for item in skill_loader.list_system_skills_with_meta()],
            "custom_skills": [item.__dict__ for item in skill_loader.list_custom_skills_with_meta()],
        }

    @app.get("/api/skills/custom/{folder_name}")
    async def get_custom_skill_detail(folder_name: str):
        safe_folder_name = _validate_custom_skill_folder_name(folder_name)
        skill_loader = app_state["brain"]._skill_loader
        skill_loader.discover()

        custom_skill = next(
            (
                skill
                for skill in skill_loader._cache_by_name.values()
                if "custom" in skill.path.parts and skill.path.name == safe_folder_name
            ),
            None,
        )
        if custom_skill is None:
            raise HTTPException(status_code=404, detail="Custom skill not found")

        skill_md_path = custom_skill.path / "SKILL.md"
        if not skill_md_path.exists():
            raise HTTPException(status_code=404, detail="SKILL.md not found")

        skill_md = skill_md_path.read_text(encoding="utf-8")
        frontmatter, body = skill_loader._parse_frontmatter(skill_md)
        metadata = frontmatter.get("metadata", {}) if isinstance(frontmatter.get("metadata"), dict) else {}
        version = str(frontmatter.get("version") or metadata.get("version") or custom_skill.meta.version or "0.1.0")

        return {
            "meta": {
                "name": custom_skill.meta.name,
                "description": custom_skill.meta.description,
                "scope": "custom",
                "folder_name": safe_folder_name,
                "device_types": list(custom_skill.meta.device_types),
                "version": version,
                "path": str(custom_skill.path),
            },
            "content": {
                "skill_md": skill_md,
                "knowledge_md": (custom_skill.path / "references" / "knowledge.md").read_text(encoding="utf-8")
                if (custom_skill.path / "references" / "knowledge.md").exists()
                else "",
                "decide_md": (custom_skill.path / "references" / "decide.md").read_text(encoding="utf-8")
                if (custom_skill.path / "references" / "decide.md").exists()
                else "",
            },
            "structured": {
                "trigger_text": _extract_markdown_section(body, "Trigger"),
                "action_text": _extract_markdown_section(body, "Action"),
            },
            "editable": True,
        }

    @app.put("/api/skills/custom/{folder_name}")
    async def update_custom_skill(folder_name: str, body: UpdateCustomSkillRequest):
        safe_folder_name = _validate_custom_skill_folder_name(folder_name)
        skill_loader = app_state["brain"]._skill_loader
        skill_loader.discover()

        custom_skill = next(
            (
                skill
                for skill in skill_loader._cache_by_name.values()
                if "custom" in skill.path.parts and skill.path.name == safe_folder_name
            ),
            None,
        )
        if custom_skill is None:
            raise HTTPException(status_code=404, detail="Custom skill not found")
        if body.mode != "structured":
            raise HTTPException(status_code=400, detail="Only structured mode is supported")

        name = body.name.strip()
        description = body.description.strip()
        device_types = [device_type.strip() for device_type in body.device_types if device_type.strip()]
        if not name:
            raise HTTPException(status_code=400, detail="Skill name cannot be empty")
        if not description:
            raise HTTPException(status_code=400, detail="Skill description cannot be empty")
        if not device_types:
            raise HTTPException(status_code=400, detail="At least one device type is required")

        skill_md_path = custom_skill.path / "SKILL.md"
        existing_skill_md = skill_md_path.read_text(encoding="utf-8")
        frontmatter, _existing_body = skill_loader._parse_frontmatter(existing_skill_md)
        metadata = frontmatter.get("metadata", {}) if isinstance(frontmatter.get("metadata"), dict) else {}
        version = str(frontmatter.get("version") or metadata.get("version") or custom_skill.meta.version or "0.1.0")

        rendered_skill_md = _render_custom_skill_md(
            name=name,
            description=description,
            device_types=device_types,
            version=version,
            trigger_text=body.trigger_text,
            action_text=body.action_text,
        )

        references_dir = custom_skill.path / "references"
        references_dir.mkdir(parents=True, exist_ok=True)
        skill_md_path.write_text(rendered_skill_md, encoding="utf-8")
        (references_dir / "knowledge.md").write_text(body.knowledge_md or "", encoding="utf-8")

        decide_path = references_dir / "decide.md"
        if body.decide_md.strip():
            decide_path.write_text(body.decide_md, encoding="utf-8")
        elif not decide_path.exists():
            decide_path.write_text(
                "Use {current_data}, {capabilities}, {user_preferences}, {learned_profile}, {recent_history}, and {knowledge} to decide whether to return `none` or an action.",
                encoding="utf-8",
            )

        skill_loader.discover()
        updated_skill = next(
            (
                skill
                for skill in skill_loader._cache_by_name.values()
                if "custom" in skill.path.parts and skill.path.name == safe_folder_name
            ),
            None,
        )
        if updated_skill is None:
            raise HTTPException(status_code=500, detail="Skill reload failed after update")

        return {
            "status": "updated",
            "skill": skill_loader._to_inventory_item(updated_skill).__dict__,
        }

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
            await discovery._bus.emit(
                Event(
                    type=EventType.DEVICE_DISCOVERED,
                    device_id=device_id,
                    data=device.model_dump(),
                )
            )

        # Save to persistent config
        manual_devices = store.get("manual_devices", [])
        # Avoid duplicates
        manual_devices = [d for d in manual_devices if d.get("ip") != req.ip]
        manual_devices.append(
            {
                "ip": req.ip,
                "token": req.token,
                "name": name,
                "device_type": device_type,
                "model": model,
            }
        )
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
        import miio as miio_lib

        from adapters.miot.adapter import MIoTAdapter

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
            "ip": ip,
            "token": req.token,
            "model": model,
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
        manual_devices.append(
            {
                "ip": ip,
                "token": req.token,
                "name": device.name,
                "device_type": device_type,
                "model": model,
            }
        )
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
    async def xiaomi_qr_poll(body: dict | None = None):
        """Poll QR login status."""
        from adapters.miot.adapter import MIoTAdapter
        from adapters.miot.xiaomi_cloud import fetch_all_devices
        from core.models import Device

        flow = app_state.get("_xiaomi_qr_flow")
        if not flow:
            return {"status": "error", "error": "没有进行中的扫码登录"}

        region = (body or {}).get("country", "cn") or "cn"
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
                        "ip": ip,
                        "token": token,
                        "model": model,
                        "did": did,
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
                        "ip": ip,
                        "token": token,
                        "model": model,
                        "did": did,
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
        store.update(
            {
                "llm_api_key": req.api_key,
                "llm_model": req.model,
                "llm_base_url": req.base_url,
                "llm_disable_thinking": req.disable_thinking,
            }
        )
        return {"success": True, "model": req.model}

    return app
