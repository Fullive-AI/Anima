from __future__ import annotations

import mimetypes
import secrets
import socket
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

ALLOWED_AUDIO_EXTENSIONS = {
    ".wav",
    ".mp3",
    ".m4a",
    ".aac",
    ".flac",
    ".ogg",
}


@dataclass(frozen=True)
class RegisteredAudio:
    path: Path
    media_type: str
    filename: str


class LocalAudioRegistry:
    def __init__(self, port: int = 8080) -> None:
        self._port = port
        self._entries: dict[str, RegisteredAudio] = {}

    def register_file(self, file_path: str | Path) -> str:
        path = self._normalize_path(file_path)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"Audio file not found: {path}")

        media_type, _ = mimetypes.guess_type(path.name)
        if path.suffix.lower() not in ALLOWED_AUDIO_EXTENSIONS and not (media_type or "").startswith("audio/"):
            raise ValueError(f"Unsupported audio file: {path.name}")

        token = secrets.token_urlsafe(18)
        self._entries[token] = RegisteredAudio(
            path=path,
            media_type=media_type or "application/octet-stream",
            filename=path.name,
        )
        return token

    def get(self, token: str) -> RegisteredAudio | None:
        return self._entries.get(token)

    def register_file_url(self, file_path: str | Path, *, target_ip: str | None = None) -> str:
        token = self.register_file(file_path)
        return self.build_url(token, target_ip=target_ip)

    def build_url(self, token: str, *, target_ip: str | None = None) -> str:
        host = self._resolve_host(target_ip)
        return f"http://{host}:{self._port}/api/audio/{token}"

    @staticmethod
    def _normalize_path(file_path: str | Path) -> Path:
        if isinstance(file_path, Path):
            return file_path.expanduser().resolve()

        raw = str(file_path).strip()
        if raw.startswith("file:"):
            parsed = urlparse(raw)
            candidate = unquote(parsed.path or "")
            if parsed.netloc and not candidate.startswith("/"):
                candidate = f"/{candidate}"
            return Path(candidate).expanduser().resolve()

        return Path(raw).expanduser().resolve()

    @staticmethod
    def _resolve_host(target_ip: str | None = None) -> str:
        probe_target = target_ip or "8.8.8.8"
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect((probe_target, 80))
            host = sock.getsockname()[0]
            return host or "127.0.0.1"
        except OSError:
            return "127.0.0.1"
        finally:
            sock.close()
