"""Отправка сообщений в Telegram Bot API (httpx, без long polling)."""

import logging
from typing import Optional, Tuple

import httpx
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import User

logger = logging.getLogger("telegram")


def bot_configured() -> bool:
    s = get_settings()
    return bool(s.TELEGRAM_BOT_TOKEN and s.TELEGRAM_WEBHOOK_SECRET)


def _api_url(method: str) -> str:
    token = get_settings().TELEGRAM_BOT_TOKEN
    return f"https://api.telegram.org/bot{token}/{method}"


async def send_message(chat_id: str, text: str, parse_mode: Optional[str] = None) -> bool:
    if not bot_configured():
        return False
    payload = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(_api_url("sendMessage"), json=payload)
            if r.status_code >= 400:
                logger.warning("telegram sendMessage failed: %s", r.status_code)
                return False
            return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("telegram sendMessage error: %s", type(exc).__name__)
        return False


async def notify_telegram_user(db: Session, user_id: int, text: str) -> None:
    """Шлёт в TG только если привязан chat_id и telegram_notify=True."""
    user = db.get(User, user_id)
    if not user or not user.telegram_chat_id or not user.telegram_notify:
        return
    await send_message(str(user.telegram_chat_id), text)


async def download_telegram_file(file_id: str) -> Tuple[bytes, str]:
    """Скачивает файл по file_id. Возвращает (content, file_path_hint)."""
    if not bot_configured():
        raise RuntimeError("bot not configured")
    async with httpx.AsyncClient(timeout=30.0) as client:
        meta = await client.get(_api_url("getFile"), params={"file_id": file_id})
        meta.raise_for_status()
        data = meta.json()
        if not data.get("ok"):
            raise RuntimeError("getFile failed")
        file_path = data["result"]["file_path"]
        token = get_settings().TELEGRAM_BOT_TOKEN
        url = f"https://api.telegram.org/file/bot{token}/{file_path}"
        content_r = await client.get(url)
        content_r.raise_for_status()
        return content_r.content, file_path
