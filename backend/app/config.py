"""
Application Configuration
Loads environment variables and provides configuration settings
"""

from __future__ import annotations
from functools import lru_cache
from typing import Optional
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # Application
    APP_NAME: str = "Make Nigeria AI Ready"
    APP_ENV: str = "development"
    APP_DEBUG: bool = True
    API_VERSION: str = "v1"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://mnair:mnair_password@localhost:5433/mnair_db"
    DATABASE_HOST: str = "localhost"
    DATABASE_PORT: int = 5433
    DATABASE_NAME: str = "mnair_db"
    DATABASE_USER: str = "mnair"
    DATABASE_PASSWORD: str = "mnair_password"

    # Redis
    REDIS_URL: str = "redis://localhost:6380/0"
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6380

    # MinIO/S3
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "mnair-certificates"
    MINIO_SECURE: bool = False

    # JWT Authentication — no default; startup fails loudly if unset in production
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_MINUTES: int = 10080

    # API Keys - Nigerian SMS/WhatsApp Providers
    TERMII_API_KEY: Optional[str] = None
    TERMII_SENDER_ID: str = "MNAIR"

    AFRICASTALKING_USERNAME: str = "sandbox"
    AFRICASTALKING_API_KEY: Optional[str] = None
    AFRICASTALKING_USSD_CODE: str = "*384*8080#"

    META_WHATSAPP_TOKEN: Optional[str] = None
    META_WHATSAPP_PHONE_NUMBER_ID: Optional[str] = None
    META_VERIFY_TOKEN: Optional[str] = None
    META_WEBHOOK_SECRET: Optional[str] = None

    # KingsChat — browser-automation channel (no official bot API; see
    # ~/.gstack/projects/yomisys-mnair/yomis-master-design-20260712-032947.md
    # and the follow-up /plan-eng-review for the full architecture rationale).
    # Feature-flagged: the whole channel is off unless explicitly enabled, so
    # a normal MNAIR deploy (WhatsApp/USSD/SMS only) never needs these vars.
    KINGSCHAT_ENABLED: bool = False
    # No defaults on any of the four below — required whenever
    # KINGSCHAT_ENABLED is true. Same fix pattern as the P0 TODOS.md item for
    # JWT_SECRET_KEY/MINIO keys: fail loudly at startup rather than silently
    # running with a guessable default.
    KINGSCHAT_ACCOUNT_EMAIL: Optional[str] = None
    KINGSCHAT_ACCOUNT_PASSWORD: Optional[str] = None
    # Path to the encrypted session/cookie store (see
    # app.services.kingschat_session_store). This file holds captured login
    # session data, which is hijack material worse than a password — it
    # bypasses login and 2FA entirely if it leaks. Encrypted at rest with
    # KINGSCHAT_SESSION_ENCRYPTION_KEY; the path itself must also be in
    # .gitignore (already added).
    KINGSCHAT_SESSION_STORE_PATH: Optional[str] = None
    KINGSCHAT_SESSION_ENCRYPTION_KEY: Optional[str] = None
    # Pooled BrowserContext sizing (see app.services.kingschat_browser_pool).
    # This is the one lever controlling both throughput and memory/CPU cost —
    # kept as a config value (not hardcoded) so it's tunable without a
    # redeploy, and pool exhaustion is logged so a capacity problem is
    # visible instead of surfacing only as learner complaints.
    KINGSCHAT_POOL_SIZE: int = 10
    # Per-context proxy assignment, if the fingerprint-isolation research
    # (TODOS.md P0 item, still open as of this commit) concludes that
    # pooled contexts sharing one browser process need separate egress IPs
    # to avoid looking more automated than isolated sessions would. Empty by
    # default (no proxy) until that research lands; wiring the setting in
    # now avoids a pool redesign later if the answer is "yes, need proxies".
    KINGSCHAT_CONTEXT_PROXY_SERVER: Optional[str] = None

    # Security — no default; startup fails loudly if unset in production
    SESSION_SECRET: str
    RATE_LIMIT_PER_MINUTE: int = 60
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173,http://localhost:3001,http://localhost:3002,http://localhost:3003"

    # Public site URL — used in SMS/USSD/certificate text. Must match the
    # live domain (see FRONTEND_URL in .env for prod), not a placeholder.
    FRONTEND_URL: str = "https://mnair.ng"

    # NDPA Compliance
    DATA_RETENTION_DAYS: int = 90
    CONSENT_REQUIRED: bool = True

    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6380/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6380/2"

    # Admin
    ADMIN_EMAIL: str = "admin@mnair.gov.ng"
    ADMIN_PASSWORD: str = "change_this_password"

    # Monitoring
    PROMETHEUS_PORT: int = 9090
    GRAFANA_PORT: int = 3001

    # Email
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM_EMAIL: str = "noreply@mnair.gov.ng"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]

    @model_validator(mode="after")
    def _require_kingschat_credentials_when_enabled(self) -> "Settings":
        """Fail loudly at startup, not silently at first use.

        KINGSCHAT_ENABLED=true with any of these unset is exactly the
        hardcoded-default failure mode already flagged as P0 elsewhere in
        this config (see JWT_SECRET_KEY/MINIO_* history) — the fields have
        no defaults on purpose, so this validator is what actually turns a
        missing var into a startup crash instead of a None that reaches
        Playwright and fails confusingly three layers deep.
        """
        if self.KINGSCHAT_ENABLED:
            missing = [
                name
                for name in (
                    "KINGSCHAT_ACCOUNT_EMAIL",
                    "KINGSCHAT_ACCOUNT_PASSWORD",
                    "KINGSCHAT_SESSION_STORE_PATH",
                    "KINGSCHAT_SESSION_ENCRYPTION_KEY",
                )
                if not getattr(self, name)
            ]
            if missing:
                raise ValueError(
                    "KINGSCHAT_ENABLED=true but missing required settings: "
                    f"{', '.join(missing)}. Set these env vars or set "
                    "KINGSCHAT_ENABLED=false."
                )
        return self


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
