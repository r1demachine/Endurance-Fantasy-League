"""Shared, idempotent activity creation for website and Telegram uploads."""
import re
from datetime import datetime, timezone
from math import isfinite

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Activity, User

UPLOAD_ID_PREFIX = "UPLOAD_TELEGRAM:"
_ALLOWED_SOURCES = {"UPLOAD_SITE", "UPLOAD_TELEGRAM"}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _duplicate_reason(activity: Activity) -> str:
    when = activity.start_date.strftime("%d.%m.%Y %H:%M") if activity.start_date else "дата неизвестна"
    minutes = round((activity.moving_time or 0) / 60)
    return f"Эта тренировка уже есть ({when}, {minutes} мин), повторно не сохранена."


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

    if moving_time <= 0 or moving_time > 7 * 24 * 3600:
        return "rejected", None, "Некорректная длительность тренировки."
    if elapsed_time <= 0 or elapsed_time > 7 * 24 * 3600:
        return "rejected", None, "Некорректная общая длительность тренировки."

    from ..routers.upload import _find_intervals_duplicate
    intervals_duplicate = _find_intervals_duplicate(db, user_id, start_date, moving_time)
    if intervals_duplicate:
        return "duplicate", intervals_duplicate, _duplicate_reason(intervals_duplicate)

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
        start_date_local=start_date,
        indoor=False,
        is_indoor=False,
    )
    db.add(activity)
    try:
        updates = parsed.get("auto_zone_updates", {})
        proposed_max = updates.get("max_hr") if isinstance(updates, dict) else None
        proposed_lthr = updates.get("lthr") if isinstance(updates, dict) else None
        if isinstance(proposed_max, int) and user.max_hr is not None and user.max_hr < proposed_max <= 240:
            user.max_hr = proposed_max
        if isinstance(proposed_lthr, int) and user.lthr is not None and user.lthr < proposed_lthr <= 220:
            if user.max_hr is None or proposed_lthr < user.max_hr:
                user.lthr = proposed_lthr

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
