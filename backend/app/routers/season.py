"""Season metadata and explicit user timezone confirmation endpoints."""
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user, get_optional_current_user
from ..models import User
from ..services.seasons import current_season

router = APIRouter(prefix="/api", tags=["Season and timezone"])


@router.get("/season")
def get_season(
    timezone_name: str | None = Query(default=None, max_length=64),
    current: User | None = Depends(get_optional_current_user),
):
    """Season for the authenticated user's saved timezone or browser timezone."""
    zone = (current.timezone_name if current else timezone_name) or "UTC"
    # While a UTC account has not confirmed its timezone, use the browser hint so
    # the first page render agrees with the one-time confirmation prompt.
    if current and zone == "UTC" and not bool(current.timezone_confirmed) and timezone_name:
        zone = timezone_name
    try:
        ZoneInfo(zone)
    except (ZoneInfoNotFoundError, TypeError, ValueError):
        zone = "UTC"
    return current_season(zone).to_payload(zone)


@router.get("/timezone")
def get_timezone_status(current: User | None = Depends(get_optional_current_user)):
    if current is None:
        return {"authenticated": False}
    return {
        "authenticated": True,
        "timezone_name": current.timezone_name or "UTC",
        "timezone_confirmed": bool(current.timezone_confirmed),
    }


class TimezoneUpdate(BaseModel):
    timezone_name: str = Field(..., min_length=1, max_length=64)
    confirmed: bool = True

    @field_validator("timezone_name", mode="before")
    @classmethod
    def validate_timezone(cls, value):
        if not isinstance(value, str):
            raise ValueError("Часовой пояс должен быть строкой IANA")
        zone_name = value.strip()
        try:
            ZoneInfo(zone_name)
        except (ZoneInfoNotFoundError, ValueError, TypeError):
            raise ValueError("Неизвестный часовой пояс")
        return zone_name


@router.patch("/timezone")
def update_timezone(
    data: TimezoneUpdate,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    current.timezone_name = data.timezone_name
    current.timezone_confirmed = bool(data.confirmed)
    db.commit()
    db.refresh(current)
    return {
        "timezone_name": current.timezone_name,
        "timezone_confirmed": bool(current.timezone_confirmed),
    }
