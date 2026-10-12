"""Runtime configuration (env + secret files)."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

def _file_secret(name: str) -> str | None:
    """Read a *_FILE secret (Paperclip secret-file pattern, AUT-1533)."""
    path = os.environ.get(f"{name}_FILE")
    if path:
        try:
            return Path(path).read_text().strip()
        except OSError:
            return None
    return None

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    DATABASE_URL: str = "sqlite+aiosqlite:///./dongle.db"
    AUTOBRAIN_BACKEND_URL: str = "http://backend:8000"
    DONGLE_SERVER_API_KEY: str = ""
    DONGLE_SERVER_API_KEY_FILE: str | None = None

    MINIO_ENDPOINT: str = "minio:9000"
    MINIO_EXTERNAL_ENDPOINT: str = ""
    MINIO_BUCKET: str = "autobrain-assets"
    MINIO_ACCESS_KEY: str = ""
    MINIO_SECRET_KEY: str = ""
    MINIO_SECURE: bool = False
    MINIO_ACCESS_KEY_FILE: str | None = None
    MINIO_SECRET_KEY_FILE: str | None = None

    WEB_UI_BASIC_USER: str = "admin"
    WEB_UI_BASIC_PASSWORD: str = ""
    WEB_UI_BASIC_PASSWORD_FILE: str | None = None
    FIRMWARE_BUCKET_PREFIX: str = "dongle_firmware"
    SIGNED_URL_TTL_SECONDS: int = 900
    MAX_FIRMWARE_BYTES: int = 16 * 1024 * 1024
    ENVIRONMENT: str = "production"

    def api_key(self) -> str:
        """Internal API key, preferring *_FILE secrets (AUT-1533)."""
        return self.DONGLE_SERVER_API_KEY or _file_secret("DONGLE_SERVER_API_KEY") or ""

    def minio_creds(self) -> tuple[str, str]:
        ak = self.MINIO_ACCESS_KEY or _file_secret("MINIO_ACCESS_KEY") or ""
        sk = self.MINIO_SECRET_KEY or _file_secret("MINIO_SECRET_KEY") or ""
        return ak, sk

    def web_password(self) -> str:
        return self.WEB_UI_BASIC_PASSWORD or _file_secret("WEB_UI_BASIC_PASSWORD") or ""

settings = Settings()