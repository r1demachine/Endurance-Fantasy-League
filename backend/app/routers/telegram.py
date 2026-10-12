"""Telegram-бот: webhook, привязка /link, загрузка тренировок, /stop."""
import asyncio
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..dependencies import get_current_user
from ..models import Activity, User
from ..rate_limit import limiter
from ..services.telegram import bot_configured, download_telegram_file, send_message

router = APIRouter(prefix="/api/telegram", tags=["Telegram"])

LINK_TTL_MINUTES = 15
UPLOAD_SOURCE = "UPLOAD_TELEGRAM"
HELP_TEXT = (
    "Fantasy League бот\n\n"
    "/link КОД — привязать аккаунт (код из профиля на сайте)\n"
    "/stop — отвязать и отключить уведомления\n"
    "/status — статус привязки\n\n"
    "Пришли .fit / .gpx / .tcx — загрузим тренировку (лимиты как на сайте)."
)


class NotifyToggleIn(BaseModel):
    enabled: bool


def _unlink_user(user: User) -> None:
    user.telegram_chat_id = None
    user.telegram_notify = False
    user.telegram_link_code = None
    user.telegram_link_expires = None


@router.post("/link-code")
@limiter.limit("10/hour")
def create_link_code(
    request: Request,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Одноразовый код для /link в боте. Живёт 15 минут."""
    if not bot_configured():
        raise HTTPException(status_code=503, detail="Telegram-бот не настроен на сервере")
    code = secrets.token_hex(3).upper()
    current.telegram_link_code = code
    current.telegram_link_expires = datetime.utcnow() + timedelta(minutes=LINK_TTL_MINUTES)
    db.commit()
    settings = get_settings()
    return {
        "code": code,
        "expires_at": current.telegram_link_expires.isoformat() + "Z",
        "bot_username": settings.TELEGRAM_BOT_USERNAME,
        "linked": bool(current.telegram_chat_id),
        "notify": bool(current.telegram_notify),
        "instructions": f"Открой бота и отправь: /link {code}",
    }


@router.get("/status")
def telegram_status(current: User = Depends(get_current_user)):
    settings = get_settings()
    return {
        "bot_configured": bot_configured(),
        "bot_username": settings.TELEGRAM_BOT_USERNAME,
        "linked": bool(current.telegram_chat_id),
        "notify": bool(current.telegram_notify),
        "has_pending_code": bool(
            current.telegram_link_code
            and current.telegram_link_expires
            and current.telegram_link_expires > datetime.utcnow()
        ),
    }


@router.post("/notify")
def set_notify(
    data: NotifyToggleIn,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not current.telegram_chat_id:
        raise HTTPException(status_code=400, detail="Сначала привяжи Telegram через /link")
    current.telegram_notify = bool(data.enabled)
    db.commit()
    return {"notify": current.telegram_notify}


@router.post("/unlink")
async def unlink_telegram(
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    chat_id = current.telegram_chat_id
    _unlink_user(current)
    db.commit()
    if chat_id:
        await send_message(str(chat_id), "Привязка снята с сайта. Уведомления отключены.")
    return {"linked": False, "notify": False}


def _check_secret(header_value: Optional[str]) -> None:
    expected = get_settings().TELEGRAM_WEBHOOK_SECRET or ""
    if not expected or not header_value:
        raise HTTPException(status_code=403, detail="Forbidden")
    if not hmac.compare_digest(header_value, expected):
        raise HTTPException(status_code=403, detail="Forbidden")


@router.post("/webhook")
async def telegram_webhook(
    request: Request,
    db: Session = Depends(get_db),
    x_telegram_bot_api_secret_token: Optional[str] = Header(default=None),
):
    """Единственная точка входа бота. Без long polling."""
    if not bot_configured():
        raise HTTPException(status_code=503, detail="Bot not configured")
    _check_secret(x_telegram_bot_api_secret_token)

    try:
        update: dict[str, Any] = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    message = update.get("message") or update.get("edited_message")
    if not message:
        return {"ok": True}

    chat = message.get("chat") or {}
    chat_id = str(chat.get("id") or "")
    if not chat_id:
        return {"ok": True}

    text = (message.get("text") or "").strip()
    document = message.get("document")

    if text.startswith("/"):
        await _handle_command(db, chat_id, text)
        return {"ok": True}

    if document:
        await _handle_document(db, chat_id, document)
        return {"ok": True}

    if text:
        await send_message(chat_id, HELP_TEXT)
    return {"ok": True}


async def _handle_command(db: Session, chat_id: str, text: str) -> None:
    parts = text.split()
    cmd = parts[0].split("@")[0].lower()

    if cmd in ("/start", "/help"):
        await send_message(chat_id, HELP_TEXT)
        return

    if cmd == "/status":
        user = db.query(User).filter(User.telegram_chat_id == chat_id).first()
        if not user:
            await send_message(chat_id, "Аккаунт не привязан. Получи код в профиле на сайте и отправь /link КОД")
            return
        flag = "вкл" if user.telegram_notify else "выкл"
        await send_message(chat_id, f"Привязан: @{user.username}\nУведомления: {flag}\n/stop — отвязать")
        return

    if cmd == "/stop":
        user = db.query(User).filter(User.telegram_chat_id == chat_id).first()
        if user:
            _unlink_user(user)
            db.commit()
        await send_message(chat_id, "Привязка удалена, уведомления выключены. Чтобы снова связать — новый /link КОД из профиля.")
        return

    if cmd == "/link":
        if len(parts) < 2:
            await send_message(chat_id, "Формат: /link КОД\nКод берётся в профиле на сайте (раздел Telegram).")
            return
        code = parts[1].strip().upper()
        user = (
            db.query(User)
            .filter(
                User.telegram_link_code == code,
                User.telegram_link_expires.isnot(None),
                User.telegram_link_expires > datetime.utcnow(),
            )
            .first()
        )
        if not user:
            await send_message(chat_id, "Код неверный или истёк. Сгенерируй новый в профиле на сайте.")
            return
        other = db.query(User).filter(User.telegram_chat_id == chat_id, User.id != user.id).first()
        if other:
            _unlink_user(other)
        user.telegram_chat_id = chat_id
        user.telegram_notify = True
        user.telegram_link_code = None
        user.telegram_link_expires = None
        db.commit()
        await send_message(
            chat_id,
            f"Готово! Привязан аккаунт @{user.username}.\n"
            "Уведомления включены (итоги недели, дуэли).\n"
            "Можно присылать .fit / .gpx / .tcx.\n"
            "/stop — отвязать.",
        )
        return

    await send_message(chat_id, HELP_TEXT)


async def _handle_document(db: Session, chat_id: str, document: dict) -> None:
    user = db.query(User).filter(User.telegram_chat_id == chat_id).first()
    if not user:
        await send_message(chat_id, "Сначала привяжи аккаунт: /link КОД из профиля на сайте.")
        return

    settings = get_settings()
    if (
        user.privacy_consent_version != settings.PRIVACY_CONSENT_VERSION
        or user.privacy_consent_at is None
    ):
        await send_message(chat_id, "Нужно принять актуальную политику данных на сайте, затем загрузи файл снова.")
        return

    file_name = document.get("file_name") or "activity.fit"
    extension = Path(file_name).suffix.lower()
    from ..routers.upload import (
        ALLOWED_EXTENSIONS,
        MAX_FILE_BYTES,
        PARSE_TIMEOUT_SECONDS,
        InvalidActivityFile,
        UnsupportedActivityFile,
        _find_intervals_duplicate,
        _parse_activity_file,
    )

    if extension not in ALLOWED_EXTENSIONS:
        await send_message(chat_id, "Поддерживаются только .fit, .gpx и .tcx.")
        return

    file_size = int(document.get("file_size") or 0)
    if file_size > MAX_FILE_BYTES:
        await send_message(chat_id, "Размер файла превышает 5 МБ.")
        return

    file_id = document.get("file_id")
    if not file_id:
        await send_message(chat_id, "Не удалось получить файл.")
        return

    try:
        content, _path = await download_telegram_file(file_id)
    except Exception:
        await send_message(chat_id, "Не удалось скачать файл из Telegram.")
        return

    if not content:
        await send_message(chat_id, "Файл пустой.")
        return
    if len(content) > MAX_FILE_BYTES:
        await send_message(chat_id, "Размер файла превышает 5 МБ.")
        return

    try:
        parsed = await asyncio.wait_for(
            asyncio.to_thread(
                _parse_activity_file, content, extension, user.lthr, user.max_hr, user.resting_hr
            ),
            timeout=PARSE_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        await send_message(chat_id, "Разбор файла занял слишком много времени.")
        return
    except UnsupportedActivityFile as exc:
        await send_message(chat_id, str(exc) or "Формат файла не поддерживается.")
        return
    except InvalidActivityFile as exc:
        await send_message(chat_id, str(exc) or "Файл повреждён или неполный.")
        return
    except Exception:
        await send_message(chat_id, "Не удалось прочитать тренировку из файла.")
        return

    try:
        start_date = datetime.fromisoformat(str(parsed["start_date"]))
        if start_date.tzinfo is not None:
            start_date = start_date.astimezone(timezone.utc).replace(tzinfo=None)
        moving_time = int(parsed["moving_time"])
        elapsed_time = int(parsed.get("elapsed_time") or moving_time)
        distance = max(0.0, float(parsed.get("distance") or 0.0))
        elevation = max(0.0, float(parsed.get("elevation_gain") or 0.0))
        training_load = max(0.0, float(parsed["training_load"]))
        intensity = min(1.5, max(0.3, float(parsed["intensity"])))
        hard_secs = max(0, int(parsed.get("hard_secs") or 0))
    except (TypeError, ValueError, KeyError, OverflowError):
        await send_message(chat_id, "Данные тренировки повреждены.")
        return

    if moving_time <= 0 or moving_time > 7 * 24 * 3600:
        await send_message(chat_id, "Некорректная длительность тренировки.")
        return

    nonce = secrets.token_hex(16)
    activity_id = f"{UPLOAD_SOURCE}:{nonce}"
    if db.query(Activity).filter(
        Activity.user_id == user.id, Activity.intervals_activity_id == activity_id
    ).first():
        await send_message(chat_id, "Эта тренировка уже была сохранена.")
        return

    duplicate = _find_intervals_duplicate(db, user.id, start_date, moving_time)
    if duplicate:
        when = duplicate.start_date.strftime("%d.%m.%Y %H:%M") if duplicate.start_date else "—"
        mins = round((duplicate.moving_time or 0) / 60)
        await send_message(
            chat_id,
            f"Похожая тренировка уже есть в базе ({when}, ~{mins} мин). Дубликат не сохранён.",
        )
        return

    from ..services.xp import round_xp
    from .sync import _recalculate_user_xp, _recalculate_user_xp_v6

    before_xp = float(user.total_xp or 0)
    average_hr = parsed.get("average_heartrate")
    maximum_hr = parsed.get("max_heartrate")
    activity = Activity(
        user_id=user.id,
        intervals_activity_id=activity_id,
        source=UPLOAD_SOURCE,
        name=None,
        sport_type=str(parsed.get("sport_type") or "RIDE"),
        distance=distance,
        moving_time=moving_time,
        elapsed_time=elapsed_time,
        elevation_gain=elevation,
        average_speed=(distance / moving_time) if distance and moving_time else None,
        average_heartrate=float(average_hr) if average_hr is not None else None,
        max_heartrate=float(maximum_hr) if maximum_hr is not None else None,
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
        db.flush()
        if get_settings().XP_ENGINE == "v6":
            _recalculate_user_xp_v6(db, user)
        else:
            _recalculate_user_xp(db, user)
        db.commit()
    except Exception:
        db.rollback()
        await send_message(chat_id, "Ошибка сохранения. Попробуй позже.")
        return

    db.refresh(activity)
    db.refresh(user)
    gained = round_xp(float(user.total_xp or 0) - before_xp)
    mins = round(moving_time / 60)
    await send_message(
        chat_id,
        f"Тренировка сохранена.\n"
        f"{mins} мин · нагрузка {round(training_load, 1)}\n"
        f"+{gained} XP · всего {round_xp(user.total_xp or 0)} XP · LVL {user.level}",
    )
