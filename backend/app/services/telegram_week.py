"""Синхронная рассылка итогов недели в Telegram (вызывается из close league)."""
from datetime import datetime

import httpx
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import User, WeeklySummary


def notify_week_results(db: Session, week_start_d) -> int:
    """Шлёт итоги недели пользователям с telegram_notify=True."""
    settings = get_settings()
    if not settings.TELEGRAM_BOT_TOKEN:
        return 0
    ws_dt = datetime.combine(week_start_d, datetime.min.time())
    rows = (
        db.query(WeeklySummary, User)
        .join(User, User.id == WeeklySummary.user_id)
        .filter(
            WeeklySummary.week_start == ws_dt,
            WeeklySummary.finalized.is_(True),
            User.telegram_chat_id.isnot(None),
            User.telegram_notify.is_(True),
        )
        .all()
    )
    sent = 0
    token = settings.TELEGRAM_BOT_TOKEN
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    with httpx.Client(timeout=15.0) as client:
        for summ, user in rows:
            parts = [
                f"Итоги недели {week_start_d.isoformat()}:",
                f"{round(float(summ.total_xp or 0), 1)} XP",
                f"Дней: {summ.training_days or 0}",
            ]
            if summ.league_score is not None:
                parts.append(f"League score: {round(float(summ.league_score), 1)}")
            text = "\n".join(parts)
            try:
                r = client.post(
                    url,
                    json={
                        "chat_id": user.telegram_chat_id,
                        "text": text,
                        "disable_web_page_preview": True,
                    },
                )
                if r.status_code < 400:
                    sent += 1
            except Exception:
                pass
    return sent
