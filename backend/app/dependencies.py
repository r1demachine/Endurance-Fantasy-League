from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from .database import get_db
from .models import User
from .auth import decode_access_token
from .config import get_settings

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if not creds:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется авторизация (Bearer token)",
        )
    user_id = decode_access_token(creds.credentials)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Невалидный или просроченный токен",
        )
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не найден")
    return user


def _admin_ids() -> set[int]:
    raw = get_settings().ADMIN_USER_IDS
    return {int(x) for x in raw.split(",") if x.strip().isdigit()}


def require_admin(current: User = Depends(get_current_user)) -> User:
    """Пускает только пользователей из ADMIN_USER_IDS. Список пуст -> никого."""
    if current.id not in _admin_ids():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")
    return current