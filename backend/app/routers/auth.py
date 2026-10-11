from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..auth import hash_password, verify_password, password_needs_rehash, create_access_token
from ..dependencies import get_current_user
from ..rate_limit import limiter
from ..config import get_settings

router = APIRouter(prefix="/api/auth", tags=["Auth"])


class RegisterIn(BaseModel):
    username: str = Field(..., min_length=3, max_length=32, pattern=r"^[a-z0-9_]{3,32}$")
    password: str = Field(..., min_length=6, max_length=128)
    display_name: str = Field(..., min_length=2, max_length=50)
    privacy_consent: bool = Field(False, description="Explicit consent to the data policy")

    @field_validator("username", mode="before")
    @classmethod
    def normalize_username(cls, value):
        return value.strip().lower() if isinstance(value, str) else value

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
    }


@router.post("/register", response_model=TokenOut)
@limiter.limit("5/hour")
def register(request: Request, data: RegisterIn, db: Session = Depends(get_db)):
    if not data.privacy_consent:
        raise HTTPException(status_code=400, detail="Для регистрации необходимо согласиться с политикой обработки данных")
    normalized_username = data.username
    if db.query(User).filter(User.username == normalized_username).first():
        raise HTTPException(status_code=409, detail="Этот username уже занят")
    
    user = User(
        username=normalized_username,
        password_hash=hash_password(data.password),
        display_name=data.display_name.strip(),
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
        raise HTTPException(status_code=409, detail="Этот username уже занят")
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

    # Постепенно повышаем стоимость старых хешей при успешном входе.
    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(data.password)
        db.commit()
        db.refresh(user)
    
    return TokenOut(
        access_token=create_access_token(user.id, user.token_version or 0),
        user=_user_payload(user),
    )


@router.post("/logout")
def logout(current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Отзывает все сессии пользователя, увеличивая token_version."""
    current.token_version = int(current.token_version or 0) + 1
    db.commit()
    return {"message": "Выход выполнен; все активные сессии отозваны"}


@router.get("/me")
def me(current: User = Depends(get_current_user)):
    return _user_payload(current)