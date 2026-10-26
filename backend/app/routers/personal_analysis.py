"""Private API for deterministic personal training and wellbeing trends."""
import logging
from datetime import datetime, time, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user
from ..auth import decrypt_secret, encrypt_secret, decode_access_token_claims
from ..config import get_settings
from ..rate_limit import limiter
from ..models import Activity, ActivityCheckIn, MorningCheckIn, User, Wellness
from ..services.personal_trends import build_personal_trends, local_today, resolve_timezone
from ..services.personal_interpretation import (
    PersonalInterpretationError,
    _model_input,
    generate_personal_interpretation,
)
from ..services.personal_ai_provider import (
    generate_custom_interpretation,
    test_custom_provider,
    validate_provider_base_url,
)

router = APIRouter(prefix="/api/personal-analysis", tags=["Personal analysis"])
logger = logging.getLogger(__name__)

class ConsentUpdate(BaseModel):
    consent: bool


class ProviderUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: Literal["server", "openai_compatible", "anthropic"]
    base_url: str | None = Field(default=None, max_length=500)
    model: str | None = Field(default=None, max_length=120)
    api_key: str | None = None


def _personal_analysis_user_key(request: Request) -> str:
    authorization = request.headers.get("authorization", "")
    token = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
    claims = decode_access_token_claims(token) if token else None
    if claims is not None:
        return f"personal-analysis-user:{claims[0]}"
    return f"personal-analysis-ip:{request.client.host if request.client else 'unknown'}"


def _provider_public_config(user: User) -> dict:
    encrypted = getattr(user, "ai_api_key_encrypted", None)
    last4 = None
    if encrypted:
        try:
            last4 = decrypt_secret(encrypted)[-4:]
        except Exception:
            last4 = None
    return {
        "provider": getattr(user, "ai_provider", None) or "server",
        "base_url": getattr(user, "ai_base_url", None),
        "model": getattr(user, "ai_model", None),
        "has_key": bool(encrypted and last4 is not None),
        "key_last4": last4,
    }


def _safe_provider_detail(category: str) -> str:
    return {
        "unsafe_destination": "Адрес провайдера отклонён: разрешены только публичные HTTPS-адреса.",
        "redirect_blocked": "Провайдер вернул перенаправление; оно заблокировано.",
        "invalid_content_type": "Провайдер вернул ответ не в формате JSON.",
        "response_too_large": "Ответ провайдера превышает лимит 256 КБ.",
        "timeout": "Провайдер не ответил за установленное время.",
        "connection_error": "Не удалось безопасно подключиться к провайдеру.",
        "invalid_response": "Провайдер вернул некорректный ответ.",
        "invalid_schema": "Провайдер вернул JSON неожиданного формата.",
        "unsupported_claim": "Ответ содержит неподтверждённые утверждения и не показан.",
        "upstream_http_error": "Провайдер отклонил запрос. Проверь ключ, модель и доступность API.",
        "invalid_base_url": "Укажи корректный HTTPS-адрес без логина, пароля и нестандартного порта.",
    }.get(category, "Не удалось выполнить запрос к AI-провайдеру.")


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




@router.get("/consent")
def get_ai_consent(current: User = Depends(get_current_user)):
    return {
        "consent": bool(getattr(current, "ai_analysis_consent", False)),
        "consent_at": current.ai_analysis_consent_at.isoformat() if getattr(current, "ai_analysis_consent_at", None) else None,
    }


@router.put("/consent")
def put_ai_consent(
    payload: ConsentUpdate,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    current.ai_analysis_consent = payload.consent
    current.ai_analysis_consent_at = datetime.now(timezone.utc).replace(tzinfo=None) if payload.consent else None
    if not payload.consent:
        current.ai_api_key_encrypted = None
        current.ai_provider = "server"
        current.ai_base_url = None
        current.ai_model = None
    db.add(current)
    db.commit()
    return {
        "consent": bool(current.ai_analysis_consent),
        "consent_at": current.ai_analysis_consent_at.isoformat() if current.ai_analysis_consent_at else None,
    }


@router.get("/payload-preview")
def get_ai_payload_preview(
    days: int = Query(default=28, ge=14, le=90),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return exactly the privacy-minimized object that is passed to a model."""
    trends = get_personal_trends(days=days, current=current, db=db)
    return _model_input(trends)


@router.get("/provider")
def get_ai_provider(current: User = Depends(get_current_user)):
    return _provider_public_config(current)


@router.put("/provider")
def put_ai_provider(
    payload: ProviderUpdate,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if payload.provider == "openai_compatible":
        if not payload.base_url:
            raise HTTPException(status_code=422, detail="Для OpenAI-совместимого провайдера нужен HTTPS-адрес.")
        try:
            current.ai_base_url = validate_provider_base_url(payload.base_url)
        except ValueError:
            raise HTTPException(status_code=422, detail="Адрес должен быть публичным HTTPS URL без учётных данных и порта кроме 443.")
        if not payload.model or not payload.model.strip():
            raise HTTPException(status_code=422, detail="Укажи модель провайдера.")
    elif payload.provider == "anthropic":
        if not payload.model or not payload.model.strip():
            raise HTTPException(status_code=422, detail="Укажи модель Claude.")
        current.ai_base_url = None
    else:
        current.ai_base_url = None
        current.ai_model = None
    if payload.model is not None and payload.provider != "server":
        model_name = payload.model.strip()
        if len(model_name) > 120 or not model_name:
            raise HTTPException(status_code=422, detail="Название модели должно содержать 1–120 символов.")
        current.ai_model = model_name
    if payload.api_key is not None and payload.api_key.strip():
        if len(payload.api_key) > 512:
            raise HTTPException(status_code=422, detail="API-ключ слишком длинный.")
        current.ai_api_key_encrypted = encrypt_secret(payload.api_key.strip())
    current.ai_provider = payload.provider
    db.add(current)
    db.commit()
    return _provider_public_config(current)


@router.delete("/provider")
def delete_ai_provider_key(
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    current.ai_api_key_encrypted = None
    db.add(current)
    db.commit()
    return _provider_public_config(current)


@router.post("/provider/test")
def test_ai_provider_configuration(current: User = Depends(get_current_user)):
    provider = getattr(current, "ai_provider", None) or "server"
    if provider == "server":
        raise HTTPException(status_code=400, detail="Для серверного провайдера отдельный тестовый ключ не нужен.")
    encrypted = getattr(current, "ai_api_key_encrypted", None)
    if not encrypted:
        raise HTTPException(status_code=400, detail="Сначала сохрани API-ключ.")
    try:
        test_custom_provider(
            provider=provider,
            api_key=decrypt_secret(encrypted),
            model=current.ai_model or "",
            base_url=current.ai_base_url,
            timeout_seconds=min(float(get_settings().GROQ_TIMEOUT_SECONDS), 30.0),
        )
    except PersonalInterpretationError as exc:
        logger.warning("Personal AI provider test failed: category=%s status=%s", exc.category, exc.upstream_status)
        raise HTTPException(status_code=502, detail=_safe_provider_detail(exc.category)) from exc
    except Exception as exc:
        logger.warning("Personal AI provider test failed: category=configuration_error")
        raise HTTPException(status_code=502, detail="Не удалось проверить конфигурацию провайдера.") from exc
    return {"status": "ok"}


@router.post("/interpretation")
@limiter.limit("30/day", key_func=_personal_analysis_user_key)
@limiter.limit("5/minute", key_func=_personal_analysis_user_key)
def post_personal_interpretation(
    request: Request,
    days: int = Query(default=28, ge=14, le=90),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Interpret aggregate trends only after explicit consent."""
    if not bool(getattr(current, "ai_analysis_consent", False)):
        raise HTTPException(status_code=403, detail="Сначала разреши отправку агрегированной статистики внешнему ИИ-сервису.")
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
    provider = getattr(current, "ai_provider", None) or "server"
    if provider != "server":
        encrypted = getattr(current, "ai_api_key_encrypted", None)
        if not encrypted:
            raise HTTPException(status_code=503, detail="Сначала сохрани API-ключ выбранного провайдера.")
        try:
            analysis = generate_custom_interpretation(
                trends,
                provider=provider,
                api_key=decrypt_secret(encrypted),
                model=current.ai_model or "",
                base_url=current.ai_base_url,
                timeout_seconds=min(float(settings.GROQ_TIMEOUT_SECONDS), 30.0),
            )
        except PersonalInterpretationError as exc:
            logger.warning("Personal interpretation failed: provider=%s category=%s status=%s quality_check=%s", provider, exc.category, exc.upstream_status, exc.quality_check or "none")
            raise HTTPException(status_code=502, detail=_safe_provider_detail(exc.category)) from exc
        return {
            "status": "ready",
            "provider": provider,
            "model": current.ai_model,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "period": {"days": trends["period"]["days"]},
            "analysis": analysis.model_dump(),
            "data_quality": {"coverage": trends["coverage"], "data_gaps": trends["data_gaps"]},
            "disclaimer": trends["disclaimer"],
        }

    if not getattr(settings, "PERSONAL_ANALYSIS_AI_ENABLED", False):
        raise HTTPException(
            status_code=503,
            detail="AI-анализ отключён настройкой PERSONAL_ANALYSIS_AI_ENABLED.",
        )
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
            "Personal interpretation failed: category=%s quality_check=%s upstream_status=%s upstream_error_code=%s retry_after_seconds=%s model=%s",
            exc.category,
            exc.quality_check or "none",
            exc.upstream_status,
            exc.upstream_error_code or "none",
            exc.retry_after_seconds if exc.retry_after_seconds is not None else "none",
            settings.GROQ_MODEL,
        )
        if exc.category == "unsupported_claim":
            detail = "Groq вернул неподтверждённое утверждение или проигнорировал пропуски. Ответ не показан; попробуй ещё раз."
        elif exc.category == "timeout":
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
            detail = "Groq временно ограничил запросы или исчерпан лимит токенов (HTTP 429). Не нажимай повторно подряд; проверь лимиты Groq и попробуй позже."
        elif exc.upstream_status is not None and exc.upstream_status >= 500:
            detail = f"Groq временно ответил ошибкой HTTP {exc.upstream_status}. Попробуй позже."
        elif exc.category in {"invalid_response", "invalid_schema"}:
            detail = "Groq ответил, но формат ответа оказался некорректным. Попробуй ещё раз."
        else:
            detail = "Не удалось получить корректный ответ AI-сервиса. Данные не изменены; попробуй позже."
        if exc.upstream_status == 429:
            headers = (
                {"Retry-After": str(exc.retry_after_seconds)}
                if exc.retry_after_seconds is not None
                else None
            )
            raise HTTPException(status_code=429, detail=detail, headers=headers) from exc
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
