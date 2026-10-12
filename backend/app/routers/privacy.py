from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..auth import verify_password
from ..config import get_settings
from ..database import get_db
from ..dependencies import get_current_user
from ..models import (
    Activity,
    Club,
    ClubJoinAttempt,
    ClubJoinRequest,
    ClubMember,
    ClubMemberRole,
    Duel,
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
    password: str = Field(..., min_length=1, max_length=128)


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


def _cleanup_social_for_user(db: Session, uid: int) -> None:
    """Дуэли, клубы и заявки до удаления User (FK без cascade)."""
    db.query(Duel).filter(
        or_(Duel.challenger_id == uid, Duel.opponent_id == uid)
    ).delete(synchronize_session=False)
    db.query(Duel).filter(Duel.winner_id == uid).update(
        {Duel.winner_id: None}, synchronize_session=False
    )

    db.query(ClubJoinRequest).filter(ClubJoinRequest.user_id == uid).delete(
        synchronize_session=False
    )
    # Attempt audit rows reference users without ON DELETE CASCADE.
    db.query(ClubJoinAttempt).filter(ClubJoinAttempt.user_id == uid).delete(
        synchronize_session=False
    )

    owned_clubs = db.query(Club).filter(Club.owner_id == uid).all()
    for club in owned_clubs:
        others = (
            db.query(ClubMember)
            .filter(ClubMember.club_id == club.id, ClubMember.user_id != uid)
            .order_by(ClubMember.joined_at.asc(), ClubMember.id.asc())
            .all()
        )
        if others:
            successor = others[0]
            club.owner_id = successor.user_id
            successor.role = ClubMemberRole.OWNER.value
        else:
            db.query(ClubJoinRequest).filter(ClubJoinRequest.club_id == club.id).delete(
                synchronize_session=False
            )
            db.query(ClubMember).filter(ClubMember.club_id == club.id).delete(
                synchronize_session=False
            )
            db.delete(club)

    db.query(ClubMember).filter(ClubMember.user_id == uid).delete(
        synchronize_session=False
    )


@router.delete("/account")
def delete_account(
    data: DeleteAccountInput,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Permanently delete this user's personal and derived records."""
    if not verify_password(data.password, current.password_hash):
        raise HTTPException(status_code=403, detail="Неверный пароль")

    uid = current.id
    try:
        _cleanup_social_for_user(db, uid)

        db.query(Friendship).filter(
            (Friendship.from_user_id == uid) | (Friendship.to_user_id == uid)
        ).delete(synchronize_session=False)
        db.query(Notification).filter(Notification.user_id == uid).delete(
            synchronize_session=False
        )
        db.query(LeagueMembership).filter(LeagueMembership.user_id == uid).delete(
            synchronize_session=False
        )
        db.query(XPEvent).filter(XPEvent.user_id == uid).delete(synchronize_session=False)
        db.query(WeeklySummary).filter(WeeklySummary.user_id == uid).delete(
            synchronize_session=False
        )
        db.query(Wellness).filter(Wellness.user_id == uid).delete(synchronize_session=False)
        db.query(Activity).filter(Activity.user_id == uid).delete(synchronize_session=False)

        current.api_key_encrypted = None
        current.intervals_id = None
        db.delete(current)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {"deleted": True, "message": "Аккаунт и связанные данные удалены"}
