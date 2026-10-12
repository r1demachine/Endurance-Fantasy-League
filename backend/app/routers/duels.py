"""Дуэли 1 на 1: недельный челлендж между друзьями."""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user
from ..models import (
    Duel,
    DuelStatus,
    Friendship,
    FriendshipStatus,
    User,
    WeeklySummary,
)
from ..rate_limit import limiter
from ..services.notifications import notify_user
from ..services import xp_v6 as X6

router = APIRouter(prefix="/api/duels", tags=["Duels"])


class ChallengeIn(BaseModel):
    username: str = Field(..., min_length=3, max_length=32, pattern=r"^[a-z0-9_]{3,32}$")

    @field_validator("username", mode="before")
    @classmethod
    def normalize_username(cls, value):
        if isinstance(value, str):
            return value.strip().lower()
        return value


class RespondIn(BaseModel):
    duel_id: int
    accept: bool


def _monday_dt(d: date | None = None) -> datetime:
    day = d or date.today()
    ws = X6.week_start(day)
    return datetime.combine(ws, datetime.min.time())


def _are_friends(db: Session, a: int, b: int) -> bool:
    return (
        db.query(Friendship)
        .filter(
            or_(
                and_(Friendship.from_user_id == a, Friendship.to_user_id == b),
                and_(Friendship.from_user_id == b, Friendship.to_user_id == a),
            ),
            Friendship.status == FriendshipStatus.ACCEPTED,
        )
        .first()
        is not None
    )


def _pair_active(db: Session, a: int, b: int, week_start: datetime) -> Duel | None:
    return (
        db.query(Duel)
        .filter(
            Duel.week_start == week_start,
            Duel.status.in_([DuelStatus.PENDING.value, DuelStatus.ACTIVE.value]),
            or_(
                and_(Duel.challenger_id == a, Duel.opponent_id == b),
                and_(Duel.challenger_id == b, Duel.opponent_id == a),
            ),
        )
        .first()
    )


def _user_brief(u: User) -> dict:
    return {
        "id": u.id,
        "username": u.username,
        "display_name": u.display_name,
        "level": u.level,
    }


def _serialize(d: Duel, me_id: int, db: Session) -> dict:
    challenger = db.get(User, d.challenger_id)
    opponent = db.get(User, d.opponent_id)
    winner = db.get(User, d.winner_id) if d.winner_id else None
    my_role = "challenger" if d.challenger_id == me_id else "opponent"
    other = opponent if my_role == "challenger" else challenger
    live_me = None
    live_other = None
    if d.status == DuelStatus.ACTIVE.value:
        s_me = (
            db.query(WeeklySummary)
            .filter(WeeklySummary.user_id == me_id, WeeklySummary.week_start == d.week_start)
            .first()
        )
        other_id = other.id if other else None
        s_ot = (
            db.query(WeeklySummary)
            .filter(WeeklySummary.user_id == other_id, WeeklySummary.week_start == d.week_start)
            .first()
            if other_id
            else None
        )
        live_me = round(float(s_me.total_xp or 0), 2) if s_me else 0.0
        live_other = round(float(s_ot.total_xp or 0), 2) if s_ot else 0.0
    return {
        "id": d.id,
        "week_start": d.week_start.date().isoformat() if d.week_start else None,
        "status": d.status,
        "my_role": my_role,
        "challenger": _user_brief(challenger) if challenger else None,
        "opponent": _user_brief(opponent) if opponent else None,
        "other": _user_brief(other) if other else None,
        "challenger_xp": d.challenger_xp,
        "opponent_xp": d.opponent_xp,
        "my_xp": (
            d.challenger_xp if my_role == "challenger" else d.opponent_xp
        )
        if d.status == DuelStatus.FINISHED.value
        else live_me,
        "other_xp": (
            d.opponent_xp if my_role == "challenger" else d.challenger_xp
        )
        if d.status == DuelStatus.FINISHED.value
        else live_other,
        "winner_id": d.winner_id,
        "winner": _user_brief(winner) if winner else None,
        "is_draw": d.status == DuelStatus.FINISHED.value and d.winner_id is None,
        "i_won": d.winner_id == me_id if d.status == DuelStatus.FINISHED.value else None,
        "created_at": d.created_at.isoformat() if d.created_at else None,
        "finished_at": d.finished_at.isoformat() if d.finished_at else None,
    }


@router.post("/challenge")
@limiter.limit("20/hour")
async def challenge(
    request: Request,
    data: ChallengeIn,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    uname = data.username.strip().lower()
    target = db.query(User).filter(User.username == uname).first()
    if not target:
        raise HTTPException(status_code=404, detail="Атлет не найден")
    if target.id == current.id:
        raise HTTPException(status_code=400, detail="Нельзя вызвать самого себя")
    if not _are_friends(db, current.id, target.id):
        raise HTTPException(status_code=400, detail="Дуэль только между друзьями")

    ws = _monday_dt()
    if _pair_active(db, current.id, target.id, ws):
        raise HTTPException(
            status_code=400,
            detail="Уже есть активная или ожидающая дуэль с этим другом на эту неделю",
        )

    duel = Duel(
        challenger_id=current.id,
        opponent_id=target.id,
        week_start=ws,
        status=DuelStatus.PENDING.value,
    )
    db.add(duel)
    db.commit()
    db.refresh(duel)
    await notify_user(
        db,
        target.id,
        "duel_challenge",
        f"{current.display_name} вызывает тебя на дуэль этой недели!",
    )
    return {"message": f"Вызов отправлен: {target.display_name}", "duel": _serialize(duel, current.id, db)}


@router.post("/respond")
@limiter.limit("30/hour")
async def respond(
    request: Request,
    data: RespondIn,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    duel = (
        db.query(Duel)
        .filter(
            Duel.id == data.duel_id,
            Duel.opponent_id == current.id,
            Duel.status == DuelStatus.PENDING.value,
        )
        .first()
    )
    if not duel:
        raise HTTPException(status_code=404, detail="Заявка на дуэль не найдена")

    if duel.week_start.date() != X6.week_start(date.today()):
        duel.status = DuelStatus.DECLINED.value
        duel.responded_at = datetime.utcnow()
        db.commit()
        raise HTTPException(status_code=400, detail="Неделя этой дуэли уже прошла")

    duel.responded_at = datetime.utcnow()
    if data.accept:
        duel.status = DuelStatus.ACTIVE.value
        db.commit()
        await notify_user(
            db,
            duel.challenger_id,
            "duel_accepted",
            f"{current.display_name} принял(а) дуэль!",
        )
        return {"message": "Дуэль принята!", "duel": _serialize(duel, current.id, db)}

    duel.status = DuelStatus.DECLINED.value
    db.commit()
    await notify_user(
        db,
        duel.challenger_id,
        "duel_declined",
        f"{current.display_name} отклонил(а) дуэль",
    )
    return {"message": "Дуэль отклонена", "duel": _serialize(duel, current.id, db)}


@router.get("/current")
def current_duel(
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Активная или pending дуэль текущей недели (для карточки «Твоя неделя»)."""
    ws = _monday_dt()
    duel = (
        db.query(Duel)
        .filter(
            Duel.week_start == ws,
            Duel.status.in_([DuelStatus.PENDING.value, DuelStatus.ACTIVE.value]),
            or_(Duel.challenger_id == current.id, Duel.opponent_id == current.id),
        )
        .order_by(Duel.created_at.desc())
        .first()
    )
    if not duel:
        return {"duel": None}
    return {"duel": _serialize(duel, current.id, db)}


@router.get("")
def list_duels(
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(Duel)
        .filter(or_(Duel.challenger_id == current.id, Duel.opponent_id == current.id))
        .order_by(Duel.created_at.desc())
        .limit(40)
        .all()
    )
    return {"items": [_serialize(d, current.id, db) for d in rows]}


def finalize_duels_for_week(db: Session, week_start_d: date) -> int:
    """Закрытие дуэлей при закрытии недели. Возвращает число завершённых."""
    ws_dt = datetime.combine(week_start_d, datetime.min.time())
    closed = 0

    pending = (
        db.query(Duel)
        .filter(Duel.week_start == ws_dt, Duel.status == DuelStatus.PENDING.value)
        .all()
    )
    for d in pending:
        d.status = DuelStatus.DECLINED.value
        d.responded_at = datetime.utcnow()

    active = (
        db.query(Duel)
        .filter(Duel.week_start == ws_dt, Duel.status == DuelStatus.ACTIVE.value)
        .all()
    )
    for d in active:
        s1 = (
            db.query(WeeklySummary)
            .filter(
                WeeklySummary.user_id == d.challenger_id,
                WeeklySummary.week_start == ws_dt,
            )
            .first()
        )
        s2 = (
            db.query(WeeklySummary)
            .filter(
                WeeklySummary.user_id == d.opponent_id,
                WeeklySummary.week_start == ws_dt,
            )
            .first()
        )
        xp1 = float(s1.total_xp or 0) if s1 else 0.0
        xp2 = float(s2.total_xp or 0) if s2 else 0.0
        d.challenger_xp = round(xp1, 2)
        d.opponent_xp = round(xp2, 2)
        if xp1 > xp2:
            d.winner_id = d.challenger_id
        elif xp2 > xp1:
            d.winner_id = d.opponent_id
        else:
            d.winner_id = None
        d.status = DuelStatus.FINISHED.value
        d.finished_at = datetime.utcnow()
        closed += 1

        if d.winner_id is None:
            text_c = f"Дуэль завершена: ничья ({d.challenger_xp} : {d.opponent_xp} XP)"
            text_o = text_c
        elif d.winner_id == d.challenger_id:
            text_c = f"Победа в дуэли! {d.challenger_xp} : {d.opponent_xp} XP"
            text_o = f"Поражение в дуэли. {d.opponent_xp} : {d.challenger_xp} XP"
        else:
            text_c = f"Поражение в дуэли. {d.challenger_xp} : {d.opponent_xp} XP"
            text_o = f"Победа в дуэли! {d.opponent_xp} : {d.challenger_xp} XP"

        from ..models import Notification

        db.add(Notification(user_id=d.challenger_id, type="duel_finished", text=text_c, read=False))
        db.add(Notification(user_id=d.opponent_id, type="duel_finished", text=text_o, read=False))

    if pending or active:
        db.commit()
    return closed
