from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from ..dependencies import get_current_user
from ..auth import decrypt_secret, decode_access_token
from ..database import get_db
from ..models import User, Activity, Wellness
from collections import defaultdict
from ..services.xp import recalculate_timeline, level_from_xp, round_xp
from datetime import date as _date
from ..services.intervals import (
    fetch_athlete_activities,
    fetch_athlete_activities_csv,
    fetch_wellness,
    calculate_xp,
    sleep_multiplier,
)
from ..config import get_settings
from datetime import datetime, timedelta
from typing import Optional

router = APIRouter(prefix="/api", tags=["Sync"])
settings = get_settings()
_optional_bearer = HTTPBearer(auto_error=False)

def _parse_activity(act: dict) -> dict | None:
    """Нормализует активность из JSON или CSV в единый dict."""
    act = {str(k).replace("\ufeff", "").strip(): v for k, v in act.items()}

    act_id = str(act.get("id") or act.get("icu_id") or "").strip()
    if not act_id:
        return None

    sport_type = str(act.get("type") or act.get("activity_type") or "WORKOUT").upper()
    act_name = act.get("name") or "Без названия"

    def _f(key, default=0.0):
        try:
            return float(act.get(key) or default)
        except (TypeError, ValueError):
            return float(default)

    def _i(key, default=0):
        try:
            return int(float(act.get(key) or default))
        except (TypeError, ValueError):
            return int(default)

    distance_m = _f("distance")
    moving_time_s = _i("moving_time")
    elevation_m = _f("total_elevation_gain") or _f("elevation_gain")
    training_load = _f("icu_training_load") or _f("training_load")
    intensity = _f("icu_intensity") or _f("intensity")

    # IF иногда приходит как проценты (85) вместо 0.85
    if intensity > 3.0:
        intensity = intensity / 100.0
    intensity_multiplier = round(max(0.5, min(2.0, intensity if intensity > 0 else 1.0)), 2)

    if training_load > 0:
        base_xp = training_load * 1.5
    else:
        base_xp = calculate_xp(sport_type, distance_m, elevation_m, moving_time_s)

    xp_earned = round(base_xp * intensity_multiplier, 2)
    base_xp = round(base_xp, 2)

    start_date_str = (
        act.get("start_date_local")
        or act.get("start_date")
        or act.get("startDateLocal")
        or ""
    )
    try:
        start_date = (
            datetime.fromisoformat(str(start_date_str).replace("Z", "+00:00"))
            if start_date_str
            else datetime.utcnow()
        )
    except Exception:
        start_date = datetime.utcnow()

    return {
        "intervals_activity_id": act_id,
        "name": act_name,
        "sport_type": sport_type,
        "distance": distance_m,
        "moving_time": moving_time_s,
        "elevation_gain": elevation_m,
        "training_load": training_load,
        "intensity": intensity,
        "base_xp": base_xp,
        "intensity_multiplier": intensity_multiplier,
        "xp_earned": xp_earned,
        "start_date": start_date,
        "average_heartrate": _f("average_heartrate") or _f("avg_hr"),
        "average_watts": _f("average_watts") or _f("icu_average_watts"),
        "normalized_power": _f("normalized_power") or _f("icu_weighted_avg_watts"),
    }


def _has_real_data(parsed: dict) -> bool:
    """False = Strava-заглушка или пустая запись."""
    if not parsed:
        return False
    name = (parsed.get("name") or "").strip()
    if name and name not in ("Без названия", "Untitled", "Workout"):
        return True
    if (parsed.get("distance") or 0) > 0:
        return True
    if (parsed.get("moving_time") or 0) > 0:
        return True
    if (parsed.get("training_load") or 0) > 0:
        return True
    if (parsed.get("xp_earned") or 0) > 0:
        return True
    return False


def _recalculate_user_xp(db: Session, user: User) -> None:
    """Пересчитывает XP ВСЕХ активностей юзера по календарным дням (согласованно)."""
    acts = (db.query(Activity)
              .filter(Activity.user_id == user.id)
              .order_by(Activity.start_date.asc())
              .all())
    if not acts:
        user.total_xp = 0.0
        user.level = 1
        return

    # группа по календарной дате
    by_day: dict[_date, list] = defaultdict(list)
    for a in acts:
        d = a.start_date.date() if a.start_date else _date.today()
        by_day[d].append(a)

    # полный диапазон дат (чтобы считать пропуски)
    start_d, end_d = min(by_day), max(by_day)
    day_records = []
    cur = start_d
    while cur <= end_d:
        acts_d = by_day.get(cur, [])
        # сон для дня: берём sleep_secs первой тренировки дня (уже сохранён при синке)
        sleep_secs = next((x.sleep_secs for x in acts_d if x.sleep_secs), None)
        day_records.append({
            "date": cur,
            "is_train": bool(acts_d),
            "sleep_secs": sleep_secs,
            "activities": [{
                "id": x.id,
                "sport_type": x.sport_type,
                "moving_time": x.moving_time,
                "intensity": x.intensity,
                "training_load": x.training_load,
            } for x in acts_d],
        })
        cur += timedelta(days=1)

    recalculate_timeline(day_records)

    # пишем результаты обратно
    total = 0.0
    for d in day_records:
        if not d["is_train"]:
            continue
        for ra in d["activities"]:
            row = db.get(Activity, ra["id"])
            if not row:
                continue
            row.base_xp = ra["base_xp"]
            row.rate_per_hour = ra["rate_per_hour"]
            row.sleep_multiplier = ra["sleep_multiplier"]
            row.intensity_multiplier = ra["intensity_multiplier"]
            row.intensity_category = ra["intensity_category"]
            row.intensity_reason = ra["intensity_reason"]
            row.streak_multiplier = ra["streak_multiplier"]
            row.streak_reason = ra["streak_reason"]
            row.xp_earned = ra["xp_earned"]
            total += ra["xp_earned"]

    user.total_xp = round_xp(total)
    user.level = level_from_xp(user.total_xp)

async def _sync_wellness_for_user(db, athlete_user, oldest, newest) -> dict:
    """Тянет wellness, пишет в БД, возвращает { 'YYYY-MM-DD': sleep_secs }."""
    records = await fetch_wellness(oldest=oldest, newest=newest)
    sleep_by_date: dict[str, int] = {}

    for row in records:
        if not isinstance(row, dict):
            continue
        date_str = str(row.get("id") or row.get("date") or "").strip()[:10]
        if len(date_str) < 10:
            continue

        raw_sleep = row.get("sleepSecs") if row.get("sleepSecs") is not None else row.get("sleep_secs")
        try:
            secs = int(raw_sleep) if raw_sleep is not None else None
        except (TypeError, ValueError):
            secs = None

        if secs is not None and secs > 0:
            sleep_by_date[date_str] = secs

        existing = (
            db.query(Wellness)
            .filter(Wellness.user_id == athlete_user.id, Wellness.date == date_str)
            .first()
        )
        if existing:
            if secs is not None:
                existing.sleep_secs = secs
            existing.sleep_score = _safe_float(row.get("sleepScore") or row.get("sleep_score"))
            existing.hrv = _safe_float(row.get("hrv"))
            existing.resting_hr = _safe_int(row.get("restingHR") or row.get("resting_hr"))
            existing.ctl = _safe_float(row.get("ctl"))
            existing.atl = _safe_float(row.get("atl"))
        else:
            db.add(
                Wellness(
                    user_id=athlete_user.id,
                    date=date_str,
                    sleep_secs=secs,
                    sleep_score=_safe_float(row.get("sleepScore") or row.get("sleep_score")),
                    hrv=_safe_float(row.get("hrv")),
                    resting_hr=_safe_int(row.get("restingHR") or row.get("resting_hr")),
                    ctl=_safe_float(row.get("ctl")),
                    atl=_safe_float(row.get("atl")),
                )
            )

    db.commit()
    return sleep_by_date


def _safe_float(v):
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _safe_int(v):
    try:
        return int(float(v)) if v is not None else None
    except (TypeError, ValueError):
        return None

@router.post("/sync")
async def sync_activities(
    oldest: str | None = None,
    newest: str | None = None,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Синхронизирует тренировки ТЕКУЩЕГО пользователя его ключом Intervals."""
    from ..auth import decrypt_secret
    from ..services.intervals import fetch_activities_for_user, fetch_wellness_for_user
    
    if not current.api_key_encrypted or not current.intervals_id:
        raise HTTPException(
            status_code=400,
            detail="Сначала привяжи Intervals.icu в профиле",
        )
    
    try:
        api_key = decrypt_secret(current.api_key_encrypted)
    except Exception:
        raise HTTPException(status_code=400, detail="Не удалось расшифровать ключ. Подключи заново.")
    
    athlete_id = current.intervals_id
    
    # ── Тянем активности этим юзером/ключом ──
    try:
        activities_data = await fetch_activities_for_user(
            api_key=api_key, athlete_id=athlete_id, oldest=oldest, newest=newest
        )
    except PermissionError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Intervals.icu недоступен: {type(e).__name__}")
    
    if not activities_data:
        return {"message": "Нет активностей для синхронизации", "synced_count": 0, "new_xp": 0}
    
    # ── Тянем wellness этим же юзером ──
    sleep_by_date: dict = {}
    try:
        wellness_records = await fetch_wellness_for_user(
            api_key=api_key, athlete_id=athlete_id, oldest=oldest, newest=newest
        )
        for row in wellness_records:
            if not isinstance(row, dict):
                continue
            date_str = str(row.get("id") or row.get("date") or "").strip()[:10]
            if len(date_str) < 10:
                continue
            raw_sleep = row.get("sleepSecs") if row.get("sleepSecs") is not None else row.get("sleep_secs")
            try:
                secs = int(raw_sleep) if raw_sleep is not None else None
            except (TypeError, ValueError):
                secs = None
            if secs is not None and secs > 0:
                sleep_by_date[date_str] = secs
    except Exception as e:
        print(f"⚠️ Wellness skip: {type(e).__name__}: {e}")
    
    # ── Пишем в БД ──
    new_xp = 0.0
    synced_count = 0
    skipped_empty = 0
    sleep_updated = 0
    seen_ids: set[str] = set()
    existing_rows = {
        row.intervals_activity_id: row
        for row in db.query(Activity).filter(Activity.user_id == current.id).all()
    }
    existing_ids = set(existing_rows.keys())
    for raw in activities_data:
        if not isinstance(raw, dict):
            continue
        parsed = _parse_activity(raw)
        if not parsed:
            continue
        act_id = parsed["intervals_activity_id"]
        if act_id in seen_ids:
            continue
        seen_ids.add(act_id)
        if act_id in existing_ids:
            # тренировка уже в БД — но ДОДОЛИВАЕМ сон, если он появился в Intervals
            row = existing_rows[act_id]
            act_date = parsed["start_date"].strftime("%Y-%m-%d")
            new_sleep = sleep_by_date.get(act_date)
            if new_sleep is None:
                prev = (parsed["start_date"] - timedelta(days=1)).strftime("%Y-%m-%d")
                new_sleep = sleep_by_date.get(prev)
            if new_sleep and (row.sleep_secs or 0) != new_sleep:
                row.sleep_secs = new_sleep
                sleep_updated += 1
            continue
        if not _has_real_data(parsed):
            skipped_empty += 1
            continue
        
        act_date = parsed["start_date"].strftime("%Y-%m-%d")
        sleep_secs = sleep_by_date.get(act_date)
        if sleep_secs is None:
            prev = (parsed["start_date"] - timedelta(days=1)).strftime("%Y-%m-%d")
            sleep_secs = sleep_by_date.get(prev)

        new_activity = Activity(
            user_id=current.id,
            intervals_activity_id=act_id,
            name=parsed["name"],
            sport_type=parsed["sport_type"],
            distance=parsed["distance"],
            moving_time=parsed["moving_time"],
            elevation_gain=parsed["elevation_gain"],
            average_heartrate=parsed.get("average_heartrate") or 0,
            training_load=parsed.get("training_load") or 0,
            intensity=parsed.get("intensity") or 0,
            sleep_secs=sleep_secs,
            start_date=parsed["start_date"],
        )
        db.add(new_activity)
        existing_ids.add(act_id)
        synced_count += 1

        dist_km = parsed["distance"] / 1000 if parsed["distance"] else 0
        print(
            f"✅ {parsed['name']} | {parsed['sport_type']} | "
            f"{dist_km:.1f}km | {parsed['moving_time'] // 60} мин"
        )
    
    if sleep_updated:
        print(f"😴 Обновлён сон на существующих тренировках: {sleep_updated}")
    db.commit()

    total_before = float(current.total_xp or 0)
    _recalculate_user_xp(db, current)
    db.commit()
    db.refresh(current)
    new_xp = round(float(current.total_xp or 0) - total_before, 2)

    return {
        "message": "Синхронизация успешна!",
        "synced_count": synced_count,
        "skipped_empty": skipped_empty,
        "sleep_updated": sleep_updated,
        "new_xp": new_xp,
        "user": {
            "id": current.id,
            "name": current.display_name,
            "level": current.level,
            "total_xp": round(float(current.total_xp or 0), 2),
        },
    }


@router.get("/user")
async def get_user_profile(
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Данные ТЕКУЩЕГО пользователя."""
    user = current
    
    activities = db.query(Activity).filter(Activity.user_id == user.id).order_by(Activity.start_date.desc()).limit(40).all()
    all_activities = db.query(Activity).filter(Activity.user_id == user.id).all()
    today = datetime.utcnow().date()
    
    dates = sorted({a.start_date.date() for a in all_activities if a.start_date}, reverse=True)
    day_streak = 0
    if dates and (today - dates[0]).days <= 1:
        day_streak = 1
        for i in range(len(dates) - 1):
            if (dates[i] - dates[i+1]).days == 1:
                day_streak += 1
            else:
                break
    
    def week_start(d):
        return d - timedelta(days=d.weekday())
    
    weeks = sorted({week_start(a.start_date.date()) for a in all_activities if a.start_date}, reverse=True)
    this_week = week_start(today)
    week_streak = 0
    if weeks and (this_week - weeks[0]).days <= 7:
        week_streak = 1
        for i in range(len(weeks) - 1):
            if (weeks[i] - weeks[i+1]).days == 7:
                week_streak += 1
            else:
                break
    
    week_seconds = sum(a.moving_time or 0 for a in all_activities if a.start_date and week_start(a.start_date.date()) == this_week)
    week_hours = round(week_seconds / 3600, 1)
    
    SEASON_START = datetime(2026, 9, 1)
    season_acts = [a for a in all_activities if a.start_date and a.start_date >= SEASON_START]
    season_stats = {
        "season_start": SEASON_START.strftime("%d.%m.%Y"),
        "total_km": round(sum(a.distance or 0 for a in season_acts) / 1000, 1),
        "total_hours": round(sum(a.moving_time or 0 for a in season_acts) / 3600, 1),
        "total_elevation": int(round(sum(a.elevation_gain or 0 for a in season_acts))),
        "total_workouts": len(season_acts),
        "total_xp": round(sum(a.xp_earned or 0 for a in season_acts)),
    }
    
    return {
        "user": {
            "id": user.id,
            "name": user.display_name,
            "username": user.username,
            "level": user.level,
            "total_xp": round(float(user.total_xp or 0), 2),
            "xp_to_next_level": round(((user.level) ** 2) * 100 - float(user.total_xp or 0), 2),
            "has_intervals_key": bool(user.api_key_encrypted),
            "intervals_id": user.intervals_id,
        },
        "stats": {
            "day_streak": day_streak,
            "week_streak": week_streak,
            "week_hours": week_hours,
            "week_goal_hours": 10,
        },
        "season_stats": season_stats,
        "recent_activities": [
            {
                "id": act.id,
                "name": act.name,
                "sport": act.sport_type,
                "distance_km": round((act.distance or 0) / 1000, 2),
                "moving_time_min": (act.moving_time or 0) // 60,
                "xp": act.xp_earned,
                "base_xp": act.base_xp or 0,
                "rate_per_hour": act.rate_per_hour or 0,
                "intensity_multiplier": act.intensity_multiplier or 1.0,
                "intensity_category": act.intensity_category or "MEDIUM",
                "intensity_reason": act.intensity_reason or "",
                "sleep_multiplier": act.sleep_multiplier or 1.0,
                "sleep_hours": round(act.sleep_secs / 3600, 1) if act.sleep_secs else None,
                "streak_multiplier": act.streak_multiplier or 1.0,
                "streak_reason": act.streak_reason or "",
                "date": act.start_date.strftime("%d.%m.%Y") if act.start_date else "Неизвестно",
            }
            for act in activities
        ]
    }


@router.get("/debug/csv-sample")
async def debug_csv_sample():
    """Показывает первые 3 активности из CSV для проверки парсинга"""
    try:
        activities = await fetch_athlete_activities()
        if not activities:
            return {"error": "No activities found"}
        
        sample = []
        for act in activities[:3]:
            act = {k.replace('\ufeff', ''): v for k, v in act.items()}
            sample.append({
                "id": act.get('id'),
                "name": act.get('name'),
                "type": act.get('type'),
                "distance": act.get('distance'),
                "moving_time": act.get('moving_time'),
                "icu_training_load": act.get('icu_training_load'),
                "start_date_local": act.get('start_date_local')
            })
        
        return {
            "total_activities": len(activities),
            "sample": sample
        }
    except Exception as e:
        return {"error": str(e)}



def _sleep_xp(sleep_secs: int | None, sleep_score: float | None) -> float:
    """Небольшой бонус XP за сон."""
    if not sleep_secs or sleep_secs < 3600:
        return 0.0
    hours = sleep_secs / 3600.0
    # 7–9 часов — база 15 XP, иначе меньше
    if 7 <= hours <= 9:
        base = 15.0
    elif 6 <= hours < 7 or 9 < hours <= 10:
        base = 10.0
    else:
        base = 5.0
    if sleep_score and sleep_score >= 80:
        base *= 1.3
    elif sleep_score and sleep_score < 60:
        base *= 0.7
    return round(base, 2)


@router.post("/sync-wellness")
async def sync_wellness(
    oldest: Optional[str] = Query(None),
    newest: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Синхронизирует сон/wellness из Intervals.icu и начисляет sleep XP."""
    try:
        records = await fetch_wellness(oldest=oldest, newest=newest)
        if not records:
            return {"message": "Нет wellness-данных", "synced_count": 0}

        user = db.query(User).filter(User.intervals_id == settings.INTERVALS_ATHLETE_ID).first()
        if not user:
            raise HTTPException(status_code=404, detail="Сначала выполните POST /api/sync")

        new_xp = 0.0
        synced = 0

        for row in records:
            date_str = str(row.get("id") or row.get("date") or "").strip()[:10]
            if not date_str or len(date_str) < 10:
                continue

            existing = (
                db.query(Wellness)
                .filter(Wellness.user_id == user.id, Wellness.date == date_str)
                .first()
            )
            if existing:
                continue

            sleep_secs = row.get("sleepSecs") or row.get("sleep_secs")
            try:
                sleep_secs = int(sleep_secs) if sleep_secs is not None else None
            except (TypeError, ValueError):
                sleep_secs = None

            sleep_score = row.get("sleepScore") or row.get("sleep_score")
            try:
                sleep_score = float(sleep_score) if sleep_score is not None else None
            except (TypeError, ValueError):
                sleep_score = None

            sxp = _sleep_xp(sleep_secs, sleep_score)

            def _num(key_camel, key_snake=None):
                v = row.get(key_camel)
                if v is None and key_snake:
                    v = row.get(key_snake)
                try:
                    return float(v) if v is not None else None
                except (TypeError, ValueError):
                    return None

            def _int(key_camel, key_snake=None):
                v = _num(key_camel, key_snake)
                return int(v) if v is not None else None

            rec = Wellness(
                user_id=user.id,
                date=date_str,
                sleep_secs=sleep_secs,
                sleep_score=sleep_score,
                sleep_quality=_int("sleepQuality", "sleep_quality"),
                avg_sleeping_hr=_num("avgSleepingHR", "avg_sleeping_hr"),
                resting_hr=_int("restingHR", "resting_hr"),
                hrv=_num("hrv"),
                fatigue=_int("fatigue"),
                soreness=_int("soreness"),
                stress=_int("stress"),
                mood=_int("mood"),
                readiness=_num("readiness"),
                weight=_num("weight"),
                ctl=_num("ctl"),
                atl=_num("atl"),
                sleep_xp=sxp,
            )
            db.add(rec)
            new_xp += sxp
            synced += 1

        db.commit()

        

        return {
            "message": "Wellness синхронизирован",
            "synced_count": synced,
            "new_xp": round(new_xp, 2),
            "user": {
                "level": user.level,
                "total_xp": round(user.total_xp, 2),
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/wellness")
async def get_wellness(
    limit: int = Query(14, ge=1, le=90),
    db: Session = Depends(get_db),
):
    """Последние записи сна/wellness."""
    user = db.query(User).filter(User.intervals_id == settings.INTERVALS_ATHLETE_ID).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    rows = (
        db.query(Wellness)
        .filter(Wellness.user_id == user.id)
        .order_by(Wellness.date.desc())
        .limit(limit)
        .all()
    )
    return {
        "wellness": [
            {
                "date": r.date,
                "sleep_hours": round(r.sleep_secs / 3600, 1) if r.sleep_secs else None,
                "sleep_score": r.sleep_score,
                "sleep_xp": r.sleep_xp,
                "hrv": r.hrv,
                "resting_hr": r.resting_hr,
                "fatigue": r.fatigue,
                "ctl": r.ctl,
                "atl": r.atl,
            }
            for r in rows
        ]
    }


@router.delete("/reset")
async def reset_all_data(
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Очистка данных ТЕКУЩЕГО пользователя."""
    deleted_activities = db.query(Activity).filter(Activity.user_id == current.id).delete(synchronize_session=False)
    deleted_wellness = 0
    try:
        from ..models import Wellness
        deleted_wellness = db.query(Wellness).filter(Wellness.user_id == current.id).delete(synchronize_session=False)
    except Exception:
        pass
    
    current.total_xp = 0.0
    current.level = 1
    db.commit()
    
    return {
        "message": "Все данные очищены",
        "deleted_activities": deleted_activities,
        "deleted_wellness": deleted_wellness,
        "user": {
            "name": current.display_name,
            "level": current.level,
            "total_xp": 0,
        },
    }


@router.get("/leaderboard")
async def leaderboard(
    scope: str = Query("global", regex="^(global|friends)$"),
    limit: int = Query(50, ge=1, le=100),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_optional_bearer),
    db: Session = Depends(get_db),
):
    """Рейтинг: global — все (публично), friends — только принятые друзья (авторизация)."""
    current: Optional[User] = None
    if credentials is not None:
        uid = decode_access_token(credentials.credentials)
        if uid is not None:
            current = db.get(User, uid)

    if scope == "global":
        users = (
            db.query(User)
            .order_by(User.total_xp.desc())
            .limit(limit)
            .all()
        )
 
    else:
        if current is None:
            raise HTTPException(status_code=401, detail="Friends-рейтинг доступен после входа")
        # друзья = accepted с обеих сторон; нет друзей → пустой рейтинг
        from ..models import Friendship, FriendshipStatus
        friend_ids_rows = (
            db.query(Friendship.to_user_id)
            .filter(
                Friendship.from_user_id == current.id,
                Friendship.status == FriendshipStatus.ACCEPTED,
            )
            .union(
                db.query(Friendship.from_user_id).filter(
                    Friendship.to_user_id == current.id,
                    Friendship.status == FriendshipStatus.ACCEPTED,
                )
            )
            .all()
        )
        friend_ids = {r[0] for r in friend_ids_rows}
        if not friend_ids:
            return {"scope": scope, "entries": []}
        friend_ids.add(current.id)
        users = (
            db.query(User)
            .filter(User.id.in_(friend_ids))
            .order_by(User.total_xp.desc())
            .limit(limit)
            .all()
        )
    
    return {
        "scope": scope,
        "entries": [
            {
                "rank": i + 1,
                "id": u.id,
                "display_name": u.display_name,
                "username": u.username,
                "level": u.level,
                "total_xp": round(float(u.total_xp or 0), 2),
                "is_you": current is not None and u.id == current.id,
            }
            for i, u in enumerate(users)
        ],
    }


