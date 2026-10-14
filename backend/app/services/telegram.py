"""Telegram Bot API helpers: async networking, bounded downloads, and blocked-chat handling."""
import asyncio
import logging
from typing import Optional, Tuple

import httpx
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import SessionLocal
from ..models import User

logger = logging.getLogger("telegram")
MAX_TELEGRAM_FILE_BYTES = 5 * 1024 * 1024


class TelegramFileTooLarge(ValueError):
    """Telegram file download exceeded the byte limit."""


def bot_configured() -> bool:
    settings = get_settings()
    return bool(settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_WEBHOOK_SECRET)


def _api_url(method: str) -> str:
    token = get_settings().TELEGRAM_BOT_TOKEN
    return f"https://api.telegram.org/bot{token}/{method}"


def _unlink_blocked_chat(chat_id: str) -> None:
    db: Session = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_chat_id == str(chat_id)).first()
        if user:
            user.telegram_chat_id = None
            user.telegram_notify = False
            user.telegram_link_code = None
            user.telegram_link_expires = None
            db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.warning("could not unlink blocked Telegram chat (%s)", type(exc).__name__)
    finally:
        db.close()


def _response_payload(response: httpx.Response) -> dict:
    try:
        payload = response.json()
        return payload if isinstance(payload, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _retry_after(response: httpx.Response) -> int:
    payload = _response_payload(response)
    parameters = payload.get("parameters") if isinstance(payload.get("parameters"), dict) else {}
    value = parameters.get("retry_after") or response.headers.get("Retry-After") or 1
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 1


async def send_message(chat_id: str, text: str, parse_mode: Optional[str] = None) -> bool:
    if not bot_configured():
        return False
    payload = {"chat_id": str(chat_id), "text": text, "disable_web_page_preview": True}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            for attempt in range(3):
                response = await client.post(_api_url("sendMessage"), json=payload)
                body = _response_payload(response)
                api_status = int(body.get("error_code") or response.status_code)
                if api_status == 403:
                    _unlink_blocked_chat(str(chat_id))
                    logger.info("Telegram chat disabled after Bot API 403")
                    return False
                if api_status == 429:
                    if attempt == 2:
                        logger.warning("Telegram sendMessage rate limit retry exhausted")
                        return False
                    await asyncio.sleep(_retry_after(response))
                    continue
                if response.status_code >= 400 or body.get("ok") is False:
                    logger.warning("Telegram sendMessage failed: status=%s", api_status)
                    return False
                return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("telegram sendMessage error: %s", type(exc).__name__)
    return False


async def notify_telegram_user(db: Session, user_id: int, text: str) -> None:
    """Send only when an explicit notification consent and a chat binding exist."""
    user = db.get(User, user_id)
    if not user or not user.telegram_chat_id or not user.telegram_notify:
        return
    await send_message(str(user.telegram_chat_id), text)


async def download_telegram_file(
    file_id: str,
    max_bytes: int = MAX_TELEGRAM_FILE_BYTES,
) -> Tuple[bytes, str]:
    """Download into memory only, enforcing max_bytes while streaming each chunk."""
    if not bot_configured():
        raise RuntimeError("bot not configured")
    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=15.0, read=60.0, write=15.0, pool=15.0)) as client:
        meta = None
        for attempt in range(3):
            meta = await client.get(_api_url("getFile"), params={"file_id": file_id})
            if meta.status_code == 429:
                if attempt == 2:
                    meta.raise_for_status()
                await asyncio.sleep(_retry_after(meta))
                continue
            meta.raise_for_status()
            break
        data = _response_payload(meta)
        if not data.get("ok") or not isinstance(data.get("result"), dict):
            raise RuntimeError("getFile failed")
        file_path = data["result"].get("file_path")
        if not isinstance(file_path, str) or not file_path:
            raise RuntimeError("getFile did not return file_path")

        token = get_settings().TELEGRAM_BOT_TOKEN
        file_url = f"https://api.telegram.org/file/bot{token}/{file_path}"
        for attempt in range(3):
            delay = 0
            async with client.stream("GET", file_url) as response:
                if response.status_code == 429:
                    if attempt == 2:
                        response.raise_for_status()
                    delay = _retry_after(response)
                else:
                    response.raise_for_status()
                    chunks = []
                    total = 0
                    async for chunk in response.aiter_bytes():
                        total += len(chunk)
                        if total > max_bytes:
                            raise TelegramFileTooLarge(f"Telegram file exceeds {max_bytes} bytes")
                        chunks.append(chunk)
                    return b"".join(chunks), file_path
            await asyncio.sleep(delay)
    raise RuntimeError("Could not download Telegram file")
