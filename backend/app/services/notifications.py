"""Создание уведомления: запись в БД + публикация в брокер."""
from sqlalchemy.orm import Session

from ..models import Notification
from ..broker import publish


async def notify_user(db: Session, user_id: int, ntype: str, text: str) -> None:
    db.add(Notification(user_id=user_id, type=ntype, text=text, read=False))
    db.commit()
    await publish(user_id, {"kind": "notification", "type": ntype, "text": text})