"""Single gate for rate-limited, opt-in proactive Telegram messages."""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Activity, Friendship, FriendshipStatus, NotificationLog, User, XPEvent
from . import xp_v6 as X6
from .telegram import send_message

logger = logging.getLogger(__name__)

# These defaults preserve existing weekly/social notifications for users who
# already opted into Telegram. The master telegram_notify switch remains mandatory.
DEFAULT_NOTIFY_PREFS = {
    "daily_bonus_reminder": True,
    "league_overtaken": True,
    "weekly_results": True,
    "activity_social": True,
}
DAILY_LIMIT = 1
WEEKLY_LIMIT = 4
QUIET_START_HOUR = 22
QUIET_END_HOUR = 8
REMINDER_START_HOUR = 21
REMINDER_END_HOUR = 22
REMINDER_DECAY_COUNT = 3
PROACTIVE_FOOTER = "Отключить уведомления: /notify off или в настройках профиля на сайте."


def _zone(user: User) -> ZoneInfo:
    try:
        return ZoneInfo(getattr(user, "timezone_name", None) or "UTC")
    except (ZoneInfoNotFoundError, TypeError, ValueError):
        return ZoneInfo("UTC")


def user_local_datetime(user: User, now: datetime | None = None) -> datetime:
    """Convert an optional instant to the user's timezone, safely handling naive test values."""
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(_zone(user))


def local_date_for_user(user: User, now: datetime | None = None) -> date:
    return user_local_datetime(user, now).date()


def is_quiet_hours(local_moment: datetime) -> bool:
    """Quiet hours are [22:00, 08:00) in the user's local timezone."""
    return local_moment.hour >= QUIET_START_HOUR or local_moment.hour < QUIET_END_HOUR


def is_daily_reminder_window(local_moment: datetime) -> bool:
    return REMINDER_START_HOUR <= local_moment.hour < REMINDER_END_HOUR


def get_notify_prefs(user: User) -> dict[str, bool]:
    try:
        stored = json.loads(user.notify_prefs or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        stored = {}
    if not isinstance(stored, dict):
        stored = {}
    return {
        key: stored.get(key) if isinstance(stored.get(key), bool) else default
        for key, default in DEFAULT_NOTIFY_PREFS.items()
    }


def qualified_activity_days(
    db: Session,
    user: User,
    start_day: date,
    end_day: date,
) -> set[date]:
    """Return qualifying dates using the XP v6 training-load/time predicate."""
    from .day_ledger import activity_day, activity_tss

    start_dt = datetime.combine(start_day, time.min)
    end_dt = datetime.combine(end_day + timedelta(days=1), time.min)
    activities = (
        db.query(Activity)
        .filter(
            Activity.user_id == user.id,
            func.coalesce(Activity.start_date_local, Activity.start_date) >= start_dt,
            func.coalesce(Activity.start_date_local, Activity.start_date) < end_dt,
        )
        .order_by(Activity.id.asc())
        .all()
    )
    by_day: dict[date, list[Activity]] = {}
    for activity in activities:
        day = activity_day(activity)
        if day is not None and start_day <= day <= end_day:
            by_day.setdefault(day, []).append(activity)

    qualifying = set()
    for day, day_activities in by_day.items():
        daily_tss = sum(activity_tss(activity) for activity in day_activities)
        if X6.is_qualifying_day(
            [{"moving_time": int(activity.moving_time or 0)} for activity in day_activities],
            daily_tss,
        ):
            qualifying.add(day)
    return qualifying


def _user_is_paused(user: User, day: date) -> bool:
    if user.pause_set_at is None or user.paused_until is None:
        return False
    start_week = X6.week_start(user.pause_set_at.date())
    end_week = X6.week_start(user.paused_until.date())
    return start_week <= X6.week_start(day) < end_week


def _has_daily_bonus(db: Session, user: User, day: date) -> bool:
    start_dt = datetime.combine(day, time.min)
    end_dt = datetime.combine(day + timedelta(days=1), time.min)
    return (
        db.query(XPEvent.id)
        .filter(
            XPEvent.user_id == user.id,
            XPEvent.event_type == "activity_bonus",
            XPEvent.event_key.like("bonus:daily_workout:%"),
            XPEvent.amount > 0,
            XPEvent.date >= start_dt,
            XPEvent.date < end_dt,
        )
        .first()
        is not None
    )


def reminder_decay_active(db: Session, user: User, today: date) -> bool:
    """Suppress further reminders after three consecutive reminder days until a workout occurs."""
    reminders = (
        db.query(NotificationLog)
        .filter(
            NotificationLog.user_id == user.id,
            NotificationLog.kind == "daily_bonus_reminder",
            NotificationLog.local_date <= today,
        )
        .order_by(NotificationLog.local_date.desc(), NotificationLog.id.desc())
        .limit(60)
        .all()
    )
    reminder_dates = {row.local_date for row in reminders}
    if len(reminder_dates) < REMINDER_DECAY_COUNT:
        return False

    # The streak remains in the log while reminders are suppressed. The user
    # remains suppressed even after the first 24 hours until any workout occurs.
    for last_day in sorted(reminder_dates, reverse=True):
        streak_dates = {
            last_day - timedelta(days=offset)
            for offset in range(REMINDER_DECAY_COUNT)
        }
        if not streak_dates.issubset(reminder_dates):
            continue
        earliest_day = min(streak_dates)
        start_dt = datetime.combine(earliest_day, time.min)
        end_dt = datetime.combine(today + timedelta(days=1), time.min)
        had_activity = (
            db.query(Activity.id)
            .filter(
                Activity.user_id == user.id,
                func.coalesce(Activity.start_date_local, Activity.start_date) >= start_dt,
                func.coalesce(Activity.start_date_local, Activity.start_date) < end_dt,
            )
            .first()
            is not None
        )
        if not had_activity:
            return True
    return False

def daily_reminder_context(db: Session, user: User, now: datetime | None = None) -> tuple[date, int] | None:
    """Return (local date, streak) only when the daily-bonus reminder is appropriate."""
    if not user.telegram_chat_id or not bool(user.telegram_notify):
        return None
    if not get_notify_prefs(user)["daily_bonus_reminder"] or not bool(user.timezone_confirmed):
        return None

    local_moment = user_local_datetime(user, now)
    today = local_moment.date()
    if not is_daily_reminder_window(local_moment) or is_quiet_hours(local_moment):
        return None
    if _user_is_paused(user, today) or _has_daily_bonus(db, user, today):
        return None

    alive_days = qualified_activity_days(db, user, today - timedelta(days=6), today)
    if not alive_days:
        return None
    if reminder_decay_active(db, user, today):
        return None

    from .day_ledger import qualifying_day_streak

    streak = qualifying_day_streak(db, user, today)
    return today, streak


def daily_bonus_reminder_text(db: Session, user: User, now: datetime | None = None) -> str | None:
    context = daily_reminder_context(db, user, now)
    if context is None:
        return None
    today, streak = context
    variants = (
        "Сегодня ещё можно взять +20 XP: тренировка от 45 минут. Осталось около 3 часов.",
        "Не упусти дневной бонус +20 XP — нужна тренировка от 45 минут. До полуночи примерно 3 часа.",
        "Ещё можно получить +20 XP за тренировку продолжительностью от 45 минут. Осталось около 3 часов.",
        "Дневной бонус +20 XP ещё доступен: потренируйся не менее 45 минут. До полуночи около 3 часов.",
    )
    text = variants[today.toordinal() % len(variants)]
    if streak >= 3:
        text += f" Серия {streak} дн. под угрозой."
    return text


def profile_visible_on_leaderboard(db: Session, viewer: User, target: User) -> bool:
    """Mirror the leaderboard's profile-visibility rule for a particular viewer."""
    if viewer.id == target.id:
        return True
    visibility = target.profile_visibility or "authenticated"
    if visibility == "authenticated":
        return True
    if visibility != "friends":
        return False
    return (
        db.query(Friendship.id)
        .filter(
            Friendship.status == FriendshipStatus.ACCEPTED,
            (
                ((Friendship.from_user_id == viewer.id) & (Friendship.to_user_id == target.id))
                | ((Friendship.from_user_id == target.id) & (Friendship.to_user_id == viewer.id))
            ),
        )
        .first()
        is not None
    )


def format_overtaken_message(
    *,
    rank: int,
    delta: float,
    visible_name: str | None,
) -> str:
    points = f"{max(0.0, float(delta)):.1f}".rstrip("0").rstrip(".")
    if visible_name:
        return f"{visible_name} обошёл(а) тебя в лиге: ты {rank}-й. До него {points} очков."
    return f"Кто-то обошёл тебя в лиге: ты {rank}-й."


async def send_proactive(
    db: Session,
    user: User,
    kind: str,
    text: str,
    *,
    now: datetime | None = None,
) -> bool:
    """The one gate for every scheduled proactive Telegram message."""
    if kind not in DEFAULT_NOTIFY_PREFS or not getattr(user, "id", None):
        return False
    settings = get_settings()
    if not settings.TELEGRAM_BOT_TOKEN:
        return False

    # Serialize concurrent tick workers for this user. Limits across different
    # kinds cannot be guaranteed by the per-kind unique constraint alone.
    locked_user = (
        db.query(User)
        .filter(User.id == user.id)
        .with_for_update()
        .first()
    )
    if locked_user is None:
        return False
    user = locked_user
    if not user.telegram_chat_id or not bool(user.telegram_notify):
        return False
    if not get_notify_prefs(user).get(kind, False):
        return False
    if kind == "daily_bonus_reminder" and not bool(user.timezone_confirmed):
        return False

    local_moment = user_local_datetime(user, now)
    if is_quiet_hours(local_moment):
        return False
    if kind == "daily_bonus_reminder" and daily_reminder_context(db, user, now) is None:
        return False

    today = local_moment.date()
    week_start = today - timedelta(days=today.weekday())
    if db.query(NotificationLog.id).filter(
        NotificationLog.user_id == user.id,
        NotificationLog.kind == kind,
        NotificationLog.local_date == today,
    ).first():
        return False

    sent_today = db.query(NotificationLog.id).filter(
        NotificationLog.user_id == user.id,
        NotificationLog.local_date == today,
    ).count()
    if sent_today >= DAILY_LIMIT:
        return False

    sent_this_week = db.query(NotificationLog.id).filter(
        NotificationLog.user_id == user.id,
        NotificationLog.local_date >= week_start,
        NotificationLog.local_date <= today,
    ).count()
    if sent_this_week >= WEEKLY_LIMIT:
        return False

    reservation = NotificationLog(
        user_id=user.id,
        kind=kind,
        local_date=today,
        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    db.add(reservation)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return False

    outgoing = f"{text.strip()}\n\n{PROACTIVE_FOOTER}"
    try:
        delivered = await send_message(str(user.telegram_chat_id), outgoing)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Proactive Telegram delivery failed (%s): %s", kind, type(exc).__name__)
        delivered = False

    if not delivered:
        # Telegram returns False for blocked chats and exhausted retries; release
        # the reservation so failed attempts do not consume daily/weekly allowance.
        db.query(NotificationLog).filter(
            NotificationLog.user_id == user.id,
            NotificationLog.kind == kind,
            NotificationLog.local_date == today,
        ).delete(synchronize_session=False)
        db.commit()
        return False
    return True
