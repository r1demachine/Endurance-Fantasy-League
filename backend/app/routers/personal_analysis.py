"""Private API for deterministic personal training and wellbeing trends."""
import logging
import re
from datetime import datetime, time, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user
from ..config import get_settings
from ..auth import decrypt_secret, encrypt_secret, decode_access_token_claims
from ..rate_limit import get_client_address, limiter
from ..models import Activity, ActivityCheckIn, MorningCheckIn, User, Wellness
from ..services.personal_trends import build_personal_trends, local_today, resolve_timezone
from ..services.personal_interpretation import (
    PersonalInterpretationError,
    _model_input,
    generate_custom_personal_interpretation,
    generate_personal_interpretation,
    test_custom_personal_ai_provider,
    validate_openai_base_url_syntax,
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



class ConsentUpdate(BaseModel):
    enabled: bool


class ProviderUpdate(BaseModel):
    provider: Literal["server", "openai_compatible", "anthropic"]
    base_url: str | None = Field(default=None, max_length=2048)
    model: str | None = Field(default=None, max_length=128)
    # Any avoids Pydantic echoing a rejected secret in validation errors; validate it manually below.
    api_key: Any = None

    @field_validator("base_url", "model", mode="before")
    @classmethod
    def trim_optional_values(cls, value):
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("Value must be a string")
        value = value.strip()
        return value or None


def _stored_user(db: Session, current: User) -> User:
    user = db.query(User).filter(User.id == current.id).first()
    if user is None:
        raise HTTPException(status_code=401, detail="Требуется авторизация.")
    return user


def _provider_public_state(user: User) -> dict:
    has_key = False
    key_last4 = None
    encrypted = getattr(user, "ai_api_key_encrypted", None)
    if encrypted:
        try:
            secret = decrypt_secret(encrypted)
            has_key = bool(secret)
            key_last4 = secret[-4:] if secret else None
        except Exception:
            # Never include encrypted content, plaintext key, or exception text in output/logs.
            has_key = False
            key_last4 = None
    return {
        "provider": user.ai_provider or "server",
        "base_url": user.ai_base_url,
        "model": user.ai_model,
        "has_key": has_key,
        "key_last4": key_last4,
    }


def _provider_error_detail(exc: PersonalInterpretationError) -> dict:
    """Return a fixed, credential-safe error category and message."""
    messages = {
        "invalid_configuration": "Проверь адрес, модель и API-ключ.",
        "invalid_endpoint": "Адрес должен начинаться с https://, не содержать логин/пароль и использовать порт 443.",
        "ssrf_blocked": "Адрес сервиса запрещён политикой сетевой безопасности.",
        "dns_resolution_failed": "Не удалось безопасно проверить адрес сервиса.",
        "redirect_blocked": "Сервис перенаправил запрос; переходы на другие адреса запрещены.",
        "invalid_content_type": "Сервис должен возвращать JSON с Content-Type application/json.",
        "response_too_large": "Ответ сервиса превысил разрешённый размер.",
        "timeout": "Сервис не ответил за отведённое время.",
        "connection_error": "Не удалось безопасно подключиться к AI-сервису.",
        "invalid_response": "AI-сервис вернул некорректный ответ.",
        "invalid_schema": "AI-сервис вернул ответ неожиданного формата.",
        "unsupported_claim": "Ответ содержал неподтверждённые числа или выводы; он не показан.",
        "provider_unauthorized": "Сервис отклонил API-ключ (401).",
        "provider_forbidden": "Сервис запретил доступ (403).",
        "provider_model_not_found": "Модель не найдена или недоступна (404).",
        "provider_rate_limited": "Сервис ограничил число запросов (429).",
        "provider_invalid_request": "Сервис отклонил параметры запроса (400).",
        "provider_unavailable": "AI-сервис временно недоступен.",
        "provider_http_error": "AI-сервис вернул ошибку.",
    }
    return {
        "category": exc.category,
        "message": messages.get(exc.category, "Не удалось получить корректный ответ AI-сервиса."),
    }


def _personal_analysis_user_rate_key(request: Request) -> str:
    """Apply the daily quota by the authenticated user ID, not the shared proxy IP."""
    authorization = request.headers.get("authorization", "")
    scheme, separator, token = authorization.partition(" ")
    if separator and scheme.lower() == "bearer" and token.strip():
        claims = decode_access_token_claims(token.strip())
        if claims is not None:
            return f"personal-analysis-user:{claims[0]}"
    return "personal-analysis-client:" + get_client_address(request)


def _require_ai_consent(db: Session, current: User) -> User:
    user = _stored_user(db, current)
    if not bool(user.ai_analysis_consent):
        raise HTTPException(
            status_code=403,
            detail="Чтобы отправить агрегированную статистику во внешний ИИ-сервис, сначала явно разреши ИИ-анализ в настройках.",
        )
    return user


@router.get("/consent")
def get_personal_analysis_consent(
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user = _stored_user(db, current)
    return {
        "enabled": bool(user.ai_analysis_consent),
        "consent_at": user.ai_analysis_consent_at.isoformat() if user.ai_analysis_consent_at else None,
    }


@router.put("/consent")
def put_personal_analysis_consent(
    payload: ConsentUpdate,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user = _stored_user(db, current)
    if payload.enabled:
        if not user.ai_analysis_consent:
            user.ai_analysis_consent_at = datetime.now(timezone.utc).replace(tzinfo=None)
        user.ai_analysis_consent = True
    else:
        # Withdrawal is immediate: erase credentials and all saved user-provider configuration.
        user.ai_analysis_consent = False
        user.ai_analysis_consent_at = None
        user.ai_api_key_encrypted = None
        user.ai_provider = "server"
        user.ai_base_url = None
        user.ai_model = None
    db.add(user)
    db.commit()
    db.refresh(user)
    return {
        "enabled": bool(user.ai_analysis_consent),
        "consent_at": user.ai_analysis_consent_at.isoformat() if user.ai_analysis_consent_at else None,
    }


@router.get("/payload-preview")
def get_personal_analysis_payload_preview(
    days: int = Query(default=28, ge=14, le=90),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return precisely the allow-listed JSON body sent to the model, with no external request."""
    trends = get_personal_trends(days=days, current=current, db=db)
    return _model_input(trends)


@router.get("/provider")
def get_personal_analysis_provider(
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _provider_public_state(_stored_user(db, current))


@router.put("/provider")
def put_personal_analysis_provider(
    payload: ProviderUpdate,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user = _stored_user(db, current)
    if payload.provider == "server":
        user.ai_provider = "server"
        user.ai_base_url = None
        user.ai_model = None
        # Selecting server mode also deletes the personal key so it cannot be reused accidentally.
        user.ai_api_key_encrypted = None
    else:
        model = payload.model or user.ai_model
        if not model or len(model) > 128:
            raise HTTPException(status_code=422, detail="Укажи название модели длиной до 128 символов.")
        if payload.provider == "openai_compatible":
            base_url = payload.base_url or user.ai_base_url
            if not base_url:
                raise HTTPException(status_code=422, detail="Укажи HTTPS-адрес OpenAI-совместимого API.")
            try:
                base_url = validate_openai_base_url_syntax(base_url)
            except PersonalInterpretationError as exc:
                raise HTTPException(status_code=422, detail=_provider_error_detail(exc)) from None
            user.ai_base_url = base_url
        else:
            # Anthropic endpoint is fixed in backend; never accept a user-controlled base URL.
            user.ai_base_url = None

        if payload.api_key is not None and not isinstance(payload.api_key, str):
            raise HTTPException(status_code=422, detail="API-ключ должен быть текстовой строкой.")
        supplied_key = payload.api_key.strip() if isinstance(payload.api_key, str) else ""
        if supplied_key:
            if len(supplied_key) > 512 or any(ord(char) < 32 or ord(char) == 127 for char in supplied_key):
                raise HTTPException(status_code=422, detail="API-ключ должен быть не длиннее 512 символов и не содержать управляющие символы.")

        endpoint_changed = (
            (user.ai_provider or "server") != payload.provider
            or (
                payload.provider == "openai_compatible"
                and (user.ai_base_url or "") != (base_url or "")
            )
        )
        if endpoint_changed and not supplied_key:
            raise HTTPException(
                status_code=422,
                detail="При смене провайдера или адреса требуется новый API-ключ, чтобы не отправить прежний ключ другому сервису.",
            )
        if supplied_key:
            user.ai_api_key_encrypted = encrypt_secret(supplied_key)
        if not user.ai_api_key_encrypted:
            raise HTTPException(status_code=422, detail="Добавь API-ключ для выбранного ИИ-сервиса.")
        user.ai_provider = payload.provider
        user.ai_model = model

    db.add(user)
    db.commit()
    db.refresh(user)
    return _provider_public_state(user)


@router.delete("/provider")
def delete_personal_analysis_provider_key(
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user = _stored_user(db, current)
    user.ai_api_key_encrypted = None
    db.add(user)
    db.commit()
    db.refresh(user)
    return _provider_public_state(user)


@router.post("/provider/test")
def test_personal_analysis_provider(
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Test an external custom provider with a generic prompt containing no user information."""
    user = _stored_user(db, current)
    if user.ai_provider not in {"openai_compatible", "anthropic"}:
        raise HTTPException(status_code=400, detail={"category": "invalid_configuration", "message": "Выбери собственный API-сервис."})
    if not user.ai_api_key_encrypted or not user.ai_model:
        raise HTTPException(status_code=422, detail={"category": "invalid_configuration", "message": "Сначала сохрани ключ и модель."})
    try:
        key = decrypt_secret(user.ai_api_key_encrypted)
        test_custom_personal_ai_provider(
            provider=user.ai_provider,
            api_key=key,
            model=user.ai_model,
            base_url=user.ai_base_url,
            timeout_seconds=min(float(get_settings().GROQ_TIMEOUT_SECONDS or 20), 30.0),
        )
    except PersonalInterpretationError as exc:
        safe = _provider_error_detail(exc)
        status_code = 400 if exc.category in {"invalid_configuration", "invalid_endpoint", "ssrf_blocked"} else 502
        raise HTTPException(status_code=status_code, detail=safe) from None
    except Exception:
        raise HTTPException(status_code=502, detail={"category": "provider_error", "message": "Проверка подключения не удалась."}) from None
    return {"status": "ok"}


@router.post("/interpretation")
@limiter.limit("5/minute")
@limiter.limit("30/day", key_func=_personal_analysis_user_rate_key)
def post_personal_interpretation(
    request: Request,
    days: int = Query(default=28, ge=14, le=90),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Send only consented aggregate trends to the selected provider; never persist its response."""
    # Check consent before calculating the request body or contacting any external service.
    user = _require_ai_consent(db, current)
    trends = get_personal_trends(days=days, current=user, db=db)

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
    provider = user.ai_provider or "server"
    model = settings.GROQ_MODEL if provider == "server" else user.ai_model
    public_provider = "groq" if provider == "server" else provider

    if provider == "server":
        if not settings.PERSONAL_ANALYSIS_AI_ENABLED:
            raise HTTPException(
                status_code=503,
                detail="Серверный ИИ-анализ отключён настройкой PERSONAL_ANALYSIS_AI_ENABLED.",
            )
        if not settings.GROQ_API_KEY:
            raise HTTPException(
                status_code=503,
                detail="Серверный ИИ-анализ пока не настроен.",
            )
        generate = lambda: generate_personal_interpretation(
            trends,
            api_key=settings.GROQ_API_KEY,
            model=settings.GROQ_MODEL,
            timeout_seconds=min(float(settings.GROQ_TIMEOUT_SECONDS or 20), 30.0),
        )
    else:
        if provider not in {"openai_compatible", "anthropic"} or not user.ai_api_key_encrypted or not user.ai_model:
            raise HTTPException(status_code=503, detail="Настройки собственного ИИ-сервиса неполны.")
        if provider == "openai_compatible" and not user.ai_base_url:
            raise HTTPException(status_code=503, detail="Не задан HTTPS-адрес собственного ИИ-сервиса.")
        try:
            user_key = decrypt_secret(user.ai_api_key_encrypted)
        except Exception:
            raise HTTPException(status_code=503, detail="Не удалось расшифровать сохранённый ключ; удали его и сохрани заново.") from None
        generate = lambda: generate_custom_personal_interpretation(
            trends,
            provider=provider,
            api_key=user_key,
            model=user.ai_model,
            base_url=user.ai_base_url,
            timeout_seconds=min(float(settings.GROQ_TIMEOUT_SECONDS or 20), 30.0),
        )

    try:
        analysis = generate()
    except PersonalInterpretationError as exc:
        logger.warning(
            "Personal interpretation failed: provider=%s category=%s quality_check=%s upstream_status=%s upstream_error_code=%s retry_after_seconds=%s",
            public_provider,
            exc.category,
            exc.quality_check or "none",
            exc.upstream_status,
            exc.upstream_error_code or "none",
            exc.retry_after_seconds if exc.retry_after_seconds is not None else "none",
        )
        safe = _provider_error_detail(exc)
        status_code = 429 if exc.category in {"provider_rate_limited"} or exc.upstream_status == 429 else 502
        if exc.upstream_status == 429 and exc.retry_after_seconds is not None:
            raise HTTPException(status_code=429, detail=safe, headers={"Retry-After": str(exc.retry_after_seconds)}) from None
        raise HTTPException(status_code=status_code, detail=safe) from None
    except Exception:
        logger.warning("Personal interpretation failed: provider=%s category=internal_error", public_provider)
        raise HTTPException(status_code=502, detail={"category": "internal_error", "message": "Не удалось получить корректный ответ AI-сервиса."}) from None

    return {
        "status": "ready",
        "provider": public_provider,
        "model": model,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "period": trends["period"],
        "analysis": analysis.model_dump(),
        "data_quality": {
            "coverage": trends["coverage"],
            "data_gaps": trends["data_gaps"],
        },
        "disclaimer": trends["disclaimer"],
    }
