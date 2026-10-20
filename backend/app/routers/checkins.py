"""Private daily and activity check-ins for personal training context."""
from datetime import date, datetime, timezone
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user
from ..models import Activity, ActivityCheckIn, MorningCheckIn, User, Wellness

router = APIRouter(prefix="/api/check-ins", tags=["Private check-ins"])


class MorningCheckInInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    readiness: int | None = Field(default=None, ge=1, le=5)
    fatigue: int | None = Field(default=None, ge=1, le=5)
    soreness: int | None = Field(default=None, ge=1, le=5)
    wellbeing: int | None = Field(default=None, ge=1, le=5)

    @model_validator(mode="after")
    def require_at_least_one_answer(self):
        if all(getattr(self, field) is None for field in ("readiness", "fatigue", "soreness", "wellbeing")):
            raise ValueError("Укажи хотя бы один известный показатель или используй пропуск")
        return self


class ActivityCheckInInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rpe: int = Field(ge=1, le=10)
    load_expectation: Literal["easier", "as_expected", "harder"] | None = None
    discomfort: Literal["none", "mild", "significant"] | None = None


def _utc_now() -> datetime:
    """UTC timestamp stored as a naive datetime for compatibility with current models."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat().replace("+00:00", "Z")


def _local_today(user: User, now: datetime | None = None) -> date:
    try:
        zone = ZoneInfo(getattr(user, "timezone_name", None) or "UTC")
    except (ZoneInfoNotFoundError, TypeError, ValueError):
        zone = ZoneInfo("UTC")
    instant = now or _utc_now()
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    else:
        instant = instant.astimezone(timezone.utc)
    return instant.astimezone(zone).date()


def _morning_payload(row: MorningCheckIn) -> dict:
    return {
        "id": row.id,
        "local_date": row.local_date.isoformat(),
        "status": row.status,
        "prompted_at": _iso_utc(row.prompted_at),
        "skip_warning_at": _iso_utc(row.skip_warning_at),
        "readiness": row.readiness,
        "fatigue": row.fatigue,
        "soreness": row.soreness,
        "wellbeing": row.wellbeing,
        "created_at": _iso_utc(row.created_at),
        "updated_at": _iso_utc(row.updated_at),
    }


def _activity_payload(row: ActivityCheckIn) -> dict:
    return {
        "activity_id": row.activity_id,
        "rpe": row.rpe,
        "load_expectation": row.load_expectation,
        "discomfort": row.discomfort,
        "updated_at": _iso_utc(row.updated_at),
    }


def _get_today_morning(db: Session, user: User, now: datetime) -> MorningCheckIn:
    local_date = _local_today(user, now)
    row = (
        db.query(MorningCheckIn)
        .filter(MorningCheckIn.user_id == user.id, MorningCheckIn.local_date == local_date)
        .first()
    )
    if row is not None:
        return row

    row = MorningCheckIn(
        user_id=user.id,
        local_date=local_date,
        status="pending",
        prompted_at=now,
    )
    db.add(row)
    try:
        db.commit()
        db.refresh(row)
        return row
    except IntegrityError:
        # Concurrent prompt requests for the same user/date converge on one row.
        db.rollback()
        existing = (
            db.query(MorningCheckIn)
            .filter(MorningCheckIn.user_id == user.id, MorningCheckIn.local_date == local_date)
            .first()
        )
        if existing is None:
            raise
        return existing


def _today_row_or_conflict(db: Session, user: User, now: datetime) -> MorningCheckIn:
    local_date = _local_today(user, now)
    row = (
        db.query(MorningCheckIn)
        .filter(MorningCheckIn.user_id == user.id, MorningCheckIn.local_date == local_date)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=409, detail="Сначала открой утренний чек-ин")
    return row


def _morning_response(db: Session, row: MorningCheckIn, now: datetime) -> dict:
    # Wellness values are imported from Intervals.icu; they are not user-entered check-in answers.
    wellness = (
        db.query(Wellness)
        .filter(Wellness.user_id == row.user_id, Wellness.date == row.local_date.isoformat())
        .first()
    )
    sleep = None
    if wellness is not None and (wellness.sleep_secs is not None or wellness.sleep_score is not None):
        sleep = {
            "source": "Intervals.icu",
            "sleep_secs": wellness.sleep_secs,
            "sleep_score": wellness.sleep_score,
        }
    return {
        "checkin": _morning_payload(row),
        "sleep": sleep,
        "server_now": _iso_utc(now),
    }


@router.post("/morning/prompt")
def start_morning_prompt(
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Idempotently create or return today's prompt state in the user's local timezone."""
    now = _utc_now()
    row = _get_today_morning(db, current, now)
    return _morning_response(db, row, now)


@router.post("/morning")
def save_morning_checkin(
    data: MorningCheckInInput,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create or edit today's answers; unknown values remain NULL."""
    now = _utc_now()
    row = _get_today_morning(db, current, now)
    row.readiness = data.readiness
    row.fatigue = data.fatigue
    row.soreness = data.soreness
    row.wellbeing = data.wellbeing
    row.status = "completed"
    row.skip_warning_at = None
    row.updated_at = now
    db.commit()
    db.refresh(row)
    return _morning_response(db, row, now)


@router.post("/morning/skip-warning")
def begin_morning_skip_warning(
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    now = _utc_now()
    row = _today_row_or_conflict(db, current, now)
    if row.status != "pending":
        raise HTTPException(status_code=409, detail="Утренний чек-ин уже закрыт")
    if (now - row.prompted_at).total_seconds() < 15:
        raise HTTPException(status_code=409, detail="Кнопка пропуска пока недоступна")
    if row.skip_warning_at is None:
        row.skip_warning_at = now
        row.updated_at = now
        db.commit()
        db.refresh(row)
    return _morning_response(db, row, now)


@router.post("/morning/skip-warning/cancel")
def cancel_morning_skip_warning(
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    now = _utc_now()
    row = _today_row_or_conflict(db, current, now)
    if row.status == "pending" and row.skip_warning_at is not None:
        row.skip_warning_at = None
        row.updated_at = now
        db.commit()
        db.refresh(row)
    return _morning_response(db, row, now)


@router.post("/morning/skip")
def skip_morning_checkin(
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    now = _utc_now()
    row = _today_row_or_conflict(db, current, now)
    if row.status != "pending":
        raise HTTPException(status_code=409, detail="Утренний чек-ин уже закрыт")
    if row.skip_warning_at is None or (now - row.skip_warning_at).total_seconds() < 5:
        raise HTTPException(status_code=409, detail="Подтверждение пропуска пока недоступно")
    row.status = "skipped"
    row.skip_warning_at = None
    row.updated_at = now
    db.commit()
    db.refresh(row)
    return _morning_response(db, row, now)


@router.get("/activities")
def list_activity_checkins(
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Only return check-ins attached to activities owned by the authenticated user."""
    rows = (
        db.query(ActivityCheckIn)
        .join(Activity, Activity.id == ActivityCheckIn.activity_id)
        .filter(Activity.user_id == current.id, ActivityCheckIn.user_id == current.id)
        .order_by(ActivityCheckIn.updated_at.desc(), ActivityCheckIn.id.desc())
        .limit(100)
        .all()
    )
    return {"checkins": [_activity_payload(row) for row in rows]}


@router.get("/activities/{activity_id}")
def get_activity_checkin(
    activity_id: int,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    activity = (
        db.query(Activity)
        .filter(Activity.id == activity_id, Activity.user_id == current.id)
        .first()
    )
    if activity is None:
        raise HTTPException(status_code=404, detail="Тренировка не найдена")
    row = (
        db.query(ActivityCheckIn)
        .filter(ActivityCheckIn.activity_id == activity.id, ActivityCheckIn.user_id == current.id)
        .first()
    )
    return {"checkin": _activity_payload(row) if row else None}


@router.post("/activities/{activity_id}")
def save_activity_checkin(
    activity_id: int,
    data: ActivityCheckInInput,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Idempotent upsert for an activity belonging to the current user."""
    activity = (
        db.query(Activity)
        .filter(Activity.id == activity_id, Activity.user_id == current.id)
        .first()
    )
    if activity is None:
        raise HTTPException(status_code=404, detail="Тренировка не найдена")

    now = _utc_now()
    row = (
        db.query(ActivityCheckIn)
        .filter(ActivityCheckIn.activity_id == activity.id, ActivityCheckIn.user_id == current.id)
        .first()
    )
    if row is None:
        row = ActivityCheckIn(
            user_id=current.id,
            activity_id=activity.id,
            rpe=data.rpe,
            load_expectation=data.load_expectation,
            discomfort=data.discomfort,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
    else:
        row.rpe = data.rpe
        row.load_expectation = data.load_expectation
        row.discomfort = data.discomfort
        row.updated_at = now
    db.commit()
    db.refresh(row)
    return {"checkin": _activity_payload(row)}
