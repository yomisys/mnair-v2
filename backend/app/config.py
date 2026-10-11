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

    # API Keys - Nigerian SMS/USSD providers (paid channels; kept for USSD
    # learners and as an OPT-IN reminder fallback — see SMS_REMINDERS_ENABLED)
    TERMII_API_KEY: Optional[str] = None
    TERMII_SENDER_ID: str = "MNAIR"

    AFRICASTALKING_USERNAME: str = "sandbox"
    AFRICASTALKING_API_KEY: Optional[str] = None
    AFRICASTALKING_USSD_CODE: str = "*384*8080#"

    # Telegram Bot API — the free chat channel that replaced WhatsApp.
    # No per-message cost, no template approval, no 24h window. Unset token
    # = dev mode: outbound messages are logged instead of sent.
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    # Public handle (without '@') — used to build https://t.me/<username>
    # deep links on the landing page and in SMS/USSD copy.
    TELEGRAM_BOT_USERNAME: Optional[str] = None
    # Random string passed to setWebhook(secret_token=...); Telegram echoes it
    # back in X-Telegram-Bot-Api-Secret-Token so the webhook can reject
    # forged requests. Required when running in webhook mode in production.
    TELEGRAM_WEBHOOK_SECRET: Optional[str] = None
    # Long-polling is the zero-infrastructure alternative to a public webhook
    # (python telegram_bot.py). Poll timeout in seconds.
    TELEGRAM_POLL_TIMEOUT: int = 30

    # Web Push (VAPID) — free reminders for web-app learners. Generate once:
    #   python -c "from app.channels.webpush import generate_vapid_keys as g; print(g())"
    VAPID_PUBLIC_KEY: Optional[str] = None
    VAPID_PRIVATE_KEY: Optional[str] = None
    VAPID_CLAIMS_EMAIL: str = "mailto:info@mnair.ng"

    # SMS costs money per message. Off by default: reminders and certificate
    # notices go out over Telegram / Web Push. Turn on only for learners who
    # have no free channel (USSD-only) and only with budget approval.
    SMS_REMINDERS_ENABLED: bool = False

    # Web learner sign-in PIN length (digits). 4 is the floor; bump to 6 if
    # brute-force attempts show up in the auth rate-limit logs.
    LEARNER_PIN_MIN_LENGTH: int = 4

    # KingsChat — browser-automation channel (no official bot API; see
    # ~/.gstack/projects/yomisys-mnair/yomis-master-design-20260712-032947.md
    # and the follow-up /plan-eng-review for the full architecture rationale).
    # Feature-flagged: the whole channel is off unless explicitly enabled, so
    # a normal MNAIR deploy (Telegram/web/USSD/SMS) never needs these vars.
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
    # The KingsChat username (handle, without '@') the bot session MUST be
    # logged in as. Added 2026-07-17 after the first live test ran an entire
    # lesson flow as the WRONG account: the stored session file predated the
    # bot (captured during 2026-07-12 selector verification against the
    # founder's personal account), ensure_logged_in only checked that the
    # session *worked* — never *whose* it was — and every "bot" reply went
    # out as the founder. When set, the identity is verified after every
    # session establishment (stored or fresh login); a mismatched stored
    # session is discarded and a mismatched fresh login is a hard failure.
    # Optional so existing setups don't break, but any real deployment
    # should set it.
    KINGSCHAT_EXPECTED_USERNAME: Optional[str] = None
    # How many conversations are processed in parallel per poll cycle, each
    # on its own BrowserContext (from the pool) and its own DB session.
    # This is the throughput lever AND the ban-risk lever: N workers means
    # N simultaneous automated streams from one account. Keep modest.
    KINGSCHAT_CONCURRENCY: int = 3
    # Max known-active conversations direct-polled per cycle. Direct
    # polling navigates a real browser to each thread (~30-60s each), so
    # an uncapped poll makes cycle time linear in active learners — at 100
    # actives that's over an hour per cycle. The cap bounds cycle time;
    # a rotating cursor guarantees every active conversation is still
    # visited within ceil(actives/cap) cycles.
    KINGSCHAT_DIRECT_POLL_CAP: int = 12

    # Security — no default; startup fails loudly if unset in production
    SESSION_SECRET: str
    RATE_LIMIT_PER_MINUTE: int = 60
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173,http://localhost:3001,http://localhost:3002,http://localhost:3003"

    # Public site URL — used in SMS/USSD/certificate text. Must match the
    # live domain (see FRONTEND_URL in .env for prod), not a placeholder.
    FRONTEND_URL: str = "https://mnair.ng"

    # Payments (Paystack — card, bank transfer and USSD in one checkout).
    # Unset secret = payments disabled: pay endpoints answer 503 and the
    # learner is told to try later. Amounts are kobo (₦1 = 100 kobo).
    PAYSTACK_SECRET_KEY: Optional[str] = None
    PAYSTACK_PUBLIC_KEY: Optional[str] = None
    PAYSTACK_BASE_URL: str = "https://api.paystack.co"
    # Paystack insists on an email; learners sign up by phone, so they get a
    # synthetic, non-identifying address learner-{id}@<this domain>.
    PAYSTACK_PLACEHOLDER_EMAIL_DOMAIN: str = "learners.mnair.ng"

    # Individual verified certificate. Paywall is OFF by default so turning
    # this release on changes nothing for learners until it is switched on.
    # Sponsored learners never see it.
    CERTIFICATE_PAYWALL_ENABLED: bool = False
    CERTIFICATE_PRICE_KOBO: int = 200_000  # ₦2,000

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

    @property
    def telegram_link(self) -> Optional[str]:
        """Deep link to the bot, or None when no username is configured."""
        if not self.TELEGRAM_BOT_USERNAME:
            return None
        return f"https://t.me/{self.TELEGRAM_BOT_USERNAME.lstrip('@')}?start=learn"

    @property
    def learn_url(self) -> str:
        """Public URL of the web learner app."""
        return f"{self.FRONTEND_URL.rstrip('/')}/learn"

    @property
    def payments_configured(self) -> bool:
        return bool(self.PAYSTACK_SECRET_KEY)

    @property
    def payment_callback_url(self) -> str:
        """Where Paystack sends the payer back after checkout."""
        return f"{self.FRONTEND_URL.rstrip('/')}/payment/callback"

    @property
    def webpush_configured(self) -> bool:
        return bool(self.VAPID_PUBLIC_KEY and self.VAPID_PRIVATE_KEY)

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
