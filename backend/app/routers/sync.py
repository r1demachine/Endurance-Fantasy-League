from fastapi import APIRouter, Depends, HTTPException, Query, Request
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, func
from ..dependencies import get_current_user, require_privacy_consent
from ..auth import decrypt_secret, decode_access_token_claims
from ..database import get_db, SessionLocal
from ..models import User, Activity, Wellness, Friendship, FriendshipStatus, WeeklySummary, XPEvent, LeagueWeek, LeagueMembership, SyncProgress
import asyncio
from collections import defaultdict
from ..services.xp import recalculate_timeline, level_from_xp, round_xp
from datetime import date as _date
from ..services.intervals import calculate_xp, _month_ranges
from ..config import get_settings
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Optional

from ..rate_limit import limiter

router = APIRouter(prefix="/api", tags=["Sync"])
settings = get_settings()
_optional_bearer = HTTPBearer(auto_error=False)

def _user_local_today(user: User | None) -> _date:
    """Current calendar date in the user's configured IANA timezone."""
    try:
        zone = ZoneInfo(getattr(user, "timezone_name", None) or "UTC")
    except (ZoneInfoNotFoundError, TypeError, ValueError):
        zone = ZoneInfo("UTC")
    return datetime.now(timezone.utc).astimezone(zone).date()


def _parse_activity(act: dict, timezone_name: str | None = "UTC") -> dict | None:
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

    raw_start_utc = act.get("start_date") or act.get("startDate")
    raw_start_local = act.get("start_date_local") or act.get("startDateLocal")

    try:
        zone = ZoneInfo(timezone_name or "UTC")
    except (ZoneInfoNotFoundError, TypeError, ValueError):
        zone = ZoneInfo("UTC")

    def _dt(value):
        if isinstance(value, datetime):
            return value
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None

    utc_value = _dt(raw_start_utc)
    local_value = _dt(raw_start_local)
    if utc_value is not None:
        if utc_value.tzinfo is None:
            start_date = utc_value
            utc_aware = utc_value.replace(tzinfo=timezone.utc)
        else:
            utc_aware = utc_value.astimezone(timezone.utc)
            start_date = utc_aware.replace(tzinfo=None)
        if local_value is not None:
            start_date_local = local_value.replace(tzinfo=None)
        else:
            start_date_local = utc_aware.astimezone(zone).replace(tzinfo=None)
    elif local_value is not None:
        if local_value.tzinfo is None:
            start_date_local = local_value
            start_date = local_value.replace(tzinfo=zone).astimezone(timezone.utc).replace(tzinfo=None)
        else:
            start_date_local = local_value.replace(tzinfo=None)
            start_date = local_value.astimezone(timezone.utc).replace(tzinfo=None)
    else:
        start_date = datetime.utcnow()
        start_date_local = start_date.replace(tzinfo=timezone.utc).astimezone(zone).replace(tzinfo=None)

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
        "start_date_local": start_date_local,
        "is_manual": _detect_manual(act),
        "is_indoor": any(_as_bool(act.get(k)) for k in ("trainer", "is_indoor", "indoor")),
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

def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value or "").strip().lower() in {"true", "1", "yes", "y", "on"}


def _detect_manual(raw: dict) -> bool:
    """Определяет ручную запись по явным полям payload Intervals."""
    src = str(raw.get("source") or raw.get("icu_source") or "").strip().lower()
    if src in {"manual", "manually", "entered", "manual entry"}:
        return True

    # Поддерживаем оба варианта флага, включая строковые значения из JSON/CSV.
    for key in ("is_manual", "manual"):
        value = raw.get(key)
        if value is True or value == 1:
            return True
        if isinstance(value, str) and value.strip().lower() in {"true", "1", "yes"}:
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
        d = (a.start_date_local or a.start_date).date() if (a.start_date_local or a.start_date) else _date.today()
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


def _recalculate_user_xp_v6(db: Session, user: User, *, allow_week_notifications: bool = False) -> None:
    """XP v6: аддитивный пересчёт всей истории + upsert XPEvent/WeeklySummary.

    Недели: ВСЕ календарные недели от первой активности до текущей, нулевые тоже —
    иначе после перерыва база цели остаётся докризисной и возвращающегося наказывают.
    Производительность: медианы по спорту считаются один раз (O(n log n)),
    события загружаются одним запросом и апсертятся из памяти.
    """
    from ..models import WeeklySummary, XPEvent
    from ..services import xp_v6 as X6

    acts = (db.query(Activity)
            .filter(Activity.user_id == user.id)
            .order_by(Activity.start_date.asc(), Activity.id.asc())
            .all())

    # 1) нагрузка каждой активности + источник + гашение legacy-полей
    for a in acts:
        tss, source = X6.resolve_training_load({
            "training_load": a.training_load, "moving_time": a.moving_time,
            "intensity": a.intensity, "sport_type": a.sport_type,
            "is_manual": bool(a.is_manual), "source": getattr(a, "source", None),
        })
        a.tss = round(tss, 2)
        # HR-derived TSS from uploaded files is useful for effort XP, but remains an estimate.
        a.tss_estimated = (source == "estimated") or (getattr(a, "source", None) in {"UPLOAD_SITE", "UPLOAD_TELEGRAM"})
        a.base_xp = None
        a.rate_per_hour = None
        a.sleep_multiplier = None
        a.intensity_multiplier = None
        a.streak_multiplier = None

    hist = [{"id": a.id, "sport_type": a.sport_type, "moving_time": a.moving_time} for a in acts]

    by_day: dict[_date, list] = defaultdict(list)
    for a in acts:
        by_day[(a.start_date_local or a.start_date).date() if (a.start_date_local or a.start_date) else _date.today()].append(a)

    # медианы по спорту — один раз
    sorted_by_sport: dict[str, list[float]] = {}
    for a in acts:
        sorted_by_sport.setdefault(str(a.sport_type or "").upper(), []).append(float(a.moving_time or 0))
    for v in sorted_by_sport.values():
        v.sort()

    # 2) дни: effort, распределение долей, qualifying, is_long
    day_info: dict[_date, dict] = {}
    for d, day_acts in by_day.items():
        tss_day = sum(a.tss or 0 for a in day_acts)
        day_xp = X6.effort_xp_day(tss_day)
        shares = X6.allocate_daily_effort_xp([{"tss": a.tss} for a in day_acts], day_xp)
        for a, share in zip(day_acts, shares):
            a.xp_earned = share
            sport_key = str(a.sport_type or "").upper()
            med = X6.median_excluding_sorted(sorted_by_sport.get(sport_key, []), float(a.moving_time or 0))
            a.is_long = bool(med and (a.moving_time or 0) >= med * X6.LONG_WORKOUT_MEDIAN_MULTIPLIER)
        day_info[d] = {
            "acts": day_acts, "tss": tss_day, "day_xp": day_xp,
            "qualifying": X6.is_qualifying_day([{"moving_time": a.moving_time} for a in day_acts], tss_day),
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

    # 4) ВСЕ календарные недели, включая нулевые (справедливо после перерыва)
    this_week = X6.week_start(_user_local_today(user))
    if day_info:
        first_week = min(X6.week_start(d) for d in day_info)
        all_weeks: list[_date] = []
        w = first_week
        while w <= this_week:
            all_weeks.append(w)
            w += timedelta(days=7)
    else:
        all_weeks = [this_week]

    week_load = {ws: 0.0 for ws in all_weeks}
    week_days = {ws: 0 for ws in all_weeks}
    for d, info in day_info.items():
        ws = X6.week_start(d)
        week_load[ws] += info["tss"]
        if info["qualifying"]:
            week_days[ws] += 1

    scores_by_week: dict[_date, list] = defaultdict(list)
    for wrow in db.query(Wellness).filter(Wellness.user_id == user.id).all():
        if wrow.date and wrow.sleep_score:
            try:
                scores_by_week[X6.week_start(datetime.fromisoformat(wrow.date).date())].append(float(wrow.sleep_score))
            except Exception:
                continue

    # события: один запрос, апсерт из памяти (без N+1)
    from ..services import quests as Q
    summaries_all = (
        db.query(WeeklySummary)
        .filter(WeeklySummary.user_id == user.id)
        .order_by(WeeklySummary.week_start.asc())
        .all()
    )
    Q.grant_quests(db, user, acts, summaries_all)
    all_events = db.query(XPEvent).filter(XPEvent.user_id == user.id).all()
    events_by_key = {e.event_key: e for e in all_events}
    quest_by_week: dict = {}
    for e in all_events:
        if e.event_type in ("quest", "achievement"):
            quest_by_week[e.week_start] = quest_by_week.get(e.week_start, 0.0) + e.amount

    generated_quality_consistency_keys: set[str] = set()

    def upsert_event(key, etype, amount, ws, dt, title):
        ev = events_by_key.get(key)
        if amount <= 0:
            if ev is not None and ev.id is not None:
                db.delete(ev)
                events_by_key.pop(key, None)
            return
        if etype in {"consistency", "quality_hard", "quality_long"}:
            generated_quality_consistency_keys.add(key)
        if ev is not None:
            ev.amount = round_xp(amount)
            ev.title = title
        else:
            ev = XPEvent(
                user_id=user.id,
                week_start=datetime.combine(ws, datetime.min.time()),
                date=datetime.combine(dt, datetime.min.time()),
                event_type=etype, event_key=key,
                amount=round_xp(amount), source_type="week", title=title,
            )
            db.add(ev)
            events_by_key[key] = ev

    medians = X6.medians_by_sport(hist, set())

    # 5) недели: сводки + недельные события
    for ws in all_weeks:
        finalized = ws < this_week
        prior = [p for p in all_weeks if p < ws]
        paused = _is_paused_week(user, ws)
        # паузы исключаются из базы цели: болезнь не повышает будущую норму
        prior_loads = [week_load[p] for p in prior if not _is_paused_week(user, p)]
        baseline = X6.weekly_baseline(prior_loads)
        target = baseline or X6.starter_target()
        ratio = (week_load[ws] / target) if target else 0.0
        deload = (not paused) and X6.is_deload_week(
            week_load[ws], baseline or 0.0, [week_load[p] for p in prior]
        )
        eff_ratio = max(ratio, X6.DELOAD_GOAL_FLOOR) if deload else ratio
        days = week_days[ws]
        t_days = X6.target_training_days([week_days[p] for p in prior])

        if ws >= activation_ws:
            for d, info in day_info.items():
                if X6.week_start(d) == ws and info["qualifying"]:
                    upsert_event(f"consistency:{d.isoformat()}", "consistency",
                                 X6.CONSISTENCY_XP_PER_DAY, ws, d, "Training day +30")

        quality_xp = 0.0
        if ws >= activation_ws:
            day_dicts = {
                d: [{
                    "moving_time": a.moving_time, "intensity": a.intensity, "hard_secs": a.hard_secs or 0,
                    "load_source": "estimated" if a.tss_estimated else "real",
                    "sport_type": a.sport_type, "id": a.id,
                } for a in info["acts"]]
                for d, info in day_info.items() if X6.week_start(d) == ws
            }
            for kind, amt in X6.quality_events_week(day_dicts, medians):
                upsert_event(f"{kind}:{ws.isoformat()}", kind, amt, ws, ws,
                             "High intensity +15" if kind == "quality_hard" else "Long workout +15")
                quality_xp += amt

        goal_xp = 0.0
        recovery = 0.0
        if finalized and ws >= activation_ws:
            goal_xp = X6.weekly_goal_xp(ratio)
            upsert_event(f"weekly_goal:{ws.isoformat()}", "weekly_goal", goal_xp, ws, ws,
                         f"Weekly goal {int(ratio * 100)}%")
            recovery = X6.recovery_xp_week(scores_by_week.get(ws, []))
            upsert_event(f"recovery:{ws.isoformat()}", "recovery", recovery, ws, ws,
                         "Recovery (sleep score)")

        quest_xp = round_xp(quest_by_week.get(datetime.combine(ws, datetime.min.time()), 0.0))
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
        summ.league_score = None if paused else X6.league_score(eff_ratio, days, t_days, quality_xp)
        summ.is_deload = bool(deload)
        summ.paused = bool(paused)
        summ.finalized = finalized

    # Remove regularity/quality events that no longer correspond to the current
    # activity history (for example, an Intervals update makes a workout
    # non-qualifying). Only v6-generated event types are reconciled here.
    for event in all_events:
        if event.event_type not in {"consistency", "quality_hard", "quality_long"}:
            continue
        event_week = X6.week_start(event.week_start.date()) if event.week_start else None
        if (
            event_week is not None
            and event_week >= activation_ws
            and event.event_key not in generated_quality_consistency_keys
        ):
            db.delete(event)
            events_by_key.pop(event.event_key, None)

    # 6) lиги: финализация идемпотентна; повторно обрабатываем незавершённые недели.
    for ws in all_weeks:
        if ws < this_week:
            _close_league_week(db, ws, allow_week_notifications=allow_week_notifications)

    db.flush()
    events_sum = round_xp(sum(e.amount for e in events_by_key.values()))
    acts_sum = round_xp(sum(a.xp_earned or 0 for a in acts))
    user.total_xp = round_xp(float(user.legacy_xp_offset or 0) + acts_sum + events_sum)
    user.level = level_from_xp(user.total_xp)


def _is_paused_week(user: User, ws: _date) -> bool:
    from ..services import xp_v6 as X6
    return (
        user.pause_set_at is not None
        and user.paused_until is not None
        and X6.week_start(user.pause_set_at.date()) <= ws < X6.week_start(user.paused_until.date())
    )


def _division_for_week(db: Session, user: User, week_start_d: _date, week_load: float):
    """Лестница: дивизион липкий. Новые юзеры размещаются по CTL/нагрузке один раз."""
    from ..services import xp_v6 as X6
    if user.division_current:
        return X6.division_name(user.division_current - 1), "ladder"
    div, src = _user_division(db, user, week_start_d, week_load)
    if div:
        user.division_current = X6.DIVISION_NAMES.index(div) + 1
        user.division_placed_at = datetime.utcnow()
        return div, src
    return None, "provisional"

def _user_division(db: Session, user: User, week_start_d: _date, week_load: float):
    """(division, source): CTL первичен; нет CTL → fallback по 12 неделям нагрузки;
    мало истории → provisional (без фиктивного дивизиона)."""
    from ..services import xp_v6 as X6
    week_end = week_start_d + timedelta(days=7)
    ctl_rows = (
        db.query(Wellness.ctl)
        .filter(Wellness.user_id == user.id,
                Wellness.date >= week_start_d.isoformat(),
                Wellness.date < week_end.isoformat())
        .all()
    )
    ctls = [float(r[0]) for r in ctl_rows if r[0] is not None and float(r[0]) > 0]
    if ctls:
        return X6.division_name(X6.division_index_from_ctl(sum(ctls) / len(ctls))), "ctl"
    finalized_count = (
        db.query(WeeklySummary)
        .filter(WeeklySummary.user_id == user.id, WeeklySummary.finalized == True)  # noqa: E712
        .count()
    )
    if finalized_count >= 3:
        recent = (
            db.query(WeeklySummary.actual_load)
            .filter(WeeklySummary.user_id == user.id, WeeklySummary.finalized == True)  # noqa: E712
            .order_by(WeeklySummary.week_start.desc())
            .limit(12)
            .all()
        )
        avg12 = sum(r[0] or 0 for r in recent) / len(recent)
        return X6.division_name(X6.division_index_from_load(avg12)), "load_fallback"
    return None, "provisional"


def _close_league_week(
    db: Session,
    week_start_d: _date,
    *,
    allow_week_notifications: bool = False,
) -> bool:
    """Close a league once; return True only when a real league was formed."""
    from ..services import xp_v6 as X6
    from ..models import LeagueWeek, LeagueMembership

    ws_dt = datetime.combine(week_start_d, datetime.min.time())
    existing_week = db.query(LeagueWeek).filter(LeagueWeek.week_start == ws_dt).first()
    if existing_week:
        # Retry idempotent side effects for a week whose league row was already
        # committed before duel finalization or Telegram delivery failed.
        try:
            from ..models import Duel
            has_open_duels = db.query(Duel.id).filter(
                Duel.week_start == ws_dt,
                Duel.status.in_(["pending", "active"]),
            ).first() is not None
            if has_open_duels:
                from .duels import finalize_duels_for_week
                finalize_duels_for_week(db, week_start_d)
        except Exception as exc:  # noqa: BLE001
            print(f"finalize_duels_for_week retry failed: {type(exc).__name__}")
        try:
            from ..services.telegram_week import notify_week_results
            notify_week_results(db, week_start_d)
        except Exception as exc:  # noqa: BLE001
            print(f"telegram week notify retry failed: {type(exc).__name__}")
        return existing_week.status == "closed"
    summaries = (
        db.query(WeeklySummary)
        .filter(WeeklySummary.week_start == ws_dt, WeeklySummary.finalized == True)  # noqa: E712
        .all()
    )
    if not summaries:
        return False

    entries = []
    for summary in summaries:
        user = db.get(User, summary.user_id)
        if not user or _is_paused_week(user, week_start_d):
            continue
        division, source = _division_for_week(db, user, week_start_d, summary.actual_load or 0)
        entries.append({
            "user": user, "summ": summary, "div": division,
            "source": source, "score": summary.league_score or 0,
        })

    formed = len(entries) >= X6.MIN_LEAGUE_SIZE
    db.add(LeagueWeek(week_start=ws_dt, status="closed" if formed else "not_formed"))

    if entries:
        groups: dict = {}
        for entry in entries:
            groups.setdefault(entry["div"] or "Open", []).append(entry)
        order = list(X6.DIVISION_NAMES) + ["Open"]
        keys = [key for key in order if key in groups] + [key for key in groups if key not in order]
        merged = []
        for key in keys:
            if merged and len(merged[-1][1]) < X6.MIN_LEAGUE_SIZE:
                merged[-1][0].append(key)
                merged[-1][1].extend(groups[key])
            else:
                merged.append(([key], list(groups[key])))
        if len(merged) > 1 and len(merged[-1][1]) < X6.MIN_LEAGUE_SIZE:
            merged[-2][0].extend(merged[-1][0])
            merged[-2][1].extend(merged[-1][1])
            merged.pop()

        for group_keys, members in merged:
            members.sort(key=lambda entry: (-entry["score"], entry["user"].id))
            count = len(members)
            zone = X6.PROMOTION_ZONE if formed and count >= 2 * X6.PROMOTION_ZONE else 0
            for index, entry in enumerate(members):
                user = entry["user"]
                protected = False
                if user.xp_migrated_at:
                    weeks_since = (week_start_d - X6.week_start(user.xp_migrated_at.date())).days // 7
                    protected = weeks_since < X6.NEWCOMER_PROTECTION_WEEKS
                promoted = bool(zone) and index < zone
                demoted = bool(zone) and index >= count - zone and not protected
                if promoted and user.division_current:
                    user.division_current = min(user.division_current + 1, len(X6.DIVISION_NAMES))
                elif demoted and user.division_current:
                    user.division_current = max(user.division_current - 1, 1)
                db.add(LeagueMembership(
                    week_start=ws_dt, user_id=user.id, division=entry["div"],
                    division_source=entry["source"], league_score=round(entry["score"], 2),
                    rank=index + 1, group_key="+".join(group_keys), promoted=promoted,
                    demoted=demoted, protected=protected,
                ))
                entry["summ"].division = entry["div"]
                entry["summ"].division_source = entry["source"]

    db.commit()

    # Finalize duels even if the league itself did not meet the minimum size.
    try:
        from .duels import finalize_duels_for_week
        finalize_duels_for_week(db, week_start_d)
    except Exception as exc:  # noqa: BLE001
        print(f"finalize_duels_for_week failed: {type(exc).__name__}")

    try:
        from ..services.telegram_week import notify_week_results
        notify_week_results(db, week_start_d)
    except Exception as exc:  # noqa: BLE001
        print(f"telegram week notify failed: {type(exc).__name__}")

    return bool(formed)

def _has_invalid_since_query(errors: list[dict]) -> bool:
    """Identify malformed since query parameters for the route's HTTP 400 contract."""
    return any(
        len(error.get("loc", ())) >= 2
        and error["loc"][0] == "query"
        and error["loc"][1] == "since"
        for error in errors
    )


_SYNC_PROGRESS_STALE_AFTER = timedelta(minutes=15)


def _progress_payload(row: SyncProgress | None) -> dict:
    if row is None:
        return {
            "active": False, "status": "idle", "phase": "idle",
            "months_done": 0, "months_total": 0, "current_month": None, "message": None,
        }
    return {
        "active": bool(row.active),
        "status": row.status,
        "phase": row.phase,
        "months_done": int(row.months_done or 0),
        "months_total": int(row.months_total or 0),
        "current_month": row.current_month,
        "message": row.message,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _claim_sync_progress_in_worker(user_id: int, months_total: int) -> bool:
    """Claim a sync using an independent DB session in the threadpool."""
    session = SessionLocal()
    try:
        return _claim_sync_progress(session, user_id, months_total)
    finally:
        session.close()


def _has_prior_intervals_activity(user_id: int) -> bool:
    """Perform this sync eligibility query outside the async event loop."""
    session = SessionLocal()
    try:
        return session.query(Activity.id).filter(
            Activity.user_id == user_id,
            Activity.source == "INTERVALS",
        ).first() is not None
    finally:
        session.close()


def _claim_sync_progress(db: Session, user_id: int, months_total: int) -> bool:
    """Serialize syncs per user across app workers by locking the existing User row."""
    try:
        db.query(User.id).filter(User.id == user_id).with_for_update().one()
        row = db.query(SyncProgress).filter(SyncProgress.user_id == user_id).first()
        now = datetime.utcnow()
        if row is not None and row.active:
            last_update = row.updated_at or now
            if now - last_update < _SYNC_PROGRESS_STALE_AFTER:
                db.rollback()
                return False
            row.status = "interrupted"
            row.active = False
        if row is None:
            row = SyncProgress(user_id=user_id)
            db.add(row)
        row.active = True
        row.status = "running"
        row.phase = "activities"
        row.months_done = 0
        row.months_total = months_total
        row.current_month = None
        row.message = None
        row.updated_at = now
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise


def _write_sync_progress(user_id: int, values: dict) -> None:
    """Persist progress through an independent short-lived session."""
    session = SessionLocal()
    try:
        row = session.query(SyncProgress).filter(SyncProgress.user_id == user_id).first()
        if row is None:
            row = SyncProgress(user_id=user_id)
            session.add(row)
        for key, value in values.items():
            setattr(row, key, value)
        row.updated_at = datetime.utcnow()
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@router.get("/sync/progress")
def get_sync_progress(
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = db.query(SyncProgress).filter(SyncProgress.user_id == current.id).first()
    if row is not None and row.active and row.updated_at:
        if datetime.utcnow() - row.updated_at >= _SYNC_PROGRESS_STALE_AFTER:
            row.active = False
            row.status = "interrupted"
            row.phase = "interrupted"
            row.current_month = None
            row.message = "Синхронизация прервана, запусти её повторно."
            row.updated_at = datetime.utcnow()
            db.commit()
    return _progress_payload(row)

def _persist_sync_payload(
    user_id: int,
    activities_data: list[dict],
    wellness_data: list[dict],
    allow_week_notifications: bool,
    full_sync: bool,
    months_total: int,
) -> dict:
    """Persist downloaded Intervals data and recalculate XP in a worker thread."""
    db = SessionLocal()
    try:
        current = db.query(User).filter(User.id == user_id).first()
        if current is None:
            raise RuntimeError("Пользователь синхронизации больше не существует.")
        # ── Тянем wellness этим же юзером + upsert в БД (не зависит от активностей) ──
        sleep_by_date: dict = {}
        wellness_upserted = 0
        try:
            wellness_records = wellness_data
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
            print(f"⚠️ Wellness sync skipped ({type(e).__name__})")
        
        # ── Нет новых тренировок: сон всё равно обновился → пересчитываем ──
        if not activities_data:
            if get_settings().XP_ENGINE == "v6":
                _recalculate_user_xp_v6(db, current, allow_week_notifications=allow_week_notifications)
            else:
                _recalculate_user_xp(db, current)
            if full_sync:
                current.last_full_sync_at = datetime.utcnow()
            db.commit()
            db.refresh(current)
            return {
                "message": "Новых активностей нет, но сон и восстановление обновлены",
                "synced_count": 0,
                "updated_count": 0,
                "wellness_upserted": wellness_upserted,
                "months_done": months_total, "months_total": months_total,
                "new_xp": 0,
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
        merged_upload_count = 0
        for raw in activities_data:
            if not isinstance(raw, dict):
                continue
            parsed = _parse_activity(raw, current.timezone_name)
            if not parsed:
                continue
            act_id = parsed["intervals_activity_id"]
            if act_id in seen_ids:
                continue
            seen_ids.add(act_id)
            if not _has_real_data(parsed):
                skipped_empty += 1
                continue
            act_date = (parsed.get("start_date_local") or parsed["start_date"]).strftime("%Y-%m-%d")
            sleep_secs = sleep_by_date.get(act_date)
            if sleep_secs is None:
                prev = ((parsed.get("start_date_local") or parsed["start_date"]) - timedelta(days=1)).strftime("%Y-%m-%d")
                sleep_secs = sleep_by_date.get(prev)
            from ..services.activity_dedupe import remove_matching_upload_duplicate
            uploaded_match = remove_matching_upload_duplicate(
                db,
                current.id,
                parsed["start_date"],
                parsed.get("start_date_local"),
                int(parsed.get("moving_time") or 0),
            )
            if uploaded_match is not None:
                existing_rows.pop(uploaded_match.intervals_activity_id, None)
                merged_upload_count += 1
    
            if act_id in existing_rows:
                # UPSERT: Intervals досылает TSS/пульс/сон ПОЗЖЕ самой тренировки
                row = existing_rows[act_id]
                changed = False
                if bool(parsed.get("is_manual")) != bool(row.is_manual):
                    row.is_manual = bool(parsed.get("is_manual"))
                    changed = True
                is_indoor = bool(parsed.get("is_indoor"))
                if bool(getattr(row, "is_indoor", False)) != is_indoor:
                    row.is_indoor = is_indoor
                    changed = True
                if bool(row.indoor) != is_indoor:
                    row.indoor = is_indoor
                    changed = True
                if parsed.get("start_date_local") is not None and row.start_date_local != parsed["start_date_local"]:
                    row.start_date_local = parsed["start_date_local"]
                    changed = True
                if row.start_date != parsed["start_date"]:
                    row.start_date = parsed["start_date"]
                    changed = True
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
                start_date_local=parsed.get("start_date_local") or parsed["start_date"],
                is_manual=bool(parsed.get("is_manual", False)),
                indoor=bool(parsed.get("is_indoor", False)),
                is_indoor=bool(parsed.get("is_indoor", False)),
            )
            db.add(new_activity)
            existing_rows[act_id] = new_activity
            synced_count += 1
            dist_km = parsed["distance"] / 1000 if parsed["distance"] else 0
            # Do not write private workout names, distances, durations or health data to logs.
            print("✅ Activity synchronized")
        db.commit()
    
    
        # Не удаляем активности только потому, что их нет в текущем ответе Intervals.
        # API-синхронизация использует ограниченное окно истории (обычно 90 дней), поэтому
        # старые активности закономерно отсутствуют в payload. Удаление выполняется явными
        # пользовательскими действиями (disconnect/account deletion), не этим sync.
        deleted_count = merged_upload_count
        db.commit()
    
        total_before = float(current.total_xp or 0)
        if get_settings().XP_ENGINE == "v6":
            _recalculate_user_xp_v6(db, current, allow_week_notifications=allow_week_notifications)
        else:
            _recalculate_user_xp(db, current)
        if full_sync:
            current.last_full_sync_at = datetime.utcnow()
        db.commit()
        db.refresh(current)
        new_xp = round(float(current.total_xp or 0) - total_before, 2)
    
        return {
            "message": "Синхронизация успешна!",
            "synced_count": synced_count,
            "updated_count": updated_count,
            "deleted_count": deleted_count,
            "wellness_upserted": wellness_upserted,
            "months_done": months_total, "months_total": months_total,
            "skipped_empty": skipped_empty,
            "new_xp": new_xp,
            "user": {
                "id": current.id,
                "name": current.display_name,
                "level": current.level,
                "total_xp": round(float(current.total_xp or 0), 2),
            },
        }
    
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _earliest_sync_date(today: _date) -> _date:
    """First day of the earliest month in an inclusive 24-calendar-month window."""
    month_index = today.year * 12 + (today.month - 1) - 23
    year, month_zero_based = divmod(month_index, 12)
    return _date(year, month_zero_based + 1, 1)


@router.post("/sync")
@limiter.limit("3/minute")
async def sync_activities(
    request: Request,
    since: _date | None = Query(default=None),
    current: User = Depends(require_privacy_consent),
    db: Session = Depends(get_db),
):
    """Async Intervals download; synchronous persistence and XP run in a worker thread."""
    if "oldest" in request.query_params or "newest" in request.query_params:
        raise HTTPException(
            status_code=400,
            detail="Параметры oldest/newest больше не поддерживаются. Используй since=YYYY-MM-DD.",
        )
    if not current.api_key_encrypted or not current.intervals_id:
        raise HTTPException(status_code=400, detail="Сначала привяжи Intervals.icu в профиле")

    try:
        api_key = decrypt_secret(current.api_key_encrypted)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Не удалось расшифровать ключ. Подключи заново.") from exc

    user_id = current.id
    athlete_id = current.intervals_id
    today = _user_local_today(current)
    start_date = since or (today - timedelta(days=90))
    end_date = today

    if since is not None:
        earliest = _earliest_sync_date(today)
        if since < earliest:
            raise HTTPException(
                status_code=400,
                detail=f"За один запрос можно импортировать не более 24 календарных месяцев (начиная с {earliest.isoformat()}).",
            )
        if since > today:
            raise HTTPException(status_code=400, detail="Дата начала не может быть в будущем")

    if start_date > end_date:
        raise HTTPException(status_code=400, detail="Дата начала не может быть позже текущей даты")
    month_ranges = _month_ranges(start_date, end_date)
    if len(month_ranges) > 24:
        raise HTTPException(status_code=400, detail="За один запрос разрешено не более 24 календарных месяцев.")

    full_sync = since is not None
    if full_sync:
        last_sync = current.last_full_sync_at
        now = datetime.utcnow()
        if last_sync and now - last_sync < timedelta(hours=1):
            remaining = int((timedelta(hours=1) - (now - last_sync)).total_seconds())
            raise HTTPException(
                status_code=429,
                detail=f"Полный импорт доступен не чаще одного раза в час. Повтори через {max(1, remaining // 60 + 1)} мин.",
            )

    claimed = await run_in_threadpool(
        _claim_sync_progress_in_worker, user_id, len(month_ranges)
    )
    if not claimed:
        raise HTTPException(status_code=409, detail="Синхронизация уже выполняется")

    final_status = "error"
    final_message = "Синхронизация не завершена."
    allow_week_notifications = False

    try:
        # From this point onward every exception passes through the active-reset finally block.
        had_prior_intervals_activity = await run_in_threadpool(
            _has_prior_intervals_activity, user_id
        )
        allow_week_notifications = bool(had_prior_intervals_activity and not full_sync)
        from ..services.intervals import fetch_activities_for_user, fetch_wellness_for_user

        async def report_progress(phase: str, done: int, total: int, month_start: _date) -> None:
            status = "fetching_activities" if phase == "activities" else "fetching_wellness"
            await run_in_threadpool(
                _write_sync_progress,
                user_id,
                {
                    "active": True, "status": status, "phase": phase,
                    "months_done": done, "months_total": total,
                    "current_month": month_start.strftime("%Y-%m"), "message": None,
                },
            )

        await run_in_threadpool(
            _write_sync_progress,
            user_id,
            {
                "active": True, "status": "fetching_activities", "phase": "activities",
                "months_done": 0, "months_total": len(month_ranges),
                "current_month": None, "message": None,
            },
        )

        try:
            activities_data = await fetch_activities_for_user(
                api_key=api_key,
                athlete_id=athlete_id,
                oldest=start_date.isoformat(),
                newest=end_date.isoformat(),
                progress_callback=report_progress,
            )
        except PermissionError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Intervals.icu недоступен: {type(exc).__name__}") from exc

        await run_in_threadpool(
            _write_sync_progress,
            user_id,
            {
                "active": True,
                "status": "fetching_wellness",
                "phase": "wellness",
                "months_done": 0,
                "months_total": len(month_ranges),
                "current_month": None,
                "message": None,
            },
        )

        try:
            wellness_data = await fetch_wellness_for_user(
                api_key=api_key,
                athlete_id=athlete_id,
                oldest=start_date.isoformat(),
                newest=end_date.isoformat(),
                progress_callback=report_progress,
            )
        except Exception as exc:
            print(f"Wellness sync skipped ({type(exc).__name__})")
            wellness_data = []

        await run_in_threadpool(
            _write_sync_progress,
            user_id,
            {
                "active": True, "status": "processing", "phase": "database",
                "months_done": len(month_ranges), "months_total": len(month_ranges),
                "current_month": None, "message": "Сохраняем данные и пересчитываем XP.",
            },
        )

        try:
            result = await run_in_threadpool(
                _persist_sync_payload,
                user_id,
                activities_data,
                wellness_data,
                allow_week_notifications,
                full_sync,
                len(month_ranges),
            )
        except Exception as exc:
            print(f"Sync persistence failed ({type(exc).__name__})")
            raise HTTPException(
                status_code=500,
                detail="Данные получены, но не удалось сохранить синхронизацию. Попробуй ещё раз.",
            ) from exc

        final_status = "complete"
        final_message = "Синхронизация успешна."
        return result
    except HTTPException as exc:
        final_status = "error"
        final_message = str(exc.detail)[:255]
        raise
    finally:
        try:
            await run_in_threadpool(
                _write_sync_progress,
                user_id,
                {
                    "active": False, "status": final_status, "phase": final_status,
                    "current_month": None, "message": final_message,
                },
            )
        except Exception as exc:
            print(f"Could not persist final sync progress ({type(exc).__name__})")




@router.get("/user")
async def get_user_profile(
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    
):
    """Данные ТЕКУЩЕГО пользователя."""
    user = current
    
    activities = db.query(Activity).filter(Activity.user_id == user.id).order_by(Activity.start_date.desc()).limit(40).all()
    all_activities = db.query(Activity).filter(Activity.user_id == user.id).all()
    today = _user_local_today(user)
    
    dates = sorted({(a.start_date_local or a.start_date).date() for a in all_activities if (a.start_date_local or a.start_date)}, reverse=True)
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
    
    weeks = sorted({week_start((a.start_date_local or a.start_date).date()) for a in all_activities if (a.start_date_local or a.start_date)}, reverse=True)
    this_week = week_start(today)
    week_streak = 0
    if weeks and (this_week - weeks[0]).days <= 7:
        week_streak = 1
        for i in range(len(weeks) - 1):
            if (weeks[i] - weeks[i+1]).days == 7:
                week_streak += 1
            else:
                break
    
    week_seconds = sum(a.moving_time or 0 for a in all_activities if (a.start_date_local or a.start_date) and week_start((a.start_date_local or a.start_date).date()) == this_week)
    week_hours = round(week_seconds / 3600, 1)
    
    season_year = today.year if today.month >= 9 else today.year - 1
    SEASON_START = datetime(season_year, 9, 1)
    season_acts = [a for a in all_activities if (a.start_date_local or a.start_date) and (a.start_date_local or a.start_date) >= SEASON_START]
    season_stats = {
        "season_start": SEASON_START.strftime("%d.%m.%Y"),
        "total_km": round(sum(a.distance or 0 for a in season_acts) / 1000, 1),
        "total_hours": round(sum(a.moving_time or 0 for a in season_acts) / 3600, 1),
        "total_elevation": int(round(sum(a.elevation_gain or 0 for a in season_acts))),
        "total_workouts": len(season_acts),
        "total_xp": round(sum(a.xp_earned or 0 for a in season_acts)),
    }

    # ── v6: текущая неделя и лента событий ──
    from ..models import WeeklySummary, XPEvent
    this_week_start = week_start(today)
    current_summary = (
        db.query(WeeklySummary)
        .filter(WeeklySummary.user_id == user.id, WeeklySummary.week_start == datetime.combine(this_week_start, datetime.min.time()))
        .first()
    )
    
    # Если сводки нет (ещё не синхронизировался в v6), создаём заглушку
    if not current_summary:
        from ..services import xp_v6 as X6
        last_summ = (
            db.query(WeeklySummary)
            .filter(WeeklySummary.user_id == user.id)
            .order_by(WeeklySummary.week_start.desc())
            .first()
        )
        fallback_target = (
            round(last_summ.target_load, 1)
            if last_summ and last_summ.target_load
            else X6.starter_target()
        )
        week_data = {
            "actual_load": 0, "target_load": fallback_target, "completion_ratio": 0,
            "training_days": 0, "effort_xp": 0, "goal_xp": 0,
            "consistency_xp": 0, "quality_xp": 0, "recovery_xp": 0,
            "quest_xp": 0, "total_xp": 0, "league_score": 0,
            "state": "no_data", "is_deload": False, "paused": False,
        }
    else:
        week_data = {
            "actual_load": round(current_summary.actual_load or 0, 1),
            "target_load": round(current_summary.target_load or 0, 1),
            "completion_ratio": round((current_summary.completion_ratio or 0) * 100, 1),
            "training_days": current_summary.training_days or 0,
            "effort_xp": round(current_summary.effort_xp or 0, 1),
            "goal_xp": round(current_summary.goal_xp or 0, 1),
            "consistency_xp": round(current_summary.consistency_xp or 0, 1),
            "quality_xp": round(current_summary.quality_xp or 0, 1),
            "recovery_xp": round(current_summary.recovery_xp or 0, 1),
            "quest_xp": round(current_summary.quest_xp or 0, 1),
            "total_xp": round(current_summary.total_xp or 0, 1),
            "league_score": round(current_summary.league_score or 0, 1),
            "state": "ready" if current_summary.finalized else "in_progress",
            "is_deload": bool(current_summary.is_deload),
            "paused": bool(current_summary.paused),
        }

    div, div_src = _user_division(db, user, this_week_start, week_data["actual_load"])
    week_data["division"] = div
    week_data["division_source"] = div_src

    from ..models import LeagueMembership
    last_mem = (
        db.query(LeagueMembership)
        .filter(LeagueMembership.user_id == user.id)
        .order_by(LeagueMembership.week_start.desc())
        .first()
    )
    last_league = None
    if last_mem:
        last_league = {
            "week": last_mem.week_start.strftime("%d.%m"),
            "division": last_mem.division,
            "division_source": last_mem.division_source,
            "rank": last_mem.rank,
            "group": last_mem.group_key,
            "promoted": bool(last_mem.promoted),
            "demoted": bool(last_mem.demoted),
            "protected": bool(last_mem.protected),
        }

    recent_events = (
        db.query(XPEvent)
        .filter(XPEvent.user_id == user.id)
        .order_by(XPEvent.date.desc(), XPEvent.id.desc())
        .limit(10)
        .all()
    )
    
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
            "xp_version": get_settings().XP_ENGINE,
            "privacy_consent_current": bool(user.privacy_consent_version == get_settings().PRIVACY_CONSENT_VERSION and user.privacy_consent_at),
            "pause_set_at": user.pause_set_at.isoformat() if user.pause_set_at else None,
            "paused_until": user.paused_until.isoformat() if user.paused_until else None,
        },
        "stats": {
            "day_streak": day_streak,
            "week_streak": week_streak,
            "week_hours": week_hours,
            "week_goal_hours": 10,
        },
        "season_stats": season_stats,

        "week": week_data,
        "last_league": last_league,
        "quests": __import__("app.services.quests", fromlist=["quest_states"]).quest_states(db, user),
        "recent_events": [
            {
                "id": e.id,
                "type": e.event_type,
                "amount": round(e.amount, 1),
                "title": e.title or e.event_type,
                "date": e.date.strftime("%d.%m") if e.date else "",
            }
            for e in recent_events
        ],

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
                "tss_estimated": bool(act.tss_estimated),
                "is_long": bool(act.is_long),
                "date": (act.start_date_local or act.start_date).strftime("%d.%m.%Y") if (act.start_date_local or act.start_date) else "Неизвестно",
            }
            for act in activities
        ]
    }



def _monday_for_day(day: _date) -> _date:
    return day - timedelta(days=day.weekday())


def _week_activity_payload(act: Activity) -> dict:
    activity_date = act.start_date_local or act.start_date
    return {
        "id": act.id,
        "name": act.name or "Без названия",
        "sport": act.sport_type or "WORKOUT",
        "distance_km": round((act.distance or 0) / 1000, 2),
        "moving_time_min": (act.moving_time or 0) // 60,
        "xp": round(float(act.xp_earned or 0), 2),
        "base_xp": act.base_xp or 0,
        "rate_per_hour": act.rate_per_hour or 0,
        "intensity_multiplier": act.intensity_multiplier or 1.0,
        "intensity_category": act.intensity_category or "MEDIUM",
        "intensity_reason": act.intensity_reason or "",
        "sleep_multiplier": act.sleep_multiplier or 1.0,
        "sleep_hours": round(act.sleep_secs / 3600, 1) if act.sleep_secs else None,
        "streak_multiplier": act.streak_multiplier or 1.0,
        "streak_reason": act.streak_reason or "",
        "tss_estimated": bool(act.tss_estimated),
        "is_long": bool(act.is_long),
        "is_indoor": bool(getattr(act, "is_indoor", False) or act.indoor),
        "date": activity_date.strftime("%d.%m.%Y") if activity_date else "Неизвестно",
    }


@router.get("/weekly-summary")
def get_weekly_summary(
    week_start: _date | None = Query(default=None),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Сводка, события и тренировки выбранной недели; по умолчанию текущая неделя."""
    today = _user_local_today(current)
    current_start = _monday_for_day(today)
    selected_start = _monday_for_day(week_start or today)
    if selected_start > current_start:
        raise HTTPException(status_code=422, detail="Нельзя выбрать будущую неделю")
    selected_dt = datetime.combine(selected_start, datetime.min.time())
    next_dt = selected_dt + timedelta(days=7)

    from ..models import WeeklySummary, XPEvent
    summaries = (
        db.query(WeeklySummary)
        .filter(WeeklySummary.user_id == current.id, WeeklySummary.week_start <= datetime.combine(current_start, datetime.min.time()))
        .order_by(WeeklySummary.week_start.desc())
        .limit(52)
        .all()
    )
    option_dates = {_monday_for_day(row.week_start.date()) for row in summaries if row.week_start}
    option_dates.add(current_start)
    if selected_start not in option_dates:
        option_dates.add(selected_start)
    week_options = [
        {
            "week_start": start.isoformat(),
            "label": f"{start.strftime('%d.%m')}–{(start + timedelta(days=6)).strftime('%d.%m.%Y')}",
        }
        for start in sorted(option_dates, reverse=True)[:53]
    ]
    # Ensure the selected/current week remains selectable even if older than the 52-row window.
    if selected_start not in { _date.fromisoformat(item["week_start"]) for item in week_options }:
        week_options.append({
            "week_start": selected_start.isoformat(),
            "label": f"{selected_start.strftime('%d.%m')}–{(selected_start + timedelta(days=6)).strftime('%d.%m.%Y')}",
        })

    summary = (
        db.query(WeeklySummary)
        .filter(WeeklySummary.user_id == current.id, WeeklySummary.week_start == selected_dt)
        .first()
    )
    if summary:
        week = {
            "week_start": selected_start.isoformat(),
            "actual_load": round(summary.actual_load or 0, 1),
            "target_load": round(summary.target_load or 0, 1),
            "completion_ratio": round((summary.completion_ratio or 0) * 100, 1),
            "training_days": summary.training_days or 0,
            "effort_xp": round(summary.effort_xp or 0, 1),
            "goal_xp": round(summary.goal_xp or 0, 1),
            "consistency_xp": round(summary.consistency_xp or 0, 1),
            "quality_xp": round(summary.quality_xp or 0, 1),
            "recovery_xp": round(summary.recovery_xp or 0, 1),
            "quest_xp": round(summary.quest_xp or 0, 1),
            "total_xp": round(summary.total_xp or 0, 1),
            "league_score": round(summary.league_score or 0, 1),
            "state": "ready" if summary.finalized else "in_progress",
            "is_deload": bool(summary.is_deload),
            "paused": bool(summary.paused),
            "division": summary.division or (f"Division {current.division_current}" if current.division_current else None),
            "division_source": summary.division_source,
        }
    else:
        previous = next((row for row in summaries if row.week_start and row.week_start < selected_dt and row.target_load), None)
        from ..services import xp_v6 as X6
        week = {
            "week_start": selected_start.isoformat(),
            "actual_load": 0, "target_load": round((previous.target_load if previous else X6.starter_target()) or 0, 1),
            "completion_ratio": 0, "training_days": 0,
            "effort_xp": 0, "goal_xp": 0, "consistency_xp": 0, "quality_xp": 0,
            "recovery_xp": 0, "quest_xp": 0, "total_xp": 0, "league_score": 0,
            "state": "no_data", "is_deload": False, "paused": False,
            "division": f"Division {current.division_current}" if current.division_current else None,
            "division_source": "ladder" if current.division_current else "provisional",
        }

    # Match the existing current-week placement logic, without recalculating a user's division from a historical week.
    if selected_start == current_start:
        division, division_source = _user_division(db, current, selected_start, week["actual_load"])
        week["division"] = division
        week["division_source"] = division_source
    else:
        membership = (
            db.query(LeagueMembership)
            .filter(LeagueMembership.user_id == current.id, LeagueMembership.week_start == selected_dt)
            .first()
        )
        if membership is not None:
            week["division"] = membership.division
            week["division_source"] = membership.division_source

    event_rows = (
        db.query(XPEvent)
        .filter(XPEvent.user_id == current.id, XPEvent.week_start == selected_dt)
        .order_by(XPEvent.date.asc(), XPEvent.id.asc())
        .all()
    )
    events = [{
        "id": event.id,
        "type": event.event_type,
        "amount": round(event.amount or 0, 1),
        "title": event.title or event.event_type,
        "date": event.date.strftime("%d.%m") if event.date else "",
    } for event in event_rows]

    activities = (
        db.query(Activity)
        .filter(
            Activity.user_id == current.id,
            func.coalesce(Activity.start_date_local, Activity.start_date) >= selected_dt,
            func.coalesce(Activity.start_date_local, Activity.start_date) < next_dt,
        )
        .order_by(func.coalesce(Activity.start_date_local, Activity.start_date).desc(), Activity.id.desc())
        .all()
    )
    return {
        "week": week,
        "week_options": week_options,
        "events": events,
        "activities": [_week_activity_payload(act) for act in activities],
        "is_current_week": selected_start == current_start,
    }


@router.get("/season-weeks")
def get_season_weeks(current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """WeeklySummary timeline for the current September–August season."""
    from ..models import WeeklySummary
    today = _user_local_today(current)
    season_year = today.year if today.month >= 9 else today.year - 1
    season_start = _date(season_year, 9, 1)
    first_week = _monday_for_day(season_start)
    current_week = _monday_for_day(today)
    rows = (
        db.query(WeeklySummary)
        .filter(WeeklySummary.user_id == current.id,
                WeeklySummary.week_start >= datetime.combine(first_week, datetime.min.time()),
                WeeklySummary.week_start <= datetime.combine(current_week, datetime.min.time()))
        .order_by(WeeklySummary.week_start.asc())
        .all()
    )
    by_week = {_monday_for_day(row.week_start.date()): row for row in rows if row.week_start}
    weeks = []
    cursor = first_week
    while cursor <= current_week:
        row = by_week.get(cursor)
        weeks.append({
            "week_start": cursor.isoformat(),
            "label": cursor.strftime("%d.%m"),
            "total_xp": round(row.total_xp or 0, 1) if row else 0,
            "actual_load": round(row.actual_load or 0, 1) if row else 0,
            "target_load": round(row.target_load or 0, 1) if row and row.target_load is not None else 0,
            "has_summary": row is not None,
        })
        cursor += timedelta(days=7)
    return {"season_start": season_start.isoformat(), "weeks": weeks}


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
    
    from ..models import WeeklySummary, XPEvent, LeagueMembership
    db.query(XPEvent).filter(XPEvent.user_id == current.id).delete(synchronize_session=False)
    db.query(WeeklySummary).filter(WeeklySummary.user_id == current.id).delete(synchronize_session=False)
    db.query(LeagueMembership).filter(LeagueMembership.user_id == current.id).delete(synchronize_session=False)
    current.legacy_xp_offset = 0.0
    current.xp_migrated_at = None
    current.division_current = None
    current.division_placed_at = None
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


def _is_accepted_friend(db: Session, viewer_id: int, owner_id: int) -> bool:
    if viewer_id == owner_id:
        return True
    return db.query(Friendship.id).filter(
        Friendship.status == FriendshipStatus.ACCEPTED,
        or_(
            and_(Friendship.from_user_id == viewer_id, Friendship.to_user_id == owner_id),
            and_(Friendship.from_user_id == owner_id, Friendship.to_user_id == viewer_id),
        ),
    ).first() is not None


@router.get("/users/{username}")
async def public_profile(
    username: str,
    viewer: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Профиль доступен только после входа; права определяются настройками и дружбой."""
    user = db.query(User).filter(User.username == username.lower().strip()).first()
    if not user:
        raise HTTPException(status_code=404, detail="Athlete not found")

    is_owner = viewer.id == user.id
    is_friend = _is_accepted_friend(db, viewer.id, user.id)
    profile_visibility = user.profile_visibility or "authenticated"
    activity_visibility = user.activity_visibility or "friends"

    if not is_owner and profile_visibility == "private":
        raise HTTPException(status_code=403, detail="Этот профиль скрыт владельцем")
    can_view_profile_stats = is_owner or is_friend or profile_visibility == "authenticated"
    can_view_activities = is_owner or (is_friend and activity_visibility == "friends")

    relation = None
    friendship_id = None
    if not is_owner:
        rel = (
            db.query(Friendship)
            .filter(or_(
                and_(Friendship.from_user_id == viewer.id, Friendship.to_user_id == user.id),
                and_(Friendship.from_user_id == user.id, Friendship.to_user_id == viewer.id),
            ))
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

    season_stats = {
        "season_start": "01.09.2026",
        "total_km": 0,
        "total_hours": 0,
        "total_elevation": 0,
        "total_workouts": 0,
        "total_xp": 0,
    }
    hr_points = []
    if can_view_profile_stats:
        all_acts = db.query(Activity).filter(Activity.user_id == user.id).all()
        season_start = datetime(2026, 9, 1)
        season_acts = [a for a in all_acts if (a.start_date_local or a.start_date) and (a.start_date_local or a.start_date) >= season_start]
        season_stats = {
            "season_start": season_start.strftime("%d.%m.%Y"),
            "total_km": round(sum(a.distance or 0 for a in season_acts) / 1000, 1),
            "total_hours": round(sum(a.moving_time or 0 for a in season_acts) / 3600, 1),
            "total_elevation": int(round(sum(a.elevation_gain or 0 for a in season_acts))),
            "total_workouts": len(season_acts),
            "total_xp": round(sum(a.xp_earned or 0 for a in season_acts)),
        }

        # Heart-rate history is sensitive: visible only to the owner or an accepted friend.
        if is_owner or (is_friend and activity_visibility == "friends"):
            month_ago = datetime.utcnow() - timedelta(days=30)
            hr_points = [
                {"date": (a.start_date_local or a.start_date).strftime("%d.%m"), "hr": round(a.average_heartrate, 1)}
                for a in sorted(all_acts, key=lambda x: x.start_date or datetime.min)
                if a.start_date and a.start_date >= month_ago and (a.average_heartrate or 0) > 0
            ]

    return {
        "user": {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "level": user.level if can_view_profile_stats else None,
            "total_xp": round(float(user.total_xp or 0), 2) if can_view_profile_stats else None,
            "friends_count": friends_count if can_view_profile_stats else None,
            "is_you": is_owner,
            "relation": relation,
            "friendship_id": friendship_id,
            "profile_visibility": profile_visibility,
            "activity_visibility": activity_visibility,
            "can_view_profile_stats": can_view_profile_stats,
            "can_view_activities": can_view_activities,
        },
        "season_stats": season_stats,
        "hr_last_month": hr_points,
    }


@router.get("/users/{username}/activities")
async def public_activities(
    username: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=50),
    viewer: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Детали тренировок доступны только владельцу либо принятому другу по настройке владельца."""
    user = db.query(User).filter(User.username == username.lower().strip()).first()
    if not user:
        raise HTTPException(status_code=404, detail="Athlete not found")

    is_owner = viewer.id == user.id
    is_friend = _is_accepted_friend(db, viewer.id, user.id)
    if not is_owner:
        if (user.profile_visibility or "authenticated") == "private":
            raise HTTPException(status_code=403, detail="Этот профиль скрыт владельцем")
        if (user.profile_visibility or "authenticated") == "friends" and not is_friend:
            raise HTTPException(status_code=403, detail="Подробности профиля доступны только друзьям")
        if (user.activity_visibility or "friends") != "friends" or not is_friend:
            raise HTTPException(status_code=403, detail="Тренировки доступны только владельцу или друзьям")

    query = db.query(Activity).filter(Activity.user_id == user.id)
    total = query.count()
    acts = query.order_by(Activity.start_date.desc(), Activity.id.desc()).offset(offset).limit(limit).all()
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
                "streak_multiplier": a.streak_multiplier or 1.0,
                "streak_reason": a.streak_reason or "",
                "tss_estimated": bool(a.tss_estimated),
                "is_long": bool(a.is_long),
                "date": (a.start_date_local or a.start_date).strftime("%d.%m.%Y") if (a.start_date_local or a.start_date) else "—",
            }
            for a in acts
        ],
    }


from ..services.leaderboard_privacy import (
    viewer_friend_ids as _viewer_friend_ids,
    profile_visible_on_leaderboard as _profile_visible_on_leaderboard,
)

@router.get("/leaderboard")
async def leaderboard(
    scope: str = Query("global", regex="^(global|friends|weekly)$"),
    limit: int = Query(10, ge=1, le=10),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Authenticated leaderboards; visibility filtering and top-10 selection run in SQL."""
    from ..services import xp_v6 as X6
    from ..models import LeagueWeek, WeeklySummary

    friend_ids = _viewer_friend_ids(db, current)
    visible_ids = friend_ids | {current.id}
    visible_filter = or_(
        User.profile_visibility.is_(None),
        User.profile_visibility == "authenticated",
        and_(
            User.profile_visibility == "friends",
            User.id.in_(visible_ids),
        ),
        and_(
            User.profile_visibility == "private",
            User.id == current.id,
        ),
    )
    rank_expr = func.coalesce(User.total_xp, 0.0)

    def _rank_before_user(scope_filter):
        score = float(current.total_xp or 0)
        ahead = (
            db.query(func.count(User.id))
            .filter(
                scope_filter,
                or_(
                    rank_expr > score,
                    and_(rank_expr == score, User.id < current.id),
                ),
            )
            .scalar()
        )
        return int(ahead or 0) + 1

    if scope == "weekly":
        today = _user_local_today(current)
        this_ws_d = X6.week_start(today)
        this_ws = datetime.combine(this_ws_d, datetime.min.time())
        rows = (
            db.query(WeeklySummary, User)
            .join(User, User.id == WeeklySummary.user_id)
            .filter(WeeklySummary.week_start == this_ws, visible_filter)
            .order_by(
                func.coalesce(WeeklySummary.league_score, 0.0).desc(),
                User.id.asc(),
            )
            .limit(limit)
            .all()
        )
        entries = []
        for summary, user in rows:
            div, source = _user_division(
                db, user, this_ws_d, summary.actual_load or 0
            )
            entries.append({
                "id": user.id,
                "username": user.username,
                "display_name": user.display_name,
                "level": user.level,
                "score": round(summary.league_score or 0, 1),
                "division": div,
                "division_source": source,
                "is_you": user.id == current.id,
            })
        division_order = {name: i for i, name in enumerate(X6.DIVISION_NAMES)}
        division_order["Open"] = len(division_order)
        division_order[None] = len(division_order) + 1
        entries.sort(key=lambda entry: (
            division_order.get(entry["division"], 99),
            -entry["score"],
            entry["id"],
        ))
        per_division: dict = {}
        for entry in entries:
            div = entry["division"]
            per_division[div] = per_division.get(div, 0) + 1
            entry["rank"] = per_division[div]

        last_week = (
            db.query(LeagueWeek)
            .order_by(LeagueWeek.week_start.desc())
            .first()
        )
        return {
            "scope": "weekly",
            "your_rank": next(
                (entry["rank"] for entry in entries if entry["is_you"]), None
            ),
            "week": this_ws_d.isoformat(),
            "formed": len(entries) >= X6.MIN_LEAGUE_SIZE,
            "min_size": X6.MIN_LEAGUE_SIZE,
            "last_closed": last_week.week_start.strftime("%d.%m") if last_week else None,
            "entries": entries,
        }

    if scope == "global":
        users = (
            db.query(User)
            .filter(visible_filter)
            .order_by(rank_expr.desc(), User.id.asc())
            .limit(limit)
            .all()
        )
        your_rank = _rank_before_user(visible_filter)
    else:
        if not friend_ids:
            return {"scope": scope, "entries": [], "your_rank": None}
        friend_scope_filter = and_(
            visible_filter,
            User.id.in_(visible_ids),
        )
        users = (
            db.query(User)
            .filter(friend_scope_filter)
            .order_by(rank_expr.desc(), User.id.asc())
            .limit(limit)
            .all()
        )
        your_rank = _rank_before_user(friend_scope_filter)

    return {
        "scope": scope,
        "your_rank": your_rank,
        "entries": [
            {
                "rank": i + 1,
                "id": user.id,
                "display_name": user.display_name,
                "username": user.username,
                "level": user.level,
                "total_xp": round(float(user.total_xp or 0), 2),
                "is_you": user.id == current.id,
            }
            for i, user in enumerate(users)
        ],
    }


class PauseIn(BaseModel):
    weeks: int = Field(default=0, ge=0, le=8)


@router.post("/pause")
@limiter.limit("10/hour")
async def set_pause(
    request: Request,
    payload: PauseIn,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Пауза (болезнь/отпуск): недели окна не ждут цели и не входят в базу нормы."""
    weeks = payload.weeks
    if weeks == 0:
        current.pause_set_at = None
        current.paused_until = None
        message = "Пауза снята"
    else:
        current.pause_set_at = datetime.utcnow()
        current.paused_until = datetime.utcnow() + timedelta(weeks=weeks)
        message = f"Пауза установлена на {weeks} нед."
    db.commit()
    return {
        "message": message,
        "paused_until": current.paused_until.isoformat() if current.paused_until else None,
    }
