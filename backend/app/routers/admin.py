from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, HTTPException
from ..database import get_db
from ..dependencies import require_admin
from ..models import Activity, Friendship, User

# dependencies на уровне роутера: КАЖДЫЙ эндпоинт, который ты добавишь
# в этот файл в будущем, автоматически закрыт проверкой require_admin.
router = APIRouter(
    prefix="/api/admin",
    tags=["Admin"],
    dependencies=[Depends(require_admin)],
)


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    """Безопасная read-only сводка. Деструктивных операций здесь нет."""
    return {
        "users": db.query(func.count(User.id)).scalar(),
        "activities": db.query(func.count(Activity.id)).scalar(),
        "friendships": db.query(func.count(Friendship.id)).scalar(),
    }

@router.get("/xp-compare")
def xp_compare(user_id: int, db: Session = Depends(get_db)):
    """Диагностика v5 vs v6 по неделям. НИЧЕГО не записывает."""
    from collections import defaultdict as _dd
    from datetime import date as _d
    from ..services import xp_v6 as X6

    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    acts = (db.query(Activity).filter(Activity.user_id == user_id)
            .order_by(Activity.start_date.asc(), Activity.id.asc()).all())
    by_day = _dd(list)
    for a in acts:
        by_day[a.start_date.date() if a.start_date else _d.today()].append(a)
    weeks = _dd(lambda: {"v5": 0.0, "v6_load": 0.0, "days": 0})
    for d, day_acts in by_day.items():
        ws = X6.week_start(d)
        weeks[ws]["v5"] += sum(a.xp_earned or 0 for a in day_acts)
        tss_day = sum(X6.resolve_training_load({
            "training_load": a.training_load, "moving_time": a.moving_time,
            "intensity": a.intensity, "sport_type": a.sport_type})[0] for a in day_acts)
        weeks[ws]["v6_load"] += X6.effort_xp_day(tss_day)
        if X6.is_qualifying_day([{"moving_time": a.moving_time} for a in day_acts]):
            weeks[ws]["days"] += 1
    return {
        "user_id": user_id,
        "current_total_xp": round(float(user.total_xp or 0), 2),
        "legacy_offset": round(float(user.legacy_xp_offset or 0), 2),
        "weeks": [
            {
                "week": ws.isoformat(),
                "v5_xp": round(w["v5"], 2),
                "v6_load_xp": round(w["v6_load"], 2),
                "v6_load_plus_consistency": round(
                    w["v6_load"] + min(w["days"], X6.CONSISTENCY_DAYS_CAP) * X6.CONSISTENCY_XP_PER_DAY, 2),
            }
            for ws, w in sorted(weeks.items())
        ],
    }


@router.post("/xp-migrate")
def xp_migrate(db: Session = Depends(get_db)):
    """Одноразовый бэкфилл XP v6 на ВСЕХ пользователей (идемпотентный).
    Прогоняет v6-пересчёт: миграционная компенсация (одноразово),
    исторические WeeklySummary, события только от недели активации.
    Возвращает отчёт before/after — это же снапшот для сверки."""
    from ..routers.sync import _recalculate_user_xp_v6

    report = []
    for user in db.query(User).order_by(User.id.asc()).all():
        before_total = round(float(user.total_xp or 0), 2)
        before_level = user.level
        _recalculate_user_xp_v6(db, user)
        db.commit()
        report.append({
            "user_id": user.id,
            "username": user.username,
            "total_before": before_total,
            "total_after": round(float(user.total_xp or 0), 2),
            "level_before": before_level,
            "level_after": user.level,
            "legacy_offset": round(float(user.legacy_xp_offset or 0), 2),
        })
    return {"migrated": len(report), "report": report}

@router.post("/reset-all")
def reset_all(db: Session = Depends(get_db)):
    """ПОЛНЫЙ сброс базы данных (только для админа).
    Удаляет ВСЕХ пользователей, тренировки, wellness, события, рейтинги.
    Использовать только на чистой базе перед запуском v6."""
    from sqlalchemy import text
    
    # Отключаем проверки внешних ключей для CASCADE
    db.execute(text("TRUNCATE TABLE xp_events RESTART IDENTITY CASCADE"))
    db.execute(text("TRUNCATE TABLE weekly_summaries RESTART IDENTITY CASCADE"))
    db.execute(text("TRUNCATE TABLE notifications RESTART IDENTITY CASCADE"))
    db.execute(text("TRUNCATE TABLE friendships RESTART IDENTITY CASCADE"))
    db.execute(text("TRUNCATE TABLE wellness RESTART IDENTITY CASCADE"))
    db.execute(text("TRUNCATE TABLE activities RESTART IDENTITY CASCADE"))
    db.execute(text("TRUNCATE TABLE users RESTART IDENTITY CASCADE"))
    db.commit()
    
    return {
        "message": "✅ База данных полностью очищена",
        "warning": "Все пользователи, тренировки и данные удалены. Зарегистрируйся заново.",
    }


@router.get("/xp-calibration")
def xp_calibration(db: Session = Depends(get_db)):
    """Калибровка по РЕАЛЬНЫМ данным + синтетика. Read-only, ничего не пишет."""
    from ..models import WeeklySummary
    from ..services import xp_v6 as X6

    weeks = (
        db.query(WeeklySummary)
        .filter(WeeklySummary.finalized == True)  # noqa: E712
        .all()
    )
    per_user: dict = {}
    for s in weeks:
        per_user.setdefault(s.user_id, []).append(s)

    ratios, load_shares = [], []
    cap_cons = cap_qual = no_recovery = 0
    users_report = []
    for uid, sums in per_user.items():
        user = db.get(User, uid)
        rows = []
        for s in sorted(sums, key=lambda x: x.week_start):
            ratio = s.completion_ratio or 0
            total = s.total_xp or 0
            ratios.append(ratio)
            load_shares.append((s.effort_xp / total) if total else 0)
            if (s.consistency_xp or 0) >= X6.CONSISTENCY_DAYS_CAP * X6.CONSISTENCY_XP_PER_DAY:
                cap_cons += 1
            if (s.quality_xp or 0) >= X6.QUALITY_WEEKLY_XP_CAP:
                cap_qual += 1
            if (s.recovery_xp or 0) == 0:
                no_recovery += 1
            rows.append({
                "week": s.week_start.strftime("%d.%m"),
                "load": round(s.actual_load or 0, 1),
                "target": round(s.target_load or 0, 1),
                "ratio": round(ratio, 2),
                "days": s.training_days,
                "xp": {
                    "effort": s.effort_xp, "goal": s.goal_xp,
                    "consistency": s.consistency_xp, "quality": s.quality_xp,
                    "recovery": s.recovery_xp, "quest": s.quest_xp,
                },
                "total": round(total, 1),
                "league_score": s.league_score,
                "division": s.division,
            })
        users_report.append({
            "user_id": uid,
            "username": user.username if user else "?",
            "weeks": len(rows),
            "rows": rows,
        })

    hints = []
    if ratios:
        med = sorted(ratios)[len(ratios) // 2]
        if med > 1.1:
            hints.append("Медиана выполнения > 1.10: база отстаёт от реальной нагрузки — "
                         "кандидат: BASE_LONG_FACTOR 0.8→0.85 или окно 6→5 недель")
        if med < 0.7:
            hints.append("Медиана выполнения < 0.70: цели завышены — проверь, что неизвестные "
                         "недели не зануляются и upsert доносит поздний TSS")
    if load_shares:
        avg_share = sum(load_shares) / len(load_shares)
        if avg_share > 0.6:
            hints.append("Нагрузка > 60% всего XP: объём доминирует — кандидат: "
                         "GOAL_XP_MAX 100→120 или CONSISTENCY_XP_PER_DAY 30→35")
        if avg_share < 0.2:
            hints.append("Нагрузка < 20% XP: объём недооценён — кандидат: DAILY_LOAD_XP_BASE 14→16")
        if cap_cons / len(ratios) > 0.5:
            hints.append("Кап регулярности (5 дней) достигается >50% недель — обсудить CONSISTENCY_DAYS_CAP")
        if no_recovery / len(ratios) > 0.5:
            hints.append("Recovery = 0 в >50% недель: мало sleep score — проверь wellness-синк")

    return {
        "finalized_weeks": len(weeks),
        "median_completion": round(sorted(ratios)[len(ratios) // 2], 2) if ratios else None,
        "avg_load_share_of_xp": round(sum(load_shares) / len(load_shares), 2) if load_shares else None,
        "hints": hints,
        "users": users_report,
        "synthetic": X6.synthetic_report(),
        "params": {
            "DAILY_LOAD_XP_BASE": X6.DAILY_LOAD_XP_BASE,
            "LOAD_EXPONENT": X6.LOAD_EXPONENT,
            "DAILY_TSS_CAP": X6.DAILY_TSS_CAP,
            "GOAL_XP_MAX": X6.GOAL_XP_MAX,
            "GOAL_XP_OVERACHIEVEMENT": X6.GOAL_XP_OVERACHIEVEMENT,
            "CONSISTENCY_XP_PER_DAY": X6.CONSISTENCY_XP_PER_DAY,
            "CONSISTENCY_DAYS_CAP": X6.CONSISTENCY_DAYS_CAP,
            "QUALITY_WEEKLY_XP_CAP": X6.QUALITY_WEEKLY_XP_CAP,
            "RECOVERY_TIERS": X6.RECOVERY_TIERS,
            "LEAGUE_WEIGHTS": [X6.LEAGUE_GOAL_WEIGHT, X6.LEAGUE_CONSISTENCY_WEIGHT, X6.LEAGUE_QUALITY_WEIGHT],
        },
    }