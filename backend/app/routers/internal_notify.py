"""Secret-protected scheduled proactive notification tick."""
import hmac
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import SessionLocal, get_db
from ..models import LeagueRankSnapshot, User, WeeklySummary
from ..rate_limit import limiter
from ..services.league import league_ranking_key
from ..services.proactive import (
    daily_bonus_reminder_text,
    format_overtaken_message,
    local_date_for_user,
    profile_visible_on_leaderboard,
    send_proactive,
    user_local_datetime,
)
from ..services import xp_v6 as X6

router = APIRouter(prefix="/api/internal/notify", tags=["Internal notifications"])


def _authorize_cron_secret(header_value: str | None) -> None:
    expected = get_settings().CRON_SECRET or ""
    if not expected:
        raise HTTPException(status_code=404, detail="Not found")
    if not header_value or not hmac.compare_digest(
        header_value.encode("utf-8"), expected.encode("utf-8")
    ):
        raise HTTPException(status_code=403, detail="Forbidden")


def _monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _rank_current_weeks(db: Session, now: datetime) -> list[dict[str, Any]]:
    """Compute current local-week ranks with the same score/XP/load/ID tie-break as the leaderboard."""
    from ..routers.sync import _is_paused_week, _user_divisions_for_week

    users = db.query(User).order_by(User.id.asc()).all()
    summaries = (
        db.query(WeeklySummary, User)
        .join(User, User.id == WeeklySummary.user_id)
        .filter(
            WeeklySummary.week_start >= datetime.combine(now.date() - timedelta(days=8), time.min),
            WeeklySummary.week_start < datetime.combine(now.date() + timedelta(days=1), time.min),
        )
        .all()
    )

    grouped: dict[date, list[tuple[WeeklySummary, User]]] = {}
    for summary, user in summaries:
        local_today = local_date_for_user(user, now)
        expected_week = _monday(local_today)
        if summary.week_start.date() != expected_week:
            continue
        if _is_paused_week(user, expected_week):
            continue
        grouped.setdefault(expected_week, []).append((summary, user))

    results: list[dict[str, Any]] = []
    division_order = {name: index for index, name in enumerate(X6.DIVISION_NAMES)}
    division_order["Open"] = len(division_order)
    division_order[None] = len(division_order) + 1

    for week_start, participants in grouped.items():
        participant_ids = [user.id for _summary, user in participants]
        divisions_by_user = _user_divisions_for_week(db, participant_ids, week_start)
        beta = len(participants) < X6.BETA_SINGLE_LEAGUE_UNTIL_USERS
        rows = []
        for summary, user in participants:
            division, source = divisions_by_user.get(user.id, (None, "provisional"))
            if beta:
                division, source = "Бета-лига", "beta"
            rows.append({
                "user": user,
                "summary": summary,
                "week_start": week_start,
                "division": division,
                "division_source": source,
                "score": float(summary.league_score or 0.0),
                "weekly_xp": float(summary.total_xp or 0.0),
                "actual_load": float(summary.actual_load or 0.0),
            })

        rows.sort(key=lambda row: (
            division_order.get(row["division"], 99),
            *league_ranking_key(
                row["score"], row["weekly_xp"], row["actual_load"], row["user"].id
            ),
        ))
        per_division: dict[str | None, int] = {}
        for position, row in enumerate(rows, start=1):
            if beta:
                rank = position
            else:
                division = row["division"]
                per_division[division] = per_division.get(division, 0) + 1
                rank = per_division[division]
            row["rank"] = rank
            results.append(row)
    return results


def _overtaker_for(
    entry: dict[str, Any],
    entries: list[dict[str, Any]],
    old_ranks: dict[tuple[date, int], int],
    previous_rank: int,
) -> dict[str, Any] | None:
    same_league = [
        row for row in entries
        if row["week_start"] == entry["week_start"]
        and row["division"] == entry["division"]
        and row["rank"] < entry["rank"]
    ]
    newly_ahead = [
        row for row in same_league
        if old_ranks.get((row["week_start"], row["user"].id), row["rank"]) >= previous_rank
    ]
    candidates = newly_ahead or same_league
    return max(candidates, key=lambda row: row["rank"]) if candidates else None


async def _deliver_week_result_if_due(db: Session, user: User, now: datetime) -> bool:
    local_today = local_date_for_user(user, now)
    week_start = _monday(local_today) - timedelta(days=7)
    if user.telegram_last_notified_week is not None and user.telegram_last_notified_week >= week_start:
        return False
    summary = (
        db.query(WeeklySummary)
        .filter(
            WeeklySummary.user_id == user.id,
            WeeklySummary.week_start == datetime.combine(week_start, time.min),
            WeeklySummary.finalized.is_(True),
        )
        .first()
    )
    if summary is None:
        return False
    parts = [
        f"Итоги недели {week_start.isoformat()}:",
        f"{round(float(summary.total_xp or 0), 1)} XP",
        f"Дней: {summary.training_days or 0}",
    ]
    if summary.league_score is not None:
        parts.append(f"League score: {round(float(summary.league_score), 1)}")
    sent = await send_proactive(db, user, "weekly_results", "\n".join(parts), now=now)
    if sent:
        user.telegram_last_notified_week = week_start
        db.commit()
    return sent


@router.post("/tick")
@limiter.limit("4/minute")
async def notify_tick(
    request: Request,
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
    db: Session = Depends(get_db),
):
    _authorize_cron_secret(x_cron_secret)
    now = datetime.now(timezone.utc)
    users = db.query(User).order_by(User.id.asc()).all()
    rank_entries = _rank_current_weeks(db, now)
    rank_by_key = {(entry["week_start"], entry["user"].id): entry for entry in rank_entries}
    week_starts = sorted({entry["week_start"] for entry in rank_entries})
    snapshots = (
        db.query(LeagueRankSnapshot)
        .filter(LeagueRankSnapshot.week_start.in_(week_starts))
        .all()
        if week_starts else []
    )
    snapshot_by_key = {(row.week_start, row.user_id): row for row in snapshots}
    old_ranks = {key: row.rank for key, row in snapshot_by_key.items()}

    sent = {"league_overtaken": 0, "daily_bonus_reminder": 0, "weekly_results": 0}
    overtaken_events: list[tuple[User, dict[str, Any], str]] = []
    for entry in rank_entries:
        key = (entry["week_start"], entry["user"].id)
        snapshot = snapshot_by_key.get(key)
        if snapshot is None or entry["rank"] <= snapshot.rank:
            continue
        overtaker = _overtaker_for(entry, rank_entries, old_ranks, snapshot.rank)
        if overtaker is None:
            text = f"Кто-то обошёл тебя в лиге: ты {entry['rank']}-й."
        else:
            visible_name = (
                overtaker["user"].display_name or overtaker["user"].username
            ) if profile_visible_on_leaderboard(db, entry["user"], overtaker["user"]) else None
            delta = float(overtaker["score"] - entry["score"])
            text = format_overtaken_message(
                rank=entry["rank"], delta=delta, visible_name=visible_name
            )
        overtaken_events.append((entry["user"], entry, text))

    # Overtakes are attempted first so they win the one-message-per-day budget.
    from .notifications import notify_user

    for user, entry, message in overtaken_events:
        await notify_user(db, user.id, "league_overtaken", message, link="/compete", send_telegram=False)
        if await send_proactive(db, user, "league_overtaken", message, now=now):
            sent["league_overtaken"] += 1

    # Persist the newest ranks only after evaluating all prior snapshots.
    for entry in rank_entries:
        key = (entry["week_start"], entry["user"].id)
        snapshot = snapshot_by_key.get(key)
        if snapshot is None:
            db.add(LeagueRankSnapshot(
                user_id=entry["user"].id,
                week_start=entry["week_start"],
                rank=entry["rank"],
            ))
        else:
            snapshot.rank = entry["rank"]
            snapshot.created_at = now.replace(tzinfo=None)
    db.commit()

    for user in users:
        reminder = daily_bonus_reminder_text(db, user, now)
        if reminder and await send_proactive(db, user, "daily_bonus_reminder", reminder, now=now):
            sent["daily_bonus_reminder"] += 1

    for user in users:
        if not user.telegram_chat_id or not user.telegram_notify:
            continue
        if await _deliver_week_result_if_due(db, user, now):
            sent["weekly_results"] += 1

    return {
        "ok": True,
        "evaluated_users": len(users),
        "rank_snapshots": len(rank_entries),
        "sent": sent,
        "checked_at": now.isoformat(),
    }
