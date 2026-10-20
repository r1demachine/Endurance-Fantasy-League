"""Season metadata, recap, and explicit user timezone confirmation endpoints."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user, get_optional_current_user
from ..models import Activity, Duel, DuelStatus, LeagueMembership, User, WeeklySummary, XPEvent
from ..services.seasons import current_season, local_date, longest_consecutive_streak, season_for_date, sum_weekly_xp

router = APIRouter(prefix="/api", tags=["Season and timezone"])


@router.get("/season")
def get_season(
    timezone_name: str | None = Query(default=None, max_length=64),
    current: User | None = Depends(get_optional_current_user),
):
    """Season for the authenticated user's saved timezone or browser timezone."""
    zone = (current.timezone_name if current else timezone_name) or "UTC"
    if current and zone == "UTC" and not bool(current.timezone_confirmed) and timezone_name:
        zone = timezone_name
    try:
        ZoneInfo(zone)
    except (ZoneInfoNotFoundError, TypeError, ValueError):
        zone = "UTC"
    return current_season(zone).to_payload(zone)


@router.get("/season/recap")
def get_season_recap(
    season_start: date | None = Query(default=None),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Season statistics use weekly XP totals, including non-workout bonuses."""
    zone = current.timezone_name or "UTC"
    today = local_date(zone)
    season = season_for_date(season_start or today)
    start_dt = datetime.combine(season.start, datetime.min.time())
    end_dt = datetime.combine(season.next_start, datetime.min.time())
    activities = db.query(Activity).filter(Activity.user_id == current.id).all()
    season_activities = []
    active_days = set()
    for activity in activities:
        stamp = activity.start_date_local or activity.start_date
        if stamp is not None and season.start <= stamp.date() < season.next_start:
            season_activities.append(activity)
            active_days.add(stamp.date())

    weekly_rows = (
        db.query(WeeklySummary)
        .filter(
            WeeklySummary.user_id == current.id,
            WeeklySummary.week_start >= start_dt,
            WeeklySummary.week_start < end_dt,
        )
        .order_by(WeeklySummary.week_start.asc())
        .all()
    )
    season_xp = sum_weekly_xp([row.total_xp for row in weekly_rows])
    best_week_row = max(weekly_rows, key=lambda row: float(row.total_xp or 0.0), default=None)
    best_week = (
        {
            "week_start": best_week_row.week_start.date().isoformat(),
            "total_xp": round(float(best_week_row.total_xp or 0.0), 1),
        }
        if best_week_row is not None
        else None
    )

    achievements_count = (
        db.query(XPEvent)
        .filter(
            XPEvent.user_id == current.id,
            XPEvent.event_type == "achievement",
            XPEvent.date >= start_dt,
            XPEvent.date < end_dt,
        )
        .count()
    )
    placements = (
        db.query(LeagueMembership)
        .filter(
            LeagueMembership.user_id == current.id,
            LeagueMembership.week_start >= start_dt,
            LeagueMembership.week_start < end_dt,
            LeagueMembership.rank.is_not(None),
        )
        .order_by(LeagueMembership.rank.asc(), LeagueMembership.week_start.desc())
        .all()
    )
    best_place = (
        {
            "rank": placements[0].rank,
            "week_start": placements[0].week_start.date().isoformat(),
            "division": placements[0].division,
        }
        if placements
        else None
    )

    duels = (
        db.query(Duel)
        .filter(
            Duel.status == DuelStatus.FINISHED.value,
            Duel.week_start >= start_dt,
            Duel.week_start < end_dt,
            or_(Duel.challenger_id == current.id, Duel.opponent_id == current.id),
        )
        .all()
    )
    duel_balance = {"wins": 0, "draws": 0, "losses": 0, "played": len(duels)}
    for duel in duels:
        if duel.winner_id is None:
            duel_balance["draws"] += 1
        elif duel.winner_id == current.id:
            duel_balance["wins"] += 1
        else:
            duel_balance["losses"] += 1

    active_dates = sorted(active_days)
    is_final = today > season.end
    return {
        "season": season.to_payload(zone),
        "state": "final" if is_final else "interim",
        "is_final": is_final,
        "metrics": {
            "total_km": round(sum(float(row.distance or 0.0) for row in season_activities) / 1000, 1),
            "total_hours": round(sum(float(row.moving_time or 0.0) for row in season_activities) / 3600, 1),
            "total_elevation": int(round(sum(float(row.elevation_gain or 0.0) for row in season_activities))),
            "total_workouts": len(season_activities),
            "total_xp": season_xp,
            "best_week": best_week,
            "longest_streak_days": longest_consecutive_streak(active_dates),
            "achievements_count": achievements_count,
            "best_league_place": best_place,
            "duels": duel_balance,
        },
    }


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
