"""Idempotent weekly summary delivery through the proactive notification gate."""
import asyncio
from datetime import date, datetime, timedelta
from sqlalchemy.orm import Session, sessionmaker

from ..config import get_settings
from ..models import User, WeeklySummary
from .proactive import send_proactive


def latest_completed_week_start(today: date | None = None) -> date:
    today = today or date.today()
    current_week_start = today - timedelta(days=today.weekday())
    return current_week_start - timedelta(days=7)


async def _deliver(bind, messages: list[tuple[int, date, str]]) -> int:
    factory = sessionmaker(bind=bind, expire_on_commit=False)
    delivered = 0
    with factory() as db:
        for user_id, week_start, message in messages:
            user = db.get(User, user_id)
            if user is None or not user.telegram_chat_id or not user.telegram_notify:
                continue
            if user.telegram_last_notified_week is not None and user.telegram_last_notified_week >= week_start:
                continue
            if await send_proactive(db, user, "weekly_results", message):
                user.telegram_last_notified_week = week_start
                db.commit()
                delivered += 1
    return delivered


def notify_week_results(db: Session, week_start_d: date) -> int:
    """Queue finalized weekly summaries; a skipped delivery remains eligible for the next cron tick."""
    if not get_settings().TELEGRAM_BOT_TOKEN:
        return 0

    last_completed = latest_completed_week_start()
    if week_start_d > last_completed:
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
    messages = []
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
        messages.append((user.id, week_start_d, "\n".join(parts)))

    if not messages:
        return 0
    bind = db.get_bind()
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_deliver(bind, messages))
    loop.create_task(_deliver(bind, messages))
    return len(messages)