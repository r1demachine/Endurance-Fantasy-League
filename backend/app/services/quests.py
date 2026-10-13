"""Квесты и достижения v6 (PR5).

Прогресс и статус достижений вычисляются по Activity, Wellness и WeeklySummary
за всю доступную историю. XPEvent используется для идемпотентной выдачи XP и даты
получения, но не как источник прогресса. Невычислимые метрики не имитируются.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..config import get_settings

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

def _cond_first_three_day_week(ctx):
    return any((s.training_days or 0) >= 3 for s in ctx["weeks"])


def _cond_goal_met(ctx):
    return any((s.completion_ratio or 0) >= 1.0 and s.finalized for s in ctx["weeks"])


def _summary_week_day(summary) -> date | None:
    stamp = getattr(summary, "week_start", None)
    if stamp is None:
        return None
    return stamp.date() if isinstance(stamp, datetime) else stamp


def _max_goal_streak(summaries) -> int:
    """Longest historical run of finalized weeks that met the personal goal."""
    good_weeks = []
    for summary in summaries:
        week_day = _summary_week_day(summary)
        if (
            week_day is not None
            and bool(getattr(summary, "finalized", False))
            and float(getattr(summary, "completion_ratio", 0.0) or 0.0) >= 1.0
        ):
            good_weeks.append(week_day)

    longest = current = 0
    previous = None
    for week_day in sorted(set(good_weeks)):
        current = current + 1 if previous is not None and week_day - previous == timedelta(days=7) else 1
        longest = max(longest, current)
        previous = week_day
    return longest


def _cond_goal_streak_3(ctx):
    return _max_goal_streak(ctx["weeks"]) >= 3


def _cond_first_50km_ride_week(ctx):
    per_week = {}
    for a in ctx["acts"]:
        activity_day = _local_activity_day(a)
        if str(a.sport_type or "").upper() != "RIDE" or activity_day is None:
            continue
        ws = _trainer_week_start(activity_day)
        per_week[ws] = per_week.get(ws, 0) + (a.distance or 0)
    return any(v >= 50000 for v in per_week.values())


def _record_duration_progress(activities) -> dict:
    """Measure lifetime progress toward a workout 10% longer than a prior PB."""
    dated = []
    for activity in activities:
        activity_day = _local_activity_day(activity)
        duration = int(getattr(activity, "moving_time", 0) or 0)
        if (
            activity_day is None
            or bool(getattr(activity, "is_manual", False))
            or duration <= 0
        ):
            continue
        dated.append((activity_day, getattr(activity, "id", 0) or 0, activity, duration))

    dated.sort(key=lambda item: (item[0], item[1]))
    previous_record = 0
    seen = 0
    best_percentage = 0.0
    best_duration = 0
    best_previous_record = 0

    for _, _, _, duration in dated:
        if seen >= 3 and previous_record > 0:
            percentage = duration / (previous_record * 1.1) * 100.0
            if percentage > best_percentage:
                best_percentage = percentage
                best_duration = duration
                best_previous_record = previous_record
        previous_record = max(previous_record, duration)
        seen += 1

    return {
        "percentage": min(best_percentage, 100.0),
        "duration_secs": best_duration,
        "previous_record_secs": best_previous_record,
        "required_duration_secs": round(best_previous_record * 1.1),
    }


def _cond_record_duration(ctx):
    return _record_duration_progress(ctx["all_acts"])["percentage"] >= 100.0


def _best_activity_training_days(activities) -> int:
    """Fallback for weeks without a stored summary; use the same TSS/duration floor."""
    daily: dict[date, dict[str, float | bool]] = {}
    for activity in activities:
        activity_day = _local_activity_day(activity)
        if activity_day is None:
            continue
        try:
            load = float(
                getattr(activity, "tss", None)
                or getattr(activity, "training_load", 0.0)
                or 0.0
            )
        except (TypeError, ValueError):
            load = 0.0
        row = daily.setdefault(activity_day, {"load": 0.0, "has_duration": False})
        row["load"] = float(row["load"]) + max(load, 0.0)
        if int(getattr(activity, "moving_time", 0) or 0) >= 20 * 60:
            row["has_duration"] = True

    training_days_by_week: dict[date, int] = {}
    for activity_day, row in daily.items():
        if float(row["load"]) < 20.0 or not bool(row["has_duration"]):
            continue
        week_start = _trainer_week_start(activity_day)
        training_days_by_week[week_start] = training_days_by_week.get(week_start, 0) + 1
    return max(training_days_by_week.values(), default=0)


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
    """Award quest XP idempotently, evaluating lifetime achievements from all source data."""
    from ..models import XPEvent, Wellness
    from sqlalchemy import or_

    # Do not apply the quest activation cutoff to progress. Existing source history
    # is the source of truth even when an event is missing or older than the activation date.
    all_summaries = [summary for summary in summaries if _summary_week_day(summary) is not None]
    all_activities = [activity for activity in acts if _local_activity_day(activity) is not None]
    sleep_records = (
        db.query(Wellness)
        .filter(
            Wellness.user_id == user.id,
            or_(Wellness.sleep_secs > 0, Wellness.sleep_score > 0),
        )
        .all()
    )
    ctx = {
        "weeks": all_summaries,
        "acts": all_activities,
        "all_acts": acts,
        "sleep_nights_count": len({row.date for row in sleep_records if row.date}),
    }
    try:
        local_zone = ZoneInfo(getattr(user, "timezone_name", None) or "UTC")
    except (ZoneInfoNotFoundError, TypeError, ValueError):
        local_zone = ZoneInfo("UTC")
    today = datetime.now(timezone.utc).astimezone(local_zone).date()
    granted = 0
    for quest in QUEST_REGISTRY:
        slug = quest["slug"]
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
                amount=quest["reward"],
                source_type="quest",
                title=f"🏆 {quest['title']}",
            ))
            granted += 1

    # The recurring trainer XP bonus remains limited to the configured activation
    # window to avoid retroactively paying XP for historical weeks. Achievement
    # progress/status itself is computed independently from the XPEvent below.
    activation_date: date = get_settings().XP_QUESTS_ACTIVATION_DATE
    trainer_by_week = {}
    for activity in acts:
        activity_day = _local_activity_day(activity)
        if (
            activity_day is None
            or activity_day < activation_date
            or not _is_qualifying_trainer_activity(activity)
        ):
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


def _quest_status(quest, progress: dict | None) -> str:
    """Status comes from measured source-data progress, never from XPEvent presence."""
    if quest.get("requires"):
        return "unavailable"
    if not progress:
        return "open"
    try:
        return "earned" if float(progress.get("current", 0) or 0) >= float(progress.get("target", 1) or 1) else "open"
    except (TypeError, ValueError):
        return "open"


def quest_states(db, user) -> list:
    """Return full-history progress/status; XPEvent is only optional earned-date metadata."""
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
    eligible_summaries = [
        summary for summary in summaries
        if _summary_week_day(summary) is not None
    ]
    eligible_activities = [
        activity for activity in activities
        if _local_activity_day(activity) is not None
    ]

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

    best_training_days = max(
        max((int(summary.training_days or 0) for summary in eligible_summaries), default=0),
        _best_activity_training_days(activities),
    )
    finalized = sorted(
        [summary for summary in eligible_summaries if summary.finalized and summary.week_start],
        key=lambda summary: summary.week_start,
    )
    best_goal_pct = max(
        (
            max(0.0, float(summary.completion_ratio or 0.0)) * 100
            for summary in eligible_summaries
            if summary.finalized
        ),
        default=0.0,
    )

    # Achievement progress is lifetime: remember the best historical streak even
    # if the latest weeks no longer form a consecutive run.
    goal_streak = _max_goal_streak(eligible_summaries)

    ride_km_by_week: dict[date, float] = {}
    for activity in eligible_activities:
        activity_day = _local_activity_day(activity)
        if activity_day is None or str(activity.sport_type or "").upper() != "RIDE":
            continue
        week = _trainer_week_start(activity_day)
        ride_km_by_week[week] = ride_km_by_week.get(week, 0.0) + max(float(activity.distance or 0.0), 0.0) / 1000.0
    best_ride_km = max(ride_km_by_week.values(), default=0.0)

    record_progress = _record_duration_progress(activities)

    trainer_key = _trainer_week_key(current_week)
    trainer_qualifies = any(
        _is_qualifying_trainer_activity(activity)
        and _local_activity_day(activity) is not None
        and _trainer_week_start(_local_activity_day(activity)) == current_week
        for activity in activities
    )
    trainer_done = bool(trainer_qualifies)
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
            "current": round(float(record_progress["percentage"]), 1), "target": 100, "unit": "%",
            "recent_duration_secs": record_progress["duration_secs"],
            "record_before_recent_secs": record_progress["previous_record_secs"],
            "required_duration_secs": record_progress["required_duration_secs"],
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

    out = []
    for quest in QUEST_REGISTRY:
        slug = quest["slug"]
        event_key = trainer_key if slug == "trainer_week" else _quest_key(slug)
        event = earned.get(event_key)
        progress = progress_by_slug.get(slug)
        status = _quest_status(quest, progress)
        earned_at = (
            event.date.strftime("%d.%m.%Y")
            if status == "earned" and event and event.date
            else None
        )

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
            item["progress"] = progress
        out.append(item)

    return out
