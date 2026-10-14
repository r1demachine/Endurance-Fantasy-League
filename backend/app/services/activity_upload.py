"""Shared, idempotent activity creation for website and Telegram uploads."""
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from math import isfinite

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Activity, HeartRateSettingsHistory, User
from .activity_dedupe import ALL_ACTIVITY_SOURCES, UPLOAD_SOURCES, find_matching_activity

UPLOAD_ID_PREFIX = "UPLOAD_TELEGRAM:"
_ALLOWED_SOURCES = {"UPLOAD_SITE", "UPLOAD_TELEGRAM"}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _duplicate_reason(activity: Activity) -> str:
    display_start = activity.start_date_local or activity.start_date
    when = display_start.strftime("%d.%m.%Y %H:%M") if display_start else "дата неизвестна"
    minutes = round((activity.moving_time or 0) / 60)
    return f"Эта тренировка уже есть ({when}, {minutes} мин), повторно не сохранена."


def _settings_day_start_utc(user: User) -> datetime:
    try:
        local_tz = ZoneInfo(getattr(user, "timezone_name", None) or "UTC")
    except Exception:
        local_tz = ZoneInfo("UTC")
    local_now = datetime.now(timezone.utc).astimezone(local_tz)
    midnight = datetime.combine(local_now.date(), datetime.min.time(), tzinfo=local_tz)
    return midnight.astimezone(timezone.utc).replace(tzinfo=None)


def _apply_auto_hr_updates(db: Session, user: User, updates: dict) -> None:
    if not isinstance(updates, dict) or not updates:
        return
    day_start = _settings_day_start_utc(user)
    already_changed = db.query(HeartRateSettingsHistory.id).filter(
        HeartRateSettingsHistory.user_id == user.id,
        HeartRateSettingsHistory.changed_at >= day_start,
    ).first()
    if already_changed:
        return

    next_max = user.max_hr
    next_lthr = user.lthr
    next_resting = user.resting_hr
    proposed_max = updates.get("max_hr")
    proposed_lthr = updates.get("lthr")

    if isinstance(proposed_max, int) and user.max_hr is not None and user.max_hr < proposed_max <= 240:
        next_max = proposed_max
    if isinstance(proposed_lthr, int) and user.lthr is not None and user.lthr < proposed_lthr <= 220:
        next_lthr = proposed_lthr

    if (next_lthr, next_max, next_resting) == (user.lthr, user.max_hr, user.resting_hr):
        return

    # Automatic calibration is only allowed with a complete set of thresholds.
    # This keeps all saved settings within the same physiological constraints.
    if next_resting is None or next_lthr is None or next_max is None:
        return
    if not (next_resting < next_lthr < next_max):
        return
    if not (0.75 * next_max <= next_lthr <= 0.97 * next_max):
        return
    user.lthr = next_lthr
    user.max_hr = next_max
    user.resting_hr = next_resting
    db.add(HeartRateSettingsHistory(
        user_id=user.id,
        changed_at=datetime.utcnow(),
        lthr=next_lthr,
        max_hr=next_max,
        resting_hr=next_resting,
    ))

def _valid_float(value, default=0.0) -> float:
    try:
        number = float(value if value is not None else default)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("числовые показатели тренировки повреждены") from exc
    if not isfinite(number):
        raise ValueError("числовые показатели тренировки повреждены")
    return number


def create_activity_from_upload(
    db: Session,
    user: User,
    parsed: dict,
    file_sha256: str,
    *,
    source: str,
) -> tuple[str, Activity | None, str | None]:
    """Return (created|duplicate|rejected, activity, reason); safe across both upload channels."""
    if source not in _ALLOWED_SOURCES:
        return "rejected", None, "Неизвестный источник загрузки."
    if not isinstance(file_sha256, str) or not _SHA256_RE.fullmatch(file_sha256):
        return "rejected", None, "Не удалось проверить контрольную сумму файла."

    user_id = user.id
    intervals_activity_id = f"{UPLOAD_ID_PREFIX}{file_sha256}"
    existing = db.query(Activity).filter(
        Activity.user_id == user_id,
        Activity.intervals_activity_id == intervals_activity_id,
    ).first()
    if existing:
        return "duplicate", existing, _duplicate_reason(existing)

    try:
        start_date = datetime.fromisoformat(str(parsed["start_date"]))
        if start_date.tzinfo is not None:
            start_date = start_date.astimezone(timezone.utc).replace(tzinfo=None)
        start_local_raw = parsed.get("start_date_local")
        start_date_local = datetime.fromisoformat(str(start_local_raw)) if start_local_raw else start_date
        if start_date_local.tzinfo is not None:
            start_date_local = start_date_local.replace(tzinfo=None)
        moving_time = int(parsed["moving_time"])
        elapsed_time = int(parsed.get("elapsed_time") or moving_time)
        distance = max(0.0, _valid_float(parsed.get("distance")))
        elevation = max(0.0, _valid_float(parsed.get("elevation_gain")))
        training_load = max(0.0, _valid_float(parsed["training_load"]))
        intensity = min(1.5, max(0.3, _valid_float(parsed["intensity"])))
        hard_secs = max(0, int(parsed.get("hard_secs") or 0))
        average_hr = _valid_float(parsed.get("average_heartrate")) if parsed.get("average_heartrate") is not None else None
        maximum_hr = _valid_float(parsed.get("max_heartrate")) if parsed.get("max_heartrate") is not None else None
    except (KeyError, TypeError, ValueError, OverflowError):
        return "rejected", None, "Данные тренировки повреждены или неполные."

    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    if start_date > now_utc:
        return "rejected", None, "Начало тренировки находится в будущем."
    if start_date < now_utc - timedelta(days=30):
        return "rejected", None, "Можно загружать тренировки не старше 30 дней."
    if moving_time <= 0 or moving_time > 7 * 24 * 3600:
        return "rejected", None, "Некорректная длительность тренировки."
    if elapsed_time <= 0 or elapsed_time > 7 * 24 * 3600:
        return "rejected", None, "Некорректная общая длительность тренировки."

    duplicate = find_matching_activity(
        db, user_id, start_date, start_date_local, moving_time,
        sources=ALL_ACTIVITY_SOURCES,
    )
    if duplicate:
        return "duplicate", duplicate, _duplicate_reason(duplicate)

    cutoff = now_utc - timedelta(hours=1)
    recent_uploads = db.query(Activity.id).filter(
        Activity.user_id == user_id,
        Activity.source.in_(UPLOAD_SOURCES),
        Activity.created_at >= cutoff,
    ).count()
    if recent_uploads >= 5:
        return "rejected", None, "Лимит — 5 сохранённых загрузок в час. Попробуй позже."

    is_indoor = bool(parsed.get("is_indoor", False))
    activity = Activity(
        user_id=user_id,
        intervals_activity_id=intervals_activity_id,
        source=source,
        name=str(parsed.get("name") or "Загруженная тренировка")[:255],
        sport_type=str(parsed.get("sport_type") or "WORKOUT")[:32],
        distance=distance,
        moving_time=moving_time,
        elapsed_time=elapsed_time,
        elevation_gain=elevation,
        average_speed=(distance / moving_time) if distance and moving_time else None,
        average_heartrate=average_hr,
        max_heartrate=maximum_hr,
        training_load=training_load,
        intensity=intensity,
        hard_secs=hard_secs,
        is_manual=False,
        start_date=start_date,
        start_date_local=start_date_local,
        # Keep the legacy flag in sync for older clients, while is_indoor is canonical.
        indoor=is_indoor,
        is_indoor=is_indoor,
    )
    db.add(activity)
    try:
        _apply_auto_hr_updates(db, user, parsed.get("auto_zone_updates", {}))

        db.flush()
        from ..routers.sync import _recalculate_user_xp, _recalculate_user_xp_v6
        if get_settings().XP_ENGINE == "v6":
            _recalculate_user_xp_v6(db, user)
        else:
            _recalculate_user_xp(db, user)
        db.commit()
    except IntegrityError:
        db.rollback()
        duplicate = db.query(Activity).filter(
            Activity.user_id == user_id,
            Activity.intervals_activity_id == intervals_activity_id,
        ).first()
        if duplicate:
            return "duplicate", duplicate, _duplicate_reason(duplicate)
        return "rejected", None, "Не удалось сохранить тренировку из-за конфликта данных."
    except Exception:
        db.rollback()
        return "rejected", None, "Не удалось сохранить тренировку. Попробуй позже."

    db.refresh(activity)
    db.refresh(user)
    return "created", activity, None
