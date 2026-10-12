"""Клубы: создание, инвайт-код, заявки, рейтинги."""
from __future__ import annotations

import secrets
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user
from ..models import (
    Club, ClubJoinRequest, ClubJoinRequestStatus, ClubMember, ClubMemberRole, User, WeeklySummary,
)
from ..rate_limit import limiter
from ..services.notifications import notify_user
from ..services import xp_v6 as X6

router = APIRouter(prefix="/api/clubs", tags=["Clubs"])
MAX_MEMBERS = 30


class CreateClubIn(BaseModel):
    name: str = Field(..., min_length=2, max_length=64)


class JoinCodeIn(BaseModel):
    code: str = Field(..., min_length=4, max_length=16, pattern=r"^[A-Za-z0-9]+$")


class ClubIdIn(BaseModel):
    club_id: int


class RequestRespondIn(BaseModel):
    request_id: int
    accept: bool


class KickIn(BaseModel):
    user_id: int


def _gen_code(db: Session) -> str:
    for _ in range(12):
        code = secrets.token_hex(4).upper()
        if not db.query(Club).filter(Club.invite_code == code).first():
            return code
    raise HTTPException(status_code=500, detail="Не удалось сгенерировать код")


def _member_count(db: Session, club_id: int) -> int:
    return db.query(ClubMember).filter(ClubMember.club_id == club_id).count()


def _is_member(db: Session, club_id: int, user_id: int) -> ClubMember | None:
    return db.query(ClubMember).filter(ClubMember.club_id == club_id, ClubMember.user_id == user_id).first()


def _club_brief(c: Club, db: Session, me: User) -> dict:
    mem = _is_member(db, c.id, me.id)
    return {
        "id": c.id, "name": c.name,
        "invite_code": c.invite_code if mem else None,
        "owner_id": c.owner_id, "is_owner": c.owner_id == me.id,
        "is_member": mem is not None, "member_count": _member_count(db, c.id),
        "my_role": mem.role if mem else None,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


def _season_bounds(d: date) -> tuple[datetime, datetime]:
    return datetime(d.year, 1, 1), datetime(d.year, 12, 31, 23, 59, 59)


def _rankings(db: Session, club_id: int, me: User) -> dict:
    members = db.query(ClubMember).filter(ClubMember.club_id == club_id).all()
    user_ids = [m.user_id for m in members]
    if not user_ids:
        return {"weekly": [], "seasonal": []}
    ws = datetime.combine(X6.week_start(date.today()), datetime.min.time())
    week_map = {
        r.user_id: float(r.total_xp or 0)
        for r in db.query(WeeklySummary).filter(
            WeeklySummary.user_id.in_(user_ids), WeeklySummary.week_start == ws
        ).all()
    }
    s0, s1 = _season_bounds(date.today())
    season_map = {
        uid: float(score or 0)
        for uid, score in db.query(
            WeeklySummary.user_id, func.coalesce(func.sum(WeeklySummary.league_score), 0.0)
        ).filter(
            WeeklySummary.user_id.in_(user_ids),
            WeeklySummary.finalized.is_(True),
            WeeklySummary.week_start >= s0,
            WeeklySummary.week_start <= s1,
        ).group_by(WeeklySummary.user_id).all()
    }
    weekly, seasonal = [], []
    for m in members:
        u = db.get(User, m.user_id)
        if not u:
            continue
        vis = (u.profile_visibility or "authenticated").lower()
        if vis == "private" and u.id != me.id:
            brief = {"id": u.id, "username": None, "display_name": "Скрытый профиль", "level": None, "hidden": True}
        else:
            brief = {"id": u.id, "username": u.username, "display_name": u.display_name, "level": u.level, "hidden": False}
        weekly.append({**brief, "score": round(week_map.get(u.id, 0.0), 2), "role": m.role})
        seasonal.append({**brief, "score": round(season_map.get(u.id, 0.0), 2), "role": m.role})
    weekly.sort(key=lambda x: (-x["score"], x["id"]))
    seasonal.sort(key=lambda x: (-x["score"], x["id"]))
    for i, row in enumerate(weekly):
        row["rank"] = i + 1
    for i, row in enumerate(seasonal):
        row["rank"] = i + 1
    return {"weekly": weekly, "seasonal": seasonal}


@router.post("")
@limiter.limit("5/hour")
async def create_club(request: Request, data: CreateClubIn, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    name = data.name.strip()
    if len(name) < 2:
        raise HTTPException(status_code=400, detail="Слишком короткое название")
    club = Club(name=name, invite_code=_gen_code(db), owner_id=current.id)
    db.add(club)
    db.flush()
    db.add(ClubMember(club_id=club.id, user_id=current.id, role=ClubMemberRole.OWNER.value))
    db.commit()
    db.refresh(club)
    return {"message": "Клуб создан", "club": _club_brief(club, db, current)}


@router.post("/join")
@limiter.limit("20/hour")
async def join_by_code(request: Request, data: JoinCodeIn, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    club = db.query(Club).filter(Club.invite_code == data.code.strip().upper()).first()
    if not club:
        raise HTTPException(status_code=404, detail="Клуб с таким кодом не найден")
    if _is_member(db, club.id, current.id):
        raise HTTPException(status_code=400, detail="Ты уже в этом клубе")
    if _member_count(db, club.id) >= MAX_MEMBERS:
        raise HTTPException(status_code=400, detail="Клуб заполнен (макс. 30)")
    db.add(ClubMember(club_id=club.id, user_id=current.id, role=ClubMemberRole.MEMBER.value))
    req = db.query(ClubJoinRequest).filter(
        ClubJoinRequest.club_id == club.id, ClubJoinRequest.user_id == current.id,
        ClubJoinRequest.status == ClubJoinRequestStatus.PENDING.value,
    ).first()
    if req:
        req.status = ClubJoinRequestStatus.ACCEPTED.value
        req.responded_at = datetime.utcnow()
    db.commit()
    await notify_user(db, club.owner_id, "club_join", f"{current.display_name} вступил(а) в клуб «{club.name}» по коду")
    return {"message": f"Ты в клубе «{club.name}»", "club": _club_brief(club, db, current)}


@router.get("/search")
def search_clubs(q: str = Query(..., min_length=2, max_length=64), current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    escaped = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    clubs = db.query(Club).filter(Club.name.ilike(f"%{escaped}%", escape="\\")).order_by(Club.name.asc()).limit(15).all()
    return {"results": [{
        "id": c.id, "name": c.name, "member_count": _member_count(db, c.id),
        "is_member": _is_member(db, c.id, current.id) is not None,
        "has_pending_request": db.query(ClubJoinRequest).filter(
            ClubJoinRequest.club_id == c.id, ClubJoinRequest.user_id == current.id,
            ClubJoinRequest.status == ClubJoinRequestStatus.PENDING.value,
        ).first() is not None,
    } for c in clubs]}


@router.post("/request")
@limiter.limit("20/hour")
async def request_join(request: Request, data: ClubIdIn, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    club = db.get(Club, data.club_id)
    if not club:
        raise HTTPException(status_code=404, detail="Клуб не найден")
    if _is_member(db, club.id, current.id):
        raise HTTPException(status_code=400, detail="Ты уже в этом клубе")
    if _member_count(db, club.id) >= MAX_MEMBERS:
        raise HTTPException(status_code=400, detail="Клуб заполнен (макс. 30)")
    existing = db.query(ClubJoinRequest).filter(ClubJoinRequest.club_id == club.id, ClubJoinRequest.user_id == current.id).first()
    if existing and existing.status == ClubJoinRequestStatus.PENDING.value:
        raise HTTPException(status_code=400, detail="Заявка уже отправлена")
    if existing:
        existing.status = ClubJoinRequestStatus.PENDING.value
        existing.created_at = datetime.utcnow()
        existing.responded_at = None
    else:
        db.add(ClubJoinRequest(club_id=club.id, user_id=current.id, status=ClubJoinRequestStatus.PENDING.value))
    db.commit()
    await notify_user(db, club.owner_id, "club_join_request", f"{current.display_name} просится в клуб «{club.name}»")
    return {"message": "Заявка отправлена владельцу"}


@router.post("/requests/respond")
@limiter.limit("30/hour")
async def respond_request(request: Request, data: RequestRespondIn, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    req = db.get(ClubJoinRequest, data.request_id)
    if not req or req.status != ClubJoinRequestStatus.PENDING.value:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    club = db.get(Club, req.club_id)
    if not club or club.owner_id != current.id:
        raise HTTPException(status_code=403, detail="Только владелец клуба")
    req.responded_at = datetime.utcnow()
    if data.accept:
        if _member_count(db, club.id) >= MAX_MEMBERS:
            raise HTTPException(status_code=400, detail="Клуб заполнен (макс. 30)")
        if not _is_member(db, club.id, req.user_id):
            db.add(ClubMember(club_id=club.id, user_id=req.user_id, role=ClubMemberRole.MEMBER.value))
        req.status = ClubJoinRequestStatus.ACCEPTED.value
        db.commit()
        await notify_user(db, req.user_id, "club_join_accepted", f"Тебя приняли в клуб «{club.name}»")
        return {"message": "Заявка принята"}
    req.status = ClubJoinRequestStatus.DECLINED.value
    db.commit()
    await notify_user(db, req.user_id, "club_join_declined", f"Заявку в клуб «{club.name}» отклонили")
    return {"message": "Заявка отклонена"}


@router.get("/mine")
def my_clubs(current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    memberships = db.query(ClubMember).filter(ClubMember.user_id == current.id).all()
    clubs = []
    for m in memberships:
        c = db.get(Club, m.club_id)
        if c:
            clubs.append(_club_brief(c, db, current))
    incoming = []
    owned_ids = [c["id"] for c in clubs if c["is_owner"]]
    if owned_ids:
        for req in db.query(ClubJoinRequest).filter(
            ClubJoinRequest.club_id.in_(owned_ids),
            ClubJoinRequest.status == ClubJoinRequestStatus.PENDING.value,
        ).order_by(ClubJoinRequest.created_at.desc()).limit(30).all():
            u = db.get(User, req.user_id)
            club = db.get(Club, req.club_id)
            if u and club:
                incoming.append({
                    "request_id": req.id, "club_id": club.id, "club_name": club.name,
                    "user": {"id": u.id, "username": u.username, "display_name": u.display_name, "level": u.level},
                    "created_at": req.created_at.isoformat() if req.created_at else None,
                })
    return {"clubs": clubs, "incoming_requests": incoming}


@router.get("/{club_id}")
def club_detail(club_id: int, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    club = db.get(Club, club_id)
    if not club:
        raise HTTPException(status_code=404, detail="Клуб не найден")
    if not _is_member(db, club.id, current.id):
        raise HTTPException(status_code=403, detail="Клуб виден только участникам. Вступи по коду или отправь заявку.")
    return {"club": _club_brief(club, db, current), "rankings": _rankings(db, club.id, current)}


@router.post("/{club_id}/kick")
@limiter.limit("30/hour")
async def kick_member(club_id: int, request: Request, data: KickIn, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    club = db.get(Club, club_id)
    if not club or club.owner_id != current.id:
        raise HTTPException(status_code=403, detail="Только владелец может исключать")
    if data.user_id == current.id:
        raise HTTPException(status_code=400, detail="Нельзя исключить себя")
    mem = _is_member(db, club_id, data.user_id)
    if not mem:
        raise HTTPException(status_code=404, detail="Участник не найден")
    db.delete(mem)
    db.commit()
    await notify_user(db, data.user_id, "club_kicked", f"Тебя исключили из клуба «{club.name}»")
    return {"message": "Участник исключён"}


@router.post("/{club_id}/leave")
@limiter.limit("20/hour")
async def leave_club(club_id: int, request: Request, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    club = db.get(Club, club_id)
    if not club:
        raise HTTPException(status_code=404, detail="Клуб не найден")
    mem = _is_member(db, club_id, current.id)
    if not mem:
        raise HTTPException(status_code=400, detail="Ты не в этом клубе")
    if club.owner_id == current.id:
        raise HTTPException(status_code=400, detail="Владелец не может выйти — сначала исключи всех")
    db.delete(mem)
    db.commit()
    return {"message": "Ты вышел из клуба"}
