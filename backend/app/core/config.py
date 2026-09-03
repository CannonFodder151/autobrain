"""Application configuration.

All settings are read from environment variables (see .env.example).
"""

import secrets
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Known-insecure SECRET_KEY values (AUT-1181): the historic default and the
# .env.example placeholder — both public in the repo, so forgeable.
_INSECURE_SECRET_KEYS = ("", "change-me", "change-me-to-a-long-random-string")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Core
    PROJECT_NAME: str = "AutoBrain"
    ENVIRONMENT: str  # required; "development" is the only env that allows default creds
    LOG_LEVEL: str = "INFO"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = False

    # Security
    # JWT signing key (AUT-1181). No insecure default: unset/placeholder values
    # are refused everywhere except development, where an ephemeral random key
    # is generated per boot. Generate a real one with:
    #   python -c "import secrets; print(secrets.token_urlsafe(64))"
    SECRET_KEY: str = ""
    ALGORITHM: str = "HS256"
    # Short-lived access tokens (minutes) — renewal goes through /auth/refresh
    # (refresh rotation revokes the previous token). Bump token_version on
    # logout/password change to revoke all outstanding tokens.
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # Database
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
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
    MINIO_ACCESS_KEY: str
    MINIO_SECRET_KEY: str
    MINIO_BUCKET: str = "autobrain-assets"
    MINIO_SECURE: bool = False
    MINIO_PUBLIC_ENDPOINT: str = "http://localhost:9000"

    # AI router (9Router) — all AI services read this at runtime
    AI_ROUTER_URL: str = "http://your-9router-instance:port"
    AI_ROUTER_API_KEY: str = ""
    AI_ROUTER_TIMEOUT_SECONDS: int = 60
    AI_LOCAL_BASE_URL: str = "http://ai:8001"
    AI_GATEWAY_API_KEY: str = ""  # shared secret backend->AI gateway (Bearer)
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIMENSION: int = 1536  # text-embedding-3-small output size

    # AI usage caps (AUT-302): per-user fixed-window burst + UTC-day total,
    # Redis-backed and enforced before any 9Router spend. 429 once exceeded.
    AI_RATE_LIMIT_PER_WINDOW: int = 10
    AI_RATE_WINDOW_SECONDS: int = 60
    AI_DAILY_LIMIT: int = 50

    # Rego lookup rate limit: per-user fixed-window (UTC-hour).
    # Fail-open: Redis outage logs a warning but allows the request through.
    REGO_RATE_LIMIT_PER_HOUR: int = 20
    REGO_RATE_WINDOW_SECONDS: int = 3600

    # External providers (optional)
    REGO_LOOKUP_URL: str = ""
    REGO_LOOKUP_API_KEY: str = ""
    MARKET_DATA_URL: str = ""
    MARKET_DATA_API_KEY: str = ""

    # 7-Eleven fuel prices (projectzerothree.info). Public, keyless, server-cached
    # snapshot — no AI involved. Override the URL only for self-hosting a mirror.
    SEVEN_ELEVEN_API_URL: str = "https://projectzerothree.info/api.php?format=json"
    SEVEN_ELEVEN_CACHE_TTL_MINUTES: int = 60
    SEVEN_ELEVEN_USER_AGENT: str = "AutoBrain/1.0 (+https://autobrainservice.app)"

    # Servo Spy fuel-price pipeline (AUT-1817): deterministic ingest of public
    # open-data feeds. WA FuelWatch = public, no key. NSW FuelCheck = free API key
    # from api.transport.nsw.gov.au (injected via FUEL_NSW_API_KEY_FILE in prod).
    # QLD Fuel Prices = public open data. VIC Servo Saver = approved partner key
    # (AUT-1932); SA/TAS/NT need a paid aggregator (Informed Sources / MotorMouth)
    # — later premium enhancement, not MVP.
    FUEL_NSW_API_KEY: str = ""
    FUEL_NSW_API_SECRET: str = ""
    FUEL_NSW_ENABLED: bool = False
    FUEL_VIC_API_KEY: str = ""
    FUEL_VIC_API_SECRET: str = ""
    FUEL_VIC_ENABLED: bool = False
    # QLD direct fuel API (FuelPricesQLD DirectAPI v1.5). Bearer-auth bearer
    # subscription token from QLD; bound from QLD_FUEL_API_KEY env. When empty
    # the QLD feed is skipped (mirrors the NSW no-key pattern). Open-data
    # fallback (www.fuelpricesqld.com.au) can be kept for one cycle behind the
    # FUEL_QLD_USE_OPEN_FALLBACK flag for partial-outage resilience.
    FUEL_QLD_API_KEY: str = ""
    FUEL_QLD_API_URL: str = "https://fppdirectapi-prod.fuelpricesqld.com.au"
    FUEL_QLD_OPEN_DATA_URL: str = "https://www.fuelpricesqld.com.au/"
    FUEL_QLD_COUNTRY_ID: int = 21  # Australia
    FUEL_QLD_REGION_LEVEL: int = 3  # state
    FUEL_QLD_USE_OPEN_FALLBACK: bool = False
    FUEL_WA_SITES_URL: str = "https://industryprd.fuelwatch.wa.gov.au/api/sites"
    FUEL_WA_PRICES_URL: str = "https://industryprd.fuelwatch.wa.gov.au/api/report/weekly-retail-prices"
    FUEL_NSW_URL: str = "https://api.transport.nsw.gov.au/v1/fuel"
    FUEL_VIC_URL: str = "https://api.servosaver.com.au/v1/prices"
    FUEL_INGEST_USER_AGENT: str = "AutoBrain Servo Spy (+https://autobrainservice.app)"

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
    SMTP_FROM_EMAIL: str = "noreply@example.com"
    SMTP_FROM_NAME: str = "AutoBrain"
    # Recipient suppression (AUT-1167): never deliver real email to reserved/
    # throwaway test domains or addresses matching these regex patterns. Guards
    # SMTP2GO reputation from smoke/deploy/QA test sends to dead addresses.
    EMAIL_SUPPRESS_DOMAINS: str = "example.com,example.org,example.net,test,invalid,testmail.com"
    EMAIL_SUPPRESS_PATTERNS: str = (
        r"^(?:smoke(?:hst\d*|[-_.]?(?:aut)?\d)|"
        r"deploy[-_.]?(?:test[-_.-])?(?:aut|test)\d|"
        r"aut\d+[-_.](?:check|host|test)|"
        r"qa[-_.](?:verify|license))"
    )
    # Public base URL used to build password-reset links (no trailing slash)
    APP_BASE_URL: str = "http://localhost:8000"

    # Versioning (local only; the GitHub update check was removed — AUT-461)
    APP_VERSION: str = "0.3.215"  # mirror frontend/pubspec.yaml version

    # Scheduled backup (daily). When set, beats stores a full JSON snapshot to MinIO.
    BACKUP_ENABLED: bool = True
    BACKUP_RETENTION_DAYS: int = 14

    # Admin API key: enables machine-to-machine user management via X-Admin-API-Key.
    ADMIN_API_KEY: str = ""  # leave empty to disable the /admin-api endpoints

    # Dongle-server backchannel: the backend calls the dongle-server to upsert
    # the serial whitelist (paid gate) and the dongle-server calls us back via
    # /devices/verify. The shared secret travels as X-Internal-Api-Key both ways.
    DONGLE_SERVER_API_KEY: str = ""  # leave empty to disable the backchannel
    DONGLE_SERVER_URL: str = ""       # base URL for the dongle-server (e.g. http://dongle-server:8000)

    # CORS origins: explicit allow-list (JSON list in env, e.g.
    # CORS_ALLOWED_ORIGINS='["https://app.example.com"]'). Empty list = same-origin
    # only (the nginx frontend proxies /api, /ws, /ai). Never pair "*" with
    # allow_credentials=True — browsers reject that combo.
    CORS_ALLOWED_ORIGINS: list[str] = []

    # CI Triage webhook (AUT-1669): receives GitHub Actions CI pings and relays
    # to the CI Triage Agent via Paperclip issue creation.
    CI_TRIAGE_WEBHOOK_SECRET: str = ""  # bearer auth secret for the webhook
    CI_TRIAGE_PARENT_ISSUE_ID: str = ""  # parent issue for child issue creation
    CI_TRIAGE_GOAL_ID: str = ""  # goal to link child issues to
    CI_TRIAGE_AGENT_ID: str = "acae6bf2"  # CI Triage Agent short id
    # Paperclip API (server-side, for creating child issues from the webhook)
    PAPERCLIP_API_URL: str = ""  # e.g. https://paperclip.nathanmartina.com
    PAPERCLIP_API_KEY: str = ""  # long-lived agent key or service token
    PAPERCLIP_COMPANY_ID: str = ""  # AutoBrain company UUID in Paperclip control plane

    # Self-service signup (hosted). When enabled, anyone can register a
    # Free-tier account via POST /auth/signup. Self-hosted instances keep
    # admin-only provisioning by leaving this off.
    SELF_SIGNUP_ENABLED: bool = False

    # Pending (invited/self-signed-up but unactivated) accounts older than this
    # are purged by the daily celery task (see workers.tasks.purge_stale_pending_accounts).
    PENDING_ACCOUNT_RETENTION_DAYS: int = 7

    # Licence/subscription feature visibility. Off by default; the hosted
    # instance turns it on. When off, the app hides the licence/upgrade page.
    LICENSE_ENABLED: bool = False

    # Community Garage (AUT-294/332). Two admin controls + federation hub.
    # SOCIAL_FEATURE_ENABLED gates the whole feature ("Disabled by your admin"
    # when off); SOCIAL_FEDERATION_ENABLED gates hub participation (off = the
    # feed still works, local builds only). Both are also runtime-overridable
    # via the admin API (persisted in social_server_config).
    SOCIAL_FEATURE_ENABLED: bool = False
    SOCIAL_FEDERATION_ENABLED: bool = False
    SOCIAL_FEDERATION_HUB_URL: str = ""  # federation hub base URL (hub is a separate service)
    SOCIAL_FEDERATION_HOSTED: bool = False  # AutoBrain-hosted = licensed free on the hub
    # Proof-of-hosting key for the hub (AUT-525): Paperclip secret injected ONLY
    # into AutoBrain-hosted stacks. Empty on self-hosted servers — sent to the
    # hub as-is, which then requires it for `hosted=true` registrations. Never
    # default this to a real value; never store it in the repo.
    SOCIAL_FEDERATION_HOSTED_REGISTRATION_KEY: str = ""

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

    # Store-native in-app purchases (AUT-610/617): Apple App Store + Google
    # Play for the store builds of the mobile app. Empty credentials keep IAP
    # disabled and the mobile app falls back to the Stripe browser path.
    # Credentials are secrets — never commit them; set them via the deployment
    # env (docker-compose.hosted.yml passes them through).
    IAP_GOOGLE_SERVICE_ACCOUNT_JSON: str = ""  # Play service-account key JSON (secret)
    IAP_GOOGLE_PACKAGE_NAME: str = "com.autobrainservice.app"
    IAP_APPLE_ISSUER_ID: str = ""              # App Store Connect API key issuer id
    IAP_APPLE_KEY_ID: str = ""                 # App Store Connect API key id
    IAP_APPLE_PRIVATE_KEY: str = ""            # App Store Connect API key .p8 PEM (secret)
    IAP_APPLE_BUNDLE_ID: str = "com.autobrainservice.app"
    # Verify-on-refresh (AUT-617): GET /auth/me re-validates the stored store
    # purchase token against the store API when the entitlement is already
    # expired or within this many days of expiring. Keeps renewals/refunds
    # propagating without webhooks; bounds external store calls to ~1/billing
    # period per user.
    IAP_REFRESH_WINDOW_DAYS: int = 2
    # Minimum minutes between store re-validations per user (AUT-617 F4). A
    # lapsed entitlement otherwise re-hits the store APIs on every /auth/me.
    IAP_REFRESH_COOLDOWN_MINUTES: int = 5
    # Google Play RTDN webhook (Pub/Sub push) OIDC token audience. Empty =
    # derive from APP_BASE_URL + the webhook path.
    IAP_GOOGLE_PUBSUB_AUDIENCE: str = ""

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
    def _harden_secrets(self) -> "Settings":
        """AUT-1181: fail closed on missing/weak secrets.

        - SECRET_KEY: required everywhere; development auto-generates an
          ephemeral random key so a known default can never sign tokens.
        - ADMIN_API_KEY: min 32 chars when enabled.
        - STRIPE_WEBHOOK_SECRET: required at startup whenever STRIPE_SECRET_KEY
          is set (otherwise forged webhooks could mutate subscriptions).
        """
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
# 
