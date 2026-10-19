"""Likes for activity social interactions (Stage 6a)."""
from datetime import datetime, timedelta, timezone
import unicodedata

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from pydantic import BaseModel

from ..database import get_db
from ..dependencies import get_current_user
from ..models import Activity, ActivityComment, ActivityReaction, User
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


class ActivityCommentCreate(BaseModel):
    body: str


def _comment_count(db: Session, activity_id: int) -> int:
    return int(
        db.query(func.count(ActivityComment.id))
        .filter(
            ActivityComment.activity_id == activity_id,
            ActivityComment.deleted_at.is_(None),
        )
        .scalar()
        or 0
    )


def _comment_payload(comment: ActivityComment, viewer: User, activity_owner_id: int) -> dict:
    author = comment.user
    return {
        "id": comment.id,
        "activity_id": comment.activity_id,
        "user_id": comment.user_id,
        "author": (author.display_name or author.username or "Пользователь") if author else "Пользователь",
        "username": author.username if author else None,
        "body": comment.body,
        "created_at": comment.created_at.isoformat() if comment.created_at else None,
        "can_delete": comment.user_id == viewer.id or activity_owner_id == viewer.id,
    }


def _recent_comments(db: Session, activity: Activity, viewer: User, limit: int = 3) -> list[dict]:
    rows = (
        db.query(ActivityComment)
        .filter(
            ActivityComment.activity_id == activity.id,
            ActivityComment.deleted_at.is_(None),
        )
        .order_by(ActivityComment.created_at.desc(), ActivityComment.id.desc())
        .limit(limit)
        .all()
    )
    return [_comment_payload(comment, viewer, activity.user_id) for comment in rows]


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
        "comments_count": _comment_count(db, activity.id),
        "latest_comments": _recent_comments(db, activity, current),
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



@router.get("/activities/{activity_id}/comments")
def list_activity_comments(
    activity_id: int,
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    activity = _visible_activity(db, current, activity_id)
    query = db.query(ActivityComment).filter(
        ActivityComment.activity_id == activity.id,
        ActivityComment.deleted_at.is_(None),
    )
    total = query.count()
    rows = (
        query.order_by(ActivityComment.created_at.desc(), ActivityComment.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {
        "total": total,
        "has_more": offset + len(rows) < total,
        "comments": [_comment_payload(comment, current, activity.user_id) for comment in rows],
    }


@router.post("/activities/{activity_id}/comments")
@limiter.limit("20/hour")
async def create_activity_comment(
    request: Request,
    activity_id: int,
    payload: ActivityCommentCreate,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    activity = _visible_activity(db, current, activity_id)
    body = payload.body.strip()
    if not body:
        raise HTTPException(status_code=422, detail="Комментарий не может быть пустым")
    if len(body) > 500:
        raise HTTPException(status_code=422, detail="Комментарий не может быть длиннее 500 символов")
    if any(unicodedata.category(char) == "Cc" for char in body):
        raise HTTPException(status_code=422, detail="Комментарий не должен содержать управляющие символы")

    comment = ActivityComment(
        activity_id=activity.id,
        user_id=current.id,
        body=body,
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)

    owner = db.get(User, activity.user_id)
    if owner is not None and owner.id != current.id:
        actor_name = (current.display_name or current.username or "Пользователь").strip()
        await notify_user(
            db,
            owner.id,
            "activity_comment",
            f"{actor_name} оставил комментарий к твоей тренировке",
            link=_activity_link(activity),
            send_telegram=True,
        )

    return {
        "comment": _comment_payload(comment, current, activity.user_id),
        "comments_count": _comment_count(db, activity.id),
    }


@router.delete("/comments/{comment_id}")
def delete_activity_comment(
    comment_id: int,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    comment = db.query(ActivityComment).filter(ActivityComment.id == comment_id).first()
    if comment is None or comment.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Комментарий не найден")

    activity = db.query(Activity).filter(Activity.id == comment.activity_id).first()
    if activity is None:
        raise HTTPException(status_code=404, detail="Тренировка не найдена")
    if not can_view_activity(db, current, activity):
        raise HTTPException(
            status_code=403,
            detail="Тренировка доступна только владельцу или принятому другу по настройкам приватности",
        )
    if comment.user_id != current.id and activity.user_id != current.id:
        raise HTTPException(status_code=403, detail="Удалить комментарий может его автор или владелец тренировки")

    comment.deleted_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    return {"ok": True, "comment_id": comment.id}
