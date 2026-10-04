import asyncio
import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from .. import broker
from ..auth import decode_access_token
from ..database import get_db
from ..dependencies import get_current_user
from ..models import Notification, User

router = APIRouter(prefix="/api/notifications", tags=["Notifications"])


@router.get("")
def list_notifications(current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (
        db.query(Notification)
        .filter(Notification.user_id == current.id)
        .order_by(Notification.created_at.desc())
        .limit(30)
        .all()
    )
    return {
        "unread": sum(1 for r in rows if not r.read),
        "items": [
            {
                "id": r.id,
                "type": r.type,
                "text": r.text,
                "read": r.read,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
    }


@router.post("/read")
def mark_all_read(current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    (
        db.query(Notification)
        .filter(Notification.user_id == current.id, Notification.read == False)  # noqa: E712
        .update({"read": True})
    )
    db.commit()
    return {"ok": True}


@router.get("/stream")
async def stream(token: str):
    """SSE-поток живых уведомлений (токен в query, т.к. EventSource без заголовков)."""
    user_id = decode_access_token(token)
    if user_id is None:
        return StreamingResponse(
            iter(['data: {"error": "unauthorized"}\n\n']),
            media_type="text/event-stream",
        )

    queue = broker.subscribe(user_id)

    async def gen():
        try:
            yield 'data: {"kind": "connected"}\n\n'
            while True:
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=20)
                    yield f"data: {json.dumps(msg)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            broker.unsubscribe(user_id, queue)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )