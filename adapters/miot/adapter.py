from __future__ import annotations

import logging
from typing import Any

import miio
from miio.integrations.airpurifier.zhimi.airpurifier_miot import AirPurifierMiot

from adapters.base import BaseAdapter
from core.models import ActionResult, Capability, Device, Sensor

from .executors import execute_action
from .extractors import default_sensors, read_sensor_snapshot
from .reflection import build_capabilities
from .resolver import create_device_instance, resolve_device_path

logger = logging.getLogger(__name__)

# Alias newer Xiaomi purifier model names to the closest supported MIoT mapping
# from python-miio so dynamic commands can resolve set_property() mappings.
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

    def __init__(self, settings_store=None) -> None:
        self._known_devices: dict[str, miio.Device] = {}
        self._device_infos: dict[str, dict] = {}
        self._settings = settings_store
        self._cloud_logged_in = False

    def _guess_device_type(self, model: str) -> str:
        for prefix, dtype in MODEL_TYPE_MAP.items():
            if model.startswith(prefix):
                return dtype
        return "unknown"

    def _build_device_id(self, ip: str, model: str) -> str:
        safe_ip = ip.replace(".", "_")
        safe_model = model.replace(".", "_")
        return f"miot_{safe_ip}_{safe_model}"

    def _build_device_id_from_did(self, did: str) -> str:
        return f"miot_cloud_{did}"

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

                    device_id = self._build_device_id_from_did(did)
                    device_type = self._guess_device_type(model)

                    device = Device(
                        device_id=device_id,
                        name=name,
                        adapter=self.name,
                        type=device_type,
                        online=bool(is_online),
                        capabilities=self._build_capabilities(model, has_token=True),
                        sensors=self._default_sensors(device_type),
                    )
                    devices.append(device)

                    if ip and token and token != "0" * 32:
                        self._device_infos[device_id] = {
                            "ip": ip,
                            "token": token,
                            "model": model,
                            "did": did,
                        }
                except Exception:
                    logger.exception("Failed to process cloud device: %s", cd.get("did", "?"))
        except Exception as exc:
            self._cloud_logged_in = False
            logger.exception("Xiaomi Cloud discovery failed: %s", exc)

        return devices

    async def _discover_local(self) -> list[Device]:
        import socket
        import struct

        hello = bytes.fromhex("21310020ffffffffffffffffffffffffffffffffffffffffffffffffffffffff")
        port = 54321
        devices: list[Device] = []

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
                    token_bytes = data[16:32]
                    token = token_bytes.hex()
                    has_token = token != "0" * 32 and token != "f" * 32
                    device_id = f"miot_local_{did}"

                    model = "xiaomi.device"
                    device_type = "unknown"
                    if has_token:
                        try:
                            dev = miio.Device(ip=ip, token=token)
                            info = dev.info()
                            model = info.model or model
                            device_type = self._guess_device_type(model)
                        except Exception:
                            logger.debug("Failed to inspect local MIoT model for %s", ip, exc_info=True)

                    name = f"小米设备 ({ip})" if not has_token else f"{model} ({ip})"
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

                    base_info = {"ip": ip, "token": token if has_token else "", "model": model, "did": str(did)}
                    if has_token:
                        self._device_infos[device_id] = base_info
                    else:
                        self._device_infos[device_id] = {**base_info, "needs_token": True}

                    logger.info("Local scan: ip=%s did=%d token=%s", ip, did, "available" if has_token else "needs_setup")
                except socket.timeout:
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
            device_id = self._build_device_id(ip, model)

            device = Device(
                device_id=device_id,
                name=name,
                adapter=self.name,
                type=device_type,
                online=True,
                capabilities=self._build_capabilities(model, has_token=True),
                sensors=self._default_sensors(device_type),
            )
            devices.append(device)
            self._device_infos[device_id] = {"ip": ip, "token": token, "model": model}

        if manual:
            logger.info("Loaded %d manual devices from config", len(manual))
        return devices

    async def discover(self) -> list[Device]:
        seen_ips: set[str] = set()
        devices: list[Device] = []

        manual = await self._load_manual_devices()
        for device in manual:
            info = self._device_infos.get(device.device_id, {})
            if info.get("ip"):
                seen_ips.add(info["ip"])
        devices.extend(manual)

        cloud = await self._discover_cloud()
        for device in cloud:
            info = self._device_infos.get(device.device_id, {})
            ip = info.get("ip", "")
            if ip and ip not in seen_ips:
                seen_ips.add(ip)
                devices.append(device)

        local = await self._discover_local()
        for device in local:
            info = self._device_infos.get(device.device_id, {})
            ip = info.get("ip", "")
            if ip and ip not in seen_ips:
                seen_ips.add(ip)
                devices.append(device)

        logger.info(
            "MIoT discovered %d devices total (%d manual, %d cloud, %d local)",
            len(devices),
            len(manual),
            len(cloud),
            len(local),
        )
        return devices

    def _get_miio_device(self, device_id: str) -> miio.Device | None:
        info = self._device_infos.get(device_id)
        if not info:
            return None

        expected_cls = resolve_device_path(info.get("model", "")).device_class
        cached = self._known_devices.get(device_id)
        if cached is not None and isinstance(cached, expected_cls):
            return cached

        try:
            dev = create_device_instance(info)
            self._known_devices[device_id] = dev
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
        return build_capabilities(model, has_token=has_token, mp5_factory=self._build_mp5_capabilities)

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
