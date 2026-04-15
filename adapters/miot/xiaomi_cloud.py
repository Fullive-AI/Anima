"""Xiaomi Cloud connector with QR code login support.

Adapted from xiaomi-token-extractor. Supports:
- QR code login (recommended, highest success rate)
- Password login (may be blocked by captcha/2FA)
- Device list + token fetching via encrypted API
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import random
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)


class _RC4:
    def __init__(self, key: bytes):
        self._s = list(range(256))
        j = 0
        for i in range(256):
            j = (j + self._s[i] + key[i % len(key)]) % 256
            self._s[i], self._s[j] = self._s[j], self._s[i]
        self._i = 0
        self._j = 0

    def crypt(self, data: bytes) -> bytes:
        out = bytearray()
        for b in data:
            self._i = (self._i + 1) % 256
            self._j = (self._j + self._s[self._i]) % 256
            self._s[self._i], self._s[self._j] = self._s[self._j], self._s[self._i]
            k = self._s[(self._s[self._i] + self._s[self._j]) % 256]
            out.append(b ^ k)
        return bytes(out)


def _encrypt_rc4(password_b64: str, payload: str) -> str:
    rc4 = _RC4(base64.b64decode(password_b64))
    rc4.crypt(bytes(1024))
    return base64.b64encode(rc4.crypt(payload.encode("utf-8"))).decode("utf-8")


def _decrypt_rc4(password_b64: str, payload_b64: str) -> bytes:
    rc4 = _RC4(base64.b64decode(password_b64))
    rc4.crypt(bytes(1024))
    return rc4.crypt(base64.b64decode(payload_b64))


class XiaomiCloudConnector:
    def __init__(self):
        self._agent = self._generate_agent()
        self._device_id = self._generate_device_id()
        self._session = requests.session()
        self._ssecurity: str | None = None
        self.userId: str | None = None
        self._serviceToken: str | None = None

    def get_homes(self, country: str) -> Any:
        url = self._get_api_url(country) + "/v2/homeroom/gethome"
        params = {"data": '{"fg": true, "fetch_share": true, "fetch_share_dev": true, "limit": 300, "app_ver": 7}'}
        return self._execute_encrypted(url, params)

    def get_devices(self, country: str, home_id: Any, owner_id: Any) -> Any:
        url = self._get_api_url(country) + "/v2/home/home_device_list"
        params = {
            "data": '{"home_owner": '
            + str(owner_id)
            + ',"home_id": '
            + str(home_id)
            + ', "limit": 200, "get_split_device": true, "support_smart_home": true}'
        }
        return self._execute_encrypted(url, params)

    def get_dev_cnt(self, country: str) -> Any:
        url = self._get_api_url(country) + "/v2/user/get_device_cnt"
        params = {"data": '{ "fetch_own": true, "fetch_share": true}'}
        return self._execute_encrypted(url, params)

    def _execute_encrypted(self, url: str, params: dict[str, str]) -> Any:
        if not self.userId or not self._serviceToken or not self._ssecurity:
            raise RuntimeError("未完成登录")

        headers = {
            "Accept-Encoding": "identity",
            "User-Agent": self._agent,
            "Content-Type": "application/x-www-form-urlencoded",
            "x-xiaomi-protocal-flag-cli": "PROTOCAL-HTTP2",
            "MIOT-ENCRYPT-ALGORITHM": "ENCRYPT-RC4",
        }
        cookies = {
            "userId": str(self.userId),
            "yetAnotherServiceToken": str(self._serviceToken),
            "serviceToken": str(self._serviceToken),
            "locale": "en_GB",
            "timezone": "GMT+02:00",
            "is_daylight": "1",
            "dst_offset": "3600000",
            "channel": "MI_APP_STORE",
        }
        millis = round(time.time() * 1000)
        nonce = self._generate_nonce(millis)
        signed_nonce = self._signed_nonce(nonce, self._ssecurity)
        fields = self._generate_enc_params(url, "POST", signed_nonce, nonce, dict(params), self._ssecurity)
        response = self._session.post(url, headers=headers, cookies=cookies, params=fields)
        if response.status_code == 200:
            decoded = _decrypt_rc4(self._signed_nonce(fields["_nonce"], self._ssecurity), response.text)
            return json.loads(decoded)
        return None

    def install_service_token_cookies(self, token: str) -> None:
        for d in [".api.io.mi.com", ".io.mi.com", ".mi.com"]:
            self._session.cookies.set("serviceToken", token, domain=d)
            self._session.cookies.set("yetAnotherServiceToken", token, domain=d)

    @staticmethod
    def _get_api_url(country: str) -> str:
        country = (country or "cn").strip().lower()
        return "https://" + ("" if country == "cn" else (country + ".")) + "api.io.mi.com/app"

    @staticmethod
    def _signed_nonce(nonce: str, ssecurity: str) -> str:
        h = hashlib.sha256(base64.b64decode(ssecurity) + base64.b64decode(nonce))
        return base64.b64encode(h.digest()).decode("utf-8")

    @staticmethod
    def _generate_nonce(millis: int) -> str:
        nonce_bytes = os.urandom(8) + (int(millis / 60000)).to_bytes(4, byteorder="big")
        return base64.b64encode(nonce_bytes).decode("utf-8")

    @staticmethod
    def _generate_agent() -> str:
        agent_id = "".join(chr(random.randint(65, 69)) for _ in range(13))
        random_text = "".join(chr(random.randint(97, 122)) for _ in range(18))
        return f"{random_text}-{agent_id} APP/com.xiaomi.mihome APPV/10.5.201"

    @staticmethod
    def _generate_device_id() -> str:
        return "".join(chr(random.randint(97, 122)) for _ in range(6))

    @staticmethod
    def _generate_enc_signature(url: str, method: str, signed_nonce: str, params: dict[str, str]) -> str:
        parts = [method.upper(), url.split("com")[1].replace("/app/", "/")]
        for k, v in params.items():
            parts.append(f"{k}={v}")
        parts.append(signed_nonce)
        return base64.b64encode(hashlib.sha1("&".join(parts).encode("utf-8")).digest()).decode()

    @staticmethod
    def _generate_enc_params(
        url: str,
        method: str,
        signed_nonce: str,
        nonce: str,
        params: dict[str, str],
        ssecurity: str,
    ) -> dict[str, str]:
        params["rc4_hash__"] = XiaomiCloudConnector._generate_enc_signature(url, method, signed_nonce, params)
        for k, v in list(params.items()):
            params[k] = _encrypt_rc4(signed_nonce, v)
        params.update(
            {
                "signature": XiaomiCloudConnector._generate_enc_signature(url, method, signed_nonce, params),
                "ssecurity": ssecurity,
                "_nonce": nonce,
            }
        )
        return params

    @staticmethod
    def _to_json(text: str) -> dict[str, Any]:
        return json.loads(text.replace("&&&START&&&", ""))


class QrLoginFlow:
    """QR code login — highest success rate, no password needed."""

    def __init__(self):
        self.connector = XiaomiCloudConnector()
        self._qr_image_url: str | None = None
        self._login_url: str | None = None
        self._long_polling_url: str | None = None
        self._timeout_s: float = 0.0
        self._start_time: float = 0.0
        self._location: str | None = None
        self.stage: str = "init"

    def start(self) -> dict[str, Any]:
        if not self._step1_get_qr_url():
            self.stage = "error"
            return {"status": "error", "error": "无法获取二维码登录信息"}
        img = self._step2_get_qr_image()
        if not img:
            self.stage = "error"
            return {"status": "error", "error": "无法获取二维码图片"}
        self.stage = "qr_pending"
        self._start_time = time.time()
        return {"status": "qr_required", "qr_image_b64": img, "login_url": self._login_url or ""}

    def poll(self) -> dict[str, Any]:
        if self.stage != "qr_pending":
            return {"status": "error", "error": "当前状态不可轮询"}
        if self._timeout_s and (time.time() - self._start_time) > self._timeout_s:
            self.stage = "error"
            return {"status": "qr_expired", "error": "二维码已过期，请重新开始"}

        resp = self._step3_poll_once()
        if resp is None:
            return {"status": "qr_pending"}
        if resp.get("status") == "error":
            self.stage = "error"
            return resp

        if not self._step4_get_service_token():
            self.stage = "error"
            return {"status": "error", "error": "无法获取 serviceToken"}

        self.stage = "ok"
        return {"status": "ok"}

    def _step1_get_qr_url(self) -> bool:
        url = "https://account.xiaomi.com/longPolling/loginUrl"
        data = {
            "_qrsize": "480",
            "qs": "%3Fsid%3Dxiaomiio%26_json%3Dtrue",
            "callback": "https://sts.api.io.mi.com/sts",
            "_hasLogo": "false",
            "sid": "xiaomiio",
            "serviceParam": "",
            "_locale": "en_GB",
            "_dc": str(int(time.time() * 1000)),
        }
        r = self.connector._session.get(url, params=data)
        if r.status_code != 200:
            return False
        jd = self.connector._to_json(r.text)
        self._qr_image_url = jd.get("qr")
        self._login_url = jd.get("loginUrl")
        self._long_polling_url = jd.get("lp")
        try:
            self._timeout_s = float(jd.get("timeout") or 0)
        except Exception:
            self._timeout_s = 0.0
        return bool(self._qr_image_url and self._long_polling_url)

    def _step2_get_qr_image(self) -> str:
        if not self._qr_image_url:
            return ""
        r = self.connector._session.get(self._qr_image_url)
        if r.status_code != 200:
            return ""
        return base64.b64encode(r.content).decode("utf-8")

    def _step3_poll_once(self) -> dict[str, Any] | None:
        if not self._long_polling_url:
            return {"status": "error", "error": "缺少长轮询地址"}
        try:
            r = self.connector._session.get(self._long_polling_url, timeout=10)
        except requests.exceptions.Timeout:
            return None
        except Exception as e:
            return {"status": "error", "error": str(e)}

        if r.status_code != 200:
            return None
        data = self.connector._to_json(r.text)
        self.connector.userId = str(data.get("userId") or "")
        self.connector._ssecurity = str(data.get("ssecurity") or "")
        self._location = str(data.get("location") or "")
        if not self.connector.userId or not self.connector._ssecurity or not self._location:
            return {"status": "error", "error": "扫码返回数据不完整"}
        return {"status": "ok"}

    def _step4_get_service_token(self) -> bool:
        if not self._location:
            return False
        r = self.connector._session.get(
            self._location,
            headers={"content-type": "application/x-www-form-urlencoded"},
        )
        if r.status_code != 200:
            return False
        token = r.cookies.get("serviceToken") or self.connector._session.cookies.get("serviceToken")
        if not token:
            return False
        self.connector._serviceToken = token
        self.connector.install_service_token_cookies(token)
        return True


def fetch_all_devices(connector: XiaomiCloudConnector, region: str) -> list[dict[str, Any]]:
    """Fetch all devices with tokens from Xiaomi Cloud after login."""
    rows: list[dict[str, Any]] = []

    homes = connector.get_homes(region)
    all_homes: list[dict[str, Any]] = []
    if homes and isinstance(homes, dict):
        for h in (homes.get("result", {}) or {}).get("homelist", []) or []:
            all_homes.append({"home_id": h.get("id"), "home_owner": connector.userId})

    dev_cnt = connector.get_dev_cnt(region)
    if dev_cnt and isinstance(dev_cnt, dict):
        share = ((dev_cnt.get("result", {}) or {}).get("share", {}) or {}).get("share_family", []) or []
        for h in share:
            all_homes.append({"home_id": h.get("home_id"), "home_owner": h.get("home_owner")})

    for home in all_homes:
        devices = connector.get_devices(region, home.get("home_id"), home.get("home_owner"))
        if not devices or not isinstance(devices, dict):
            continue
        info_list = (devices.get("result", {}) or {}).get("device_info")
        if not info_list:
            continue
        for d in info_list:
            if not isinstance(d, dict):
                continue
            rows.append(
                {
                    "name": str(d.get("name", "") or ""),
                    "model": str(d.get("model", "") or ""),
                    "did": str(d.get("did", "") or ""),
                    "mac": str(d.get("mac", "") or ""),
                    "localip": str(d.get("localip", "") or ""),
                    "token": str(d.get("token", "") or ""),
                    "isOnline": d.get("isOnline"),
                }
            )

    logger.info("Fetched %d devices from Xiaomi Cloud (region=%s)", len(rows), region)
    return rows
