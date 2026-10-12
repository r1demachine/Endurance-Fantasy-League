"""Создание уведомления: запись в БД + публикация в брокер + Telegram."""
from sqlalchemy.orm import Session

from ..models import Notification
from ..broker import publish


async def notify_user(db: Session, user_id: int, ntype: str, text: str) -> None:
    db.add(Notification(user_id=user_id, type=ntype, text=text, read=False))
    db.commit()
    await publish(user_id, {"kind": "notification", "type": ntype, "text": text})
    try:
        from .telegram import notify_telegram_user
        await notify_telegram_user(db, user_id, text)
    except Exception as exc:  # noqa: BLE001
        print(f"⚠️ telegram notify failed: {type(exc).__name__}: {exc}")
