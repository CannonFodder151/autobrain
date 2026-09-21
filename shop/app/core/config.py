"""Application configuration for AutoBrain Shop.

All settings are read from environment variables (see .env.example).
"""

import secrets
from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_INSECURE_SECRET_KEYS = ("", "change-me", "change-me-to-a-long-random-string")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Core
    PROJECT_NAME: str = "AutoBrain Shop"
    ENVIRONMENT: str  # required; "development" is the only env that allows default creds
    LOG_LEVEL: str = "INFO"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = False

    # Security
    SECRET_KEY: str = ""
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # Database
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str = "autobrain_shop"
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    DATABASE_URL: str | None = None

    # Redis / Celery
    REDIS_URL: str = "redis://redis:6379/0"
    CELERY_BROKER_URL: str = "redis://redis:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/2"

    # MinIO
    MINIO_ENDPOINT: str = "minio:9000"
    MINIO_ACCESS_KEY: str
    MINIO_SECRET_KEY: str
    MINIO_BUCKET: str = "autobrain-shop-assets"
    MINIO_SECURE: bool = False
    MINIO_PUBLIC_ENDPOINT: str = "http://localhost:9000"

    # AI router (9Router)
    AI_ROUTER_URL: str = "http://your-9router-instance:port"
    AI_ROUTER_API_KEY: str = ""
    AI_ROUTER_API_KEY_FILE: str = ""
    AI_ROUTER_TIMEOUT_SECONDS: int = 60
    AI_GATEWAY_API_KEY: str = ""
    AI_ENABLED: bool = True
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIMENSION: int = 1536

    # AI usage caps (per-user fixed-window burst + UTC-day total)
    AI_RATE_LIMIT_PER_WINDOW: int = 10
    AI_RATE_WINDOW_SECONDS: int = 60
    AI_DAILY_LIMIT: int = 50

    # External providers (optional)
    REGO_LOOKUP_URL: str = ""
    REGO_LOOKUP_API_KEY: str = ""
    MARKET_DATA_URL: str = ""
    MARKET_DATA_API_KEY: str = ""

    # Bootstrap admin account (created on first boot if missing)
    ADMIN_EMAIL: str = ""
    ADMIN_DISPLAY_NAME: str = "AutoBrain Shop Admin"
    ADMIN_INITIAL_PASSWORD: str = ""
    ADMIN_INITIAL_PASSWORD_FILE: str = ""

    # Security hardening
    MFA_ENFORCED: bool = False
    LOGIN_MAX_ATTEMPTS: int = 5
    LOGIN_WINDOW_SECONDS: int = 3 * 60 * 60

    # Push notifications
    FCM_SERVER_KEY: str = ""

    # SMTP
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_USE_TLS: bool = True
    SMTP_FROM_EMAIL: str = "noreply@example.com"
    SMTP_FROM_NAME: str = "AutoBrain Shop"
    EMAIL_SUPPRESS_DOMAINS: str = "example.com,example.org,example.net,test,invalid,testmail.com"
    EMAIL_SUPPRESS_PATTERNS: str = (
        r"^(?:smoke(?:hst\d*|[-_.]?(?:aut)?\d)|"
        r"deploy[-_.]?(?:test[-_.-])?(?:aut|test)\d|"
        r"aut\d+[-_.](?:check|host|test)|"
        r"qa[-_.](?:verify|license))"
    )
    APP_BASE_URL: str = "http://localhost:8000"

    # Versioning
    APP_VERSION: str = "0.1.0"

    # Scheduled backup
    BACKUP_ENABLED: bool = True
    BACKUP_RETENTION_DAYS: int = 14

    # Admin API key
    ADMIN_API_KEY: str = ""

    # CORS origins
    CORS_ALLOWED_ORIGINS: list[str] = []

    @model_validator(mode="after")
    def _validate_cors_no_wildcard_credentials(self) -> "Settings":
        if "*" in self.CORS_ALLOWED_ORIGINS:
            raise ValueError(
                "CORS_ALLOWED_ORIGINS must not contain '*' when allow_credentials=True. "
                "Set explicit origins instead."
            )
        return self

    # Paperclip API
    PAPERCLIP_API_URL: str = ""
    PAPERCLIP_API_KEY: str = ""
    PAPERCLIP_COMPANY_ID: str = ""

    # Self-service signup
    SELF_SIGNUP_ENABLED: bool = False

    # Pending accounts
    PENDING_ACCOUNT_RETENTION_DAYS: int = 7

    # Subscription feature visibility
    LICENSE_ENABLED: bool = False

    # Stripe billing
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    STRIPE_PRICE_STARTER_MONTHLY: str = ""
    STRIPE_PRICE_STARTER_YEARLY: str = ""
    STRIPE_PRICE_PROFESSIONAL_MONTHLY: str = ""
    STRIPE_PRICE_PROFESSIONAL_YEARLY: str = ""
    STRIPE_PRICE_ENTERPRISE_MONTHLY: str = ""
    STRIPE_PRICE_ENTERPRISE_YEARLY: str = ""

    @model_validator(mode="after")
    def _refuse_default_creds_outside_dev(self) -> "Settings":
        if self.ENVIRONMENT == "development":
            return self
        defaults = {
            "POSTGRES_PASSWORD": "autobrain",
            "MINIO_SECRET_KEY": "autobrain",
        }
        offenders = [
            name for name, default in defaults.items() if getattr(self, name) == default
        ]
        if offenders:
            raise ValueError(
                f"environment '{self.ENVIRONMENT}' refuses default credentials: "
                + ", ".join(offenders)
                + " — set real values in the deployment env (see .env.example)"
            )
        return self

    @model_validator(mode="after")
    def _load_file_secrets(self) -> "Settings":
        """AUT-1533: resolve *_FILE env vars."""
        if not self.AI_ROUTER_API_KEY and self.AI_ROUTER_API_KEY_FILE:
            p = Path(self.AI_ROUTER_API_KEY_FILE)
            if p.is_file():
                self.AI_ROUTER_API_KEY = p.read_text(encoding="utf-8").strip()
        if not self.ADMIN_INITIAL_PASSWORD and self.ADMIN_INITIAL_PASSWORD_FILE:
            p = Path(self.ADMIN_INITIAL_PASSWORD_FILE)
            if p.is_file():
                self.ADMIN_INITIAL_PASSWORD = p.read_text(encoding="utf-8").strip()
        return self

    @model_validator(mode="after")
    def _harden_secrets(self) -> "Settings":
        """AUT-1181: fail closed on missing/weak secrets."""
        if self.SECRET_KEY in _INSECURE_SECRET_KEYS:
            if self.ENVIRONMENT != "development":
                raise ValueError(
                    "SECRET_KEY is required — generate one with: "
                    'python -c "import secrets; print(secrets.token_urlsafe(64))"'
                )
            self.SECRET_KEY = secrets.token_urlsafe(64)
        if self.ADMIN_API_KEY and len(self.ADMIN_API_KEY) < 32:
            raise ValueError(
                "ADMIN_API_KEY must be at least 32 characters "
                "(or empty to disable the /admin-api endpoints)"
            )
        if self.STRIPE_SECRET_KEY and not self.STRIPE_WEBHOOK_SECRET:
            raise ValueError(
                "STRIPE_WEBHOOK_SECRET is required when STRIPE_SECRET_KEY is set "
                "(whsec_... from the Stripe Dashboard) — unsigned webhooks are refused"
            )
        return self

    @property
    def sqlalchemy_database_uri(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()