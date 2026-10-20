"""Private API for deterministic personal training and wellbeing trends."""
from datetime import datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user
from ..models import Activity, ActivityCheckIn, MorningCheckIn, User, Wellness
from ..services.personal_trends import build_personal_trends, local_today, resolve_timezone

router = APIRouter(prefix="/api/personal-analysis", tags=["Personal analysis"])


@router.get("/trends")
def get_personal_trends(
    days: int = Query(default=28, ge=14, le=90),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return data-backed comparisons for the authenticated user; no LLM is involved."""
    timezone_name = current.timezone_name or "UTC"
    zone, _ = resolve_timezone(timezone_name)
    today = local_today(timezone_name)
    period_start = today - timedelta(days=days - 1)
    period_end_exclusive = today + timedelta(days=1)

    local_start = datetime.combine(period_start, time.min)
    local_end = datetime.combine(period_end_exclusive, time.min)
    utc_start = datetime.combine(period_start, time.min, tzinfo=zone).astimezone(timezone.utc).replace(tzinfo=None)
    utc_end = datetime.combine(period_end_exclusive, time.min, tzinfo=zone).astimezone(timezone.utc).replace(tzinfo=None)

    morning_rows = (
        db.query(MorningCheckIn)
        .filter(
            MorningCheckIn.user_id == current.id,
            MorningCheckIn.local_date >= period_start,
            MorningCheckIn.local_date <= today,
        )
        .all()
    )
    wellness_rows = (
        db.query(Wellness)
        .filter(
            Wellness.user_id == current.id,
            Wellness.date >= period_start.isoformat(),
            Wellness.date <= today.isoformat(),
        )
        .all()
    )
    activity_rows = (
        db.query(Activity)
        .filter(
            Activity.user_id == current.id,
            or_(
                and_(
                    Activity.start_date_local >= local_start,
                    Activity.start_date_local < local_end,
                ),
                and_(
                    Activity.start_date >= utc_start,
                    Activity.start_date < utc_end,
                ),
            ),
        )
        .order_by(Activity.start_date_local.asc(), Activity.start_date.asc(), Activity.id.asc())
        .all()
    )

    activity_ids = [activity.id for activity in activity_rows]
    activity_checkin_rows = []
    if activity_ids:
        activity_checkin_rows = (
            db.query(ActivityCheckIn)
            .filter(
                ActivityCheckIn.user_id == current.id,
                ActivityCheckIn.activity_id.in_(activity_ids),
            )
            .all()
        )

    return build_personal_trends(
        user_id=current.id,
        timezone_name=timezone_name,
        today=today,
        days=days,
        morning_checkins=morning_rows,
        wellness_records=wellness_rows,
        activities=activity_rows,
        activity_checkins=activity_checkin_rows,
    )
