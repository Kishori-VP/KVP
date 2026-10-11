"""Encryption for secrets stored in the database (provider API keys etc.)."""

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


class CredentialsKeyMissing(RuntimeError):
    pass


def _fernet() -> Fernet:
    if not settings.credentials_encryption_key:
        raise CredentialsKeyMissing(
            "CREDENTIALS_ENCRYPTION_KEY is not set; cannot store provider credentials"
        )
    return Fernet(settings.credentials_encryption_key.encode())


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(token: str) -> str | None:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        return None


def mask(value: str) -> str:
    if len(value) <= 4:
        return "****"
    return "*" * (len(value) - 4) + value[-4:]
