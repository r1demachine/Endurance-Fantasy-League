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
TOKEN_EXPIRE_DAYS = 7


# ─── Пароли: PBKDF2 без лишних зависимостей ───
def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 120_000)
    return salt.hex() + ":" + dk.hex()


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, dk_hex = stored.split(":")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), 120_000)
        result = hmac.compare_digest(dk, bytes.fromhex(dk_hex))
        return result
    except Exception as e:
        print(f"❌ verify_password error: {type(e).__name__}: {e}")
        return False


# ─── JWT: сессия на 7 дней ───
def create_access_token(user_id: int) -> str:
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(timezone.utc) + timedelta(days=TOKEN_EXPIRE_DAYS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> int | None:
    """Возвращает user_id или None."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return int(payload["sub"])
    except jwt.PyJWTError:
        return None


# ─── Fernet: шифруем API-ключи Intervals ───
_fernet = Fernet(_settings.ENCRYPTION_KEY.encode())


def encrypt_secret(value: str) -> str:
    return _fernet.encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str:
    return _fernet.decrypt(value.encode()).decode()