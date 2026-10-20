"""Completed weekly recaps for the authenticated athlete."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user
from ..models import (
    Activity,
    Duel,
    DuelStatus,
    LeagueMembership,
    User,
    WeeklySummary,
    XPEvent,
)
from ..services.seasons import local_date

router = APIRouter(prefix="/api", tags=["Recaps"])


def monday_for(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _not_available(week_start: date, reason: str) -> dict:
    return {
        "available": False,
        "finalized": False,
        "week_start": week_start.isoformat(),
        "reason": reason,
    }


@router.get("/week-recap")
def get_week_recap(
    week_start: date | None = Query(default=None),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the finalized weekly result; never expose another athlete's records."""
    today = local_date(current.timezone_name or "UTC")
    current_week = monday_for(today)
    selected_week = monday_for(week_start or (current_week - timedelta(days=7)))
    selected_dt = datetime.combine(selected_week, datetime.min.time())
    next_dt = selected_dt + timedelta(days=7)

    if selected_week >= current_week:
        return _not_available(selected_week, "week_not_completed")

    summary = (
        db.query(WeeklySummary)
        .filter(
            WeeklySummary.user_id == current.id,
            WeeklySummary.week_start == selected_dt,
        )
        .first()
    )
    if summary is None:
        return _not_available(selected_week, "summary_missing")
    if not bool(summary.finalized):
        return _not_available(selected_week, "week_not_finalized")

    activities = (
        db.query(Activity)
        .filter(
            Activity.user_id == current.id,
            func.coalesce(Activity.start_date_local, Activity.start_date) >= selected_dt,
            func.coalesce(Activity.start_date_local, Activity.start_date) < next_dt,
        )
        .order_by(func.coalesce(Activity.start_date_local, Activity.start_date).asc(), Activity.id.asc())
        .all()
    )
    events = (
        db.query(XPEvent)
        .filter(
            XPEvent.user_id == current.id,
            XPEvent.week_start == selected_dt,
        )
        .order_by(XPEvent.date.asc(), XPEvent.id.asc())
        .all()
    )

    activity_days: set[date] = set()
    for activity in activities:
        stamp = activity.start_date_local or activity.start_date
        if stamp is not None:
            activity_days.add(stamp.date())

    # Reuse the dashboard's canonical daily ledger. Weekly-only awards must not be
    # arbitrarily attributed to the date stored on their XPEvent row.
    from ..services.day_ledger import build_day_ledger

    day_totals: dict[date, float] = {}
    best_day_candidates = set(activity_days)
    for offset in range(7):
        day = selected_week + timedelta(days=offset)
        ledger = build_day_ledger(db, current, day)
        day_total = float((ledger.get("xp") or {}).get("total") or 0.0)
        day_totals[day] = day_total
        if day_total > 0:
            best_day_candidates.add(day)

    best_day_date = (
        max(best_day_candidates, key=lambda day: (day_totals.get(day, 0.0), day))
        if best_day_candidates
        else None
    )
    best_day = None
    if best_day_date is not None:
        best_day = {
            "date": best_day_date.isoformat(),
            "label": best_day_date.strftime("%d.%m"),
            "xp": round(day_totals.get(best_day_date, 0.0), 1),
        }

    achievements = [
        {
            "id": event.id,
            "title": event.title or "Достижение",
            "xp": round(float(event.amount or 0.0), 1),
            "date": event.date.date().isoformat() if event.date else None,
        }
        for event in events
        if event.event_type == "achievement"
    ]

    membership = (
        db.query(LeagueMembership)
        .filter(
            LeagueMembership.user_id == current.id,
            LeagueMembership.week_start == selected_dt,
        )
        .first()
    )

    duel = (
        db.query(Duel)
        .filter(
            Duel.week_start == selected_dt,
            Duel.status == DuelStatus.FINISHED.value,
            or_(Duel.challenger_id == current.id, Duel.opponent_id == current.id),
        )
        .order_by(Duel.finished_at.desc(), Duel.id.desc())
        .first()
    )
    duel_result = None
    if duel is not None:
        other_id = duel.opponent_id if duel.challenger_id == current.id else duel.challenger_id
        other = db.get(User, other_id)
        mine = duel.challenger_xp if duel.challenger_id == current.id else duel.opponent_xp
        theirs = duel.opponent_xp if duel.challenger_id == current.id else duel.challenger_xp
        if duel.winner_id is None:
            outcome = "draw"
        elif duel.winner_id == current.id:
            outcome = "win"
        else:
            outcome = "loss"
        duel_result = {
            "id": duel.id,
            "status": duel.status,
            "outcome": outcome,
            "other_name": (other.display_name or other.username) if other else "Соперник",
            "my_xp": round(float(mine or 0.0), 1),
            "other_xp": round(float(theirs or 0.0), 1),
            "is_no_activity_draw": bool(duel.is_no_activity_draw),
        }

    tiles = {
        "effort": round(float(summary.effort_xp or 0.0), 1),
        "goal": round(float(summary.goal_xp or 0.0), 1),
        "consistency": round(float(summary.consistency_xp or 0.0), 1),
        "quality": round(float(summary.quality_xp or 0.0), 1),
        "recovery": round(float(summary.recovery_xp or 0.0), 1),
        "quests": round(float(summary.quest_xp or 0.0), 1),
    }
    return {
        "available": True,
        "finalized": True,
        "week_start": selected_week.isoformat(),
        "week_end": (selected_week + timedelta(days=6)).isoformat(),
        "total_xp": round(float(summary.total_xp or 0.0), 1),
        "tiles": tiles,
        "goal_percent": round(float(summary.completion_ratio or 0.0) * 100, 1),
        "target_load": round(float(summary.target_load or 0.0), 1),
        "actual_load": round(float(summary.actual_load or 0.0), 1),
        "training_days": int(summary.training_days or 0),
        "workout_days": len(activity_days),
        "workouts_count": len(activities),
        "best_day": best_day,
        "achievements": achievements,
        "achievements_count": len(achievements),
        "league_rank": membership.rank if membership is not None else None,
        "league_division": membership.division if membership is not None else summary.division,
        "duel": duel_result,
    }
