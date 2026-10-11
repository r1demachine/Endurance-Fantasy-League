"""Email verification and password-reset codes sent through the Resend HTTP API.

Only an HMAC digest of each one-time code is persisted. Email bodies are generated in
memory and are never stored by this application.
"""
import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta

import httpx
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import EmailCode

logger = logging.getLogger(__name__)

CODE_TTL = timedelta(minutes=10)
CODE_MIN_SEND_INTERVAL = timedelta(seconds=60)
MAX_CODE_ATTEMPTS = 5


class EmailDeliveryError(RuntimeError):
    """The email provider did not accept the message."""


class EmailRateLimitError(RuntimeError):
    """A code was requested too recently."""


def code_digest(email: str, purpose: str, code: str) -> str:
    """Return a keyed digest so database access alone cannot reveal a code."""
    settings = get_settings()
    message = (purpose + ":" + email.strip().lower() + ":" + code).encode("utf-8")
    return hmac.new(settings.JWT_SECRET.encode("utf-8"), message, hashlib.sha256).hexdigest()


def send_auth_email(email: str, purpose: str, code: str) -> None:
    """Send a Russian transactional email via Resend; no tracking pixel is added."""
    settings = get_settings()
    if not settings.RESEND_API_KEY:
        raise EmailDeliveryError("RESEND_API_KEY is not configured")

    messages = {
        "registration": (
            "Подтверждение регистрации — Endurance Fantasy League",
            "Чтобы завершить регистрацию, введите код ниже.",
        ),
        "verification": (
            "Подтверждение адреса — Endurance Fantasy League",
            "Введите код, чтобы подтвердить адрес электронной почты.",
        ),
        "password_reset": (
            "Сброс пароля — Endurance Fantasy League",
            "Введите код ниже, чтобы установить новый пароль. Если вы не запрашивали сброс, проигнорируйте письмо.",
        ),
    }
    subject, description = messages[purpose]
    html = (
        '<div style="font-family:Arial,sans-serif;line-height:1.6;color:#171a38">'
        '<h2>Endurance Fantasy League</h2>'
        f'<p>{description}</p>'
        f'<p style="font-size:30px;font-weight:700;letter-spacing:8px">{code}</p>'
        '<p>Код действителен 10 минут. Не передавайте его другим людям.</p>'
        '<p>Это автоматическое письмо, отвечать на него не нужно.</p></div>'
    )
    text = (
        "Endurance Fantasy League\n\n"
        + description
        + "\n\nКод: "
        + code
        + "\n\nКод действителен 10 минут. Не передавайте его другим людям."
    )

    try:
        response = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": "Bearer " + settings.RESEND_API_KEY},
            json={
                "from": settings.EMAIL_FROM,
                "to": [email],
                "subject": subject,
                "html": html,
                "text": text,
            },
            timeout=10.0,
        )
        response.raise_for_status()
    except Exception as exc:
        # Do not log recipient addresses, codes, request bodies or provider response bodies.
        logger.warning("Resend delivery failed (%s)", type(exc).__name__)
        raise EmailDeliveryError("Email delivery failed") from exc


def issue_email_code(db: Session, user_id: int, email: str, purpose: str) -> None:
    """Store a short-lived HMAC digest and send the raw code only to the provider."""
    now = datetime.utcnow()
    normalized_email = email.strip().lower()
    row = (
        db.query(EmailCode)
        .filter(EmailCode.email == normalized_email, EmailCode.purpose == purpose)
        .first()
    )
    if row is not None and row.created_at and row.created_at > now - CODE_MIN_SEND_INTERVAL:
        raise EmailRateLimitError("A code was requested too recently")

    code = f"{secrets.randbelow(1_000_000):06d}"
    if row is None:
        row = EmailCode(
            user_id=user_id,
            email=normalized_email,
            purpose=purpose,
            code_hash=code_digest(normalized_email, purpose, code),
            expires_at=now + CODE_TTL,
            attempts=0,
            created_at=now,
        )
        db.add(row)
    else:
        row.user_id = user_id
        row.code_hash = code_digest(normalized_email, purpose, code)
        row.expires_at = now + CODE_TTL
        row.attempts = 0
        row.created_at = now

    db.commit()
    try:
        send_auth_email(normalized_email, purpose, code)
    except EmailDeliveryError:
        db.delete(row)
        db.commit()
        raise


def verify_email_code(db: Session, email: str, purpose: str, code: str) -> bool:
    """Validate one code; count every incorrect attempt and consume it on success."""
    normalized_email = email.strip().lower()
    row = (
        db.query(EmailCode)
        .filter(EmailCode.email == normalized_email, EmailCode.purpose == purpose)
        .first()
    )
    now = datetime.utcnow()
    if (
        row is None
        or row.expires_at is None
        or row.expires_at <= now
        or int(row.attempts or 0) >= MAX_CODE_ATTEMPTS
    ):
        return False

    expected = row.code_hash
    actual = code_digest(normalized_email, purpose, code)
    row.attempts = int(row.attempts or 0) + 1
    if not hmac.compare_digest(expected, actual):
        db.commit()
        return False

    db.delete(row)
    db.commit()
    return True
