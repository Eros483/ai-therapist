"""Fernet app-layer encryption at rest (impl §5.5, §7.1).

Session content is encrypted before hitting Postgres; the Fernet key is
`settings.secret_key` (a deployment concern, documented at build time). The
fernet object is built lazily per call so tests can swap `settings.secret_key`.
"""

from cryptography.fernet import Fernet

from app.config.settings import settings


def _fernet() -> Fernet:
    return Fernet(settings.secret_key.encode())


def encrypt_bytes(data: bytes) -> bytes:
    return _fernet().encrypt(data)


def decrypt_bytes(token: bytes) -> bytes:
    return _fernet().decrypt(token)


def encrypt_str(plain: str) -> str:
    return _fernet().encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt_str(token: str) -> str:
    return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
