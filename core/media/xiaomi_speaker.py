from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import random
import string
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from core.media.audio_registry import ALLOWED_AUDIO_EXTENSIONS, LocalAudioRegistry

logger = logging.getLogger(__name__)

MINA_PLAY_MUSIC_HARDWARES = {
    "OH2",
    "LX04",
    "LX05",
    "L05B",
    "L05C",
    "L06",
    "L06A",
    "X08A",
    "X10A",
    "X08C",
    "X08E",
    "X8F",
}


def _random_string(length: int) -> str:
    population = string.ascii_letters + string.digits
    return "".join(random.sample(population, length))


class _MiTokenStore:
    def __init__(self, path: str) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> dict[str, Any] | None:
        if not self._path.exists():
            return None
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.exception("Failed to load Xiaomi speaker token cache")
            return None

    def save(self, token: dict[str, Any] | None) -> None:
        if token is None:
            if self._path.exists():
                self._path.unlink()
            return

        self._path.write_text(json.dumps(token, ensure_ascii=False, indent=2), encoding="utf-8")


class _MiAccount:
    def __init__(self, username: str, password: str, token_store_path: str) -> None:
        self._username = str(username)
        self._password = str(password)
        self._token_store = _MiTokenStore(token_store_path)
        self._token = self._token_store.load() or {"deviceId": _random_string(16).upper()}
        self._client = httpx.AsyncClient(timeout=15.0)
        self._user_agent = (
            "MiHome/6.0.103 (com.xiaomi.mihome; build:6.0.103.1; iOS 14.4.0) "
            "Alamofire/6.0.103 MICO/iOSApp/appStore/6.0.103"
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def login(self, sid: str) -> bool:
        try:
            response = await self._service_login(f"serviceLogin?sid={sid}&_json=true")
            if response.get("code") != 0:
                payload = {
                    "_json": "true",
                    "qs": response["qs"],
                    "sid": response["sid"],
                    "_sign": response["_sign"],
                    "callback": response["callback"],
                    "user": self._username,
                    "hash": hashlib.md5(self._password.encode()).hexdigest().upper(),
                }
                response = await self._service_login("serviceLoginAuth2", payload)
                if response.get("code") != 0:
                    raise RuntimeError(f"Xiaomi login rejected: {response}")

            self._token["userId"] = response["userId"]
            self._token["passToken"] = response["passToken"]
            self._token[sid] = (
                response["ssecurity"],
                await self._security_token_service(
                    response["location"],
                    response["nonce"],
                    response["ssecurity"],
                ),
            )
            self._token_store.save(self._token)
            return True
        except Exception:
            self._token_store.save(None)
            logger.exception("Failed to login Xiaomi account for sid=%s", sid)
            return False

    async def mi_request(
        self,
        sid: str,
        url: str,
        data: dict[str, Any] | None,
        headers: dict[str, str],
        *,
        relogin: bool = True,
    ) -> dict[str, Any]:
        if sid not in self._token and not await self.login(sid):
            raise RuntimeError("Xiaomi account login failed")

        cookies = {
            "userId": str(self._token["userId"]),
            "serviceToken": str(self._token[sid][1]),
        }
        merged_headers = {"User-Agent": self._user_agent, **headers}

        response = await self._client.request(
            "GET" if data is None else "POST",
            url,
            data=data,
            cookies=cookies,
            headers=merged_headers,
        )
        if response.status_code == 401 and relogin:
            self._token.pop(sid, None)
            self._token_store.save(self._token)
            if await self.login(sid):
                return await self.mi_request(sid, url, data, headers, relogin=False)

        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 0:
            message = str(payload.get("message", payload))
            if "auth" in message.lower() and relogin:
                self._token.pop(sid, None)
                self._token_store.save(self._token)
                if await self.login(sid):
                    return await self.mi_request(sid, url, data, headers, relogin=False)
            raise RuntimeError(message)
        return payload

    async def _service_login(self, uri: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        cookies = {
            "sdkVersion": "3.9",
            "deviceId": str(self._token["deviceId"]),
            "passToken": str(self._token.get("passToken", "")),
        }
        if "userId" in self._token:
            cookies["userId"] = str(self._token["userId"])

        response = await self._client.request(
            "GET" if data is None else "POST",
            "https://account.xiaomi.com/pass/" + uri,
            data=data,
            cookies=cookies,
            headers={"User-Agent": self._user_agent},
        )
        response.raise_for_status()
        raw = response.text
        if raw.startswith("&&&START&&&"):
            raw = raw[11:]
        return json.loads(raw)

    async def _security_token_service(self, location: str, nonce: str, ssecurity: str) -> str:
        digest = hashlib.sha1(f"nonce={nonce}&{ssecurity}".encode()).digest()
        client_sign = base64.b64encode(digest).decode()
        response = await self._client.get(location + "&clientSign=" + quote(client_sign))
        response.raise_for_status()
        service_token = response.cookies.get("serviceToken")
        if not service_token:
            raise RuntimeError("Xiaomi serviceToken missing after login")
        return service_token


class _MiNAService:
    def __init__(self, account: _MiAccount) -> None:
        self._account = account

    async def device_list(self) -> list[dict[str, Any]]:
        request_id = "app_ios_" + _random_string(30)
        payload = await self._account.mi_request(
            "micoapi",
            f"https://api2.mina.mi.com/admin/v2/device_list?master=0&requestId={request_id}",
            None,
            {},
        )
        return payload.get("data") or []

    async def ubus_request(
        self,
        *,
        device_id: str,
        method: str,
        path: str,
        message: dict[str, Any],
    ) -> dict[str, Any]:
        request_id = "app_ios_" + _random_string(30)
        payload = {
            "deviceId": str(device_id),
            "message": json.dumps(message, ensure_ascii=False),
            "method": method,
            "path": path,
            "requestId": request_id,
        }
        return await self._account.mi_request(
            "micoapi",
            "https://api2.mina.mi.com/remote/ubus",
            payload,
            {},
        )

    async def play_by_url(self, *, device_id: str, hardware: str, url: str, audio_type: int = 1) -> dict[str, Any]:
        if hardware in MINA_PLAY_MUSIC_HARDWARES:
            return await self._play_by_music_url(device_id=device_id, url=url, audio_type=audio_type)
        return await self.ubus_request(
            device_id=device_id,
            method="player_play_url",
            path="mediaplayer",
            message={"url": url, "type": audio_type, "media": "app_ios"},
        )

    async def stop(self, *, device_id: str) -> dict[str, Any]:
        return await self.ubus_request(
            device_id=device_id,
            method="player_play_operation",
            path="mediaplayer",
            message={"action": "pause", "media": "app_ios"},
        )

    async def player_status(self, *, device_id: str) -> dict[str, Any]:
        return await self.ubus_request(
            device_id=device_id,
            method="player_get_play_status",
            path="mediaplayer",
            message={"media": "app_ios"},
        )

    async def _play_by_music_url(self, *, device_id: str, url: str, audio_type: int) -> dict[str, Any]:
        music_payload = {
            "payload": {
                "audio_type": "MUSIC" if audio_type == 1 else "",
                "audio_items": [
                    {
                        "item_id": {
                            "audio_id": "1582971365183456177",
                            "cp": {
                                "album_id": "-1",
                                "episode_index": 0,
                                "id": "355454500",
                                "name": "anima",
                            },
                        },
                        "stream": {"url": url},
                    }
                ],
                "list_params": {
                    "listId": "-1",
                    "loadmore_offset": 0,
                    "origin": "anima",
                    "type": "MUSIC",
                },
            },
            "play_behavior": "REPLACE_ALL",
        }
        return await self.ubus_request(
            device_id=device_id,
            method="player_play_music",
            path="mediaplayer",
            message={
                "startaudioid": "1582971365183456177",
                "music": json.dumps(music_payload, ensure_ascii=False),
            },
        )


class XiaomiSpeakerPlayer:
    def __init__(
        self,
        *,
        settings_store,
        audio_registry: LocalAudioRegistry,
        token_store_path: str,
    ) -> None:
        self._settings = settings_store
        self._audio_registry = audio_registry
        self._token_store_path = token_store_path

    async def play_file(self, device_info: dict[str, Any], file_path: str) -> dict[str, Any]:
        url = self._audio_registry.register_file_url(file_path, target_ip=device_info.get("ip"))
        return await self.play_url(device_info, url)

    async def play_random_file(self, device_info: dict[str, Any]) -> dict[str, Any]:
        library_dir = self._resolve_audio_library_dir()
        candidates = [
            path
            for path in library_dir.rglob("*")
            if path.is_file() and path.suffix.lower() in ALLOWED_AUDIO_EXTENSIONS
        ]
        if not candidates:
            raise ValueError(f"No audio files found in library: {library_dir}")

        chosen = random.choice(candidates)
        result = await self.play_file(device_info, str(chosen))
        return {
            **result,
            "path": str(chosen),
        }

    async def play_url(self, device_info: dict[str, Any], url: str) -> dict[str, Any]:
        did = str(device_info.get("did", "")).strip()
        if not did:
            raise ValueError("Speaker device is missing Xiaomi did")

        account, service, mina_device = await self._resolve_mina_device(did)
        try:
            await service.play_by_url(
                device_id=mina_device["deviceID"],
                hardware=mina_device.get("hardware", ""),
                url=url,
                audio_type=1,
            )
            status = await self._wait_until_playing(service, mina_device["deviceID"])
            return {"url": url, "status": status}
        finally:
            await account.close()

    async def stop(self, device_info: dict[str, Any]) -> dict[str, Any]:
        did = str(device_info.get("did", "")).strip()
        if not did:
            raise ValueError("Speaker device is missing Xiaomi did")

        account, service, mina_device = await self._resolve_mina_device(did)
        try:
            await service.stop(device_id=mina_device["deviceID"])
            return await self._wait_until_stopped(service, mina_device["deviceID"])
        finally:
            await account.close()

    async def get_status(self, device_info: dict[str, Any]) -> dict[str, Any]:
        did = str(device_info.get("did", "")).strip()
        if not did:
            raise ValueError("Speaker device is missing Xiaomi did")

        account, service, mina_device = await self._resolve_mina_device(did)
        try:
            return await service.player_status(device_id=mina_device["deviceID"])
        finally:
            await account.close()

    async def _wait_until_playing(self, service: _MiNAService, device_id: str) -> dict[str, Any]:
        last_status: dict[str, Any] | None = None
        for _ in range(6):
            await asyncio.sleep(1)
            last_status = await service.player_status(device_id=device_id)
            state = self._extract_player_state(last_status)
            if state in {1, 2}:
                return last_status

        detail = self._extract_status_info(last_status) if last_status else {}
        raise RuntimeError(f"Speaker did not enter playing state: {json.dumps(detail, ensure_ascii=False)}")

    async def _wait_until_stopped(self, service: _MiNAService, device_id: str) -> dict[str, Any]:
        last_status: dict[str, Any] | None = None
        for _ in range(6):
            await asyncio.sleep(1)
            last_status = await service.player_status(device_id=device_id)
            state = self._extract_player_state(last_status)
            if state in {0, 2}:
                return last_status

        detail = self._extract_status_info(last_status) if last_status else {}
        raise RuntimeError(f"Speaker did not enter paused or stopped state: {json.dumps(detail, ensure_ascii=False)}")

    @staticmethod
    def _extract_player_state(status: dict[str, Any] | None) -> int | None:
        info = XiaomiSpeakerPlayer._extract_status_info(status)
        state = info.get("status")
        return state if isinstance(state, int) else None

    @staticmethod
    def _extract_status_info(status: dict[str, Any] | None) -> dict[str, Any]:
        if not status:
            return {}
        data = status.get("data")
        if not isinstance(data, dict):
            return {}
        raw_info = data.get("info", "{}")
        if isinstance(raw_info, str):
            try:
                parsed = json.loads(raw_info)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                return {}
        return raw_info if isinstance(raw_info, dict) else {}

    async def _resolve_mina_device(self, did: str) -> tuple[_MiAccount, _MiNAService, dict[str, Any]]:
        username, password = self._get_credentials()
        account = _MiAccount(username, password, self._token_store_path)
        service = _MiNAService(account)

        try:
            devices = await service.device_list()
            for device in devices:
                if str(device.get("miotDID", "")).strip() == did:
                    return account, service, device
                if str(device.get("deviceID", "")).strip() == did:
                    return account, service, device
        except Exception:
            await account.close()
            raise

        await account.close()
        raise ValueError(f"Xiaomi speaker did {did} not found in MiNA device list")

    def _get_credentials(self) -> tuple[str, str]:
        creds = self._settings.get_xiaomi_credentials() if self._settings else None
        if not creds:
            raise ValueError("Xiaomi cloud credentials are required to control speaker playback")
        user, password = creds
        return str(user), str(password)

    def _resolve_audio_library_dir(self) -> Path:
        configured = self._settings.get_audio_library_dir() if self._settings else ""
        candidates = []
        if configured:
            candidates.append(Path(configured).expanduser())
        candidates.extend(
            [
                Path.cwd().parent / "music",
                Path.cwd() / "music",
                Path.home() / "Music",
            ]
        )

        for candidate in candidates:
            resolved = candidate.resolve()
            if resolved.exists() and resolved.is_dir():
                return resolved

        searched = ", ".join(str(path) for path in candidates)
        raise ValueError(f"Audio library directory not found. Checked: {searched}")
