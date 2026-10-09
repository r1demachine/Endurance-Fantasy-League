from functools import lru_cache
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str

    # Redis (опционально: без него уведомления идут через in-memory брокер)
    REDIS_URL: str | None = None

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
    XP_ENGINE: str = "v5"
    # Дата активации v6 (ISO). Пусто = неделя миграции каждого юзера.
    XP_V6_ACTIVATION_DATE: str = ""

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


@lru_cache()
def get_settings():
    return Settings()