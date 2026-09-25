"""Environment-driven shared configuration.

Keeps config out of module code so backend, AI, and tests can inject settings
without mutating os.environ.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Shared settings consumed by all AutoBrain services."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = Field(default="development", validation_alias="APP_ENV")
    debug: bool = False

    # 9Router (OpenAI-compatible)
    ai_router_url: str = Field(default="http://10.0.3.17:20128/v1", validation_alias="AI_ROUTER_URL")
    ai_router_api_key: str | None = Field(default=None, validation_alias="AI_ROUTER_API_KEY")
    ai_router_model: str = Field(default="General-Use", validation_alias="AI_ROUTER_MODEL")
    ai_router_timeout_seconds: int = Field(default=120, validation_alias="AI_ROUTER_TIMEOUT_SECONDS")
    ai_enabled: bool = Field(default=True, validation_alias="AI_ENABLED")

    # AI gateway
    ai_gateway_api_key: str | None = Field(default=None, validation_alias="AI_GATEWAY_API_KEY")
    ai_gateway_max_body_bytes: int = Field(default=1_000_000, validation_alias="AI_GATEWAY_MAX_BODY_BYTES")

    # Backend
    database_url: str | None = Field(default=None, validation_alias="DATABASE_URL")
    redis_url: str | None = Field(default=None, validation_alias="REDIS_URL")
    minio_endpoint: str | None = Field(default=None, validation_alias="MINIO_ENDPOINT")
    minio_access_key: str | None = Field(default=None, validation_alias="MINIO_ACCESS_KEY")
    minio_secret_key: str | None = Field(default=None, validation_alias="MINIO_SECRET_KEY")
    minio_secure: bool = Field(default=False, validation_alias="MINIO_SECURE")
    backend_host: str = Field(default="0.0.0.0", validation_alias="BACKEND_HOST")
    backend_port: int = Field(default=8000, validation_alias="BACKEND_PORT")

    # Frontend / web
    frontend_url: str = Field(default="http://localhost:3000", validation_alias="FRONTEND_URL")
    cors_allow_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    # Logging
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")

    def ai_router_enabled(self) -> bool:
        """True when AI is enabled and the router URL is real (not a placeholder)."""
        if not self.ai_enabled:
            return False
        return bool(self.ai_router_url) and "your-9router-instance" not in self.ai_router_url

    @property
    def is_prod(self) -> bool:
        return self.environment in {"prod", "production", "hosted"}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def load_settings(overrides: dict[str, Any] | None = None) -> Settings:
    """Load settings with optional in-memory overrides (test-friendly)."""
    values = {
        "environment": os.getenv("APP_ENV", "development"),
        "debug": _env_bool("DEBUG", False),
        "ai_router_url": os.getenv("AI_ROUTER_URL", "http://10.0.3.17:20128/v1"),
        "ai_router_api_key": os.getenv("AI_ROUTER_API_KEY"),
        "ai_router_model": os.getenv("AI_ROUTER_MODEL", "General-Use"),
        "ai_router_timeout_seconds": int(os.getenv("AI_ROUTER_TIMEOUT_SECONDS", "120")),
        "ai_enabled": _env_bool("AI_ENABLED", True),
        "ai_gateway_api_key": os.getenv("AI_GATEWAY_API_KEY"),
        "ai_gateway_max_body_bytes": int(os.getenv("AI_GATEWAY_MAX_BODY_BYTES", "1000000")),
        "database_url": os.getenv("DATABASE_URL"),
        "redis_url": os.getenv("REDIS_URL"),
        "minio_endpoint": os.getenv("MINIO_ENDPOINT"),
        "minio_access_key": os.getenv("MINIO_ACCESS_KEY"),
        "minio_secret_key": os.getenv("MINIO_SECRET_KEY"),
        "minio_secure": _env_bool("MINIO_SECURE", False),
        "backend_host": os.getenv("BACKEND_HOST", "0.0.0.0"),
        "backend_port": int(os.getenv("BACKEND_PORT", "8000")),
        "frontend_url": os.getenv("FRONTEND_URL", "http://localhost:3000"),
        "log_level": os.getenv("LOG_LEVEL", "INFO"),
    }
    if overrides:
        values.update(overrides)
    return Settings(**values)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


__all__ = ["Settings", "get_settings", "load_settings"]
