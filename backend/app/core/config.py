from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Kishori Vikas Program"
    environment: str = "development"
    api_v1_prefix: str = "/api/v1"
    timezone: str = "Asia/Kolkata"

    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db_name: str = "kishori_vikas"

    cors_origins: str = "http://localhost:5173"

    # Auth
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 12

    # Fernet key used to encrypt AI/OCR/voice provider credentials at rest.
    # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    credentials_encryption_key: str = ""

    # File storage
    upload_dir: Path = BASE_DIR / "storage" / "uploads"
    reports_dir: Path = BASE_DIR / "storage" / "reports"
    max_upload_mb: int = 15

    # Background jobs (alerts, reminders, scheduled reports)
    scheduler_enabled: bool = True
    scheduler_interval_seconds: int = 900

    # Web Push (PWA notifications). Generate with: python -m app.seed.generate_vapid
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_subject: str = "mailto:admin@example.org"

    # Optional SMTP for sharing scheduled reports by email
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_use_tls: bool = True

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def push_configured(self) -> bool:
        return bool(self.vapid_public_key and self.vapid_private_key)

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_from)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
