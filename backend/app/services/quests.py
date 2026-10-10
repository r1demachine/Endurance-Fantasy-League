"""Квесты и достижения v6 (PR5).

Квесты — одноразовые (lifetime) ачивки поверх XPEvent:
стабильный ключ quest:{slug}:lifetime, повторное начисление невозможно.
Квесты, требующие данных, которые мы НЕ синхронизируем (мощность, FTP Вт/кг),
не имитируются из длительности/TSS — у них статус "unavailable".
"""
from __future__ import annotations

from datetime import datetime, timedelta

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
        "desc": "Подключить сон: 3+ ночи со sleep score",
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
        if str(a.sport_type or "").upper() != "RIDE" or not a.start_date:
            continue
        ws = a.start_date.date() - timedelta(days=a.start_date.date().weekday())
        per_week[ws] = per_week.get(ws, 0) + (a.distance or 0)
    return any(v >= 50000 for v in per_week.values())


def _cond_record_duration(ctx):
    acts = sorted([a for a in ctx["acts"] if a.start_date],
                  key=lambda a: (a.start_date, a.id))
    prev_max = 0
    seen = 0
    for a in acts:
        if getattr(a, "is_manual", False):
            continue
        dur = a.moving_time or 0
        if seen >= 3 and prev_max > 0 and dur >= prev_max * 1.1:
            return True
        prev_max = max(prev_max, dur)
        seen += 1
    return False


def _cond_sleep_connected(ctx):
    return ctx["sleep_score_count"] >= 3


CONDS = {
    "first_three_day_week": _cond_first_three_day_week,
    "goal_met": _cond_goal_met,
    "goal_streak_3": _cond_goal_streak_3,
    "first_50km_ride_week": _cond_first_50km_ride_week,
    "record_duration": _cond_record_duration,
    "sleep_connected": _cond_sleep_connected,
}


def grant_quests(db, user, acts, summaries) -> int:
    """Одноразовые ачивки поверх XPEvent. Идемпотентно: ключ уже есть → skip."""
    from ..models import XPEvent, Wellness

    sleep_score_count = (
        db.query(Wellness)
        .filter(Wellness.user_id == user.id, Wellness.sleep_score > 0)
        .count()
    )
    ctx = {"weeks": summaries, "acts": acts, "sleep_score_count": sleep_score_count}
    today = datetime.utcnow().date()
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
    return granted


def quest_states(db, user) -> list:
    """Статусы для API: earned | open | unavailable."""
    from ..models import XPEvent, Wellness

    earned = {
        e.event_key: e
        for e in db.query(XPEvent)
        .filter(XPEvent.user_id == user.id, XPEvent.event_type == "quest")
        .all()
    }
    out = []
    for q in QUEST_REGISTRY:
        key = _quest_key(q["slug"])
        ev = earned.get(key)
        if ev:
            status = "earned"
            earned_at = ev.date.strftime("%d.%m.%Y") if ev.date else None
        elif q.get("requires"):
            status = "unavailable"
            earned_at = None
        else:
            status = "open"
            earned_at = None
        out.append({
            "slug": q["slug"],
            "title": q["title"],
            "desc": q["desc"],
            "reward": int(q["reward"]),
            "status": status,
            "earned_at": earned_at,
        })
    return out