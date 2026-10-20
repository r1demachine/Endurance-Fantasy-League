"""Private API for deterministic personal training and wellbeing trends."""
import logging
from datetime import datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user
from ..config import get_settings
from ..rate_limit import limiter
from ..models import Activity, ActivityCheckIn, MorningCheckIn, User, Wellness
from ..services.personal_trends import build_personal_trends, local_today, resolve_timezone
from ..services.personal_interpretation import (
    PersonalInterpretationError,
    generate_personal_interpretation,
)

router = APIRouter(prefix="/api/personal-analysis", tags=["Personal analysis"])
logger = logging.getLogger(__name__)


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



@router.post("/interpretation")
@limiter.limit("5/minute")
def post_personal_interpretation(
    request: Request,
    days: int = Query(default=28, ge=14, le=90),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Interpret the current user's aggregate trends without storing the LLM response."""
    trends = get_personal_trends(days=days, current=current, db=db)

    if trends["status"] != "ready":
        return {
            "status": "insufficient_data",
            "analysis": None,
            "period": trends["period"],
            "data_gaps": trends["data_gaps"],
            "disclaimer": trends["disclaimer"],
            "message": "Пока недостаточно сопоставимых данных для персональной интерпретации.",
        }

    settings = get_settings()
    if not settings.GROQ_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="AI-анализ не настроен на сервере: добавь GROQ_API_KEY в переменные окружения backend.",
        )

    try:
        analysis = generate_personal_interpretation(
            trends,
            api_key=settings.GROQ_API_KEY,
            model=settings.GROQ_MODEL,
            timeout_seconds=settings.GROQ_TIMEOUT_SECONDS,
        )
    except PersonalInterpretationError as exc:
        # Diagnostic fields intentionally exclude the API key, user data, prompt and provider body.
        logger.warning(
            "Personal interpretation failed: category=%s upstream_status=%s model=%s",
            exc.category,
            exc.upstream_status,
            settings.GROQ_MODEL,
        )
        if exc.category == "timeout":
            detail = "Groq не ответил за установленное время. Попробуй позже или увеличь GROQ_TIMEOUT_SECONDS."
        elif exc.category == "connection_error":
            detail = "Backend не смог подключиться к Groq. Проверь сетевую доступность API."
        elif exc.upstream_status == 401:
            detail = "Groq отклонил авторизацию (HTTP 401). Проверь GROQ_API_KEY в Render и перезапусти сервис после сохранения."
        elif exc.upstream_status == 403:
            detail = "Groq запретил доступ (HTTP 403). Проверь права проекта, доступность модели и состояние биллинга Groq."
        elif exc.upstream_status == 400:
            detail = "Groq отклонил параметры запроса (HTTP 400). Проверь GROQ_MODEL и настройки запроса."
        elif exc.upstream_status == 404:
            detail = "Модель Groq не найдена или недоступна (HTTP 404). Проверь значение GROQ_MODEL."
        elif exc.upstream_status == 429:
            detail = "Groq вернул лимит запросов или исчерпание квоты (HTTP 429). Проверь лимиты и баланс проекта."
        elif exc.upstream_status is not None and exc.upstream_status >= 500:
            detail = f"Groq временно ответил ошибкой HTTP {exc.upstream_status}. Попробуй позже."
        elif exc.category in {"invalid_response", "invalid_schema"}:
            detail = "Groq ответил, но формат ответа оказался некорректным. Попробуй ещё раз."
        else:
            detail = "Не удалось получить корректный ответ AI-сервиса. Данные не изменены; попробуй позже."
        raise HTTPException(status_code=502, detail=detail) from exc

    return {
        "status": "ready",
        "provider": "groq",
        "model": settings.GROQ_MODEL,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "period": trends["period"],
        "analysis": analysis.model_dump(),
        "data_quality": {
            "coverage": trends["coverage"],
            "data_gaps": trends["data_gaps"],
        },
        "disclaimer": trends["disclaimer"],
    }
