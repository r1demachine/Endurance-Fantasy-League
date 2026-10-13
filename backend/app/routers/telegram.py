"""Telegram bot webhook, private account linking, uploads, and notifications."""
import asyncio
import base64
import hashlib
import hmac
import logging
import secrets
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..dependencies import get_current_user
from ..models import TelegramLinkAttempt, TelegramWebhookUpdate, User
from ..rate_limit import limiter
from ..services.telegram import (
    TelegramFileTooLarge,
    bot_configured,
    download_telegram_file,
    send_message,
)
from ..services.activity_upload import create_activity_from_upload

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/telegram", tags=["Telegram"])

LINK_TTL_MINUTES = 15
LINK_RATE_LIMIT = 5
LINK_WINDOW_MINUTES = 15
UPDATE_TTL_DAYS = 2
UPLOAD_SOURCE = "UPLOAD_TELEGRAM"
HELP_TEXT = (
    "Fantasy League бот\n\n"
    "/link КОД — привязать аккаунт (код из профиля на сайте)\n"
    "/notify on — явно включить уведомления\n"
    "/notify off — отключить уведомления\n"
    "/stop — отвязать и отключить уведомления\n"
    "/status — статус привязки\n\n"
    "Пришли .fit / .gpx / .tcx — загрузим тренировку (лимит 5 МБ)."
)


class NotifyToggleIn(BaseModel):
    enabled: bool


def _unlink_user(user: User) -> None:
    user.telegram_chat_id = None
    user.telegram_notify = False
    user.telegram_link_code = None
    user.telegram_link_expires = None


def _hash_link_code(code: str) -> str:
    return hashlib.sha256(code.strip().upper().encode("utf-8")).hexdigest()


def _new_link_code() -> str:
    # 10 random bytes -> 16 base32 characters, no padding; only SHA-256 is persisted.
    return base64.b32encode(secrets.token_bytes(10)).decode("ascii").rstrip("=")


def _latest_completed_week_start(today: date | None = None) -> date:
    today = today or date.today()
    current_week_start = today - timedelta(days=today.weekday())
    return current_week_start - timedelta(days=7)


def _record_failed_link_attempt(db: Session, chat_id: str) -> int:
    now = datetime.utcnow()
    cutoff = now - timedelta(minutes=LINK_WINDOW_MINUTES)
    db.query(TelegramLinkAttempt).filter(
        TelegramLinkAttempt.attempted_at < now - timedelta(days=1)
    ).delete(synchronize_session=False)
    count = db.query(TelegramLinkAttempt).filter(
        TelegramLinkAttempt.chat_id == chat_id,
        TelegramLinkAttempt.attempted_at >= cutoff,
    ).count()
    db.add(TelegramLinkAttempt(chat_id=chat_id, attempted_at=now))
    db.commit()
    return count + 1


def _failed_link_attempts(db: Session, chat_id: str) -> int:
    cutoff = datetime.utcnow() - timedelta(minutes=LINK_WINDOW_MINUTES)
    return db.query(TelegramLinkAttempt).filter(
        TelegramLinkAttempt.chat_id == chat_id,
        TelegramLinkAttempt.attempted_at >= cutoff,
    ).count()


@router.post("/link-code")
@limiter.limit("10/hour")
def create_link_code(
    request: Request,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate a one-time base32 linking code; persist only its hash for 15 minutes."""
    if not bot_configured():
        raise HTTPException(status_code=503, detail="Telegram-бот не настроен на сервере")
    code = _new_link_code()
    current.telegram_link_code = _hash_link_code(code)
    current.telegram_link_expires = datetime.utcnow() + timedelta(minutes=LINK_TTL_MINUTES)
    db.commit()
    settings = get_settings()
    return {
        "code": code,
        "expires_at": current.telegram_link_expires.isoformat() + "Z",
        "bot_username": settings.TELEGRAM_BOT_USERNAME,
        "linked": bool(current.telegram_chat_id),
        "notify": bool(current.telegram_notify),
        "instructions": f"Открой бота и отправь: /link {code}. Затем включи уведомления командой /notify on.",
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
    # This endpoint is an explicit user action and therefore serves as consent.
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
    if not hmac.compare_digest(header_value.encode("utf-8"), expected.encode("utf-8")):
        raise HTTPException(status_code=403, detail="Forbidden")


def _unmark_update_processed(db: Session, update_id: int) -> None:
    """Release a webhook claim after handler failure so Telegram can retry it."""
    try:
        db.query(TelegramWebhookUpdate).filter(
            TelegramWebhookUpdate.update_id == update_id
        ).delete(synchronize_session=False)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to release Telegram webhook claim update_id=%s", update_id)


def _mark_update_processed(db: Session, update_id: Any) -> bool:
    if isinstance(update_id, bool) or not isinstance(update_id, int) or update_id < 0:
        raise HTTPException(status_code=400, detail="Invalid or missing update_id")
    now = datetime.utcnow()
    cutoff = now - timedelta(days=UPDATE_TTL_DAYS)
    db.query(TelegramWebhookUpdate).filter(
        TelegramWebhookUpdate.processed_at < cutoff
    ).delete(synchronize_session=False)
    db.add(TelegramWebhookUpdate(update_id=update_id, processed_at=now))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return False
    return True


@router.post("/webhook")
async def telegram_webhook(
    request: Request,
    db: Session = Depends(get_db),
    x_telegram_bot_api_secret_token: Optional[str] = Header(default=None),
):
    if not bot_configured():
        raise HTTPException(status_code=503, detail="Bot not configured")
    _check_secret(x_telegram_bot_api_secret_token)
    try:
        update: dict[str, Any] = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON") from exc
    if not isinstance(update, dict):
        raise HTTPException(status_code=400, detail="Invalid update")
    update_id = update.get("update_id")
    # The SQLAlchemy session and claim operation are synchronous; keep the DB
    # call off the ASGI event loop.
    if not await run_in_threadpool(_mark_update_processed, db, update_id):
        return {"ok": True, "duplicate": True}

    try:
        # Do not process edited_message; it is a separate update from Telegram.
        message = update.get("message")
        if not isinstance(message, dict):
            return {"ok": True}
        chat = message.get("chat") or {}
        chat_id = str(chat.get("id") or "")
        chat_type = str(chat.get("type") or "")
        if not chat_id:
            return {"ok": True}

        text = (message.get("text") or "").strip()
        document = message.get("document")
        if text.startswith("/"):
            await _handle_command(db, chat_id, text, chat_type)
            return {"ok": True}
        if document:
            await _handle_document(db, chat_id, document)
            return {"ok": True}
        if text:
            await send_message(chat_id, HELP_TEXT)
        return {"ok": True}
    except Exception:
        await run_in_threadpool(db.rollback)
        await run_in_threadpool(_unmark_update_processed, db, update_id)
        raise


async def _handle_command(db: Session, chat_id: str, text: str, chat_type: str = "private") -> None:
    parts = text.split()
    command = parts[0].split("@")[0].lower()

    if command in ("/start", "/help"):
        await send_message(chat_id, HELP_TEXT)
        return

    if command == "/status":
        user = await run_in_threadpool(
            lambda: db.query(User).filter(User.telegram_chat_id == chat_id).first()
        )
        if not user:
            await send_message(chat_id, "Аккаунт не привязан. Получи код в профиле на сайте и отправь /link КОД.")
            return
        enabled = "вкл" if user.telegram_notify else "выкл"
        await send_message(
            chat_id,
            f"Привязан: @{user.username}\nУведомления: {enabled}\n"
            "/notify on — включить · /notify off — выключить\n/stop — отвязать",
        )
        return

    if command == "/stop":
        user = await run_in_threadpool(
            lambda: db.query(User).filter(User.telegram_chat_id == chat_id).first()
        )
        if user:
            await run_in_threadpool(_unlink_user, user)
            await run_in_threadpool(db.commit)
        await send_message(chat_id, "Привязка удалена, уведомления выключены. Чтобы снова связать — новый /link КОД из профиля.")
        return

    if command == "/notify":
        user = await run_in_threadpool(
            lambda: db.query(User).filter(User.telegram_chat_id == chat_id).first()
        )
        if not user:
            await send_message(chat_id, "Сначала привяжи аккаунт: /link КОД из профиля на сайте.")
            return
        if len(parts) < 2 or parts[1].lower() not in {"on", "off"}:
            await send_message(chat_id, "Используй /notify on или /notify off.")
            return
        enabled = parts[1].lower() == "on"
        await run_in_threadpool(setattr, user, "telegram_notify", enabled)
        await run_in_threadpool(db.commit)
        await send_message(chat_id, "Уведомления включены." if enabled else "Уведомления отключены.")
        return

    if command == "/link":
        if chat_type != "private":
            await send_message(chat_id, "Для безопасности /link можно использовать только в личном чате с ботом.")
            return
        if await run_in_threadpool(_failed_link_attempts, db, chat_id) >= LINK_RATE_LIMIT:
            await send_message(chat_id, "Слишком много неверных кодов. Попробуй через 15 минут.")
            return
        if len(parts) < 2:
            await send_message(chat_id, "Формат: /link КОД\nКод берётся в профиле на сайте (раздел Telegram).")
            return

        code = parts[1].strip().upper()
        now = datetime.utcnow()
        user = await run_in_threadpool(lambda: db.query(User).filter(
            User.telegram_link_code == _hash_link_code(code),
            User.telegram_link_expires.isnot(None),
            User.telegram_link_expires > now,
        ).first())
        if not user:
            await run_in_threadpool(_record_failed_link_attempt, db, chat_id)
            await send_message(chat_id, "Код неверный или истёк. Сгенерируй новый в профиле на сайте.")
            return

        other_owner = await run_in_threadpool(lambda: db.query(User).filter(
            User.telegram_chat_id == chat_id,
            User.id != user.id,
        ).first())
        if other_owner:
            await send_message(
                chat_id,
                "Этот Telegram уже привязан к другому аккаунту. Выполни /stop, затем повтори /link с новым кодом.",
            )
            return

        def _save_link():
            old = user.telegram_chat_id if user.telegram_chat_id and user.telegram_chat_id != chat_id else None
            user.telegram_chat_id = chat_id
            user.telegram_notify = False  # consent must be given separately
            user.telegram_link_code = None
            user.telegram_link_expires = None
            last_completed = _latest_completed_week_start()
            if user.telegram_last_notified_week is None or user.telegram_last_notified_week < last_completed:
                user.telegram_last_notified_week = last_completed
            db.commit()
            return old, user.username

        old_chat_id, username = await run_in_threadpool(_save_link)

        if old_chat_id:
            await send_message(
                str(old_chat_id),
                "Аккаунт Fantasy League перепривязан к другому Telegram. Уведомления на этом чате отключены.",
            )
        await send_message(
            chat_id,
            f"Готово! Привязан аккаунт @{username}.\n"
            "Уведомления пока выключены — включи их командой /notify on.\n"
            "Можно присылать .fit / .gpx / .tcx.\n"
            "/stop — отвязать.",
        )
        return

    await send_message(chat_id, HELP_TEXT)


async def _handle_document(db: Session, chat_id: str, document: dict) -> None:
    user = await run_in_threadpool(
        lambda: db.query(User).filter(User.telegram_chat_id == chat_id).first()
    )
    if not user:
        await send_message(chat_id, "Сначала привяжи аккаунт: /link КОД из профиля на сайте.")
        return

    settings = get_settings()
    if user.privacy_consent_version != settings.PRIVACY_CONSENT_VERSION or user.privacy_consent_at is None:
        await send_message(chat_id, "Нужно принять актуальную политику данных на сайте, затем загрузи файл снова.")
        return

    file_name = document.get("file_name") or "activity.fit"
    extension = Path(file_name).suffix.lower()
    from ..routers.upload import (
        ALLOWED_EXTENSIONS, MAX_FILE_BYTES,
        InvalidActivityFile, UnsupportedActivityFile, _parse_activity_file_bounded,
    )

    if extension not in ALLOWED_EXTENSIONS:
        await send_message(chat_id, "Поддерживаются только .fit, .gpx и .tcx.")
        return
    file_id = document.get("file_id")
    if not file_id:
        await send_message(chat_id, "Не удалось получить файл.")
        return

    try:
        content, _path = await download_telegram_file(file_id, max_bytes=MAX_FILE_BYTES)
    except TelegramFileTooLarge:
        await send_message(chat_id, "Размер файла превышает 5 МБ.")
        return
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
        parsed = await _parse_activity_file_bounded(
            content,
            extension,
            user.lthr,
            user.max_hr,
            user.resting_hr,
            user.timezone_name,
        )
    except TimeoutError:
        await send_message(chat_id, "Разбор файла занял слишком много времени.")
        return
    except (UnsupportedActivityFile, InvalidActivityFile) as exc:
        await send_message(chat_id, str(exc) or "Файл повреждён или формат не поддерживается.")
        return
    except Exception:
        await send_message(chat_id, "Не удалось прочитать тренировку из файла.")
        return

    before_xp = float(user.total_xp or 0)
    file_sha256 = hashlib.sha256(content).hexdigest()
    status, activity, reason = await run_in_threadpool(
        create_activity_from_upload,
        db,
        user,
        parsed,
        file_sha256,
        source=UPLOAD_SOURCE,
    )
    if status == "duplicate":
        await send_message(chat_id, reason or "Эта тренировка уже есть, повторно не сохранена.")
        return
    if status == "rejected" or activity is None:
        await send_message(chat_id, f"Не принято: {reason or 'не удалось сохранить тренировку.'}")
        return

    from ..services.xp import round_xp
    gained = round_xp(float(user.total_xp or 0) - before_xp)
    minutes = round((activity.moving_time or 0) / 60)
    started = activity.start_date.strftime("%d.%m.%Y %H:%M") if activity.start_date else "дата неизвестна"
    await send_message(
        chat_id,
        f"Сохранено: {activity.name or 'Тренировка'} · {started} · {minutes} мин\n"
        f"Нагрузка {round(float(activity.training_load or 0), 1)} · +{gained} XP · "
        f"всего {round_xp(user.total_xp or 0)} XP · LVL {user.level}",
    )
