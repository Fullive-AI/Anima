from __future__ import annotations

import hashlib
import logging
import re
from typing import Any

try:
    import miio
    from miio.integrations.airpurifier.zhimi.airpurifier_miot import AirPurifierMiot

    MIIO_AVAILABLE = True
except ImportError:
    miio = None  # type: ignore[assignment]
    AirPurifierMiot = None  # type: ignore[assignment]
    MIIO_AVAILABLE = False

from adapters.base import BaseAdapter
from core.models import ActionResult, Capability, Device, Sensor

from .executors import execute_action
from .extractors import default_sensors, read_sensor_snapshot
from .reflection import build_capabilities
from .resolver import create_device_instance, resolve_device_path

logger = logging.getLogger(__name__)

# Alias newer Xiaomi purifier model names to the closest supported MIoT mapping
# from python-miio so dynamic commands can resolve set_property() mappings.
if MIIO_AVAILABLE and AirPurifierMiot is not None:
    if "xiaomi.airp.mp5" not in AirPurifierMiot._mappings and "zhimi.airp.mb5" in AirPurifierMiot._mappings:
        AirPurifierMiot._mappings["xiaomi.airp.mp5"] = AirPurifierMiot._mappings["zhimi.airp.mb5"]

# Model prefix → device type mapping
MODEL_TYPE_MAP = {
    "zhimi.humidifier": "humidifier",
    "deerma.humidifier": "humidifier",
    "zhimi.airpurifier": "air_purifier",
    "xiaomi.airp": "air_purifier",
    "xiaomi.aircondition": "air_conditioner",
    "midea.aircondition": "air_conditioner",
    "yeelink.light": "light",
    "xiaomi.light": "light",
    "philips.light": "light",
    "dreame.vacuum": "vacuum",
    "roborock.vacuum": "vacuum",
    "lumi.curtain": "curtain",
    "lumi.sensor": "sensor",
    "lumi.gateway": "gateway",
    "chuangmi.plug": "plug",
    "chuangmi.camera": "camera",
    "xiaomi.wifispeaker": "speaker",
    "xiaomi.repeater": "repeater",
}


class MIoTAdapter(BaseAdapter):
    name = "miot"

    def __init__(self, settings_store=None, speaker_player=None) -> None:
        self._known_devices: dict[str, Any] = {}
        # token-based ID 后，同一个 device_id 的 IP 可能变化；这里记录缓存对应的连接参数。
        self._known_device_keys: dict[str, tuple[str, str, str]] = {}
        self._device_infos: dict[str, dict] = {}
        self._settings = settings_store
        self._speaker_player = speaker_player
        self._cloud_logged_in = False

    def _guess_device_type(self, model: str) -> str:
        for prefix, dtype in MODEL_TYPE_MAP.items():
            if model.startswith(prefix):
                return dtype
        return "unknown"

    def _is_valid_token(self, token: str) -> bool:
        token = str(token or "").strip().lower()
        return bool(re.fullmatch(r"[0-9a-f]{32}", token)) and token != "0" * 32 and token != "f" * 32

    def _build_device_id_from_token(self, token: str) -> str:
        # 不把明文 token 暴露为 device_id；同一 token 的 hash 会稳定生成同一个展示 ID。
        token = str(token or "").strip().lower()
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]
        return f"miot_token_{digest}"

    def _build_pending_device_id_from_did(self, did: str) -> str:
        # 局域网扫描通常没有真实 token，先用 did 生成临时 ID，等激活后迁移到 token ID。
        return f"miot_pending_{did}"

    def _build_pending_device_id_from_ip(self, ip: str, model: str) -> str:
        safe_ip = ip.replace(".", "_")
        safe_model = (model or "unknown").replace(".", "_")
        return f"miot_pending_{safe_ip}_{safe_model}"

    def _build_device_id(
        self,
        ip: str = "",
        model: str = "",
        *,
        token: str = "",
        did: str = "",
    ) -> str:
        token = str(token or "").strip().lower()
        did = str(did or "").strip()

        # 统一身份优先级：真实控制 token > did 临时身份 > ip/model 兜底临时身份。
        if self._is_valid_token(token):
            return self._build_device_id_from_token(token)
        if did:
            return self._build_pending_device_id_from_did(did)
        return self._build_pending_device_id_from_ip(ip, model)

    def _build_device_id_from_did(self, did: str) -> str:
        return self._build_device_id(did=did)

    def _cached_cloud_info_by_did(self) -> dict[str, dict[str, Any]]:
        # 本地扫描只能稳定拿到 did/ip；用 did 到云端缓存里补 token/model/name。
        if not self._settings:
            return {}

        result: dict[str, dict[str, Any]] = {}
        for item in self._settings.get("xiaomi_cloud_devices", []) or []:
            did = str(item.get("did", "")).strip()
            token = str(item.get("token", "")).strip().lower()
            if did and self._is_valid_token(token):
                result[did] = dict(item)
        return result

    def _set_device_info(self, device_id: str, info: dict[str, Any]) -> None:
        # 集中更新连接信息，并让旧 miio 实例失效，避免继续访问旧 IP。
        current = dict(self._device_infos.get(device_id, {}))
        current.update({key: value for key, value in info.items() if value not in (None, "")})
        self._device_infos[device_id] = current
        self._known_devices.pop(device_id, None)
        self._known_device_keys.pop(device_id, None)

    def _merge_device_object(self, target: Device, incoming: Device) -> Device:
        target.name = incoming.name or target.name
        if target.type == "unknown" or incoming.type != "unknown":
            target.type = incoming.type
        target.online = incoming.online
        if incoming.capabilities:
            target.capabilities = incoming.capabilities
        if incoming.sensors:
            target.sensors = incoming.sensors
        return target

    def _append_or_merge_discovered_device(
        self,
        devices: list[Device],
        device: Device,
        seen_ids: set[str],
        seen_ips: set[str],
    ) -> None:
        # 不同来源可能归一到同一个 token ID；这里合并 Device 展示信息，避免重复展示。
        info = self._device_infos.get(device.device_id, {})
        ip = info.get("ip", "")
        if ip:
            seen_ips.add(ip)

        if device.device_id in seen_ids:
            existing = next((d for d in devices if d.device_id == device.device_id), None)
            if existing is not None:
                self._merge_device_object(existing, device)
            return

        seen_ids.add(device.device_id)
        devices.append(device)

    async def _discover_cloud(self) -> list[Device]:
        if not self._settings:
            return []

        creds = self._settings.get_xiaomi_credentials()
        if not creds:
            logger.debug("No Xiaomi Cloud credentials configured, skipping cloud discovery")
            return []

        username, password = creds
        country = self._settings.get_xiaomi_country()
        devices: list[Device] = []

        try:
            from micloud import MiCloud

            mc = MiCloud(username=username, password=password)
            mc.login()
            self._cloud_logged_in = True

            cloud_devices = mc.get_devices(country=country) or []
            logger.info("Xiaomi Cloud returned %d devices (country=%s)", len(cloud_devices), country)

            for cd in cloud_devices:
                try:
                    did = str(cd.get("did", ""))
                    ip = cd.get("localip", "")
                    token = cd.get("token", "")
                    model = cd.get("model", "unknown")
                    name = cd.get("name", model)
                    is_online = cd.get("isOnline", False)

                    if not did:
                        continue

                    # 云端能拿到 token 时直接生成最终 token-based ID。
                    device_id = self._build_device_id(token=token, did=did, ip=ip, model=model)
                    device_type = self._guess_device_type(model)
                    has_token = self._is_valid_token(token)

                    device = Device(
                        device_id=device_id,
                        name=name,
                        adapter=self.name,
                        type=device_type,
                        online=bool(is_online),
                        capabilities=self._build_capabilities(model, has_token=has_token),
                        sensors=self._default_sensors(device_type) if has_token else [],
                    )
                    devices.append(device)

                    self._set_device_info(
                        device_id,
                        {
                            "ip": ip,
                            "token": token if has_token else "",
                            "model": model,
                            "did": did,
                            "source": "cloud",
                            "needs_token": not has_token,
                        },
                    )
                except Exception:
                    logger.exception("Failed to process cloud device: %s", cd.get("did", "?"))
        except Exception as exc:
            self._cloud_logged_in = False
            logger.exception("Xiaomi Cloud discovery failed: %s", exc)

        return devices

    async def _load_cached_cloud_devices(self) -> list[Device]:
        if not self._settings:
            return []

        cached_devices = self._settings.get("xiaomi_cloud_devices", []) or []
        devices: list[Device] = []
        for cd in cached_devices:
            did = str(cd.get("did", "")).strip()
            if not did:
                continue

            ip = cd.get("localip", "")
            token = cd.get("token", "")
            model = cd.get("model", "unknown")
            name = cd.get("name", model)
            is_online = bool(cd.get("isOnline", False))

            # 启动时读取云端缓存也必须使用同一套 ID 规则，避免重启后回到旧 ID。
            device_id = self._build_device_id(token=token, did=did, ip=ip, model=model)
            device_type = self._guess_device_type(model)
            has_token = self._is_valid_token(token)
            devices.append(
                Device(
                    device_id=device_id,
                    name=name,
                    adapter=self.name,
                    type=device_type,
                    online=is_online,
                    capabilities=self._build_capabilities(model, has_token=has_token),
                    sensors=self._default_sensors(device_type) if has_token else [],
                )
            )

            self._set_device_info(
                device_id,
                {
                    "ip": ip,
                    "token": token if has_token else "",
                    "model": model,
                    "did": did,
                    "source": "cloud_cache",
                    "needs_token": not has_token,
                },
            )

        if devices:
            logger.info("Loaded %d cached Xiaomi cloud devices from config", len(devices))
        return devices

    async def _discover_local(self) -> list[Device]:
        import socket
        import struct

        hello = bytes.fromhex("21310020ffffffffffffffffffffffffffffffffffffffffffffffffffffffff")
        port = 54321
        devices: list[Device] = []
        # local scan 若没有 token，会尝试用 did 从云端缓存补齐 token。
        cloud_info_by_did = self._cached_cloud_info_by_did()

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.settimeout(3)
            sock.sendto(hello, ("<broadcast>", port))
            logger.info("Sent miio UDP broadcast on port %d...", port)

            while True:
                try:
                    data, addr = sock.recvfrom(1024)
                    ip = addr[0]

                    if len(data) < 32 or data[:2] != b"\x21\x31":
                        continue

                    did = struct.unpack(">I", data[8:12])[0]
                    did_str = str(did)
                    token_bytes = data[16:32]
                    token = token_bytes.hex()
                    has_token = self._is_valid_token(token)
                    cloud_info = cloud_info_by_did.get(did_str, {})
                    cloud_token = str(cloud_info.get("token", "")).strip().lower()
                    # 真实扫描 token 优先；多数设备会返回空 token，此时用云端缓存 token。
                    resolved_token = token if has_token else cloud_token

                    model = str(cloud_info.get("model", "") or "xiaomi.device")
                    name = str(cloud_info.get("name", "") or "")
                    device_type = "unknown"
                    if self._is_valid_token(resolved_token):
                        try:
                            dev = miio.Device(ip=ip, token=resolved_token)
                            info = dev.info()
                            model = info.model or model
                            device_type = self._guess_device_type(model)
                        except Exception:
                            logger.debug("Failed to inspect local MIoT model for %s", ip, exc_info=True)
                            device_type = self._guess_device_type(model)

                    has_resolved_token = self._is_valid_token(resolved_token)
                    # 有 token 就归一到最终 ID；没有 token 就保留 pending DID ID 等待激活。
                    device_id = self._build_device_id(token=resolved_token, did=did_str, ip=ip, model=model)

                    if not name:
                        name = f"小米设备 ({ip})" if not has_resolved_token else f"{model} ({ip})"
                    device = Device(
                        device_id=device_id,
                        name=name,
                        adapter=self.name,
                        type=device_type,
                        online=True,
                        capabilities=self._build_capabilities(model, has_token=has_resolved_token),
                        sensors=self._default_sensors(device_type) if has_resolved_token else [],
                    )
                    devices.append(device)

                    base_info = {
                        "ip": ip,
                        "token": resolved_token if has_resolved_token else "",
                        "model": model,
                        "did": did_str,
                        "source": "local",
                        "needs_token": not has_resolved_token,
                    }
                    self._set_device_info(device_id, base_info)

                    logger.info(
                        "Local scan: ip=%s did=%d token=%s", ip, did, "available" if has_resolved_token else "needs_setup"
                    )
                except TimeoutError:
                    break

            sock.close()
        except Exception:
            logger.exception("UDP broadcast discovery failed")

        logger.info("Local scan found %d Xiaomi devices", len(devices))
        return devices

    async def _load_manual_devices(self) -> list[Device]:
        if not self._settings:
            return []

        manual = self._settings.get("manual_devices", [])
        devices: list[Device] = []
        for md in manual:
            ip = md.get("ip", "")
            token = md.get("token", "")
            model = md.get("model", "manual")
            name = md.get("name", f"{model} ({ip})")
            device_type = md.get("device_type", self._guess_device_type(model))
            did = str(md.get("did", "")).strip()
            # 手动设备重启加载时也重新计算 token ID，不信任旧配置里的历史 device_id。
            device_id = self._build_device_id(ip, model, token=token, did=did)
            has_token = self._is_valid_token(token)

            device = Device(
                device_id=device_id,
                name=name,
                adapter=self.name,
                type=device_type,
                online=True,
                capabilities=self._build_capabilities(model, has_token=has_token),
                sensors=self._default_sensors(device_type) if has_token else [],
            )
            devices.append(device)
            self._set_device_info(
                device_id,
                {
                    "ip": ip,
                    "token": token if has_token else "",
                    "model": model,
                    "did": did,
                    "source": "manual",
                    "needs_token": not has_token,
                },
            )

        if manual:
            logger.info("Loaded %d manual devices from config", len(manual))
        return devices

    async def discover(self) -> list[Device]:
        if not MIIO_AVAILABLE:
            logger.warning("python-miio not installed, MIoT adapter disabled. Install with: uv sync --extra miot")
            return []
        seen_ips: set[str] = set()
        seen_ids: set[str] = set()
        devices: list[Device] = []

        # 三种来源统一进入 append/merge，token ID 相同的设备会被合并。
        manual = await self._load_manual_devices()
        for device in manual:
            self._append_or_merge_discovered_device(devices, device, seen_ids, seen_ips)

        cached_cloud = await self._load_cached_cloud_devices()
        for device in cached_cloud:
            self._append_or_merge_discovered_device(devices, device, seen_ids, seen_ips)

        cloud = await self._discover_cloud()
        for device in cloud:
            self._append_or_merge_discovered_device(devices, device, seen_ids, seen_ips)

        local = await self._discover_local()
        for device in local:
            info = self._device_infos.get(device.device_id, {})
            ip = info.get("ip", "")
            if device.device_id in seen_ids:
                self._append_or_merge_discovered_device(devices, device, seen_ids, seen_ips)
                continue
            if ip and ip in seen_ips:
                continue
            self._append_or_merge_discovered_device(devices, device, seen_ids, seen_ips)

        logger.info(
            "MIoT discovered %d devices total (%d manual, %d cloud, %d local)",
            len(devices),
            len(manual),
            len(cached_cloud) + len(cloud),
            len(local),
        )
        return devices

    def _get_miio_device(self, device_id: str) -> Any | None:
        if not MIIO_AVAILABLE:
            return None

        info = self._device_infos.get(device_id)
        if not info:
            return None

        expected_cls = resolve_device_path(info.get("model", "")).device_class
        # token-based ID 下 IP 会被 local scan 更新；缓存 key 不一致时必须重建 miio 连接对象。
        cache_key = (
            str(info.get("ip", "")),
            str(info.get("token", "")),
            str(info.get("model", "")),
        )
        cached = self._known_devices.get(device_id)
        if cached is not None and isinstance(cached, expected_cls) and self._known_device_keys.get(device_id) == cache_key:
            return cached

        try:
            dev = create_device_instance(info)
            self._known_devices[device_id] = dev
            self._known_device_keys[device_id] = cache_key
            return dev
        except Exception:
            logger.exception("Failed to create miio device for %s", device_id)
            return None

    async def subscribe(self, device: Device) -> None:
        dev = self._get_miio_device(device.device_id)
        if not dev:
            return

        try:
            snapshot = read_sensor_snapshot(device.type, dev)
        except Exception:
            logger.exception("Failed to refresh MIoT sensor state for %s", device.device_id)
            return

        if not snapshot:
            return

        for sensor in device.sensors:
            if sensor.name in snapshot:
                sensor.value = snapshot[sensor.name]

    async def execute(self, device_id: str, action: str, params: dict[str, Any]) -> ActionResult:
        if action in {"play_audio_file", "play_audio_url", "play_random_audio", "stop_audio"}:
            return await self._execute_speaker_action(device_id, action, params)

        dev = self._get_miio_device(device_id)
        if not dev:
            return ActionResult(
                device_id=device_id,
                action=action,
                success=False,
                message=f"Device {device_id} not found or not reachable",
            )

        try:
            execute_action(dev, action, params)
            logger.info("MIoT execute: %s.%s(%s) → OK", device_id, action, params)
            return ActionResult(device_id=device_id, action=action, success=True)
        except Exception as exc:
            logger.exception("MIoT execute failed: %s.%s", device_id, action)
            return ActionResult(device_id=device_id, action=action, success=False, message=str(exc))

    def _build_capabilities(self, model: str, has_token: bool = True) -> list[Capability]:
        if model.startswith("xiaomi.wifispeaker") and has_token:
            return [
                Capability(
                    name="play_audio_file",
                    params={
                        "label": "播放本地音频",
                        "help": "Enter the absolute path on the Anima host, e.g. /path/to/audio.wav",
                        "inputs": [{"name": "path", "required": True, "type": "string"}],
                    },
                ),
                Capability(
                    name="play_audio_url",
                    params={
                        "label": "播放音频 URL",
                        "help": "输入音箱可直接访问的 HTTP 音频地址。",
                        "inputs": [{"name": "url", "required": True, "type": "string"}],
                    },
                ),
                Capability(
                    name="play_random_audio",
                    params={
                        "label": "随机播放一首",
                        "help": "从本地音频库目录随机挑选一首播放。",
                        "inputs": [],
                    },
                ),
                Capability(name="stop_audio", params={"label": "停止播放", "help": "停止当前音频播放。", "inputs": []}),
            ]
        return build_capabilities(model, has_token=has_token, mp5_factory=self._build_mp5_capabilities)

    async def _execute_speaker_action(self, device_id: str, action: str, params: dict[str, Any]) -> ActionResult:
        info = self._device_infos.get(device_id)
        if not info:
            return ActionResult(
                device_id=device_id,
                action=action,
                success=False,
                message=f"Speaker info for {device_id} not found",
            )

        if not self._speaker_player:
            return ActionResult(
                device_id=device_id,
                action=action,
                success=False,
                message="Speaker playback service is not configured",
            )

        try:
            if action == "play_audio_file":
                path = str(params.get("path", "")).strip()
                if not path:
                    raise ValueError("Missing required parameter: path")
                result = await self._speaker_player.play_file(info, path)
                return ActionResult(
                    device_id=device_id, action=action, success=True, message=str(result.get("url", ""))
                )

            if action == "play_audio_url":
                url = str(params.get("url", "")).strip()
                if not url:
                    raise ValueError("Missing required parameter: url")
                result = await self._speaker_player.play_url(info, url)
                return ActionResult(device_id=device_id, action=action, success=True, message=url)

            if action == "play_random_audio":
                result = await self._speaker_player.play_random_file(info)
                return ActionResult(
                    device_id=device_id,
                    action=action,
                    success=True,
                    message=str(result.get("path", result.get("url", ""))),
                )

            if action == "stop_audio":
                await self._speaker_player.stop(info)
                return ActionResult(device_id=device_id, action=action, success=True)
        except Exception as exc:
            logger.exception("Speaker action failed: %s.%s", device_id, action)
            return ActionResult(device_id=device_id, action=action, success=False, message=str(exc))

        return ActionResult(device_id=device_id, action=action, success=False, message="Unsupported speaker action")

    @staticmethod
    def _build_mp5_capabilities() -> list[Capability]:
        return [
            Capability(name="on", params={"label": "开启", "help": "Power on.", "inputs": []}),
            Capability(name="off", params={"label": "关闭", "help": "Power off.", "inputs": []}),
            Capability(
                name="set_mode",
                params={
                    "label": "模式",
                    "help": "设置空气净化器模式。",
                    "inputs": [
                        {
                            "name": "mode",
                            "required": True,
                            "type": "enum",
                            "options": ["0", "1", "2", "3", "4", "5", "6"],
                        }
                    ],
                },
            ),
            Capability(
                name="set_fan_level",
                params={
                    "label": "风量",
                    "help": "设置风量等级。",
                    "inputs": [
                        {
                            "name": "level",
                            "required": True,
                            "type": "number",
                            "default": 1,
                        }
                    ],
                },
            ),
        ]

    @staticmethod
    def _default_sensors(device_type: str) -> list[Sensor]:
        return [Sensor(name=name, unit=unit) for name, unit in default_sensors(device_type, include_generic=True)]
