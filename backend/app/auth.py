"""Безопасность: пароли (PBKDF2), JWT-токены, шифрование API-ключей (Fernet)."""

import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

import jwt
from cryptography.fernet import Fernet

from .config import get_settings

_settings = get_settings()
JWT_SECRET = _settings.JWT_SECRET
JWT_ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24
LEGACY_PASSWORD_HASH_ITERATIONS = 120_000
PASSWORD_HASH_ITERATIONS = 600_000
MAX_PASSWORD_HASH_ITERATIONS = 2_000_000


# ─── Пароли: PBKDF2 без лишних зависимостей ───
def hash_password(password: str) -> str:
    """Создаёт новый PBKDF2-SHA256 хеш с текущей стоимостью."""
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_HASH_ITERATIONS
    )
    # Формат хранит алгоритм и число итераций, чтобы параметры можно было повышать.
    return f"pbkdf2_sha256\${PASSWORD_HASH_ITERATIONS}\${salt.hex()}\${dk.hex()}"


def _parse_password_hash(stored: str) -> tuple[int, bytes, bytes, bool] | None:
    """Возвращает (iterations, salt, digest, is_legacy); принимает старый salt:digest."""
    try:
        if ":" in stored and "$" not in stored:
            salt_hex, digest_hex = stored.split(":", 1)
            iterations = LEGACY_PASSWORD_HASH_ITERATIONS
            is_legacy = True
        else:
            algorithm, iterations_text, salt_hex, digest_hex = stored.split("$", 3)
            if algorithm != "pbkdf2_sha256":
                return None
            iterations = int(iterations_text)
            is_legacy = False

        if not LEGACY_PASSWORD_HASH_ITERATIONS <= iterations <= MAX_PASSWORD_HASH_ITERATIONS:
            return None

        salt = bytes.fromhex(salt_hex)
        digest = bytes.fromhex(digest_hex)
        if len(salt) != 16 or len(digest) != hashlib.sha256().digest_size:
            return None
        return iterations, salt, digest, is_legacy
    except (TypeError, ValueError):
        return None


def verify_password(password: str, stored: str) -> bool:
    parsed = _parse_password_hash(stored)
    if parsed is None:
        return False
    iterations, salt, expected_digest, _ = parsed
    actual_digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, iterations
    )
    return hmac.compare_digest(actual_digest, expected_digest)


def password_needs_rehash(stored: str) -> bool:
    parsed = _parse_password_hash(stored)
    if parsed is None:
        return True
    iterations, _, _, is_legacy = parsed
    return is_legacy or iterations < PASSWORD_HASH_ITERATIONS


# ─── JWT: 24-часовая сессия с серверным отзывом через token_version ───
def create_access_token(user_id: int, token_version: int = 0) -> str:
    payload = {
        "sub": str(user_id),
        "ver": int(token_version or 0),
        "exp": datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token_claims(token: str) -> tuple[int, int] | None:
    """Возвращает (user_id, token_version); старые токены считаются версией 0."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return int(payload["sub"]), int(payload.get("ver", 0))
    except (jwt.PyJWTError, TypeError, ValueError):
        return None


def decode_access_token(token: str) -> int | None:
    """Совместимый помощник для необязательной аутентификации публичных endpoint'ов."""
    claims = decode_access_token_claims(token)
    return claims[0] if claims is not None else None


# ─── Fernet: шифруем API-ключи Intervals ───
_fernet = Fernet(_settings.ENCRYPTION_KEY.encode())


def encrypt_secret(value: str) -> str:
    return _fernet.encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str:
    return _fernet.decrypt(value.encode()).decode()