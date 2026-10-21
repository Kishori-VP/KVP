"""
Application configuration for the Kishori Vikas Program backend.

Settings are loaded from environment variables and, when available,
the local .env file. Environment variables take precedence over defaults.
"""

from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """Central application settings."""

    model_config = SettingsConfigDict(
        env_file=(str(BASE_DIR / ".env"), ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    app_name: str = "Kishori Vikas Program"
    environment: str = "development"
    api_v1_prefix: str = "/api/v1"
    timezone: str = "Asia/Kolkata"

    # MongoDB
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db_name: str = "kishori_vikas"

    # Frontend CORS configuration.
    # Supports comma-separated origins in the CORS_ORIGINS environment variable.
    cors_origins: str = "http://localhost:5173"

    # Authentication
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 12

    # Encryption for AI/OCR/voice provider credentials at rest.
    # Generate a key with:
    # python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    credentials_encryption_key: str = ""

    # File storage
    upload_dir: Path = BASE_DIR / "storage" / "uploads"
    reports_dir: Path = BASE_DIR / "storage" / "reports"
    max_upload_mb: int = 15

    # Background jobs: alerts, reminders, and scheduled reports
    scheduler_enabled: bool = True
    scheduler_interval_seconds: int = 900

    # Web Push notifications
    # Generate keys with: python -m app.seed.generate_vapid
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_subject: str = "mailto:admin@example.org"

    # Gemini RAG assistant (Stakeholder-only). Keep keys in backend/.env, never frontend/.env.
    gemini_api_key: str = ""
    gemini_chat_model: str = "gemini-3.5-flash-lite"
    gemini_embedding_model: str = "models/gemini-embedding-001"

    # Optional SMTP configuration for scheduled report emails
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_use_tls: bool = True

    @property
    def cors_origin_list(self) -> List[str]:
        """Return configured CORS origins as a list."""
        return [
            origin.strip()
            for origin in self.cors_origins.split(",")
            if origin.strip()
        ]

    @property
    def push_configured(self) -> bool:
        """Return whether both Web Push keys are configured."""
        return bool(
            self.vapid_public_key
            and self.vapid_private_key
        )

    @property
    def smtp_configured(self) -> bool:
        """Return whether the minimum SMTP settings are configured."""
        return bool(
            self.smtp_host
            and self.smtp_from
        )


@lru_cache()
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()


settings = get_settings()