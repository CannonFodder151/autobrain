"""Application configuration.

All settings are read from environment variables (see .env.example).
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Core
    PROJECT_NAME: str = "AutoBrain"
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = False

    # Security
    SECRET_KEY: str = "change-me"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # Database
    POSTGRES_USER: str = "autobrain"
    POSTGRES_PASSWORD: str = "autobrain"
    POSTGRES_DB: str = "autobrain"
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    DATABASE_URL: str | None = None

    # Redis / Celery
    REDIS_URL: str = "redis://redis:6379/0"
    CELERY_BROKER_URL: str = "redis://redis:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/2"

    # MinIO
    MINIO_ENDPOINT: str = "minio:9000"
    MINIO_ACCESS_KEY: str = "autobrain"
    MINIO_SECRET_KEY: str = "autobrain"
    MINIO_BUCKET: str = "autobrain-assets"
    MINIO_SECURE: bool = False
    MINIO_PUBLIC_ENDPOINT: str = "http://localhost:9000"

    # AI router (9Router) — all AI services read this at runtime
    AI_ROUTER_URL: str = "http://your-9router-instance:port"
    AI_ROUTER_API_KEY: str = ""
    AI_ROUTER_TIMEOUT_SECONDS: int = 60
    AI_LOCAL_BASE_URL: str = "http://ai:8001"
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIMENSION: int = 1536  # text-embedding-3-small output size

    # External providers (optional)
    REGO_LOOKUP_URL: str = ""
    REGO_LOOKUP_API_KEY: str = ""
    MARKET_DATA_URL: str = ""
    MARKET_DATA_API_KEY: str = ""

    # Bootstrap admin account (created on first boot if missing)
    ADMIN_EMAIL: str = ""
    ADMIN_DISPLAY_NAME: str = "AutoBrain Admin"
    ADMIN_INITIAL_PASSWORD: str = ""

    # Demo mode: seeds a read-only demo account + sample data. No AI, no writes.
    DEMO_MODE: bool = False
    DEMO_EMAIL: str = "demo@autobrainservice.app"
    DEMO_PASSWORD: str = "demo"
    DEMO_DISPLAY_NAME: str = "Demo Garage"
    # One-shot demo reseed: wipe + regenerate the demo data on startup
    # (used when the seed changes so existing instances get new sample data).
    DEMO_RESET: bool = False

    # Security hardening
    MFA_ENFORCED: bool = False  # force MFA setup for all accounts except demo
    LOGIN_MAX_ATTEMPTS: int = 5  # failed logins allowed per IP before lockout
    LOGIN_WINDOW_SECONDS: int = 3 * 60 * 60  # lockout window (3 hours)

    # Push notifications (Firebase Cloud Messaging). Optional — push alerts are
    # skipped when unset; email/discord still work.
    FCM_SERVER_KEY: str = ""

    # SMTP (email notifications + self-service password reset)
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_USE_TLS: bool = True  # STARTTLS (TLS on connect when False → SSL)
    SMTP_FROM_EMAIL: str = "noreply@nathanmartina.com"
    SMTP_FROM_NAME: str = "AutoBrain"
    # Public base URL used to build password-reset links (no trailing slash)
    APP_BASE_URL: str = "http://localhost:8000"

    # Versioning + GitHub release checking
    APP_VERSION: str = "0.3.5"  # mirror frontend/pubspec.yaml version
    GITHUB_REPO: str = "CannonFodder151/autobrain"
    GITHUB_TOKEN: str = ""  # optional, raises the GitHub API rate limit for release checks

    # Scheduled backup (daily). When set, beats stores a full JSON snapshot to MinIO.
    BACKUP_ENABLED: bool = True
    BACKUP_RETENTION_DAYS: int = 14

    # Admin API key: enables machine-to-machine user management via X-Admin-API-Key.
    ADMIN_API_KEY: str = ""  # leave empty to disable the /admin-api endpoints

    # Self-service signup (hosted). When enabled, anyone can register a
    # Free-tier account via POST /auth/signup. Self-hosted instances keep
    # admin-only provisioning by leaving this off.
    SELF_SIGNUP_ENABLED: bool = False

    # Licence/subscription feature visibility. Off by default; the hosted
    # instance turns it on. When off, the app hides the licence/upgrade page.
    LICENSE_ENABLED: bool = False

    # Stripe billing (hosted subscriptions). Price IDs come from the Stripe
    # Dashboard (or scripts/stripe-setup.py). Leave empty to disable /billing.
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""  # whsec_... from the Stripe Dashboard
    STRIPE_PRICE_ENTHUSIAST_MONTHLY: str = ""
    STRIPE_PRICE_ENTHUSIAST_YEARLY: str = ""
    STRIPE_PRICE_GARAGE_MONTHLY: str = ""
    STRIPE_PRICE_GARAGE_YEARLY: str = ""

    # Early-adopter sale (AUT-93): 40% off the first 3 months for the first
    # 100 subscribers within 6 months of launch. The coupon/promotion code is
    # created by scripts/stripe-setup.py; the app auto-applies it to monthly
    # checkouts while the window is open. Stripe enforces the 100-subscriber
    # cap and redeem-by date at checkout.
    STRIPE_PROMO_EARLY_ADOPTER: str = ""      # promotion code id (promo_...)
    STRIPE_PROMO_EARLY_ADOPTER_CODE: str = "EARLY40"
    STRIPE_SALE_ENDS_AT: str = ""             # ISO date (YYYY-MM-DD); empty = sale on

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
