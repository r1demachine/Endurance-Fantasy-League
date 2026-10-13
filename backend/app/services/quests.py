"""Квесты и достижения v6 (PR5).

Квесты — одноразовые (lifetime) ачивки поверх XPEvent:
стабильный ключ quest:{slug}:lifetime, повторное начисление невозможно.
Квесты, требующие данных, которые мы НЕ синхронизируем (мощность, FTP Вт/кг),
не имитируются из длительности/TSS — у них статус "unavailable".
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

QUEST_REGISTRY = [
    {
        "slug": "first_three_day_week",
        "title": "Первый шаг",
        "desc": "Неделя с тремя квалифицирующими тренировками",
        "reward": 50.0,
    },
    {
        "slug": "goal_met",
        "title": "План выполнен",
        "desc": "Выполнить 100% персональной недельной цели",
        "reward": 40.0,
    },
    {
        "slug": "goal_streak_3",
        "title": "Стабильность",
        "desc": "Три недели подряд на персональной цели",
        "reward": 75.0,
    },
    {
        "slug": "first_50km_ride_week",
        "title": "Полтинник",
        "desc": "50+ км велосипеда за одну неделю",
        "reward": 40.0,
    },
    {
        "slug": "record_duration",
        "title": "Дольше всех",
        "desc": "Тренировка на 10%+ длиннее личного рекорда",
        "reward": 30.0,
    },
    {
        "slug": "sleep_connected",
        "title": "Сон имеет значение",
        "desc": "Три ночи с данными о сне (продолжительность или sleep score)",
        "reward": 25.0,
    },
    {
        "slug": "trainer_week",
        "title": "Станок",
        "desc": "Тренировка на тренажёре от 30 минут в сезон",
        "reward": 15.0,
    },
    # ── Сейчас невычислимо: данные не синхронизируются. НЕ имитируем. ──
    {
        "slug": "power_record_20m",
        "title": "Рекорд мощности 20 мин",
        "desc": "Требует данные мощности (не синхронизируются)",
        "reward": 50.0,
        "requires": "power",
    },
    {
        "slug": "ftp_growth_8w",
        "title": "Рост FTP",
        "desc": "Требует FTP в Вт/кг (не синхронизируется)",
        "reward": 150.0,
        "requires": "ftp",
    },
]


def _quest_key(slug: str) -> str:
    return f"quest:{slug}:lifetime"


TRAINER_WEEKLY_REWARD = 15.0


def _trainer_season_active(day: date) -> bool:
    """Сезон станка: с 1 октября по 30 апреля включительно."""
    return day.month >= 10 or day.month <= 4


def _trainer_week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _trainer_week_key(week_start: date) -> str:
    return f"quest:trainer_week:{week_start.isoformat()}"


def _is_qualifying_trainer_activity(activity) -> bool:
    activity_date = getattr(activity, "start_date_local", None) or getattr(activity, "start_date", None)
    if activity_date is None:
        return False
    day = activity_date.date() if isinstance(activity_date, datetime) else activity_date
    is_indoor = bool(getattr(activity, "is_indoor", False) or getattr(activity, "indoor", False))
    return (
        is_indoor
        and not bool(getattr(activity, "is_manual", False))
        and int(getattr(activity, "moving_time", 0) or 0) >= 30 * 60
        and _trainer_season_active(day)
    )


# ── Условия квестов (чистые функции от контекста) ──

def _record_duration_progress(activities) -> float:
    """Best historical attempt to beat the previous duration record by 10%."""
    dated = [
        (activity, _local_activity_day(activity))
        for activity in activities
        if not bool(getattr(activity, "is_manual", False))
        and _local_activity_day(activity) is not None
        and int(getattr(activity, "moving_time", 0) or 0) > 0
    ]
    dated.sort(key=lambda item: (item[1], int(getattr(item[0], "id", 0) or 0)))
    previous_max = 0
    seen = 0
    best_progress = 0.0
    for activity, _day in dated:
        duration = int(getattr(activity, "moving_time", 0) or 0)
        if seen >= 3 and previous_max > 0:
            best_progress = max(best_progress, duration / (previous_max * 1.1) * 100.0)
        previous_max = max(previous_max, duration)
        seen += 1
    return min(best_progress, 100.0)


def _qualifying_training_days_by_week(activities) -> dict[date, int]:
    """Recompute qualifying days directly from activities, not weekly XP events."""
    from . import xp_v6 as X6
    per_day = {}
    for activity in activities:
        day = _local_activity_day(activity)
        if day is None:
            continue
        load, _source = X6.resolve_training_load({
            "training_load": getattr(activity, "training_load", None),
            "moving_time": getattr(activity, "moving_time", 0),
            "intensity": getattr(activity, "intensity", None),
            "sport_type": getattr(activity, "sport_type", None),
            "is_manual": bool(getattr(activity, "is_manual", False)),
            "source": getattr(activity, "source", None),
        })
        row = per_day.setdefault(day, {"activities": [], "tss": 0.0})
        row["activities"].append({"moving_time": getattr(activity, "moving_time", 0)})
        row["tss"] += float(load or 0.0)
    by_week: dict[date, int] = {}
    for day, row in per_day.items():
        if X6.is_qualifying_day(row["activities"], row["tss"]):
            week_start = _trainer_week_start(day)
            by_week[week_start] = by_week.get(week_start, 0) + 1
    return by_week


def _best_goal_streak(summaries) -> int:
    """Longest lifetime streak of finalized weeks that met the weekly goal."""
    achieved_weeks = {
        summary.week_start.date()
        for summary in summaries
        if summary.week_start and summary.finalized
        and float(summary.completion_ratio or 0.0) >= 1.0
    }
    longest = 0
    for start in sorted(achieved_weeks):
        if start - timedelta(days=7) in achieved_weeks:
            continue
        streak = 1
        cursor = start
        while cursor + timedelta(days=7) in achieved_weeks:
            cursor += timedelta(days=7)
            streak += 1
        longest = max(longest, streak)
    return longest


def _cond_first_three_day_week(ctx):
    return any(days >= 3 for days in ctx["qualifying_days_by_week"].values())


def _cond_goal_met(ctx):
    return any((s.completion_ratio or 0) >= 1.0 and s.finalized for s in ctx["weeks"])


def _cond_goal_streak_3(ctx):
    return _best_goal_streak(ctx["weeks"]) >= 3


def _cond_first_50km_ride_week(ctx):
    per_week = {}
    for a in ctx["acts"]:
        activity_day = _local_activity_day(a)
        if str(a.sport_type or "").upper() != "RIDE" or activity_day is None:
            continue
        ws = _trainer_week_start(activity_day)
        per_week[ws] = per_week.get(ws, 0) + (a.distance or 0)
    return any(v >= 50000 for v in per_week.values())


def _cond_record_duration(ctx):
    return _record_duration_progress(ctx["all_acts"]) >= 100.0


def _cond_sleep_connected(ctx):
    return ctx["sleep_nights_count"] >= 3


CONDS = {
    "first_three_day_week": _cond_first_three_day_week,
    "goal_met": _cond_goal_met,
    "goal_streak_3": _cond_goal_streak_3,
    "first_50km_ride_week": _cond_first_50km_ride_week,
    "record_duration": _cond_record_duration,
    "sleep_connected": _cond_sleep_connected,
}


def grant_quests(db, user, acts, summaries) -> int:
    """Idempotently grant awards when lifetime progress meets data-derived conditions."""
    from sqlalchemy import or_
    from ..models import XPEvent, Wellness

    all_activities = list(acts)
    all_summaries = [summary for summary in summaries if summary.week_start]
    sleep_dates = {
        row.date
        for row in db.query(Wellness.date)
        .filter(
            Wellness.user_id == user.id,
            or_(Wellness.sleep_secs > 0, Wellness.sleep_score > 0),
        )
        .all()
        if row.date
    }
    ctx = {
        "weeks": all_summaries,
        "acts": [activity for activity in all_activities if _local_activity_day(activity) is not None],
        "all_acts": all_activities,
        "qualifying_days_by_week": _qualifying_training_days_by_week(all_activities),
        "sleep_nights_count": len(sleep_dates),
    }
    try:
        local_zone = ZoneInfo(getattr(user, "timezone_name", None) or "UTC")
    except (ZoneInfoNotFoundError, TypeError, ValueError):
        local_zone = ZoneInfo("UTC")
    today = datetime.now(timezone.utc).astimezone(local_zone).date()
    granted = 0
    for q in QUEST_REGISTRY:
        slug = q["slug"]
        if slug not in CONDS:
            continue  # unavailable-квесты не начисляются
        key = _quest_key(slug)
        exists = (
            db.query(XPEvent)
            .filter(XPEvent.user_id == user.id, XPEvent.event_key == key)
            .first()
        )
        if exists:
            continue
        if CONDS[slug](ctx):
            db.add(XPEvent(
                user_id=user.id,
                week_start=datetime.combine(today - timedelta(days=today.weekday()), datetime.min.time()),
                date=datetime.combine(today, datetime.min.time()),
                event_type="quest",
                event_key=key,
                amount=q["reward"],
                source_type="quest",
                title=f"🏆 {q['title']}",
            ))
            granted += 1
    # Повторяемый недельный бонус за станок: не больше одного XPEvent на неделю.
    trainer_by_week = {}
    for activity in all_activities:
        activity_day = _local_activity_day(activity)
        if activity_day is None or not _is_qualifying_trainer_activity(activity):
            continue
        week_start = _trainer_week_start(activity_day)
        trainer_by_week.setdefault(week_start, activity)

    for week_start, activity in trainer_by_week.items():
        key = _trainer_week_key(week_start)
        exists = db.query(XPEvent).filter(
            XPEvent.user_id == user.id,
            XPEvent.event_key == key,
        ).first()
        if exists:
            continue
        activity_dt = getattr(activity, "start_date_local", None) or activity.start_date
        db.add(XPEvent(
            user_id=user.id,
            week_start=datetime.combine(week_start, datetime.min.time()),
            date=activity_dt if isinstance(activity_dt, datetime) else datetime.combine(activity_dt, datetime.min.time()),
            event_type="quest",
            event_key=key,
            amount=TRAINER_WEEKLY_REWARD,
            source_type="quest",
            source_id=str(activity.id) if getattr(activity, "id", None) is not None else None,
            title="🏆 Станок",
        ))
        granted += 1

    return granted


def _local_activity_day(activity) -> date | None:
    stamp = getattr(activity, "start_date_local", None) or getattr(activity, "start_date", None)
    if stamp is None:
        return None
    return stamp.date() if isinstance(stamp, datetime) else stamp


def _user_local_today(user) -> date:
    try:
        zone = ZoneInfo(getattr(user, "timezone_name", None) or "UTC")
    except (ZoneInfoNotFoundError, TypeError, ValueError):
        zone = ZoneInfo("UTC")
    return datetime.now(timezone.utc).astimezone(zone).date()


def quest_states(db, user) -> list:
    """Quest statuses and measurable progress for the authenticated user's data."""
    from sqlalchemy import or_
    from ..models import Activity, XPEvent, Wellness, WeeklySummary

    today = _user_local_today(user)
    current_week = _trainer_week_start(today)
    earned = {
        event.event_key: event
        for event in db.query(XPEvent)
        .filter(XPEvent.user_id == user.id, XPEvent.event_type.in_(("quest", "achievement")))
        .all()
    }
    activities = db.query(Activity).filter(Activity.user_id == user.id).all()
    summaries = (
        db.query(WeeklySummary)
        .filter(WeeklySummary.user_id == user.id)
        .order_by(WeeklySummary.week_start.asc())
        .all()
    )
    all_summaries = [summary for summary in summaries if summary.week_start]
    dated_activities = [activity for activity in activities if _local_activity_day(activity) is not None]

    sleep_records = (
        db.query(Wellness)
        .filter(
            Wellness.user_id == user.id,
            or_(Wellness.sleep_secs > 0, Wellness.sleep_score > 0),
        )
        .order_by(Wellness.date.asc())
        .all()
    )
    sleep_dates = sorted({row.date for row in sleep_records if row.date})
    night_count = len(sleep_dates)

    qualifying_days_by_week = _qualifying_training_days_by_week(dated_activities)
    best_training_days = max(qualifying_days_by_week.values(), default=0)
    finalized = sorted(
        [summary for summary in all_summaries if summary.finalized],
        key=lambda summary: summary.week_start,
    )
    best_goal_pct = max(
        (max(0.0, float(summary.completion_ratio or 0.0)) * 100 for summary in finalized),
        default=0.0,
    )
    goal_streak = _best_goal_streak(finalized)

    ride_km_by_week: dict[date, float] = {}
    for activity in dated_activities:
        activity_day = _local_activity_day(activity)
        if activity_day is None or str(activity.sport_type or "").upper() != "RIDE":
            continue
        week = _trainer_week_start(activity_day)
        ride_km_by_week[week] = ride_km_by_week.get(week, 0.0) + max(float(activity.distance or 0.0), 0.0) / 1000.0
    best_ride_km = max(ride_km_by_week.values(), default=0.0)

    duration_progress = _record_duration_progress(activities)

    trainer_key = _trainer_week_key(current_week)
    trainer_qualifies = any(
        _is_qualifying_trainer_activity(activity)
        and _local_activity_day(activity) is not None
        and _trainer_week_start(_local_activity_day(activity)) == current_week
        for activity in activities
    )
    trainer_done = trainer_qualifies
    trainer_season_active = _trainer_season_active(today)

    progress_by_slug = {
        "first_three_day_week": {
            "current": min(best_training_days, 3), "target": 3, "unit": "дней",
        },
        "goal_met": {
            "current": round(min(best_goal_pct, 100.0), 1), "target": 100, "unit": "%",
        },
        "goal_streak_3": {
            "current": min(goal_streak, 3), "target": 3, "unit": "недель",
        },
        "first_50km_ride_week": {
            "current": round(min(best_ride_km, 50.0), 1), "target": 50, "unit": "км",
        },
        "record_duration": {
            "current": round(min(duration_progress, 100.0), 1), "target": 100, "unit": "%",
        },
        "sleep_connected": {
            "current": min(night_count, 3), "target": 3, "unit": "ночей",
            "steps": [
                {
                    "slot": index + 1,
                    "label": f"Ночь {index + 1}",
                    "filled": index < min(night_count, 3),
                    "date": sleep_dates[-3:][index] if len(sleep_dates[-3:]) > index else None,
                }
                for index in range(3)
            ],
        },
        "trainer_week": {
            "current": 1 if trainer_done else 0, "target": 1, "unit": "тренировка",
            "season_active": trainer_season_active,
            "season_window": {"starts_month": 10, "ends_month": 4},
        },
    }

    completion_by_slug = {
        "first_three_day_week": best_training_days >= 3,
        "goal_met": any(
            summary.finalized and float(summary.completion_ratio or 0.0) >= 1.0
            for summary in all_summaries
        ),
        "goal_streak_3": goal_streak >= 3,
        "first_50km_ride_week": any(distance >= 50.0 for distance in ride_km_by_week.values()),
        "record_duration": duration_progress >= 100.0,
        "sleep_connected": night_count >= 3,
        "trainer_week": trainer_qualifies,
    }

    out = []
    for quest in QUEST_REGISTRY:
        slug = quest["slug"]
        event_key = trainer_key if slug == "trainer_week" else _quest_key(slug)
        event = earned.get(event_key)
        if quest.get("requires"):
            status, earned_at = "unavailable", None
        elif completion_by_slug.get(slug, False):
            status = "earned"
            # Event date is optional metadata; current progress determines completion.
            earned_at = event.date.strftime("%d.%m.%Y") if event and event.date else None
        else:
            status, earned_at = "open", None

        item = {
            "slug": slug,
            "title": quest["title"],
            "desc": quest["desc"],
            "reward": int(quest["reward"]),
            "status": status,
            "earned_at": earned_at,
        }
        if quest.get("requires"):
            item["progress"] = None
            item["progress_reason"] = (
                "Для этого квеста нужны данные мощности." if quest["requires"] == "power"
                else "Для этого квеста нужны данные FTP в Вт/кг."
            )
        else:
            item["progress"] = progress_by_slug[slug]
        out.append(item)
    return out
