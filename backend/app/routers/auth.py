from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..auth import hash_password, verify_password, create_access_token
from ..dependencies import get_current_user
from ..rate_limit import limiter
from ..config import get_settings

router = APIRouter(prefix="/api/auth", tags=["Auth"])


class RegisterIn(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=6)
    display_name: str = Field(..., min_length=2, max_length=50)
    privacy_consent: bool = Field(False, description="Explicit consent to the data policy")


class LoginIn(BaseModel):
    username: str
    password: str


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
    normalized_username = data.username.strip().lower()
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
    db.commit()
    db.refresh(user)
    
    return TokenOut(
        access_token=create_access_token(user.id),
        user=_user_payload(user),
    )


@router.post("/login", response_model=TokenOut)
@limiter.limit("5/minute")
def login(request: Request, data: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == data.username.strip().lower()).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Неверный username или пароль")
    
    return TokenOut(
        access_token=create_access_token(user.id),
        user=_user_payload(user),
    )


@router.get("/me")
def me(current: User = Depends(get_current_user)):
    return _user_payload(current)