from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import EmailCode, User
from ..auth import hash_password, verify_password, password_needs_rehash, create_access_token
from ..dependencies import get_current_user
from ..rate_limit import limiter
from ..config import get_settings
from ..services.email_auth import (
    EmailDeliveryError,
    EmailRateLimitError,
    issue_email_code,
    verify_email_code,
)

router = APIRouter(prefix="/api/auth", tags=["Auth"])


def _normalize_email(value):
    return value.strip().lower() if isinstance(value, str) else value


class RegisterIn(BaseModel):
    username: str = Field(..., min_length=3, max_length=32, pattern=r"^[a-z0-9_]{3,32}$")
    email: EmailStr = Field(..., max_length=320)
    password: str = Field(..., min_length=6, max_length=128)
    display_name: str = Field(..., min_length=2, max_length=50)
    privacy_consent: bool = Field(False, description="Explicit consent to the data policy")

    @field_validator("username", mode="before")
    @classmethod
    def normalize_username(cls, value):
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("email", mode="before")
    @classmethod
    def normalize_register_email(cls, value):
        return _normalize_email(value)

    @field_validator("display_name", mode="before")
    @classmethod
    def normalize_display_name(cls, value):
        return value.strip() if isinstance(value, str) else value


class LoginIn(BaseModel):
    username: str = Field(..., min_length=3, max_length=32, pattern=r"^[a-z0-9_]{3,32}$")
    password: str = Field(..., min_length=1, max_length=128)

    @field_validator("username", mode="before")
    @classmethod
    def normalize_username(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


class EmailIn(BaseModel):
    email: EmailStr = Field(..., max_length=320)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value):
        return _normalize_email(value)


class RegistrationVerifyIn(EmailIn):
    code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")


class CodeIn(BaseModel):
    code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")


class PasswordResetConfirmIn(EmailIn):
    code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")
    new_password: str = Field(..., min_length=6, max_length=128)


class ChangePasswordIn(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=6, max_length=128)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


def _user_payload(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "level": user.level,
        "total_xp": round(float(user.total_xp or 0), 2),
        "has_intervals_key": bool(user.api_key_encrypted),
        "email": user.email,
        "email_verified_at": user.email_verified_at.isoformat() if user.email_verified_at else None,
        "email_verification_required": bool(user.email_verification_required),
    }


def _invalid_code() -> HTTPException:
    return HTTPException(status_code=400, detail="Код недействителен или истёк")


@router.post("/register")
@limiter.limit("5/hour")
def register(request: Request, data: RegisterIn, db: Session = Depends(get_db)):
    if not data.privacy_consent:
        raise HTTPException(status_code=400, detail="Для регистрации необходимо согласиться с политикой обработки данных")

    normalized_username = data.username
    normalized_email = str(data.email).strip().lower()
    if db.query(User).filter(User.username == normalized_username).first():
        raise HTTPException(status_code=409, detail="Этот username уже занят")
    if db.query(User).filter(func.lower(User.email) == normalized_email).first():
        raise HTTPException(status_code=409, detail="Этот email уже используется")

    user = User(
        username=normalized_username,
        email=normalized_email,
        email_verified_at=None,
        email_verification_required=True,
        password_hash=hash_password(data.password),
        display_name=data.display_name,
        privacy_consent_version=get_settings().PRIVACY_CONSENT_VERSION,
        privacy_consent_at=datetime.utcnow(),
        total_xp=0,
        level=1,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if db.query(User).filter(User.username == normalized_username).first():
            raise HTTPException(status_code=409, detail="Этот username уже занят")
        if db.query(User).filter(User.email == normalized_email).first():
            raise HTTPException(status_code=409, detail="Этот email уже используется")
        raise
    db.refresh(user)

    try:
        issue_email_code(db, user.id, normalized_email, "registration")
    except EmailRateLimitError:
        db.delete(user)
        db.commit()
        raise HTTPException(status_code=429, detail="Слишком частая отправка кодов. Попробуйте позже.")
    except EmailDeliveryError:
        db.delete(user)
        db.commit()
        raise HTTPException(status_code=503, detail="Не удалось отправить письмо. Попробуйте позже.")

    return {
        "requires_email_verification": True,
        "email": normalized_email,
        "message": "Код подтверждения отправлен на указанную почту.",
    }


@router.post("/registration/verify", response_model=TokenOut)
@limiter.limit("10/minute")
def verify_registration(request: Request, data: RegistrationVerifyIn, db: Session = Depends(get_db)):
    email = str(data.email).strip().lower()
    if not verify_email_code(db, email, "registration", data.code):
        raise _invalid_code()

    user = db.query(User).filter(func.lower(User.email) == email).first()
    if user is None or not user.email_verification_required:
        raise _invalid_code()

    user.email_verified_at = datetime.utcnow()
    user.email_verification_required = False
    db.commit()
    db.refresh(user)
    return TokenOut(
        access_token=create_access_token(user.id, user.token_version or 0),
        user=_user_payload(user),
    )


@router.post("/login", response_model=TokenOut)
@limiter.limit("5/minute")
def login(request: Request, data: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == data.username).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Неверный username или пароль")
    if user.email_verification_required and not user.email_verified_at:
        raise HTTPException(
            status_code=403,
            detail="Подтвердите почту кодом из письма, прежде чем входить в аккаунт.",
        )

    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(data.password)
        db.commit()
        db.refresh(user)

    return TokenOut(
        access_token=create_access_token(user.id, user.token_version or 0),
        user=_user_payload(user),
    )


@router.post("/email/verification/request")
@limiter.limit("5/hour")
def request_email_verification(
    request: Request,
    data: EmailIn,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    email = str(data.email).strip().lower()
    if current.email == email and current.email_verified_at:
        return {"message": "Этот адрес уже подтверждён.", "email": email}

    conflict = db.query(User).filter(func.lower(User.email) == email, User.id != current.id).first()
    if conflict:
        raise HTTPException(status_code=409, detail="Этот email уже используется.")

    if current.email != email:
        db.query(EmailCode).filter(EmailCode.user_id == current.id).delete(synchronize_session=False)
        current.email = email
    current.email_verified_at = None
    current.email_verification_required = False
    db.commit()

    try:
        issue_email_code(db, current.id, email, "verification")
    except EmailRateLimitError:
        raise HTTPException(status_code=429, detail="Код уже отправлялся недавно. Подождите минуту.")
    except EmailDeliveryError:
        raise HTTPException(status_code=503, detail="Не удалось отправить письмо. Проверьте настройки почты и попробуйте позже.")
    return {"message": "Код подтверждения отправлен.", "email": email}


@router.post("/email/verification/confirm")
@limiter.limit("10/minute")
def confirm_email_verification(
    request: Request,
    data: CodeIn,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not current.email or not verify_email_code(db, current.email, "verification", data.code):
        raise _invalid_code()
    current.email_verified_at = datetime.utcnow()
    current.email_verification_required = False
    db.commit()
    return {
        "verified": True,
        "email": current.email,
        "email_verified_at": current.email_verified_at.isoformat(),
    }


@router.post("/password-reset/request")
@limiter.limit("5/hour")
def request_password_reset(request: Request, data: EmailIn, db: Session = Depends(get_db)):
    """Always return the same public response, whether or not an account exists."""
    email = str(data.email).strip().lower()
    generic_response = {
        "message": "Если аккаунт с таким подтверждённым email существует, мы отправили код. Проверьте почту."
    }
    user = db.query(User).filter(func.lower(User.email) == email, User.email_verified_at.is_not(None)).first()
    if user is not None:
        try:
            issue_email_code(db, user.id, email, "password_reset")
        except (EmailRateLimitError, EmailDeliveryError):
            # Keep the response identical for existing and non-existing accounts.
            pass
    return generic_response


@router.post("/password-reset/confirm")
@limiter.limit("10/hour")
def confirm_password_reset(request: Request, data: PasswordResetConfirmIn, db: Session = Depends(get_db)):
    email = str(data.email).strip().lower()
    if not verify_email_code(db, email, "password_reset", data.code):
        raise _invalid_code()

    user = db.query(User).filter(User.email == email, User.email_verified_at.is_not(None)).first()
    if user is None:
        raise _invalid_code()

    user.password_hash = hash_password(data.new_password)
    user.token_version = int(user.token_version or 0) + 1
    db.query(EmailCode).filter(EmailCode.user_id == user.id).delete(synchronize_session=False)
    db.commit()
    return {"message": "Пароль изменён. Войдите с новым паролем."}


@router.post("/change-password")
@limiter.limit("5/hour")
def change_password(
    request: Request,
    data: ChangePasswordIn,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(data.current_password, current.password_hash):
        raise HTTPException(status_code=400, detail="Текущий пароль указан неверно.")
    if data.current_password == data.new_password:
        raise HTTPException(status_code=400, detail="Новый пароль должен отличаться от текущего.")

    current.password_hash = hash_password(data.new_password)
    current.token_version = int(current.token_version or 0) + 1
    db.query(EmailCode).filter(EmailCode.user_id == current.id).delete(synchronize_session=False)
    db.commit()
    return {"message": "Пароль изменён. Войдите снова."}


@router.post("/logout")
def logout(current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Отзывает все сессии пользователя, увеличивая token_version."""
    current.token_version = int(current.token_version or 0) + 1
    db.commit()
    return {"message": "Выход выполнен; все активные сессии отозваны"}


@router.get("/me")
def me(current: User = Depends(get_current_user)):
    return _user_payload(current)
