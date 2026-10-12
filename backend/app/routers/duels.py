"""Недельные дуэли 1 на 1 с защитой от повторного вызова и явной ничьей без тренировок."""
import logging
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import and_, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user
from ..models import (
    Activity,
    Duel,
    DuelStatus,
    Friendship,
    FriendshipStatus,
    Notification,
    User,
    WeeklySummary,
)
from ..rate_limit import limiter
from ..services.notifications import notify_user
from ..services import xp_v6 as X6

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/duels", tags=["Duels"])


class ChallengeIn(BaseModel):
    username: str = Field(..., min_length=3, max_length=32, pattern=r"^[a-z0-9_]{3,32}$")

    @field_validator("username", mode="before")
    @classmethod
    def normalize_username(cls, value):
        if isinstance(value, str):
            return value.strip().lstrip("@").lower()
        return value


class RespondIn(BaseModel):
    duel_id: int
    accept: bool


def _monday_dt(d: Optional[date] = None) -> datetime:
    day = d or date.today()
    return datetime.combine(X6.week_start(day), datetime.min.time())


def _normalized_pair(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a < b else (b, a)


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


def _pair_active(db: Session, a: int, b: int, week_start: datetime) -> Optional[Duel]:
    low, high = _normalized_pair(a, b)
    return (
        db.query(Duel)
        .filter(
            Duel.week_start == week_start,
            Duel.status.in_([DuelStatus.PENDING.value, DuelStatus.ACTIVE.value]),
            Duel.pair_low_id == low,
            Duel.pair_high_id == high,
        )
        .first()
    )


def _user_brief(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "level": user.level,
    }


def _serialize(duel: Duel, me_id: int, db: Session) -> dict:
    challenger = db.get(User, duel.challenger_id)
    opponent = db.get(User, duel.opponent_id)
    winner = db.get(User, duel.winner_id) if duel.winner_id else None
    my_role = "challenger" if duel.challenger_id == me_id else "opponent"
    other = opponent if my_role == "challenger" else challenger
    live_me = None
    live_other = None
    if duel.status == DuelStatus.ACTIVE.value:
        my_summary = db.query(WeeklySummary).filter(
            WeeklySummary.user_id == me_id,
            WeeklySummary.week_start == duel.week_start,
        ).first()
        other_id = other.id if other else None
        other_summary = (
            db.query(WeeklySummary).filter(
                WeeklySummary.user_id == other_id,
                WeeklySummary.week_start == duel.week_start,
            ).first()
            if other_id else None
        )
        live_me = round(float(my_summary.total_xp or 0), 2) if my_summary else 0.0
        live_other = round(float(other_summary.total_xp or 0), 2) if other_summary else 0.0

    return {
        "id": duel.id,
        "week_start": duel.week_start.date().isoformat() if duel.week_start else None,
        "status": duel.status,
        "my_role": my_role,
        "challenger": _user_brief(challenger) if challenger else None,
        "opponent": _user_brief(opponent) if opponent else None,
        "other": _user_brief(other) if other else None,
        "challenger_xp": duel.challenger_xp,
        "opponent_xp": duel.opponent_xp,
        "my_xp": (
            duel.challenger_xp if my_role == "challenger" else duel.opponent_xp
        ) if duel.status == DuelStatus.FINISHED.value else live_me,
        "other_xp": (
            duel.opponent_xp if my_role == "challenger" else duel.challenger_xp
        ) if duel.status == DuelStatus.FINISHED.value else live_other,
        "winner_id": duel.winner_id,
        "winner": _user_brief(winner) if winner else None,
        "is_draw": duel.status == DuelStatus.FINISHED.value and duel.winner_id is None,
        "is_no_activity_draw": bool(duel.is_no_activity_draw),
        "i_won": duel.winner_id == me_id if duel.status == DuelStatus.FINISHED.value else None,
        "created_at": duel.created_at.isoformat() if duel.created_at else None,
        "finished_at": duel.finished_at.isoformat() if duel.finished_at else None,
    }


@router.post("/challenge")
@limiter.limit("20/hour")
async def challenge(
    request: Request,
    data: ChallengeIn,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    username = data.username.strip().lstrip("@").lower()
    target = db.query(User).filter(User.username == username).first()
    if not target:
        raise HTTPException(status_code=404, detail="Атлет не найден")
    if target.id == current.id:
        raise HTTPException(status_code=400, detail="Нельзя вызвать самого себя")
    if not _are_friends(db, current.id, target.id):
        raise HTTPException(status_code=400, detail="Дуэль доступна только между друзьями")

    week_start = _monday_dt()
    if _pair_active(db, current.id, target.id, week_start):
        raise HTTPException(status_code=409, detail="На этой неделе уже есть активная или ожидающая дуэль с этим другом.")

    pair_low_id, pair_high_id = _normalized_pair(current.id, target.id)
    duel = Duel(
        challenger_id=current.id,
        opponent_id=target.id,
        week_start=week_start,
        status=DuelStatus.PENDING.value,
        pair_low_id=pair_low_id,
        pair_high_id=pair_high_id,
    )
    db.add(duel)
    try:
        db.commit()
        db.refresh(duel)
    except IntegrityError:
        db.rollback()
        logger.info(
            "Concurrent duplicate duel rejected: week=%s pair=(%s,%s)",
            week_start.date(), pair_low_id, pair_high_id,
        )
        raise HTTPException(
            status_code=409,
            detail="На этой неделе уже создана активная или ожидающая дуэль с этим другом.",
        )
    await notify_user(
        db,
        target.id,
        "duel_challenge",
        f"{current.display_name} вызывает тебя на дуэль этой недели!",
    )
    return {
        "message": f"Вызов отправлен: {target.display_name}",
        "duel": _serialize(duel, current.id, db),
    }


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
        .with_for_update()
        .first()
    )
    if not duel:
        raise HTTPException(status_code=404, detail="Заявка на дуэль не найдена")

    if duel.week_start.date() != X6.week_start(date.today()):
        duel.status = DuelStatus.DECLINED.value
        duel.responded_at = datetime.utcnow()
        db.commit()
        await notify_user(
            db,
            duel.challenger_id,
            "duel_auto_declined",
            f"Вызов на дуэль от {current.display_name} остался без ответа до окончания недели.",
        )
        raise HTTPException(status_code=409, detail="Неделя этой дуэли уже прошла; заявка автоматически отклонена.")

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
    """Активная или pending дуэль текущей недели."""
    week_start = _monday_dt()
    duel = (
        db.query(Duel)
        .filter(
            Duel.week_start == week_start,
            Duel.status.in_([DuelStatus.PENDING.value, DuelStatus.ACTIVE.value]),
            or_(Duel.challenger_id == current.id, Duel.opponent_id == current.id),
        )
        .order_by(Duel.created_at.desc())
        .first()
    )
    return {"duel": _serialize(duel, current.id, db) if duel else None}


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
    return {"items": [_serialize(duel, current.id, db) for duel in rows]}


def finalize_duels_for_week(db: Session, week_start_d: date) -> int:
    """Закрывает дуэли недели; ошибка транзакции логируется и пробрасывается."""
    week_start = datetime.combine(week_start_d, datetime.min.time())
    week_end = week_start + timedelta(days=7)
    closed = 0

    try:
        pending = (
            db.query(Duel)
            .filter(
                Duel.week_start == week_start,
                Duel.status == DuelStatus.PENDING.value,
            )
            .with_for_update()
            .all()
        )
        for duel in pending:
            duel.status = DuelStatus.DECLINED.value
            duel.responded_at = datetime.utcnow()
            db.add(Notification(
                user_id=duel.challenger_id,
                type="duel_auto_declined",
                text="Твой вызов на дуэль остался без ответа до окончания недели.",
                read=False,
            ))

        active = (
            db.query(Duel)
            .filter(
                Duel.week_start == week_start,
                Duel.status == DuelStatus.ACTIVE.value,
            )
            .with_for_update()
            .all()
        )
        for duel in active:
            challenger_summary = db.query(WeeklySummary).filter(
                WeeklySummary.user_id == duel.challenger_id,
                WeeklySummary.week_start == week_start,
            ).first()
            opponent_summary = db.query(WeeklySummary).filter(
                WeeklySummary.user_id == duel.opponent_id,
                WeeklySummary.week_start == week_start,
            ).first()

            challenger_xp = float(challenger_summary.total_xp or 0) if challenger_summary else 0.0
            opponent_xp = float(opponent_summary.total_xp or 0) if opponent_summary else 0.0
            duel.challenger_xp = round(challenger_xp, 2)
            duel.opponent_xp = round(opponent_xp, 2)

            if challenger_xp > opponent_xp:
                duel.winner_id = duel.challenger_id
            elif opponent_xp > challenger_xp:
                duel.winner_id = duel.opponent_id
            else:
                duel.winner_id = None

            has_activity = db.query(Activity.id).filter(
                Activity.user_id.in_([duel.challenger_id, duel.opponent_id]),
                func.coalesce(Activity.start_date_local, Activity.start_date) >= week_start,
                func.coalesce(Activity.start_date_local, Activity.start_date) < week_end,
            ).first() is not None
            duel.is_no_activity_draw = (
                duel.winner_id is None
                and duel.challenger_xp == 0
                and duel.opponent_xp == 0
                and not has_activity
            )
            duel.status = DuelStatus.FINISHED.value
            duel.finished_at = datetime.utcnow()
            closed += 1

            if duel.is_no_activity_draw:
                text_challenger = "Дуэль завершена ничьей 0:0: за эту неделю у участников не было тренировок."
                text_opponent = text_challenger
            elif duel.winner_id is None:
                text_challenger = f"Дуэль завершена: ничья ({duel.challenger_xp} : {duel.opponent_xp} XP)"
                text_opponent = text_challenger
            elif duel.winner_id == duel.challenger_id:
                text_challenger = f"Победа в дуэли! {duel.challenger_xp} : {duel.opponent_xp} XP"
                text_opponent = f"Поражение в дуэли. {duel.opponent_xp} : {duel.challenger_xp} XP"
            else:
                text_challenger = f"Поражение в дуэли. {duel.challenger_xp} : {duel.opponent_xp} XP"
                text_opponent = f"Победа в дуэли! {duel.opponent_xp} : {duel.challenger_xp} XP"

            db.add(Notification(
                user_id=duel.challenger_id,
                type="duel_finished",
                text=text_challenger,
                read=False,
            ))
            db.add(Notification(
                user_id=duel.opponent_id,
                type="duel_finished",
                text=text_opponent,
                read=False,
            ))

        if pending or active:
            db.commit()
        return closed
    except Exception:
        db.rollback()
        logger.exception("Failed to finalize duels for week_start=%s", week_start.date())
        raise
