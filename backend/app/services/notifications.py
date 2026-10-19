"""Notification persistence, realtime publication and optional Telegram delivery."""
import re
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from ..models import Notification
from ..broker import publish


_ACTIVITY_NOTIFICATION_MARKERS = {
    "activity_like": (" оценил твою тренировку", " оценили твою тренировку"),
    "activity_comment": (
        " оставил комментарий к твоей тренировке",
        " оставили комментарии к твоей тренировке",
    ),
}


def _combine_activity_notification(existing_text: str, ntype: str) -> str | None:
    """Return roll-up text for a second or later activity notification."""
    markers = _ACTIVITY_NOTIFICATION_MARKERS.get(ntype)
    if not markers:
        return None
    singular_marker, plural_marker = markers

    if " и ещё " in existing_text:
        first_actor, remainder = existing_text.split(" и ещё ", 1)
        match = re.match(r"^(\d+)\b", remainder)
        if not match:
            return None
        additional_people = int(match.group(1)) + 1
    elif existing_text.endswith(singular_marker):
        first_actor = existing_text[:-len(singular_marker)]
        additional_people = 1
    else:
        return None

    return f"{first_actor} и ещё {additional_people}{plural_marker}"


async def notify_user(
    db: Session,
    user_id: int,
    ntype: str,
    text: str,
    link: str | None = None,
    send_telegram: bool = True,
) -> None:
    """Persist and publish a notification; roll up recent unread activity notifications."""
    now = datetime.utcnow()
    row = None

    if link and ntype in _ACTIVITY_NOTIFICATION_MARKERS:
        cutoff = now - timedelta(minutes=30)
        row = (
            db.query(Notification)
            .filter(
                Notification.user_id == user_id,
                Notification.type == ntype,
                Notification.link == link,
                Notification.read.is_(False),
                Notification.created_at >= cutoff,
            )
            .order_by(Notification.created_at.desc(), Notification.id.desc())
            .first()
        )
        if row is not None:
            combined_text = _combine_activity_notification(row.text, ntype)
            if combined_text:
                row.text = combined_text
                row.created_at = now
            else:
                row = None

    if row is None:
        row = Notification(
            user_id=user_id,
            type=ntype,
            text=text,
            link=link,
            read=False,
            created_at=now,
        )
        db.add(row)

    db.commit()
    await publish(
        user_id,
        {
            "kind": "notification",
            "id": row.id,
            "type": ntype,
            "text": row.text,
            "link": row.link,
            "read": bool(row.read),
            "created_at": row.created_at.isoformat() if row.created_at else None,
        },
    )

    if send_telegram:
        try:
            from .telegram import notify_telegram_user
            await notify_telegram_user(db, user_id, row.text)
        except Exception as exc:  # noqa: BLE001
            print(f"Telegram notify failed: {type(exc).__name__}: {exc}")
