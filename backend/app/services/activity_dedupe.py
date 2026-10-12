"""Cross-source activity duplicate matching by UTC/local start and duration."""
from datetime import datetime, timedelta
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from ..models import Activity

UPLOAD_SOURCES = ("UPLOAD_SITE", "UPLOAD_TELEGRAM")
ALL_ACTIVITY_SOURCES = ("INTERVALS", "UPLOAD_SITE", "UPLOAD_TELEGRAM")


def find_matching_activity(
    db: Session,
    user_id: int,
    start_date: datetime,
    start_date_local: datetime | None,
    moving_time: int,
    *,
    sources: tuple[str, ...] = ALL_ACTIVITY_SOURCES,
) -> Activity | None:
    """Match matching UTC timestamps or matching local wall-clock timestamps."""
    window = timedelta(minutes=5)
    time_conditions = [
        and_(
            Activity.start_date >= start_date - window,
            Activity.start_date <= start_date + window,
        )
    ]
    if start_date_local is not None:
        time_conditions.append(and_(
            Activity.start_date_local >= start_date_local - window,
            Activity.start_date_local <= start_date_local + window,
        ))
    min_duration = max(1, int(moving_time * 0.90))
    max_duration = max(min_duration, int(moving_time * 1.10))
    return (
        db.query(Activity)
        .filter(
            Activity.user_id == user_id,
            Activity.source.in_(sources),
            or_(*time_conditions),
            Activity.moving_time >= min_duration,
            Activity.moving_time <= max_duration,
        )
        .order_by(Activity.start_date.asc(), Activity.id.asc())
        .first()
    )
