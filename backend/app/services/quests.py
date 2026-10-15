"""Квесты и достижения v6 (PR5).

Квесты — одноразовые (lifetime) ачивки поверх XPEvent:
стабильный ключ quest:{slug}:lifetime, повторное начисление невозможно.
Квесты, требующие данных, которые мы НЕ синхронизируем (мощность, FTP Вт/кг),
не имитируются из длительности/TSS — у них статус "unavailable".
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# ── Настройки недельных достижений ──
LIFETIME_QUESTS_ACTIVATION_DATE = date(2026, 10, 19)

WEEKLY_QUALIFYING_DAYS_TARGET = 5
WEEKLY_QUALIFYING_DAYS_REWARD = 50.0
WEEKLY_GOOD_SLEEP_NIGHTS_TARGET = 5
WEEKLY_GOOD_SLEEP_MIN_SECONDS = 6 * 60 * 60
WEEKLY_GOOD_SLEEP_MIN_SCORE = 60
WEEKLY_GOOD_SLEEP_REWARD = 35.0
WEEKLY_GOAL_TARGET_REWARD = 20.0
WEEKLY_IDEAL_WEEK_REWARD = 40.0
WEEKLY_IDEAL_WEEK_GOOD_SLEEP_TARGET = 5
WEEKLY_IDEAL_WEEK_QUALIFYING_DAYS_FALLBACK = 5
WEEKLY_LONG_WORKOUT_SECONDS = 2 * 60 * 60
WEEKLY_LONG_WORKOUT_REWARD = 25.0
WEEKLY_EXTRA_LONG_WORKOUT_SECONDS = 3 * 60 * 60
WEEKLY_EXTRA_LONG_WORKOUT_REWARD = 15.0
WEEKLY_HIGH_INTENSITY_IF_THRESHOLD = 0.75
WEEKLY_HIGH_INTENSITY_HARD_SECONDS = 5 * 60
WEEKLY_HIGH_INTENSITY_MIN_DURATION_SECONDS = 15 * 60
WEEKLY_HIGH_INTENSITY_REWARD = 30.0

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

# Every entry is reset on Monday. Keys are quest:{slug}:{week_start.isoformat()}.
WEEKLY_QUEST_REGISTRY = [
    {
        "slug": "qualifying_days_5",
        "title": "5 дней с тренировками",
        "desc": "Пять календарных дней с квалифицирующей нагрузкой",
        "reward": WEEKLY_QUALIFYING_DAYS_REWARD,
        "target": WEEKLY_QUALIFYING_DAYS_TARGET,
        "unit": "дней",
    },
    {
        "slug": "good_sleep_5",
        "title": "5 ночей хорошего сна",
        "desc": "Не менее 6 часов сна или sleep score от 60",
        "reward": WEEKLY_GOOD_SLEEP_REWARD,
        "target": WEEKLY_GOOD_SLEEP_NIGHTS_TARGET,
        "unit": "ночей",
    },
    {
        "slug": "long_workout_2h",
        "title": "Длинная тренировка",
        "desc": "Тренировка продолжительностью не менее 2 часов",
        "reward": WEEKLY_LONG_WORKOUT_REWARD,
        "target": 1,
        "unit": "тренировка",
    },
    {
        "slug": "long_workout_3h",
        "title": "Тренировка 3 часа+",
        "desc": "Дополнительная награда за тренировку от 3 часов",
        "reward": WEEKLY_EXTRA_LONG_WORKOUT_REWARD,
        "target": 1,
        "unit": "тренировка",
    },
    {
        "slug": "high_intensity",
        "title": "Высокая интенсивность",
        "desc": "Не manual: реальная IF ≥ 0,75 или не менее 5 минут в Z4+",
        "reward": WEEKLY_HIGH_INTENSITY_REWARD,
        "target": 1,
        "unit": "тренировка",
    },
    {
        "slug": "trainer_week",
        "title": "Станок",
        "desc": "Тренировка на тренажёре от 30 минут в сезон",
        "reward": TRAINER_WEEKLY_REWARD,
        "target": 1,
        "unit": "тренировка",
    },
]


def _trainer_season_active(day: date) -> bool:
    """Сезон станка: с 1 октября по 30 апреля включительно."""
    return day.month >= 10 or day.month <= 4


def _trainer_week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _weekly_quest_key(slug: str, week_start: date) -> str:
    return f"quest:{slug}:{week_start.isoformat()}"


def _trainer_week_key(week_start: date) -> str:
    # Preserve the established trainer_week key format for old XPEvent history.
    return _weekly_quest_key("trainer_week", week_start)


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


def _qualifying_days_by_week(activities) -> dict[date, list[date]]:
    """Qualified calendar days, using exactly the XP v6 qualifying-day rules."""
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

    by_week: dict[date, list[date]] = {}
    for day, row in per_day.items():
        if X6.is_qualifying_day(row["activities"], row["tss"]):
            week = _trainer_week_start(day)
            by_week.setdefault(week, []).append(day)
    for days in by_week.values():
        days.sort()
    return by_week


def _qualifying_training_days_by_week(activities) -> dict[date, int]:
    return {
        week: len(days)
        for week, days in _qualifying_days_by_week(activities).items()
    }


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


def _wellness_day(row) -> date | None:
    value = getattr(row, "date", None)
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _group_weekly_data(activities, wellness_rows):
    activities_by_week: dict[date, list] = {}
    wellness_by_week: dict[date, list] = {}
    for activity in activities:
        day = _local_activity_day(activity)
        if day is not None:
            activities_by_week.setdefault(_trainer_week_start(day), []).append(activity)
    for row in wellness_rows:
        day = _wellness_day(row)
        if day is not None:
            wellness_by_week.setdefault(_trainer_week_start(day), []).append(row)
    return activities_by_week, wellness_by_week


def _high_intensity_qualifies(activity) -> bool:
    """Real-load IF or 5 minutes of hard intervals; manually created workouts never qualify."""
    if bool(getattr(activity, "is_manual", False)):
        return False
    from . import xp_v6 as X6

    moving_time = int(getattr(activity, "moving_time", 0) or 0)
    if moving_time < WEEKLY_HIGH_INTENSITY_MIN_DURATION_SECONDS:
        return False
    if int(getattr(activity, "hard_secs", 0) or 0) >= WEEKLY_HIGH_INTENSITY_HARD_SECONDS:
        return True
    _load, source = X6.resolve_training_load({
        "training_load": getattr(activity, "training_load", None),
        "moving_time": moving_time,
        "intensity": getattr(activity, "intensity", None),
        "sport_type": getattr(activity, "sport_type", None),
        "is_manual": False,
        "source": getattr(activity, "source", None),
    })
    return (
        source == "real"
        and float(getattr(activity, "intensity", 0.0) or 0.0) >= WEEKLY_HIGH_INTENSITY_IF_THRESHOLD
    )


def _weekly_quest_progress(week_start: date, activities, wellness_rows) -> dict[str, dict]:
    """Build progress from raw records for one week; internal earned date is not exposed."""
    qualified_days = _qualifying_days_by_week(activities).get(week_start, [])
    good_sleep_days = sorted({
        day for row in wellness_rows
        if (day := _wellness_day(row)) is not None
        and _trainer_week_start(day) == week_start
        and (
            float(getattr(row, "sleep_secs", 0) or 0) >= WEEKLY_GOOD_SLEEP_MIN_SECONDS
            or float(getattr(row, "sleep_score", 0) or 0) >= WEEKLY_GOOD_SLEEP_MIN_SCORE
        )
    })
    week_activities = [
        activity for activity in activities
        if _local_activity_day(activity) is not None
        and _trainer_week_start(_local_activity_day(activity)) == week_start
    ]
    measured_activities = [
        activity for activity in week_activities
        if not bool(getattr(activity, "is_manual", False))
        and int(getattr(activity, "moving_time", 0) or 0) > 0
    ]
    long_2h = sorted(
        (activity for activity in measured_activities
         if int(getattr(activity, "moving_time", 0) or 0) >= WEEKLY_LONG_WORKOUT_SECONDS),
        key=lambda activity: (_local_activity_day(activity), int(getattr(activity, "id", 0) or 0)),
    )
    long_3h = sorted(
        (activity for activity in measured_activities
         if int(getattr(activity, "moving_time", 0) or 0) >= WEEKLY_EXTRA_LONG_WORKOUT_SECONDS),
        key=lambda activity: (_local_activity_day(activity), int(getattr(activity, "id", 0) or 0)),
    )
    hard_activities = sorted(
        (activity for activity in week_activities if _high_intensity_qualifies(activity)),
        key=lambda activity: (_local_activity_day(activity), int(getattr(activity, "id", 0) or 0)),
    )
    trainer_activities = sorted(
        (activity for activity in week_activities if _is_qualifying_trainer_activity(activity)),
        key=lambda activity: (_local_activity_day(activity), int(getattr(activity, "id", 0) or 0)),
    )

    raw = {
        "qualifying_days_5": {
            "current": min(len(qualified_days), WEEKLY_QUALIFYING_DAYS_TARGET),
            "_earned_day": qualified_days[WEEKLY_QUALIFYING_DAYS_TARGET - 1]
            if len(qualified_days) >= WEEKLY_QUALIFYING_DAYS_TARGET else None,
        },
        "good_sleep_5": {
            "current": min(len(good_sleep_days), WEEKLY_GOOD_SLEEP_NIGHTS_TARGET),
            "_earned_day": good_sleep_days[WEEKLY_GOOD_SLEEP_NIGHTS_TARGET - 1]
            if len(good_sleep_days) >= WEEKLY_GOOD_SLEEP_NIGHTS_TARGET else None,
            "steps": [
                {
                    "slot": index + 1,
                    "label": f"Ночь {index + 1}",
                    "filled": index < min(len(good_sleep_days), WEEKLY_GOOD_SLEEP_NIGHTS_TARGET),
                    "date": good_sleep_days[index].isoformat() if len(good_sleep_days) > index else None,
                }
                for index in range(WEEKLY_GOOD_SLEEP_NIGHTS_TARGET)
            ],
        },
        "long_workout_2h": {
            "current": int(bool(long_2h)),
            "_earned_day": _local_activity_day(long_2h[0]) if long_2h else None,
            "_source_id": getattr(long_2h[0], "id", None) if long_2h else None,
        },
        "long_workout_3h": {
            "current": int(bool(long_3h)),
            "_earned_day": _local_activity_day(long_3h[0]) if long_3h else None,
            "_source_id": getattr(long_3h[0], "id", None) if long_3h else None,
        },
        "high_intensity": {
            "current": int(bool(hard_activities)),
            "_earned_day": _local_activity_day(hard_activities[0]) if hard_activities else None,
            "_source_id": getattr(hard_activities[0], "id", None) if hard_activities else None,
        },
        "trainer_week": {
            "current": int(bool(trainer_activities)),
            "_earned_day": _local_activity_day(trainer_activities[0]) if trainer_activities else None,
            "_source_id": getattr(trainer_activities[0], "id", None) if trainer_activities else None,
            "season_active": _trainer_season_active(week_start),
            "season_window": {"starts_month": 10, "ends_month": 4},
        },
    }
    progress = {}
    for quest in WEEKLY_QUEST_REGISTRY:
        values = raw[quest["slug"]]
        item = {
            "current": values["current"],
            "target": quest["target"],
            "unit": quest["unit"],
        }
        if "steps" in values:
            item["steps"] = values["steps"]
        for internal_key in ("_earned_day", "_source_id"):
            if internal_key in values:
                item[internal_key] = values[internal_key]
        if quest["slug"] == "trainer_week":
            item["season_active"] = values["season_active"]
            item["season_window"] = values["season_window"]
        progress[quest["slug"]] = item
    return progress


def grant_quests(db, user, acts, summaries) -> int:
    """Idempotently grant lifetime and weekly achievements from source records."""
    from sqlalchemy import or_
    from ..models import XPEvent, Wellness

    all_activities = list(acts)
    all_summaries = [summary for summary in summaries if summary.week_start]
    wellness_rows = (
        db.query(Wellness)
        .filter(
            Wellness.user_id == user.id,
            or_(Wellness.sleep_secs > 0, Wellness.sleep_score > 0),
        )
        .all()
    )
    activities_by_week, wellness_by_week = _group_weekly_data(all_activities, wellness_rows)

    today = _user_local_today(user)

    # Lifetime progress starts on the activation date. Weekly/repeatable awards
    # still use the complete source history for their own calendar weeks.
    lifetime_activities = [
        activity for activity in all_activities
        if today >= LIFETIME_QUESTS_ACTIVATION_DATE
        and (day := _local_activity_day(activity)) is not None
        and LIFETIME_QUESTS_ACTIVATION_DATE <= day <= today
    ]
    lifetime_summaries = [
        summary for summary in all_summaries
        if today >= LIFETIME_QUESTS_ACTIVATION_DATE
        and LIFETIME_QUESTS_ACTIVATION_DATE <= summary.week_start.date() <= today
    ]
    lifetime_sleep_dates = {
        day for row in wellness_rows
        if today >= LIFETIME_QUESTS_ACTIVATION_DATE
        and (day := _wellness_day(row)) is not None
        and LIFETIME_QUESTS_ACTIVATION_DATE <= day <= today
    }
    ctx = {
        "weeks": lifetime_summaries,
        "acts": lifetime_activities,
        "all_acts": lifetime_activities,
        "qualifying_days_by_week": _qualifying_training_days_by_week(lifetime_activities),
        "sleep_nights_count": len(lifetime_sleep_dates),
    }

    # Reconcile any one-shot XP granted before the activation rule existed.
    lifetime_keys = [_quest_key(quest["slug"]) for quest in QUEST_REGISTRY]
    old_lifetime_events = (
        db.query(XPEvent)
        .filter(XPEvent.user_id == user.id, XPEvent.event_key.in_(lifetime_keys))
        .all()
    )
    removed_old_lifetime_event = False
    if today >= LIFETIME_QUESTS_ACTIVATION_DATE:
        for event in old_lifetime_events:
            if event.date is not None and event.date.date() < LIFETIME_QUESTS_ACTIVATION_DATE:
                db.delete(event)
                removed_old_lifetime_event = True
    if removed_old_lifetime_event:
        db.flush()

    granted = 0

    # Lifetime awards keep their stable quest:{slug}:lifetime keys.
    for quest in QUEST_REGISTRY:
        if today < LIFETIME_QUESTS_ACTIVATION_DATE:
            break
        slug = quest["slug"]
        if slug not in CONDS:
            continue
        key = _quest_key(slug)
        exists = (
            db.query(XPEvent)
            .filter(XPEvent.user_id == user.id, XPEvent.event_key == key)
            .first()
        )
        if exists or not CONDS[slug](ctx):
            continue
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

    # Evaluate every historical week. Paused/deload weeks do not suppress these awards.
    weeks_with_source_data = set(activities_by_week) | set(wellness_by_week)
    for week in sorted(weeks_with_source_data):
        progress_by_slug = _weekly_quest_progress(
            week,
            activities_by_week.get(week, []),
            wellness_by_week.get(week, []),
        )
        for quest in WEEKLY_QUEST_REGISTRY:
            slug = quest["slug"]
            progress = progress_by_slug[slug]
            if int(progress["current"]) < int(progress["target"]):
                continue
            key = _weekly_quest_key(slug, week)
            exists = (
                db.query(XPEvent)
                .filter(XPEvent.user_id == user.id, XPEvent.event_key == key)
                .first()
            )
            if exists:
                continue
            earned_day = progress.get("_earned_day") or week
            source_id = progress.get("_source_id")
            db.add(XPEvent(
                user_id=user.id,
                week_start=datetime.combine(week, datetime.min.time()),
                date=datetime.combine(earned_day, datetime.min.time()),
                event_type="quest",
                event_key=key,
                amount=quest["reward"],
                source_type="quest",
                source_id=str(source_id) if source_id is not None else None,
                title=f"🏆 {quest['title']}",
            ))
            granted += 1

    # Reconcile the execution bonuses against the current source history. Stable
    # week-scoped keys prevent duplicates, and an edited/deleted source record
    # cannot leave an obsolete bonus in lifetime XP.
    bonus_event_rows = (
        db.query(XPEvent)
        .filter(
            XPEvent.user_id == user.id,
            or_(
                XPEvent.event_key.like("quest:goal_100:%"),
                XPEvent.event_key.like("quest:ideal_week:%"),
            ),
        )
        .all()
    )
    bonus_events_by_key = {event.event_key: event for event in bonus_event_rows}
    expected_bonus_keys: set[str] = set()

    def reconcile_bonus_event(
        key: str,
        week: date,
        *,
        eligible: bool,
        amount: float,
        title: str,
    ) -> None:
        nonlocal granted
        expected_bonus_keys.add(key)
        event = bonus_events_by_key.get(key)
        if not eligible:
            if event is not None:
                db.delete(event)
                bonus_events_by_key.pop(key, None)
            return
        if event is not None:
            event.event_type = "quest"
            event.amount = amount
            event.title = title
            event.week_start = datetime.combine(week, datetime.min.time())
            event.date = datetime.combine(week, datetime.min.time())
            event.source_type = "quest"
            event.source_id = None
            return

        event = XPEvent(
            user_id=user.id,
            week_start=datetime.combine(week, datetime.min.time()),
            date=datetime.combine(week, datetime.min.time()),
            event_type="quest",
            event_key=key,
            amount=amount,
            source_type="quest",
            title=title,
        )
        db.add(event)
        bonus_events_by_key[key] = event
        granted += 1

    qualifying_progress_by_week = _qualifying_days_by_week(all_activities)
    for summary in all_summaries:
        week = _trainer_week_start(summary.week_start.date())
        goal_ratio = float(getattr(summary, "completion_ratio", 0.0) or 0.0)
        goal_eligible = goal_ratio >= 1.0 and not bool(getattr(summary, "paused", False))

        target_days_raw = getattr(summary, "target_training_days", None)
        try:
            target_days = int(target_days_raw) if target_days_raw else WEEKLY_IDEAL_WEEK_QUALIFYING_DAYS_FALLBACK
        except (TypeError, ValueError):
            target_days = WEEKLY_IDEAL_WEEK_QUALIFYING_DAYS_FALLBACK
        if target_days <= 0:
            target_days = WEEKLY_IDEAL_WEEK_QUALIFYING_DAYS_FALLBACK
        target_days = min(target_days, WEEKLY_IDEAL_WEEK_QUALIFYING_DAYS_FALLBACK)

        qualifying_days = len(qualifying_progress_by_week.get(week, []))
        sleep_progress = _weekly_quest_progress(
            week,
            activities_by_week.get(week, []),
            wellness_by_week.get(week, []),
        )
        good_sleep_nights = int(sleep_progress["good_sleep_5"]["current"])
        ideal_week_eligible = (
            goal_eligible
            and qualifying_days >= target_days
            and good_sleep_nights >= WEEKLY_IDEAL_WEEK_GOOD_SLEEP_TARGET
        )

        reconcile_bonus_event(
            f"quest:goal_100:{week.isoformat()}",
            week,
            eligible=goal_eligible,
            amount=WEEKLY_GOAL_TARGET_REWARD,
            title="Цель недели ≥100% (+20 XP)",
        )
        reconcile_bonus_event(
            f"quest:ideal_week:{week.isoformat()}",
            week,
            eligible=ideal_week_eligible,
            amount=WEEKLY_IDEAL_WEEK_REWARD,
            title="Идеальная неделя (+40 XP)",
        )

    # If the source history no longer produces a summary for a former week,
    # remove any orphaned execution bonus from that week as well.
    for key, event in list(bonus_events_by_key.items()):
        if key not in expected_bonus_keys:
            db.delete(event)
            bonus_events_by_key.pop(key, None)

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


def quest_states(db, user, selected_week: date | None = None) -> list:
    """Return selected-week progress (current week by default) and lifetime progress."""
    from sqlalchemy import or_
    from ..models import Activity, XPEvent, Wellness, WeeklySummary

    today = _user_local_today(user)
    selected_week_start = _trainer_week_start(selected_week or today)
    current_calendar_week = _trainer_week_start(today)
    is_historical_week = selected_week_start < current_calendar_week

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
    wellness_rows = (
        db.query(Wellness)
        .filter(
            Wellness.user_id == user.id,
            or_(Wellness.sleep_secs > 0, Wellness.sleep_score > 0),
        )
        .order_by(Wellness.date.asc())
        .all()
    )
    activities_by_week, wellness_by_week = _group_weekly_data(dated_activities, wellness_rows)

    weekly_progress = _weekly_quest_progress(
        selected_week_start,
        activities_by_week.get(selected_week_start, []),
        wellness_by_week.get(selected_week_start, []),
    )
    out = []
    for quest in WEEKLY_QUEST_REGISTRY:
        slug = quest["slug"]
        event = earned.get(_weekly_quest_key(slug, selected_week_start))
        values = weekly_progress[slug]
        current = int(values["current"])
        target = int(values["target"])
        source_completed = current >= target
        # A past XPEvent is a durable receipt. For the current week, source data is
        # the authority even if a stale event remains from an earlier calculation.
        complete = source_completed or (is_historical_week and event is not None)
        status = "earned" if complete else "open"
        earned_day = values.get("_earned_day")
        earned_at = (
            event.date.strftime("%d.%m.%Y")
            if event is not None and event.date is not None and complete
            else earned_day.strftime("%d.%m.%Y") if earned_day is not None and source_completed else None
        )
        progress = {
            key: value for key, value in values.items()
            if not key.startswith("_")
        }
        out.append({
            "slug": slug,
            "title": quest["title"],
            "desc": quest["desc"],
            "reward": int(quest["reward"]),
            "kind": "weekly",
            "week_start": selected_week_start.isoformat(),
            "status": status,
            "earned_at": earned_at,
            "progress": progress,
        })

    # Lifetime statuses/progress remain based on raw history, independent of XPEvent presence.
    lifetime_activities = [
        activity for activity in dated_activities
        if today >= LIFETIME_QUESTS_ACTIVATION_DATE
        and LIFETIME_QUESTS_ACTIVATION_DATE <= _local_activity_day(activity) <= today
    ]
    sleep_dates = sorted({
        day for row in wellness_rows
        if today >= LIFETIME_QUESTS_ACTIVATION_DATE
        and (day := _wellness_day(row)) is not None
        and LIFETIME_QUESTS_ACTIVATION_DATE <= day <= today
    })
    night_count = len(sleep_dates)
    qualifying_days_by_week = _qualifying_training_days_by_week(lifetime_activities)
    best_training_days = max(qualifying_days_by_week.values(), default=0)
    lifetime_summaries = [
        summary for summary in all_summaries
        if today >= LIFETIME_QUESTS_ACTIVATION_DATE
        and LIFETIME_QUESTS_ACTIVATION_DATE <= summary.week_start.date() <= today
    ]
    finalized = sorted(
        [summary for summary in lifetime_summaries if summary.finalized],
        key=lambda summary: summary.week_start,
    )
    best_goal_pct = max(
        (max(0.0, float(summary.completion_ratio or 0.0)) * 100 for summary in finalized),
        default=0.0,
    )
    goal_streak = _best_goal_streak(finalized)

    ride_km_by_week: dict[date, float] = {}
    for activity in lifetime_activities:
        activity_day = _local_activity_day(activity)
        if activity_day is None or str(activity.sport_type or "").upper() != "RIDE":
            continue
        week = _trainer_week_start(activity_day)
        ride_km_by_week[week] = ride_km_by_week.get(week, 0.0) + max(float(activity.distance or 0.0), 0.0) / 1000.0
    best_ride_km = max(ride_km_by_week.values(), default=0.0)
    duration_progress = _record_duration_progress(lifetime_activities)

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
                    "date": sleep_dates[-3:][index].isoformat() if len(sleep_dates[-3:]) > index else None,
                }
                for index in range(3)
            ],
        },
    }
    completion_by_slug = {
        "first_three_day_week": best_training_days >= 3,
        "goal_met": any(
            summary.finalized and float(summary.completion_ratio or 0.0) >= 1.0
            for summary in lifetime_summaries
        ),
        "goal_streak_3": goal_streak >= 3,
        "first_50km_ride_week": any(distance >= 50.0 for distance in ride_km_by_week.values()),
        "record_duration": duration_progress >= 100.0,
        "sleep_connected": night_count >= 3,
    }

    for quest in QUEST_REGISTRY:
        slug = quest["slug"]
        event = earned.get(_quest_key(slug))
        if quest.get("requires"):
            status, earned_at = "unavailable", None
        elif completion_by_slug.get(slug, False):
            status = "earned"
            earned_at = event.date.strftime("%d.%m.%Y") if event and event.date else None
        else:
            status, earned_at = "open", None

        item = {
            "slug": slug,
            "title": quest["title"],
            "desc": quest["desc"],
            "reward": int(quest["reward"]),
            "kind": "lifetime",
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
