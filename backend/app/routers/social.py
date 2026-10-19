"""Likes for activity social interactions (Stage 6a)."""
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user
from ..models import Activity, ActivityReaction, User
from ..rate_limit import limiter
from ..services.activity_visibility import can_view_activity
from ..services.notifications import notify_user

router = APIRouter(prefix="/api", tags=["Activity Social"])


def _visible_activity(db: Session, viewer: User, activity_id: int) -> Activity:
    activity = db.query(Activity).filter(Activity.id == activity_id).first()
    if activity is None:
        raise HTTPException(status_code=404, detail="Тренировка не найдена")
    if not can_view_activity(db, viewer, activity):
        raise HTTPException(
            status_code=403,
            detail="Тренировка доступна только владельцу или принятому другу по настройкам приватности",
        )
    return activity


def _week_start_for_activity(activity: Activity) -> str | None:
    stamp = activity.start_date_local or activity.start_date
    if stamp is None:
        return None
    day = stamp.date()
    return (day - timedelta(days=day.weekday())).isoformat()


def _activity_link(activity: Activity) -> str:
    week_start = _week_start_for_activity(activity)
    link = f"/dashboard?activity_id={activity.id}"
    if week_start:
        link += f"&week_start={week_start}"
    return link


def _reaction_count(db: Session, activity_id: int) -> int:
    return int(
        db.query(func.count(ActivityReaction.id))
        .filter(
            ActivityReaction.activity_id == activity_id,
            ActivityReaction.kind == "like",
        )
        .scalar()
        or 0
    )


@router.get("/activities/{activity_id}/social")
def get_activity_social(
    activity_id: int,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    activity = _visible_activity(db, current, activity_id)
    liked_by_me = (
        db.query(ActivityReaction.id)
        .filter(
            ActivityReaction.activity_id == activity.id,
            ActivityReaction.user_id == current.id,
            ActivityReaction.kind == "like",
        )
        .first()
        is not None
    )
    stamp = activity.start_date_local or activity.start_date
    return {
        "activity_id": activity.id,
        "likes_count": _reaction_count(db, activity.id),
        "liked_by_me": liked_by_me,
        "week_start": _week_start_for_activity(activity),
        "activity_date": stamp.date().isoformat() if stamp is not None else None,
    }


@router.put("/activities/{activity_id}/reaction")
@limiter.limit("60/minute")
async def toggle_activity_reaction(
    request: Request,
    activity_id: int,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    activity = _visible_activity(db, current, activity_id)
    existing = (
        db.query(ActivityReaction)
        .filter(
            ActivityReaction.activity_id == activity.id,
            ActivityReaction.user_id == current.id,
            ActivityReaction.kind == "like",
        )
        .first()
    )
    created = False

    if existing is not None:
        db.delete(existing)
        db.commit()
        liked = False
    else:
        db.add(ActivityReaction(activity_id=activity.id, user_id=current.id, kind="like"))
        try:
            db.commit()
            liked = True
            created = True
        except IntegrityError:
            # Concurrent requests can both observe the missing row. The unique
            # constraint wins; a losing insert becomes the already-created like.
            db.rollback()
            still_liked = (
                db.query(ActivityReaction.id)
                .filter(
                    ActivityReaction.activity_id == activity.id,
                    ActivityReaction.user_id == current.id,
                    ActivityReaction.kind == "like",
                )
                .first()
                is not None
            )
            if not still_liked:
                raise HTTPException(status_code=409, detail="Не удалось сохранить реакцию")
            liked = True

    likes_count = _reaction_count(db, activity.id)
    owner = db.get(User, activity.user_id)
    if created and owner is not None and owner.id != current.id:
        actor_name = (current.display_name or current.username or "Пользователь").strip()
        await notify_user(
            db,
            owner.id,
            "activity_like",
            f"{actor_name} оценил твою тренировку",
            link=_activity_link(activity),
            send_telegram=False,
        )

    return {
        "activity_id": activity.id,
        "liked": liked,
        "liked_by_me": liked,
        "likes_count": likes_count,
        "week_start": _week_start_for_activity(activity),
    }
