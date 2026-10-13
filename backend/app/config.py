from datetime import date
import re
from functools import lru_cache
from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str

    # Redis (опционально: без него уведомления идут через in-memory брокер)
    REDIS_URL: Optional[str] = None
    # Trust this header only on a deployment where Cloudflare overwrites it (Render).
    TRUST_CF_CONNECTING_IP: bool = False

    # Intervals.icu — только базовый URL. API-ключи у каждого пользователя свои.
    INTERVALS_API_URL: str = "https://intervals.icu/api/v1"

    # Секреты. Это ДВА РАЗНЫХ значения.
    JWT_SECRET: str        # подпись JWT-токенов
    ENCRYPTION_KEY: str    # ключ Fernet для шифрования API-ключей Intervals

    # Админка: id пользователей через запятую, например "1" или "1,5"
    ADMIN_USER_IDS: str = ""

    # "production" на Render -> отключает /docs, /redoc, /openapi.json
    APP_ENV: str = "development"
    # Движок XP: "v5" (старые множители) | "v6" (аддитивная система)
    XP_ENGINE: str = "v6"
    # Дата активации v6 (ISO). Пусто = неделя миграции каждого юзера.
    XP_V6_ACTIVATION_DATE: str = ""
    # Разрешённые браузерные origins, разделённые запятыми; не используем wildcard.
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000,https://endurance-fantasy-league.vercel.app"
    # Ачивки учитывают данные с начала календарного года; после настройки возможна ретроактивная выдача за этот период.
    XP_QUESTS_ACTIVATION_DATE: date = date(2026, 1, 1)
    # Increment when the data-processing consent text changes materially.
    PRIVACY_CONSENT_VERSION: str = "2026-10-11-v1"
    # Telegram bot (optional). Without token webhook is disabled.
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_WEBHOOK_SECRET: Optional[str] = None
    TELEGRAM_BOT_USERNAME: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8-sig",
        extra="ignore",
        case_sensitive=False,
    )

    @field_validator("JWT_SECRET")
    @classmethod
    def _jwt_secret_strong(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("JWT_SECRET должен быть не короче 32 символов")
        return v

    @field_validator("TELEGRAM_WEBHOOK_SECRET")
    @classmethod
    def _valid_telegram_webhook_secret(cls, value: Optional[str]) -> Optional[str]:
        if value is None or value == "":
            return None
        if not re.fullmatch(r"[A-Za-z0-9_-]{16,256}", value):
            raise ValueError("TELEGRAM_WEBHOOK_SECRET должен содержать 16–256 символов A-Z, a-z, 0-9, _ или -")
        return value


@lru_cache()
def get_settings():
    return Settings()
