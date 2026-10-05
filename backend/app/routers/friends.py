"""Друзья: поиск по нику/имени, заявки, принятие, список."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user
from ..models import Friendship, FriendshipStatus, User
from ..services.notifications import notify_user

router = APIRouter(prefix="/api/friends", tags=["Friends"])


class AddIn(BaseModel):
    username: str


class IdIn(BaseModel):
    friendship_id: int


def _entry(u: User, **extra) -> dict:
    return {
        "id": u.id,
        "username": u.username,
        "display_name": u.display_name,
        "level": u.level,
        "total_xp": round(float(u.total_xp or 0), 2),
        **extra,
    }


def _relation(db: Session, me_id: int, other_id: int) -> tuple:
    """(status: friends|sent|incoming|None, friendship_id)"""
    rel = (
        db.query(Friendship)
        .filter(
            or_(
                and_(Friendship.from_user_id == me_id, Friendship.to_user_id == other_id),
                and_(Friendship.from_user_id == other_id, Friendship.to_user_id == me_id),
            )
        )
        .first()
    )
    if not rel:
        return None, None
    if rel.status == FriendshipStatus.ACCEPTED:
        return "friends", rel.id
    if rel.from_user_id == me_id:
        return "sent", rel.id
    return "incoming", rel.id


@router.get("/search")
def search_users(q: str, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = q.strip()
    if len(query) < 2:
        return {"results": []}
    like = f"%{query}%"
    users = (
        db.query(User)
        .filter(User.id != current.id)
        .filter(or_(User.username.ilike(like), User.display_name.ilike(like)))
        .order_by(User.total_xp.desc())
        .limit(10)
        .all()
    )
    results = []
    for u in users:
        rel, fid = _relation(db, current.id, u.id)
        results.append(_entry(u, relation=rel, friendship_id=fid))
    return {"results": results}


@router.post("/add")
async def add_friend(data: AddIn, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    target = db.query(User).filter(User.username == data.username.strip().lower()).first()
    if not target:
        raise HTTPException(status_code=404, detail="Athlete not found")
    if target.id == current.id:
        raise HTTPException(status_code=400, detail="Нельзя добавить самого себя")

    rel, _ = _relation(db, current.id, target.id)
    if rel == "friends":
        raise HTTPException(status_code=400, detail="Вы уже друзья")
    if rel == "sent":
        raise HTTPException(status_code=400, detail="Заявка уже отправлена")
    if rel == "incoming":
        rel_obj = (
            db.query(Friendship)
            .filter(Friendship.from_user_id == target.id, Friendship.to_user_id == current.id)
            .first()
        )
        rel_obj.status = FriendshipStatus.ACCEPTED
        db.commit()
        await notify_user(db, target.id, "friend_accepted", f"{current.display_name} принял(а) твою заявку в друзья")
        return {"message": f"Вы теперь друзья с {target.display_name}!", "status": "accepted"}

    db.add(Friendship(from_user_id=current.id, to_user_id=target.id, status=FriendshipStatus.PENDING))
    db.commit()
    await notify_user(db, target.id, "friend_request", f"{current.display_name} отправил(а) тебе заявку в друзья")
    return {"message": f"Заявка отправлена: {target.display_name}", "status": "sent"}


@router.get("")
def list_friends(current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (
        db.query(Friendship)
        .filter(
            or_(Friendship.from_user_id == current.id, Friendship.to_user_id == current.id),
            Friendship.status == FriendshipStatus.ACCEPTED,
        )
        .all()
    )
    friends = []
    for r in rows:
        other_id = r.to_user_id if r.from_user_id == current.id else r.from_user_id
        u = db.get(User, other_id)
        if u:
            friends.append(_entry(u))
    friends.sort(key=lambda x: x["total_xp"], reverse=True)

    incoming = []
    for r in db.query(Friendship).filter(Friendship.to_user_id == current.id, Friendship.status == FriendshipStatus.PENDING).all():
        u = db.get(User, r.from_user_id)
        if u:
            incoming.append(_entry(u, friendship_id=r.id))

    outgoing = []
    for r in db.query(Friendship).filter(Friendship.from_user_id == current.id, Friendship.status == FriendshipStatus.PENDING).all():
        u = db.get(User, r.to_user_id)
        if u:
            outgoing.append(_entry(u, friendship_id=r.id))

    return {"friends": friends, "incoming": incoming, "outgoing": outgoing}


@router.post("/accept")
async def accept_friend(data: IdIn, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = (
        db.query(Friendship)
        .filter(
            Friendship.id == data.friendship_id,
            Friendship.to_user_id == current.id,
            Friendship.status == FriendshipStatus.PENDING,
        )
        .first()
    )
    if not r:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    requester_id = r.from_user_id
    r.status = FriendshipStatus.ACCEPTED
    db.commit()
    await notify_user(db, requester_id, "friend_accepted", f"{current.display_name} принял(а) твою заявку в друзья")
    return {"message": "Друг добавлен!"}


@router.post("/reject")
def reject_friend(data: IdIn, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = (
        db.query(Friendship)
        .filter(
            Friendship.id == data.friendship_id,
            Friendship.to_user_id == current.id,
            Friendship.status == FriendshipStatus.PENDING,
        )
        .first()
    )
    if not r:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    db.delete(r)
    db.commit()
    return {"message": "Заявка отклонена"}

@router.post("/remove")
async def remove_friendship(
    payload: dict,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Универсально: разорвать дружбу / отменить свою заявку / отклонить входящую."""
    fid = int(payload.get("friendship_id") or 0)
    rel = db.query(Friendship).filter(Friendship.id == fid).first()
    if not rel:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    if rel.from_user_id != current.id and rel.to_user_id != current.id:
        raise HTTPException(status_code=403, detail="Это не твоя заявка")
    db.delete(rel)
    db.commit()
    return {"message": "Заявка удалена", "status": "none"}