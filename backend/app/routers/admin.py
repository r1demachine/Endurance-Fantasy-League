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