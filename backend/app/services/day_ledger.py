"""Canonical day XP ledger and qualifying-day streak helpers.

Event scope is deliberately centralized here. Activity-linked XP is a display
subset of the day's events; it is never added to the day total a second time.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import Activity, User, Wellness, XPEvent

# Every XPEvent type written in sync.py/quests.py (plus legacy rows that can
# still exist before reconciliation) is explicitly classified in one place.
# quest events use their credited calendar date unless a weekly key overrides it.
XP_EVENT_SCOPE_BY_TYPE: dict[str, str] = {
    "activity_bonus": "day",
    "sleep_bonus": "day",
    "quest": "day",
    "achievement": "day",
    "weekly_goal": "week",
    "deload_manual": "week",
}

WEEKLY_EVENT_KEY_PREFIXES = (
    "quest:goal_100:",
    "quest:ideal_week:",
)
ACTIVITY_LINKED_EVENT_TYPES = frozenset({"activity_bonus", "quest", "achievement"})
RETIRED_ACTIVITY_BONUS_PREFIX = "activity_bonus:45m:"
WEEK_START_TIME = time.min


def _zone_for_user(user: User) -> ZoneInfo:
    try:
        return ZoneInfo(getattr(user, "timezone_name", None) or "UTC")
    except (ZoneInfoNotFoundError, TypeError, ValueError):
        return ZoneInfo("UTC")


def local_today(user: User, *, now: datetime | None = None) -> date:
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(_zone_for_user(user)).date()


def _activity_stamp(activity: Activity) -> datetime | None:
    stamp = getattr(activity, "start_date_local", None) or getattr(activity, "start_date", None)
    if isinstance(stamp, datetime):
        return stamp
    if isinstance(stamp, date):
        return datetime.combine(stamp, time.min)
    return None


def activity_day(activity: Activity) -> date | None:
    stamp = _activity_stamp(activity)
    return stamp.date() if stamp is not None else None


def activity_tss(activity: Activity) -> float:
    """Use persisted v6 TSS, falling back to the exact XP v6 resolver."""
    value = getattr(activity, "tss", None)
    if value is not None:
        return max(0.0, float(value or 0.0))
    from . import xp_v6 as X6

    resolved, _source = X6.resolve_training_load({
        "training_load": getattr(activity, "training_load", None),
        "moving_time": getattr(activity, "moving_time", 0),
        "intensity": getattr(activity, "intensity", None),
        "sport_type": getattr(activity, "sport_type", None),
        "is_manual": bool(getattr(activity, "is_manual", False)),
        "source": getattr(activity, "source", None),
    })
    return max(0.0, float(resolved or 0.0))


def _event_scope(event: XPEvent) -> str | None:
    event_type = str(getattr(event, "event_type", "") or "")
    scope = XP_EVENT_SCOPE_BY_TYPE.get(event_type)
    if scope is None:
        return None
    event_key = str(getattr(event, "event_key", "") or "")
    if any(event_key.startswith(prefix) for prefix in WEEKLY_EVENT_KEY_PREFIXES):
        return "week"
    return scope


def _is_retired_event(event: XPEvent) -> bool:
    return (
        getattr(event, "event_type", None) == "activity_bonus"
        and str(getattr(event, "event_key", "") or "").startswith(RETIRED_ACTIVITY_BONUS_PREFIX)
    )


def empty_day_ledger(day: date) -> dict:
    return {
        "date": day.isoformat(),
        "wellness": {},
        "activities": [],
        "xp": {"effort": 0.0, "bonuses": [], "total": 0.0},
        "qualifying": False,
    }


def _week_event_rows(db: Session, user: User, day: date) -> list[XPEvent]:
    from .xp_v6 import week_start

    week_dt = datetime.combine(week_start(day), WEEK_START_TIME)
    return (
        db.query(XPEvent)
        .filter(XPEvent.user_id == user.id, XPEvent.week_start == week_dt)
        .order_by(XPEvent.date.asc(), XPEvent.id.asc())
        .all()
    )


def build_week_bonuses(db: Session, user: User, week_start: date) -> list[dict]:
    """List only weekly-scope XP events; day events remain inside each day ledger."""
    week_dt = datetime.combine(week_start, WEEK_START_TIME)
    events = (
        db.query(XPEvent)
        .filter(XPEvent.user_id == user.id, XPEvent.week_start == week_dt)
        .order_by(XPEvent.date.asc(), XPEvent.id.asc())
        .all()
    )
    bonuses = []
    for event in events:
        if _is_retired_event(event) or _event_scope(event) != "week":
            continue
        amount = round(float(event.amount or 0.0), 2)
        if amount <= 0:
            continue
        bonuses.append({
            "title": event.title or event.event_type,
            "amount": amount,
        })
    return bonuses


def build_day_ledger(db: Session, user: User, day: date) -> dict:
    """Build one date's raw-source XP ledger, wellness data, and activities."""
    from . import xp_v6 as X6

    start_dt = datetime.combine(day, time.min)
    end_dt = datetime.combine(day + timedelta(days=1), time.min)
    wellness_row = (
        db.query(Wellness)
        .filter(Wellness.user_id == user.id, Wellness.date == day.isoformat())
        .first()
    )
    wellness = {}
    if wellness_row is not None:
        for field in ("sleep_secs", "sleep_score", "hrv", "resting_hr", "readiness", "ctl", "atl"):
            value = getattr(wellness_row, field, None)
            if value is not None:
                wellness[field] = value

    activities = (
        db.query(Activity)
        .filter(
            Activity.user_id == user.id,
            func.coalesce(Activity.start_date_local, Activity.start_date) >= start_dt,
            func.coalesce(Activity.start_date_local, Activity.start_date) < end_dt,
        )
        .order_by(
            func.coalesce(Activity.start_date_local, Activity.start_date).asc(),
            Activity.id.asc(),
        )
        .all()
    )

    event_rows = _week_event_rows(db, user, day)
    day_events = [
        event for event in event_rows
        if not _is_retired_event(event)
        and _event_scope(event) == "day"
        and event.date is not None
        and event.date.date() == day
        and float(event.amount or 0.0) > 0
    ]
    bonuses = [
        {
            "title": event.title or event.event_type,
            "amount": round(float(event.amount or 0.0), 2),
            "type": event.event_type,
        }
        for event in day_events
    ]

    awards_by_activity: dict[str, float] = defaultdict(float)
    for event in day_events:
        if event.event_type not in ACTIVITY_LINKED_EVENT_TYPES or event.source_id is None:
            continue
        awards_by_activity[str(event.source_id)] += float(event.amount or 0.0)

    activity_payloads = []
    day_tss = 0.0
    day_activities_for_rule = []
    for activity in activities:
        tss = activity_tss(activity)
        day_tss += tss
        awards = round(float(awards_by_activity.get(str(activity.id), 0.0)), 2)
        effort_xp = round(float(activity.xp_earned or 0.0), 2)
        activity_payloads.append({
            "id": activity.id,
            "name": activity.name or "Без названия",
            "sport": activity.sport_type or "WORKOUT",
            "moving_time_min": int(activity.moving_time or 0) // 60,
            "distance_km": round(float(activity.distance or 0.0) / 1000.0, 2),
            "tss": round(tss, 2),
            "tss_estimated": bool(activity.tss_estimated),
            "is_manual": bool(activity.is_manual),
            "is_indoor": bool(getattr(activity, "is_indoor", False) or getattr(activity, "indoor", False)),
            "effort_xp": effort_xp,
            "xp": round(effort_xp + awards, 2),
        })
        day_activities_for_rule.append({"moving_time": int(activity.moving_time or 0)})

    effort_xp = X6.effort_xp_day(day_tss)
    qualifying = X6.is_qualifying_day(day_activities_for_rule, day_tss)
    day_total = X6.round_xp(effort_xp + sum(float(item["amount"]) for item in bonuses))
    return {
        "date": day.isoformat(),
        "wellness": wellness,
        "activities": activity_payloads,
        "xp": {
            "effort": X6.round_xp(effort_xp),
            "bonuses": bonuses,
            "total": day_total,
        },
        "qualifying": bool(qualifying),
    }


def qualifying_day_streak(
    db: Session,
    user: User,
    today: date,
    *,
    activities: list[Activity] | None = None,
) -> int:
    """Current consecutive qualifying-day streak; an unfinished today is neutral."""
    from . import xp_v6 as X6

    source_activities = activities
    if source_activities is None:
        source_activities = (
            db.query(Activity)
            .filter(Activity.user_id == user.id)
            .all()
        )

    by_day: dict[date, list[Activity]] = defaultdict(list)
    for activity in source_activities:
        day = activity_day(activity)
        if day is not None and day <= today:
            by_day[day].append(activity)

    qualifying_days: set[date] = set()
    for day, day_activities in by_day.items():
        tss_day = sum(activity_tss(activity) for activity in day_activities)
        if X6.is_qualifying_day(
            [{"moving_time": int(activity.moving_time or 0)} for activity in day_activities],
            tss_day,
        ):
            qualifying_days.add(day)

    cursor = today if today in qualifying_days else today - timedelta(days=1)
    streak = 0
    while cursor in qualifying_days:
        streak += 1
        cursor -= timedelta(days=1)
    return streak
