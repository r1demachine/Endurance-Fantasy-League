"""Idempotent asynchronous Telegram summary delivery for the last completed league week."""
import asyncio
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import User, WeeklySummary
from .telegram import send_message


def latest_completed_week_start(today: date | None = None) -> date:
    today = today or date.today()
    current_week_start = today - timedelta(days=today.weekday())
    return current_week_start - timedelta(days=7)


async def _deliver(messages: list[tuple[str, str]]) -> None:
    for chat_id, message in messages:
        await send_message(chat_id, message)


def notify_week_results(db: Session, week_start_d: date) -> int:
    """Persist notification markers before enqueueing async Telegram delivery."""
    if not get_settings().TELEGRAM_BOT_TOKEN:
        return 0

    last_completed = latest_completed_week_start()
    current_week_start = last_completed + timedelta(days=7)
    if week_start_d != last_completed or week_start_d < current_week_start - timedelta(days=7):
        return 0

    week_datetime = datetime.combine(week_start_d, datetime.min.time())
    rows = (
        db.query(WeeklySummary, User)
        .join(User, User.id == WeeklySummary.user_id)
        .filter(
            WeeklySummary.week_start == week_datetime,
            WeeklySummary.finalized.is_(True),
            User.telegram_chat_id.isnot(None),
            User.telegram_notify.is_(True),
        )
        .all()
    )
    messages: list[tuple[str, str]] = []
    for summary, user in rows:
        if user.telegram_last_notified_week is not None and user.telegram_last_notified_week >= week_start_d:
            continue
        parts = [
            f"Итоги недели {week_start_d.isoformat()}:",
            f"{round(float(summary.total_xp or 0), 1)} XP",
            f"Дней: {summary.training_days or 0}",
        ]
        if summary.league_score is not None:
            parts.append(f"League score: {round(float(summary.league_score), 1)}")
        messages.append((str(user.telegram_chat_id), "\n".join(parts)))
        user.telegram_last_notified_week = week_start_d

    if not messages:
        return 0
    db.commit()

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(_deliver(messages))
    else:
        loop.create_task(_deliver(messages))
    return len(messages)
