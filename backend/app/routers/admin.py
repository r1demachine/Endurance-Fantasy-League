from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import require_admin
from ..models import Activity, Friendship, User

# dependencies на уровне роутера: КАЖДЫЙ эндпоинт, который ты добавишь
# в этот файл в будущем, автоматически закрыт проверкой require_admin.
router = APIRouter(
    prefix="/api/admin",
    tags=["Admin"],
    dependencies=[Depends(require_admin)],
)


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    """Безопасная read-only сводка. Деструктивных операций здесь нет."""
    return {
        "users": db.query(func.count(User.id)).scalar(),
        "activities": db.query(func.count(Activity.id)).scalar(),
        "friendships": db.query(func.count(Friendship.id)).scalar(),
    }