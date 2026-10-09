from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from ..dependencies import get_current_user
from ..auth import decrypt_secret, decode_access_token
from ..database import get_db
from ..models import User, Activity, Wellness, Friendship, FriendshipStatus
from collections import defaultdict
from ..services.xp import recalculate_timeline, level_from_xp, round_xp
from datetime import date as _date
from ..services.intervals import calculate_xp
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

def _parse_w_float(v):
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _parse_w_int(v):
    try:
        return int(float(v)) if v is not None else None
    except (TypeError, ValueError):
        return None


def _recalculate_user_xp(db: Session, user: User) -> None:
    """Пересчитывает XP ВСЕХ активностей юзера по календарным дням (согласованно)."""
    acts = (db.query(Activity)
            .filter(Activity.user_id == user.id)
            .order_by(Activity.start_date.asc(), Activity.id.asc())
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


def _recalculate_user_xp_v6(db: Session, user: User) -> None:
    """XP v6: аддитивный пересчёт всей истории + upsert XPEvent/WeeklySummary."""
    from ..models import WeeklySummary, XPEvent
    from ..services import xp_v6 as X6

    acts = (db.query(Activity)
            .filter(Activity.user_id == user.id)
            .order_by(Activity.start_date.asc(), Activity.id.asc())
            .all())

    # 1) нагрузка каждой активности + источник
    for a in acts:
        tss, source = X6.resolve_training_load({
            "training_load": a.training_load, "moving_time": a.moving_time,
            "intensity": a.intensity, "sport_type": a.sport_type,
        })
        a.tss = round(tss, 2)
        a.tss_estimated = (source == "estimated")

    hist = [{"id": a.id, "sport_type": a.sport_type, "moving_time": a.moving_time} for a in acts]

    by_day: dict[_date, list] = defaultdict(list)
    for a in acts:
        by_day[a.start_date.date() if a.start_date else _date.today()].append(a)

    # 2) дни: effort, распределение долей, qualifying, is_long
    day_info: dict[_date, dict] = {}
    for d, day_acts in by_day.items():
        tss_day = sum(a.tss or 0 for a in day_acts)
        day_xp = X6.effort_xp_day(tss_day)
        shares = X6.allocate_daily_effort_xp([{"tss": a.tss} for a in day_acts], day_xp)
        for a, share in zip(day_acts, shares):
            a.xp_earned = share
            med = X6.medians_by_sport(hist, {a.id}).get(str(a.sport_type or "").upper())
            a.is_long = bool(med and (a.moving_time or 0) >= med * X6.LONG_WORKOUT_MEDIAN_MULTIPLIER)
        day_info[d] = {
            "acts": day_acts, "tss": tss_day, "day_xp": day_xp,
            "qualifying": X6.is_qualifying_day([{"moving_time": a.moving_time} for a in day_acts]),
        }

    # 3) одноразовая миграция: компенсация, чтобы уровни не просели
    if user.xp_migrated_at is None:
        old_total = float(user.total_xp or 0)
        new_sum = round_xp(sum(a.xp_earned or 0 for a in acts))
        user.legacy_xp_offset = round(max(0.0, old_total - new_sum), 2)
        user.xp_migrated_at = datetime.utcnow()
    activation_ws = X6.week_start(user.xp_migrated_at.date())
    cfg = get_settings().XP_V6_ACTIVATION_DATE
    if cfg:
        try:
            activation_ws = max(activation_ws, X6.week_start(datetime.fromisoformat(cfg).date()))
        except ValueError:
            pass

    all_weeks = sorted({X6.week_start(d) for d in day_info})
    this_week = X6.week_start(_date.today())
    week_load = {ws: 0.0 for ws in all_weeks}
    week_days = {ws: 0 for ws in all_weeks}
    for d, info in day_info.items():
        ws = X6.week_start(d)
        week_load[ws] += info["tss"]
        if info["qualifying"]:
            week_days[ws] += 1

    scores_by_week: dict[_date, list] = defaultdict(list)
    for w in db.query(Wellness).filter(Wellness.user_id == user.id).all():
        if w.date and w.sleep_score:
            try:
                scores_by_week[X6.week_start(datetime.fromisoformat(w.date).date())].append(float(w.sleep_score))
            except Exception:
                continue

    def upsert_event(key, etype, amount, ws, dt, title):
        ev = (db.query(XPEvent)
              .filter(XPEvent.user_id == user.id, XPEvent.event_key == key)
              .first())
        if amount <= 0:
            if ev:
                db.delete(ev)
            return
        if ev:
            ev.amount = round_xp(amount)
            ev.title = title
        else:
            db.add(XPEvent(
                user_id=user.id,
                week_start=datetime.combine(ws, datetime.min.time()),
                date=datetime.combine(dt, datetime.min.time()),
                event_type=etype, event_key=key,
                amount=round_xp(amount), source_type="week", title=title,
            ))

    medians = X6.medians_by_sport(hist, set())

    for ws in all_weeks:
        finalized = ws < this_week
        prior = [p for p in all_weeks if p < ws]
        baseline = X6.weekly_baseline([week_load[p] for p in prior])
        target = baseline or X6.starter_target()
        ratio = (week_load[ws] / target) if target else 0.0
        days = week_days[ws]
        t_days = X6.target_training_days([week_days[p] for p in prior])

        # регулярность: по дням, сразу (недели от активации)
        if ws >= activation_ws:
            for d, info in day_info.items():
                if X6.week_start(d) == ws and info["qualifying"]:
                    upsert_event(f"consistency:{d.isoformat()}", "consistency",
                                 X6.CONSISTENCY_XP_PER_DAY, ws, d, "Training day +30")

        # качество: недельные ключи, сразу (недели от активации)
        quality_xp = 0.0
        if ws >= activation_ws:
            day_dicts = {
                d: [{
                    "moving_time": a.moving_time, "intensity": a.intensity,
                    "load_source": "estimated" if a.tss_estimated else "real",
                    "sport_type": a.sport_type, "id": a.id,
                } for a in info["acts"]]
                for d, info in day_info.items() if X6.week_start(d) == ws
            }
            for kind, amt in X6.quality_events_week(day_dicts, medians):
                upsert_event(f"{kind}:{ws.isoformat()}", kind, amt, ws, ws,
                             "High intensity +15" if kind == "quality_hard" else "Long workout +15")
                quality_xp += amt

        # цель и восстановление: только на закрытой неделе
        goal_xp = 0.0
        recovery = 0.0
        if finalized and ws >= activation_ws:
            goal_xp = X6.weekly_goal_xp(ratio)
            upsert_event(f"weekly_goal:{ws.isoformat()}", "weekly_goal", goal_xp, ws, ws,
                         f"Weekly goal {int(ratio * 100)}%")
            recovery = X6.recovery_xp_week(scores_by_week.get(ws, []))
            upsert_event(f"recovery:{ws.isoformat()}", "recovery", recovery, ws, ws,
                         "Recovery (sleep score)")

        quest_xp = round_xp(sum(e.amount for e in db.query(XPEvent).filter(
            XPEvent.user_id == user.id,
            XPEvent.week_start == datetime.combine(ws, datetime.min.time()),
            XPEvent.event_type.in_(["quest", "achievement"])).all()))

        consistency_xp = round_xp(min(days, X6.CONSISTENCY_DAYS_CAP) * X6.CONSISTENCY_XP_PER_DAY) if ws >= activation_ws else 0.0
        effort_week = round_xp(sum(i["day_xp"] for d, i in day_info.items() if X6.week_start(d) == ws))
        total_week = round_xp(effort_week + consistency_xp + quality_xp + goal_xp + recovery + quest_xp)

        summ = (db.query(WeeklySummary)
                .filter(WeeklySummary.user_id == user.id,
                        WeeklySummary.week_start == datetime.combine(ws, datetime.min.time()))
                .first())
        if not summ:
            summ = WeeklySummary(user_id=user.id, week_start=datetime.combine(ws, datetime.min.time()))
            db.add(summ)
        summ.actual_load = round_xp(week_load[ws])
        summ.target_load = round_xp(target)
        summ.completion_ratio = round(ratio, 4)
        summ.training_days = days
        summ.target_training_days = t_days
        summ.effort_xp = effort_week
        summ.goal_xp = goal_xp
        summ.consistency_xp = consistency_xp
        summ.quality_xp = quality_xp
        summ.recovery_xp = recovery
        summ.quest_xp = quest_xp
        summ.total_xp = total_week
        summ.league_score = X6.league_score(ratio, days, t_days, quality_xp)
        summ.finalized = finalized

    db.flush()
    events_sum = round_xp(sum(e.amount for e in db.query(XPEvent).filter(XPEvent.user_id == user.id).all()))
    acts_sum = round_xp(sum(a.xp_earned or 0 for a in acts))
    user.total_xp = round_xp(float(user.legacy_xp_offset or 0) + acts_sum + events_sum)
    user.level = level_from_xp(user.total_xp)

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
    

    
    # ── Тянем wellness этим же юзером + upsert в БД (не зависит от активностей) ──
    sleep_by_date: dict = {}
    wellness_upserted = 0
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
            score = _parse_w_float(row.get("sleepScore") if row.get("sleepScore") is not None else row.get("sleep_score"))
            hrv = _parse_w_float(row.get("hrv"))
            resting = _parse_w_int(row.get("restingHR") if row.get("restingHR") is not None else row.get("resting_hr"))
            ctl = _parse_w_float(row.get("ctl"))
            atl = _parse_w_float(row.get("atl"))
            existing_w = (
                db.query(Wellness)
                .filter(Wellness.user_id == current.id, Wellness.date == date_str)
                .first()
            )
            if existing_w:
                # upsert: повторный синк ОБНОВЛЯЕТ, а не дублирует
                if secs is not None:
                    existing_w.sleep_secs = secs
                if score is not None:
                    existing_w.sleep_score = score
                if hrv is not None:
                    existing_w.hrv = hrv
                if resting is not None:
                    existing_w.resting_hr = resting
                if ctl is not None:
                    existing_w.ctl = ctl
                if atl is not None:
                    existing_w.atl = atl
            else:
                db.add(Wellness(
                    user_id=current.id,
                    date=date_str,
                    sleep_secs=secs,
                    sleep_score=score,
                    hrv=hrv,
                    resting_hr=resting,
                    ctl=ctl,
                    atl=atl,
                ))
            wellness_upserted += 1
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"⚠️ Wellness skip: {type(e).__name__}: {e}")
    
    # ── Нет новых тренировок: сон всё равно обновился → пересчитываем ──
    if not activities_data:
        total_before = float(current.total_xp or 0)
    if get_settings().XP_ENGINE == "v6":
        _recalculate_user_xp_v6(db, current)
    else:
        _recalculate_user_xp(db, current)
        db.commit()
        db.refresh(current)
        return {
            "message": "Новых активностей нет, но сон и восстановление обновлены",
            "synced_count": 0,
            "updated_count": 0,
            "wellness_upserted": wellness_upserted,
            "new_xp": round(float(current.total_xp or 0) - total_before, 2),
        }

    # ── Пишем в БД (upsert: существующие обновляем, новые создаём) ──
    new_xp = 0.0
    synced_count = 0
    updated_count = 0
    skipped_empty = 0
    seen_ids: set[str] = set()
    existing_rows = {
        row.intervals_activity_id: row
        for row in db.query(Activity).filter(Activity.user_id == current.id).all()
    }
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
        if not _has_real_data(parsed):
            skipped_empty += 1
            continue
        act_date = parsed["start_date"].strftime("%Y-%m-%d")
        sleep_secs = sleep_by_date.get(act_date)
        if sleep_secs is None:
            prev = (parsed["start_date"] - timedelta(days=1)).strftime("%Y-%m-%d")
            sleep_secs = sleep_by_date.get(prev)
        if act_id in existing_rows:
            # UPSERT: Intervals досылает TSS/пульс/сон ПОЗЖЕ самой тренировки
            row = existing_rows[act_id]
            changed = False
            for field, value in (
                ("training_load", parsed.get("training_load") or 0),
                ("intensity", parsed.get("intensity") or 0),
                ("moving_time", parsed.get("moving_time") or 0),
                ("average_heartrate", parsed.get("average_heartrate") or 0),
                ("distance", parsed.get("distance") or 0),
                ("elevation_gain", parsed.get("elevation_gain") or 0),
            ):
                old = getattr(row, field) or 0
                if value and abs(old - value) > 1e-6:
                    setattr(row, field, value)
                    changed = True
            if sleep_secs and (row.sleep_secs or 0) != sleep_secs:
                row.sleep_secs = sleep_secs
                changed = True
            if changed:
                updated_count += 1
            continue
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
        existing_rows[act_id] = new_activity
        synced_count += 1
        dist_km = parsed["distance"] / 1000 if parsed["distance"] else 0
        print(
            f"✅ {parsed['name']} | {parsed['sport_type']} | "
            f"{dist_km:.1f}km | {parsed['moving_time'] // 60} мин"
        )
    db.commit()


    total_before = float(current.total_xp or 0)
    if get_settings().XP_ENGINE == "v6":
        _recalculate_user_xp_v6(db, current)
    else:
        _recalculate_user_xp(db, current)
    db.commit()
    db.refresh(current)
    new_xp = round(float(current.total_xp or 0) - total_before, 2)

    return {
        "message": "Синхронизация успешна!",
        "synced_count": synced_count,
        "updated_count": updated_count,
        "wellness_upserted": wellness_upserted,
        "skipped_empty": skipped_empty,
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
    
    from ..models import WeeklySummary, XPEvent
    db.query(XPEvent).filter(XPEvent.user_id == current.id).delete(synchronize_session=False)
    db.query(WeeklySummary).filter(WeeklySummary.user_id == current.id).delete(synchronize_session=False)
    current.legacy_xp_offset = 0.0
    current.xp_migrated_at = None
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


@router.get("/users/{username}")
async def public_profile(
    username: str,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_optional_bearer),
    db: Session = Depends(get_db),
):
    """Публичный профиль атлета (без приватных данных)."""
    user = db.query(User).filter(User.username == username.lower().strip()).first()
    if not user:
        raise HTTPException(status_code=404, detail="Athlete not found")

    viewer: Optional[User] = None
    if credentials is not None:
        uid = decode_access_token(credentials.credentials)
        if uid is not None:
            viewer = db.get(User, uid)

    all_acts = db.query(Activity).filter(Activity.user_id == user.id).all()

    # отношения со зрителем
    relation = None
    friendship_id = None
    if viewer and viewer.id != user.id:
        rel = (
            db.query(Friendship)
            .filter(
                or_(
                    and_(Friendship.from_user_id == viewer.id, Friendship.to_user_id == user.id),
                    and_(Friendship.from_user_id == user.id, Friendship.to_user_id == viewer.id),
                )
            )
            .first()
        )
        if rel:
            friendship_id = rel.id
            if rel.status == FriendshipStatus.ACCEPTED:
                relation = "friends"
            elif rel.from_user_id == viewer.id:
                relation = "sent"
            else:
                relation = "incoming"

    friends_count = (
        db.query(Friendship)
        .filter(
            or_(Friendship.from_user_id == user.id, Friendship.to_user_id == user.id),
            Friendship.status == FriendshipStatus.ACCEPTED,
        )
        .count()
    )

    # сезонная статистика
    SEASON_START = datetime(2026, 9, 1)
    season_acts = [a for a in all_acts if a.start_date and a.start_date >= SEASON_START]
    season_stats = {
        "season_start": SEASON_START.strftime("%d.%m.%Y"),
        "total_km": round(sum(a.distance or 0 for a in season_acts) / 1000, 1),
        "total_hours": round(sum(a.moving_time or 0 for a in season_acts) / 3600, 1),
        "total_elevation": int(round(sum(a.elevation_gain or 0 for a in season_acts))),
        "total_workouts": len(season_acts),
        "total_xp": round(sum(a.xp_earned or 0 for a in season_acts)),
    }

    # средний пульс за 30 дней
    month_ago = datetime.utcnow() - timedelta(days=30)
    hr_points = [
        {"date": a.start_date.strftime("%d.%m"), "hr": round(a.average_heartrate, 1)}
        for a in sorted(all_acts, key=lambda x: x.start_date or datetime.min)
        if a.start_date and a.start_date >= month_ago and (a.average_heartrate or 0) > 0
    ]

    return {
        "user": {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "level": user.level,
            "total_xp": round(float(user.total_xp or 0), 2),
            "friends_count": friends_count,
            "is_you": viewer is not None and viewer.id == user.id,
            "relation": relation,
            "friendship_id": friendship_id,
        },
        "season_stats": season_stats,
        "hr_last_month": hr_points,
    }


@router.get("/users/{username}/activities")
async def public_activities(
    username: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """Тренировки атлета с пагинацией (публично)."""
    user = db.query(User).filter(User.username == username.lower().strip()).first()
    if not user:
        raise HTTPException(status_code=404, detail="Athlete not found")

    total = db.query(Activity).filter(Activity.user_id == user.id).count()
    acts = (
        db.query(Activity)
        .filter(Activity.user_id == user.id)
        .order_by(Activity.start_date.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {
        "total": total,
        "has_more": offset + len(acts) < total,
        "activities": [
            {
                "id": a.id,
                "name": a.name,
                "sport": a.sport_type,
                "distance_km": round((a.distance or 0) / 1000, 2),
                "moving_time_min": (a.moving_time or 0) // 60,
                "xp": a.xp_earned,
                "base_xp": a.base_xp or 0,
                "rate_per_hour": a.rate_per_hour or 0,
                "intensity_multiplier": a.intensity_multiplier or 1.0,
                "intensity_category": a.intensity_category or "UNKNOWN",
                "intensity_reason": a.intensity_reason or "",
                "sleep_multiplier": a.sleep_multiplier or 1.0,
                "sleep_hours": round(a.sleep_secs / 3600, 1) if a.sleep_secs else None,
                "streak_multiplier": a.streak_multiplier or 1.0,
                "streak_reason": a.streak_reason or "",
                "date": a.start_date.strftime("%d.%m.%Y") if a.start_date else "—",
            }
            for a in acts
        ],
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


