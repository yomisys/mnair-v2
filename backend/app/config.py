"""
Application Configuration
Loads environment variables and provides configuration settings
"""

from __future__ import annotations
from functools import lru_cache
from typing import Optional
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

    # Security — no default; startup fails loudly if unset in production
    SESSION_SECRET: str
    RATE_LIMIT_PER_MINUTE: int = 60
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"

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


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
