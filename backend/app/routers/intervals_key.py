import re
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, Activity, Wellness, WeeklySummary, XPEvent, LeagueMembership
from ..dependencies import get_current_user
from ..auth import encrypt_secret, decrypt_secret
from ..config import get_settings
from ..rate_limit import limiter

router = APIRouter(prefix="/api/intervals", tags=["Intervals"])
settings = get_settings()


class KeyIn(BaseModel):
    api_key: str = Field(..., min_length=5, max_length=512)
    athlete_id: str = Field(..., min_length=2, max_length=32, pattern=r"^i?\\d+$")

    @field_validator("athlete_id", mode="before")
    @classmethod
    def normalize_athlete_id(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


class KeyStatus(BaseModel):
    has_key: bool
    athlete_id: str | None
    last_validated_at: str | None = None


async def _validate_intervals_credentials(api_key: str, athlete_id: str) -> dict | None:
    """Используем централизованную функцию из services."""
    from ..services.intervals import validate_credentials
    return await validate_credentials(api_key, athlete_id)


@router.get("/status", response_model=KeyStatus)
def key_status(current: User = Depends(get_current_user)):
    return KeyStatus(
        has_key=bool(current.api_key_encrypted),
        athlete_id=current.intervals_id,
    )


@router.post("/connect")
@limiter.limit("5/hour")
async def connect_key(
    request: Request,
    data: KeyIn,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if (
        current.privacy_consent_version != settings.PRIVACY_CONSENT_VERSION
        or current.privacy_consent_at is None
    ):
        raise HTTPException(
            status_code=403,
            detail="Перед подключением Intervals необходимо принять политику обработки данных",
        )

    # Проверяем, что athlete_id не занят другим юзером
    conflict = (
        db.query(User)
        .filter(User.intervals_id == data.athlete_id, User.id != current.id)
        .first()
    )
    if conflict:
        raise HTTPException(
            status_code=409,
            detail=f"Этот athlete_id уже привязан к другому аккаунту",
        )
    
    # Валидация ключа через Intervals API
    info = await _validate_intervals_credentials(data.api_key, data.athlete_id)
    if info is None:
        raise HTTPException(
            status_code=400,
            detail="Неверный API-ключ или athlete_id. Проверь в Intervals.icu → Settings → API",
        )
    
    # Сохраняем (шифруем ключ)
    current.intervals_id = data.athlete_id
    current.api_key_encrypted = encrypt_secret(data.api_key)
    
    # Имя из Intervals (если есть)
    fn = info.get("firstName") or info.get("first_name")
    ln = info.get("lastName") or info.get("last_name")
    if fn:
        current.firstname = fn
    if ln:
        current.lastname = ln
    
    db.commit()
    db.refresh(current)
    
    return {
        "message": "Intervals.icu подключён",
        "athlete_id": current.intervals_id,
        "name_from_intervals": f"{fn or ''} {ln or ''}".strip() or None,
    }


@router.delete("/disconnect")
def disconnect_key(
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Отвязать Intervals и удалить ключ вместе с импортированными данными источника."""
    user_id = current.id
    deleted_activities = db.query(Activity).filter(
        Activity.user_id == user_id
    ).delete(synchronize_session=False)
    deleted_wellness = db.query(Wellness).filter(
        Wellness.user_id == user_id
    ).delete(synchronize_session=False)
    db.query(XPEvent).filter(XPEvent.user_id == user_id).delete(synchronize_session=False)
    db.query(WeeklySummary).filter(WeeklySummary.user_id == user_id).delete(synchronize_session=False)
    db.query(LeagueMembership).filter(LeagueMembership.user_id == user_id).delete(synchronize_session=False)

    current.intervals_id = None
    current.api_key_encrypted = None
    current.firstname = None
    current.lastname = None
    current.legacy_xp_offset = 0.0
    current.xp_migrated_at = None
    current.division_current = None
    current.division_placed_at = None
    current.total_xp = 0.0
    current.level = 1
    db.commit()
    return {
        "message": "Intervals отвязан; API-ключ и импортированные тренировки, wellness и связанные XP удалены",
        "deleted_activities": deleted_activities,
        "deleted_wellness": deleted_wellness,
    }


def get_decrypted_intervals_creds(user: User) -> tuple[str, str] | None:
    """Вспомогательная функция для других роутеров: возвращает (api_key, athlete_id)."""
    if not user.api_key_encrypted or not user.intervals_id:
        return None
    try:
        return decrypt_secret(user.api_key_encrypted), user.intervals_id
    except Exception:
        return None