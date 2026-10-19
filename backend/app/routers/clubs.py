"""Club membership, ownership, invite, and ranking endpoints."""
import hashlib
import logging
import re
import secrets
import unicodedata
from datetime import date, datetime, timedelta
from typing import Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import and_, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user
from ..models import (
    Club,
    ClubJoinAttempt,
    ClubJoinRequest,
    ClubJoinRequestStatus,
    ClubMember,
    ClubMemberRole,
    Friendship,
    FriendshipStatus,
    User,
    WeeklySummary,
)
from ..rate_limit import limiter
from ..services.notifications import notify_user
from ..services import xp_v6 as X6

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/clubs", tags=["Clubs"])

MAX_OWNED_CLUBS = 3
MAX_USER_MEMBERSHIPS = 10
MAX_MEMBERS = 30
INVITE_CODE_LENGTH = 12
INVITE_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
FAILED_CODE_LIMIT = 8
FAILED_CODE_WINDOW = timedelta(minutes=15)


def normalize_club_name(value: str) -> str:
    """Collapse repeated spaces and reject control/format characters."""
    if not isinstance(value, str):
        raise ValueError("Название клуба должно быть текстом")
    if any(unicodedata.category(char) in {"Cc", "Cf"} for char in value):
        raise ValueError("Название не должно содержать управляющие символы")
    normalized = re.sub(r"\s+", " ", value).strip()
    if not 2 <= len(normalized) <= 40:
        raise ValueError("Название клуба должно содержать от 2 до 40 символов")
    return normalized


def normalize_invite_code(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Код вступления должен быть текстом")
    normalized = value.strip().upper()
    if not re.fullmatch(r"[A-Z2-7]{12}", normalized):
        raise ValueError("Код должен состоять из 12 символов Base32")
    return normalized


class CreateClubIn(BaseModel):
    name: str = Field(..., min_length=2, max_length=40)
    instant_join: bool = False

    @field_validator("name", mode="before")
    @classmethod
    def clean_name(cls, value):
        return normalize_club_name(value)


class UpdateClubIn(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=40)
    instant_join: Optional[bool] = None

    @field_validator("name", mode="before")
    @classmethod
    def clean_name(cls, value):
        return None if value is None else normalize_club_name(value)


class JoinCodeIn(BaseModel):
    # Keep malformed user input long enough to record unsuccessful attempts in the audit table.
    code: str = Field(..., min_length=1, max_length=128)

    @field_validator("code", mode="before")
    @classmethod
    def clean_code(cls, value):
        if isinstance(value, str):
            return value.strip().upper()
        return value


class ClubIdIn(BaseModel):
    club_id: int


class RequestRespondIn(BaseModel):
    request_id: int
    accept: bool


class KickIn(BaseModel):
    user_id: int


class TransferOwnerIn(BaseModel):
    user_id: int


class LeaveClubIn(BaseModel):
    transfer_to_user_id: Optional[int] = None


def _gen_code(db: Session) -> str:
    for _ in range(32):
        code = "".join(secrets.choice(INVITE_ALPHABET) for _ in range(INVITE_CODE_LENGTH))
        if not db.query(Club.id).filter(Club.invite_code == code).first():
            return code
    raise HTTPException(status_code=503, detail="Не удалось создать уникальный код вступления. Повтори попытку.")


def _lock_user(db: Session, user_id: int) -> User:
    user = db.query(User).filter(User.id == user_id).with_for_update().populate_existing().first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return user


def _lock_users(db: Session, *user_ids: int) -> dict[int, User]:
    locked = (
        db.query(User)
        .filter(User.id.in_(sorted(set(user_ids))))
        .order_by(User.id.asc())
        .with_for_update()
        .populate_existing()
        .all()
    )
    result = {user.id: user for user in locked}
    missing = set(user_ids) - set(result)
    if missing:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return result


def _lock_club(db: Session, club_id: int) -> Optional[Club]:
    return (
        db.query(Club)
        .filter(Club.id == club_id)
        .with_for_update()
        .populate_existing()
        .first()
    )


def _member_count(db: Session, club_id: int) -> int:
    return db.query(ClubMember).filter(ClubMember.club_id == club_id).count()


def _user_membership_count(db: Session, user_id: int) -> int:
    return db.query(ClubMember).filter(ClubMember.user_id == user_id).count()


def _owned_club_count(db: Session, owner_id: int) -> int:
    # Ownership is counted from clubs.owner_id, not inferred from the member table role.
    return db.query(Club).filter(Club.owner_id == owner_id).count()


def _ensure_membership_capacity(db: Session, user_id: int) -> None:
    if _user_membership_count(db, user_id) >= MAX_USER_MEMBERSHIPS:
        raise HTTPException(
            status_code=409,
            detail=f"Можно состоять не более чем в {MAX_USER_MEMBERSHIPS} клубах.",
        )


def _is_member(db: Session, club_id: int, user_id: int) -> Optional[ClubMember]:
    return (
        db.query(ClubMember)
        .filter(ClubMember.club_id == club_id, ClubMember.user_id == user_id)
        .first()
    )


def _club_brief(c: Club, db: Session, me: User) -> dict:
    mem = _is_member(db, c.id, me.id)
    return {
        "id": c.id,
        "name": c.name,
        "invite_code": c.invite_code if c.owner_id == me.id else None,
        "instant_join": bool(c.instant_join),
        "owner_id": c.owner_id,
        "is_owner": c.owner_id == me.id,
        "is_member": mem is not None,
        "member_count": _member_count(db, c.id),
        "my_role": mem.role if mem else None,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


def _season_bounds(d: date) -> Tuple[datetime, datetime]:
    from ..services.seasons import season_for_date
    season = season_for_date(d)
    return (
        datetime.combine(season.start, datetime.min.time()),
        datetime.combine(season.next_start, datetime.min.time()),
    )


def _friend_ids(db: Session, me_id: int) -> set[int]:
    rows = (
        db.query(Friendship.from_user_id, Friendship.to_user_id)
        .filter(
            Friendship.status == FriendshipStatus.ACCEPTED,
            or_(Friendship.from_user_id == me_id, Friendship.to_user_id == me_id),
        )
        .all()
    )
    return {
        to_id if from_id == me_id else from_id
        for from_id, to_id in rows
    }


def _member_brief(user: User, role: str, me: User, friend_ids: set[int]) -> dict:
    visibility = (user.profile_visibility or "authenticated").lower()
    hidden = user.id != me.id and (
        visibility == "private" or (visibility == "friends" and user.id not in friend_ids)
    )
    if hidden:
        return {
            "id": user.id,
            "username": None,
            "display_name": "Скрыто",
            "level": None,
            "hidden": True,
            "role": role,
        }
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "level": user.level,
        "hidden": False,
        "role": role,
    }


def _rankings(db: Session, club_id: int, me: User) -> dict:
    members = db.query(ClubMember).filter(ClubMember.club_id == club_id).all()
    user_ids = [member.user_id for member in members]
    if not user_ids:
        return {"weekly": [], "seasonal": []}

    from ..services.seasons import local_date
    today = local_date(me.timezone_name)
    week_start = datetime.combine(X6.week_start(today), datetime.min.time())
    week_scores = {
        row.user_id: float(row.total_xp or 0)
        for row in db.query(WeeklySummary).filter(
            WeeklySummary.user_id.in_(user_ids),
            WeeklySummary.week_start == week_start,
        ).all()
    }
    season_start, season_end = _season_bounds(today)
    season_scores = {
        user_id: float(score or 0)
        for user_id, score in db.query(
            WeeklySummary.user_id,
            func.coalesce(func.sum(WeeklySummary.league_score), 0.0),
        ).filter(
            WeeklySummary.user_id.in_(user_ids),
            WeeklySummary.finalized.is_(True),
            WeeklySummary.week_start >= season_start,
            WeeklySummary.week_start < season_end,
        ).group_by(WeeklySummary.user_id).all()
    }

    friends = _friend_ids(db, me.id)
    weekly, seasonal = [], []
    for member in members:
        user = db.get(User, member.user_id)
        if not user:
            continue
        brief = _member_brief(user, member.role, me, friends)
        if brief["hidden"]:
            # Never disclose a hidden member's score or ranking position.
            weekly_row = {**brief, "score": None, "rank": None}
            seasonal_row = {**brief, "score": None, "rank": None}
        else:
            weekly_row = {**brief, "score": round(week_scores.get(user.id, 0.0), 2)}
            seasonal_row = {**brief, "score": round(season_scores.get(user.id, 0.0), 2)}
        weekly.append(weekly_row)
        seasonal.append(seasonal_row)

    for rows in (weekly, seasonal):
        visible = sorted(
            (row for row in rows if not row["hidden"]),
            key=lambda row: (-row["score"], row["id"]),
        )
        hidden = sorted(
            (row for row in rows if row["hidden"]),
            key=lambda row: row["id"],
        )
        for rank, row in enumerate(visible, 1):
            row["rank"] = rank
        rows[:] = visible + hidden
    return {"weekly": weekly, "seasonal": seasonal}


def _club_members(db: Session, club_id: int, me: User) -> list[dict]:
    members = db.query(ClubMember).filter(ClubMember.club_id == club_id).order_by(ClubMember.joined_at.asc()).all()
    club = db.get(Club, club_id)
    viewer_is_owner = bool(club and club.owner_id == me.id)
    friends = _friend_ids(db, me.id)
    result = []
    for member in members:
        user = db.get(User, member.user_id)
        if user:
            brief = _member_brief(user, member.role, me, friends)
            result.append({
                **brief,
                # Use the stable member ID for owner actions while still respecting profile visibility.
                "can_be_removed": viewer_is_owner and me.id != user.id,
            })
    return result


def _record_join_attempt(db: Session, user_id: int, code: str, succeeded: bool) -> None:
    digest = hashlib.sha256(code.strip().upper().encode("utf-8")).hexdigest()
    db.add(ClubJoinAttempt(
        user_id=user_id,
        code_digest=digest,
        succeeded=succeeded,
        attempted_at=datetime.utcnow(),
    ))


def _recent_failed_code_attempts(db: Session, user_id: int) -> int:
    cutoff = datetime.utcnow() - FAILED_CODE_WINDOW
    return db.query(ClubJoinAttempt).filter(
        ClubJoinAttempt.user_id == user_id,
        ClubJoinAttempt.succeeded.is_(False),
        ClubJoinAttempt.attempted_at >= cutoff,
    ).count()


def _handle_integrity_error(db: Session, detail: str) -> None:
    db.rollback()
    raise HTTPException(status_code=409, detail=detail)


@router.post("")
@limiter.limit("5/hour")
async def create_club(
    request: Request,
    data: CreateClubIn,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    owner = _lock_user(db, current.id)
    if _owned_club_count(db, owner.id) >= MAX_OWNED_CLUBS:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"Нельзя владеть более чем {MAX_OWNED_CLUBS} клубами.")
    _ensure_membership_capacity(db, owner.id)

    club = Club(
        name=data.name,
        invite_code=_gen_code(db),
        owner_id=owner.id,
        instant_join=data.instant_join,
    )
    db.add(club)
    try:
        db.flush()
        db.add(ClubMember(club_id=club.id, user_id=owner.id, role=ClubMemberRole.OWNER.value))
        db.commit()
        db.refresh(club)
    except IntegrityError:
        _handle_integrity_error(db, "Клуб с таким названием уже существует у тебя.")
    return {"message": "Клуб создан", "club": _club_brief(club, db, owner)}


@router.post("/join")
@limiter.limit("20/hour")
async def join_by_code(
    request: Request,
    data: JoinCodeIn,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _lock_user(db, current.id)
    if _recent_failed_code_attempts(db, current.id) >= FAILED_CODE_LIMIT:
        db.rollback()
        raise HTTPException(status_code=429, detail="Слишком много неверных кодов. Попробуй через 15 минут.")

    if not re.fullmatch(r"[A-Z2-7]{12}", data.code):
        _record_join_attempt(db, current.id, data.code, False)
        db.commit()
        raise HTTPException(status_code=404, detail="Клуб с таким кодом не найден")

    club = (
        db.query(Club)
        .filter(Club.invite_code == data.code)
        .with_for_update()
        .populate_existing()
        .first()
    )
    if not club:
        _record_join_attempt(db, current.id, data.code, False)
        db.commit()
        raise HTTPException(status_code=404, detail="Клуб с таким кодом не найден")

    if _is_member(db, club.id, current.id):
        _record_join_attempt(db, current.id, data.code, True)
        db.commit()
        raise HTTPException(status_code=409, detail="Ты уже в этом клубе")
    _ensure_membership_capacity(db, current.id)
    if _member_count(db, club.id) >= MAX_MEMBERS:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"Клуб заполнен (максимум {MAX_MEMBERS} участников).")

    _record_join_attempt(db, current.id, data.code, True)
    now = datetime.utcnow()
    if not club.instant_join:
        existing = db.query(ClubJoinRequest).filter(
            ClubJoinRequest.club_id == club.id,
            ClubJoinRequest.user_id == current.id,
        ).with_for_update().first()
        if existing and existing.status == ClubJoinRequestStatus.PENDING.value:
            db.commit()
            raise HTTPException(status_code=409, detail="Заявка в этот клуб уже отправлена.")
        if existing:
            existing.status = ClubJoinRequestStatus.PENDING.value
            existing.created_at = now
            existing.responded_at = None
        else:
            db.add(ClubJoinRequest(
                club_id=club.id,
                user_id=current.id,
                status=ClubJoinRequestStatus.PENDING.value,
                created_at=now,
            ))
        try:
            db.commit()
        except IntegrityError:
            _handle_integrity_error(db, "Заявка уже создана. Обнови список клубов.")
        await notify_user(db, club.owner_id, "club_join_request", f"{current.display_name} просится в клуб «{club.name}» по коду")
        return {"message": "Код верный. Заявка отправлена владельцу клуба.", "club": _club_brief(club, db, current), "joined": False}

    db.add(ClubMember(club_id=club.id, user_id=current.id, role=ClubMemberRole.MEMBER.value))
    existing_request = db.query(ClubJoinRequest).filter(
        ClubJoinRequest.club_id == club.id,
        ClubJoinRequest.user_id == current.id,
        ClubJoinRequest.status == ClubJoinRequestStatus.PENDING.value,
    ).with_for_update().first()
    if existing_request:
        existing_request.status = ClubJoinRequestStatus.ACCEPTED.value
        existing_request.responded_at = now
    try:
        db.commit()
        db.refresh(club)
    except IntegrityError:
        _handle_integrity_error(db, "Ты уже вступил(а) в этот клуб или достигнут лимит участников.")
    await notify_user(db, club.owner_id, "club_join", f"{current.display_name} вступил(а) в клуб «{club.name}» по коду")
    return {"message": f"Ты вступил(а) в клуб «{club.name}»", "club": _club_brief(club, db, current), "joined": True}


@router.get("/search")
def search_clubs(
    q: str = Query(..., min_length=2, max_length=40),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = re.sub(r"\s+", " ", q).strip()
    if len(query) < 2:
        raise HTTPException(status_code=400, detail="Для поиска введи минимум 2 символа.")
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    clubs = db.query(Club).filter(
        Club.name.ilike(f"%{escaped}%", escape="\\")
    ).order_by(Club.name.asc()).limit(15).all()
    results = []
    for club in clubs:
        results.append({
            "id": club.id,
            "name": club.name,
            "member_count": _member_count(db, club.id),
            "is_member": _is_member(db, club.id, current.id) is not None,
            "instant_join": bool(club.instant_join),
            "has_pending_request": db.query(ClubJoinRequest).filter(
                ClubJoinRequest.club_id == club.id,
                ClubJoinRequest.user_id == current.id,
                ClubJoinRequest.status == ClubJoinRequestStatus.PENDING.value,
            ).first() is not None,
        })
    return {"results": results}


@router.post("/request")
@limiter.limit("20/hour")
async def request_join(
    request: Request,
    data: ClubIdIn,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _lock_user(db, current.id)
    club = _lock_club(db, data.club_id)
    if not club:
        raise HTTPException(status_code=404, detail="Клуб не найден")
    if _is_member(db, club.id, current.id):
        raise HTTPException(status_code=409, detail="Ты уже в этом клубе.")
    _ensure_membership_capacity(db, current.id)
    if _member_count(db, club.id) >= MAX_MEMBERS:
        raise HTTPException(status_code=409, detail=f"Клуб заполнен (максимум {MAX_MEMBERS} участников).")

    if club.instant_join:
        # Public search reveals only the club ID, never the invitation secret.
        # Instant-join clubs must be entered through POST /join with that secret.
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Для мгновенного вступления нужен код приглашения. Введи его в форме «Вступить по коду».",
        )

    existing = db.query(ClubJoinRequest).filter(
        ClubJoinRequest.club_id == club.id,
        ClubJoinRequest.user_id == current.id,
    ).with_for_update().first()
    if existing and existing.status == ClubJoinRequestStatus.PENDING.value:
        raise HTTPException(status_code=409, detail="Заявка уже отправлена.")
    if existing:
        existing.status = ClubJoinRequestStatus.PENDING.value
        existing.created_at = datetime.utcnow()
        existing.responded_at = None
    else:
        db.add(ClubJoinRequest(club_id=club.id, user_id=current.id, status=ClubJoinRequestStatus.PENDING.value))
    try:
        db.commit()
    except IntegrityError:
        _handle_integrity_error(db, "Заявка уже отправлена. Обнови список клубов.")
    await notify_user(db, club.owner_id, "club_join_request", f"{current.display_name} просится в клуб «{club.name}»")
    return {"message": "Заявка отправлена владельцу", "joined": False}


def _check_user_capacity_and_add_member(db: Session, club: Club, user_id: int, as_owner: bool) -> None:
    _ensure_membership_capacity(db, user_id)
    if _member_count(db, club.id) >= MAX_MEMBERS:
        raise HTTPException(status_code=409, detail=f"Клуб заполнен (максимум {MAX_MEMBERS} участников).")
    if not _is_member(db, club.id, user_id):
        db.add(ClubMember(
            club_id=club.id,
            user_id=user_id,
            role=ClubMemberRole.OWNER.value if as_owner else ClubMemberRole.MEMBER.value,
        ))


@router.post("/requests/respond")
@limiter.limit("30/hour")
async def respond_request(
    request: Request,
    data: RequestRespondIn,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    initial_request = db.get(ClubJoinRequest, data.request_id)
    if not initial_request:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    _lock_users(db, current.id, initial_request.user_id)
    club = _lock_club(db, initial_request.club_id)
    req = db.query(ClubJoinRequest).filter(
        ClubJoinRequest.id == data.request_id,
    ).with_for_update().populate_existing().first()
    if not req or req.status != ClubJoinRequestStatus.PENDING.value:
        raise HTTPException(status_code=404, detail="Заявка уже обработана или не найдена.")
    if not club or club.owner_id != current.id:
        raise HTTPException(status_code=403, detail="Только владелец клуба может обрабатывать заявки.")

    req.responded_at = datetime.utcnow()
    if data.accept:
        if not _is_member(db, club.id, req.user_id):
            _check_user_capacity_and_add_member(db, club, req.user_id, as_owner=False)
        req.status = ClubJoinRequestStatus.ACCEPTED.value
        try:
            db.commit()
        except IntegrityError:
            _handle_integrity_error(db, "Не удалось принять заявку: изменился состав клуба. Обнови данные.")
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
    for membership in memberships:
        club = db.get(Club, membership.club_id)
        if club:
            clubs.append(_club_brief(club, db, current))
    # Defensive recovery for old data if an owner row was removed from club_members.
    owned_ids = [club.id for club in db.query(Club).filter(Club.owner_id == current.id).all()]
    for owned_id in owned_ids:
        if not any(club["id"] == owned_id for club in clubs):
            club = db.get(Club, owned_id)
            if club:
                clubs.append(_club_brief(club, db, current))

    incoming = []
    if owned_ids:
        requests = db.query(ClubJoinRequest).filter(
            ClubJoinRequest.club_id.in_(owned_ids),
            ClubJoinRequest.status == ClubJoinRequestStatus.PENDING.value,
        ).order_by(ClubJoinRequest.created_at.desc()).limit(50).all()
        for req in requests:
            user = db.get(User, req.user_id)
            club = db.get(Club, req.club_id)
            if user and club:
                incoming.append({
                    "request_id": req.id,
                    "club_id": club.id,
                    "club_name": club.name,
                    "user": {"id": user.id, "username": user.username, "display_name": user.display_name, "level": user.level},
                    "created_at": req.created_at.isoformat() if req.created_at else None,
                })
    return {"clubs": clubs, "incoming_requests": incoming, "owned_count": _owned_club_count(db, current.id), "membership_count": _user_membership_count(db, current.id)}


@router.get("/{club_id}")
def club_detail(club_id: int, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    club = db.get(Club, club_id)
    if not club:
        raise HTTPException(status_code=404, detail="Клуб не найден")
    if not _is_member(db, club.id, current.id):
        raise HTTPException(status_code=403, detail="Клуб виден только участникам. Вступи по коду или отправь заявку.")
    return {
        "club": _club_brief(club, db, current),
        "members": _club_members(db, club.id, current),
        "rankings": _rankings(db, club.id, current),
    }


@router.put("/{club_id}")
@limiter.limit("20/hour")
async def update_club(
    club_id: int,
    request: Request,
    data: UpdateClubIn,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _lock_user(db, current.id)
    club = _lock_club(db, club_id)
    if not club:
        raise HTTPException(status_code=404, detail="Клуб не найден")
    if club.owner_id != current.id:
        raise HTTPException(status_code=403, detail="Только владелец может менять настройки клуба.")
    if data.name is None and data.instant_join is None:
        raise HTTPException(status_code=400, detail="Не переданы настройки для изменения.")
    if data.name is not None:
        club.name = data.name
    if data.instant_join is not None:
        club.instant_join = data.instant_join
    try:
        db.commit()
        db.refresh(club)
    except IntegrityError:
        _handle_integrity_error(db, "Клуб с таким названием уже существует у тебя.")
    return {"message": "Настройки клуба сохранены", "club": _club_brief(club, db, current)}


@router.delete("/{club_id}")
@limiter.limit("10/hour")
async def delete_club(
    club_id: int,
    request: Request,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _lock_user(db, current.id)
    club = _lock_club(db, club_id)
    if not club:
        raise HTTPException(status_code=404, detail="Клуб не найден")
    if club.owner_id != current.id:
        raise HTTPException(status_code=403, detail="Только владелец может удалить клуб.")
    name = club.name
    member_ids = [row.user_id for row in db.query(ClubMember).filter(ClubMember.club_id == club.id).all() if row.user_id != current.id]
    db.query(ClubJoinRequest).filter(ClubJoinRequest.club_id == club.id).delete(synchronize_session=False)
    db.query(ClubMember).filter(ClubMember.club_id == club.id).delete(synchronize_session=False)
    db.delete(club)
    db.commit()
    for user_id in member_ids:
        await notify_user(db, user_id, "club_deleted", f"Клуб «{name}» удалён владельцем")
    return {"message": f"Клуб «{name}» удалён"}


def _transfer_owner_locked(db: Session, club: Club, current: User, new_owner_id: int) -> User:
    if new_owner_id == current.id:
        raise HTTPException(status_code=400, detail="Ты уже владелец этого клуба.")
    new_owner = db.get(User, new_owner_id)
    member = _is_member(db, club.id, new_owner_id)
    if not new_owner or not member:
        raise HTTPException(status_code=400, detail="Передать клуб можно только текущему участнику.")
    if _owned_club_count(db, new_owner_id) >= MAX_OWNED_CLUBS:
        raise HTTPException(status_code=409, detail=f"Новый владелец уже владеет {MAX_OWNED_CLUBS} клубами.")
    old_member = _is_member(db, club.id, current.id)
    if not old_member:
        db.add(ClubMember(club_id=club.id, user_id=current.id, role=ClubMemberRole.MEMBER.value))
    else:
        old_member.role = ClubMemberRole.MEMBER.value
    member.role = ClubMemberRole.OWNER.value
    club.owner_id = new_owner.id
    return new_owner


@router.post("/{club_id}/transfer-owner")
@limiter.limit("10/hour")
async def transfer_owner(
    club_id: int,
    request: Request,
    data: TransferOwnerIn,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _lock_users(db, current.id, data.user_id)
    club = _lock_club(db, club_id)
    if not club:
        raise HTTPException(status_code=404, detail="Клуб не найден")
    if club.owner_id != current.id:
        raise HTTPException(status_code=403, detail="Только владелец может передать клуб.")
    new_owner = _transfer_owner_locked(db, club, current, data.user_id)
    try:
        db.commit()
    except IntegrityError:
        _handle_integrity_error(db, "Передача невозможна: новый владелец уже имеет клуб с таким названием.")
    await notify_user(db, new_owner.id, "club_owner_transferred", f"Теперь ты владелец клуба «{club.name}»")
    return {"message": "Владелец клуба изменён", "club": _club_brief(club, db, current)}


@router.post("/{club_id}/kick")
@limiter.limit("30/hour")
async def kick_member(
    club_id: int,
    request: Request,
    data: KickIn,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _lock_users(db, current.id, data.user_id)
    club = _lock_club(db, club_id)
    if not club or club.owner_id != current.id:
        raise HTTPException(status_code=403, detail="Только владелец может исключать участников.")
    if data.user_id == current.id:
        raise HTTPException(status_code=400, detail="Нельзя исключить владельца.")
    member = _is_member(db, club.id, data.user_id)
    if not member:
        raise HTTPException(status_code=404, detail="Участник не найден")
    db.delete(member)
    db.query(ClubJoinRequest).filter(
        ClubJoinRequest.club_id == club.id,
        ClubJoinRequest.user_id == data.user_id,
        ClubJoinRequest.status == ClubJoinRequestStatus.PENDING.value,
    ).delete(synchronize_session=False)
    db.commit()
    await notify_user(db, data.user_id, "club_kicked", f"Тебя исключили из клуба «{club.name}»")
    return {"message": "Участник исключён"}


@router.post("/{club_id}/leave")
@limiter.limit("20/hour")
async def leave_club(
    club_id: int,
    request: Request,
    data: LeaveClubIn = LeaveClubIn(),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_ids = [current.id] + ([data.transfer_to_user_id] if data.transfer_to_user_id else [])
    _lock_users(db, *user_ids)
    club = _lock_club(db, club_id)
    if not club:
        raise HTTPException(status_code=404, detail="Клуб не найден")
    member = _is_member(db, club.id, current.id)
    if not member:
        raise HTTPException(status_code=409, detail="Ты не состоишь в этом клубе.")
    if club.owner_id == current.id:
        if not data.transfer_to_user_id:
            raise HTTPException(status_code=409, detail="Владелец должен передать клуб другому участнику или удалить клуб.")
        new_owner = _transfer_owner_locked(db, club, current, data.transfer_to_user_id)
        old_membership = _is_member(db, club.id, current.id)
        if old_membership:
            db.delete(old_membership)
        try:
            db.commit()
        except IntegrityError:
            _handle_integrity_error(db, "Передача невозможна: новый владелец уже имеет клуб с таким названием.")
        await notify_user(db, new_owner.id, "club_owner_transferred", f"Ты стал владельцем клуба «{club.name}»; предыдущий владелец вышел из клуба.")
        return {"message": "Клуб передан новому владельцу, ты вышел из клуба."}
    db.delete(member)
    db.query(ClubJoinRequest).filter(
        ClubJoinRequest.club_id == club.id,
        ClubJoinRequest.user_id == current.id,
        ClubJoinRequest.status == ClubJoinRequestStatus.PENDING.value,
    ).delete(synchronize_session=False)
    db.commit()
    return {"message": "Ты вышел из клуба"}
