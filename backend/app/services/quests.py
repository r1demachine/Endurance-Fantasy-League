"""Квесты и достижения v6 (PR5).

Квесты — одноразовые (lifetime) ачивки поверх XPEvent:
стабильный ключ quest:{slug}:lifetime, повторное начисление невозможно.
Квесты, требующие данных, которые мы НЕ синхронизируем (мощность, FTP Вт/кг),
не имитируются из длительности/TSS — у них статус "unavailable".
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


def _cond_goal_streak_3(ctx):
    good = [s.week_start for s in ctx["weeks"]
            if s.finalized and (s.completion_ratio or 0) >= 1.0]
    if len(good) < 3:
        return False
    step = timedelta(days=7)
    for i in range(len(good) - 2):
        if good[i + 1] - good[i] == step and good[i + 2] - good[i + 1] == step:
            return True
    return False


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
    # История до даты запуска нужна как база личного рекорда, но не может сама
    # выдать награду. Засчитываем только новый рекорд, установленный после cutoff.
    acts = sorted(
        [a for a in ctx["all_acts"] if _local_activity_day(a) is not None],
        key=lambda a: (_local_activity_day(a), a.id),
    )
    activation_date = ctx["activation_date"]
    prev_max = 0
    seen = 0
    for a in acts:
        if getattr(a, "is_manual", False):
            continue
        dur = a.moving_time or 0
        is_after_cutoff = _local_activity_day(a) >= activation_date
        if is_after_cutoff and seen >= 3 and prev_max > 0 and dur >= prev_max * 1.1:
            return True
        prev_max = max(prev_max, dur)
        seen += 1
    return False


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
    """Одноразовые ачивки только по достижениям с даты активации и позже."""
    from ..models import XPEvent, Wellness

    activation_date: date = get_settings().XP_QUESTS_ACTIVATION_DATE
    # Недельные условия берём только из полных недель, начавшихся не раньше cutoff.
    eligible_summaries = [
        s for s in summaries
        if s.week_start and s.week_start.date() >= activation_date
    ]
    eligible_acts = [
        a for a in acts
        if _local_activity_day(a) is not None and _local_activity_day(a) >= activation_date
    ]
    from sqlalchemy import or_

    sleep_nights_count = (
        db.query(Wellness)
        .filter(
            Wellness.user_id == user.id,
            Wellness.date >= activation_date.isoformat(),
            or_(Wellness.sleep_secs > 0, Wellness.sleep_score > 0),
        )
        .count()
    )
    ctx = {
        "weeks": eligible_summaries,
        "acts": eligible_acts,
        "all_acts": acts,
        "activation_date": activation_date,
        "sleep_nights_count": sleep_nights_count,
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
    for activity in acts:
        if not _is_qualifying_trainer_activity(activity):
            continue
        activity_dt = getattr(activity, "start_date_local", None) or activity.start_date
        activity_day = activity_dt.date() if isinstance(activity_dt, datetime) else activity_dt
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
    activation_date: date = get_settings().XP_QUESTS_ACTIVATION_DATE
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
        if summary.week_start and summary.week_start.date() >= activation_date
    ]
    eligible_activities = [
        activity for activity in activities
        if (_local_activity_day(activity) is not None
            and _local_activity_day(activity) >= activation_date)
    ]

    sleep_records = (
        db.query(Wellness)
        .filter(
            Wellness.user_id == user.id,
            Wellness.date >= activation_date.isoformat(),
            or_(Wellness.sleep_secs > 0, Wellness.sleep_score > 0),
        )
        .order_by(Wellness.date.asc())
        .all()
    )
    sleep_dates = sorted({row.date for row in sleep_records if row.date})
    night_count = len(sleep_dates)

    best_training_days = max(
        (int(summary.training_days or 0) for summary in eligible_summaries),
        default=0,
    )
    finalized = sorted(
        [summary for summary in eligible_summaries if summary.finalized and summary.week_start],
        key=lambda summary: summary.week_start,
    )
    best_goal_pct = max(
        (max(0.0, float(summary.completion_ratio or 0.0)) * 100 for summary in eligible_summaries),
        default=0.0,
    )

    # Count the current consecutive run backwards from the most recent finalized week.
    goal_streak = 0
    if finalized:
        by_week = {summary.week_start.date(): summary for summary in finalized}
        cursor = max(by_week)
        while True:
            row = by_week.get(cursor)
            if row is None or float(row.completion_ratio or 0.0) < 1.0:
                break
            goal_streak += 1
            cursor -= timedelta(days=7)

    ride_km_by_week: dict[date, float] = {}
    for activity in eligible_activities:
        activity_day = _local_activity_day(activity)
        if activity_day is None or str(activity.sport_type or "").upper() != "RIDE":
            continue
        week = _trainer_week_start(activity_day)
        ride_km_by_week[week] = ride_km_by_week.get(week, 0.0) + max(float(activity.distance or 0.0), 0.0) / 1000.0
    best_ride_km = max(ride_km_by_week.values(), default=0.0)

    recent_start = today - timedelta(days=29)
    dated_nonmanual = [
        (activity, _local_activity_day(activity))
        for activity in activities
        if not bool(getattr(activity, "is_manual", False))
        and _local_activity_day(activity) is not None
        and int(getattr(activity, "moving_time", 0) or 0) > 0
    ]
    recent_durations = [
        int(activity.moving_time or 0)
        for activity, day in dated_nonmanual
        if recent_start <= day <= today and day >= activation_date
    ]
    previous_record = max(
        (
            int(activity.moving_time or 0)
            for activity, day in dated_nonmanual
            if day < recent_start
        ),
        default=0,
    )
    recent_longest = max(recent_durations, default=0)
    target_duration = previous_record * 1.1
    if target_duration <= 0 and recent_longest > 0:
        # With no pre-window baseline, use the current recent record as a provisional PB.
        target_duration = recent_longest * 1.1
    duration_progress = (recent_longest / target_duration * 100.0) if target_duration > 0 else 0.0

    trainer_key = _trainer_week_key(current_week)
    trainer_event = earned.get(trainer_key)
    trainer_qualifies = any(
        _is_qualifying_trainer_activity(activity)
        and _local_activity_day(activity) is not None
        and _trainer_week_start(_local_activity_day(activity)) == current_week
        for activity in activities
    )
    trainer_done = bool(trainer_event or trainer_qualifies)
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
            "recent_duration_secs": recent_longest,
            "record_before_recent_secs": previous_record,
            "required_duration_secs": round(target_duration),
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
        if event:
            status = "earned"
            earned_at = event.date.strftime("%d.%m.%Y") if event.date else None
        elif quest.get("requires"):
            status = "unavailable"
            earned_at = None
        else:
            status = "open"
            earned_at = None

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
