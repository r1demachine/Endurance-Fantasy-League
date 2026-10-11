from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..dependencies import get_current_user
from ..models import (
    Activity,
    EmailCode,
    Friendship,
    LeagueMembership,
    Notification,
    User,
    Wellness,
    WeeklySummary,
    XPEvent,
)

router = APIRouter(prefix="/api", tags=["Privacy"])


class PrivacyUpdate(BaseModel):
    profile_visibility: Literal["authenticated", "friends", "private"] | None = None
    activity_visibility: Literal["friends", "private"] | None = None


class ConsentInput(BaseModel):
    consent: bool = Field(..., description="Explicit consent to the current data policy")


class DeleteAccountInput(BaseModel):
    confirmation: Literal["DELETE"]


def _consent_is_current(user: User) -> bool:
    return (
        user.privacy_consent_version == get_settings().PRIVACY_CONSENT_VERSION
        and user.privacy_consent_at is not None
    )


@router.get("/privacy")
def get_privacy_settings(
    current: User = Depends(get_current_user),
):
    settings = get_settings()
    return {
        "profile_visibility": current.profile_visibility or "authenticated",
        "activity_visibility": current.activity_visibility or "friends",
        "privacy_consent_version": current.privacy_consent_version,
        "privacy_consent_at": current.privacy_consent_at.isoformat() if current.privacy_consent_at else None,
        "privacy_consent_current": _consent_is_current(current),
        "current_consent_version": settings.PRIVACY_CONSENT_VERSION,
    }


@router.patch("/privacy")
def update_privacy_settings(
    data: PrivacyUpdate,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if data.profile_visibility is None and data.activity_visibility is None:
        raise HTTPException(status_code=422, detail="Не переданы настройки приватности")
    if data.profile_visibility is not None:
        current.profile_visibility = data.profile_visibility
    if data.activity_visibility is not None:
        current.activity_visibility = data.activity_visibility
    db.commit()
    return {
        "profile_visibility": current.profile_visibility,
        "activity_visibility": current.activity_visibility,
    }


@router.post("/privacy/consent")
def accept_current_data_policy(
    data: ConsentInput,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not data.consent:
        raise HTTPException(status_code=400, detail="Для продолжения необходимо явное согласие")
    current.privacy_consent_version = get_settings().PRIVACY_CONSENT_VERSION
    current.privacy_consent_at = datetime.utcnow()
    db.commit()
    return {
        "accepted": True,
        "version": current.privacy_consent_version,
        "accepted_at": current.privacy_consent_at.isoformat(),
    }


@router.delete("/account")
def delete_account(
    data: DeleteAccountInput,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Permanently delete this user's personal and derived records."""
    uid = current.id

    # Delete all rows with explicit user FKs first. LeagueWeek is shared and is kept.
    db.query(Friendship).filter(
        (Friendship.from_user_id == uid) | (Friendship.to_user_id == uid)
    ).delete(synchronize_session=False)
    db.query(Notification).filter(Notification.user_id == uid).delete(synchronize_session=False)
    db.query(LeagueMembership).filter(LeagueMembership.user_id == uid).delete(synchronize_session=False)
    db.query(XPEvent).filter(XPEvent.user_id == uid).delete(synchronize_session=False)
    db.query(WeeklySummary).filter(WeeklySummary.user_id == uid).delete(synchronize_session=False)
    db.query(Wellness).filter(Wellness.user_id == uid).delete(synchronize_session=False)
    db.query(Activity).filter(Activity.user_id == uid).delete(synchronize_session=False)

    db.query(EmailCode).filter(EmailCode.user_id == uid).delete(synchronize_session=False)

    # The foreign key is unique and nullable; clear provider credentials before deleting.
    current.api_key_encrypted = None
    current.intervals_id = None
    db.delete(current)
    db.commit()
    return {"deleted": True, "message": "Аккаунт и связанные данные удалены"}
