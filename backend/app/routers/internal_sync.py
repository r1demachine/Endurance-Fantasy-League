"""Secret-protected scheduled incremental Intervals.icu sync.

The workflow runs every 30 minutes; this endpoint claims only accounts whose last
attempt is at least six hours old, and re-fetches eight local calendar dates
(today plus the preceding seven days) to catch delayed or corrected activities.
"""
import hmac
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import or_
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from ..auth import decrypt_secret
from ..config import get_settings
from ..database import SessionLocal, get_db
from ..models import User
from ..rate_limit import limiter

router = APIRouter(prefix="/api/internal/sync", tags=["Internal sync"])
AUTO_SYNC_INTERVAL = timedelta(hours=6)
MAX_USERS_PER_TICK = 40


def _authorize_cron_secret(header_value: str | None) -> None:
    expected = get_settings().CRON_SECRET or ""
    if not expected:
        raise HTTPException(status_code=404, detail="Not found")
    if not header_value or not hmac.compare_digest(
        header_value.encode("utf-8"), expected.encode("utf-8")
    ):
        raise HTTPException(status_code=403, detail="Forbidden")


def _aware_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def local_sync_window(timezone_name: str | None, now: datetime) -> tuple[date, date]:
    """Inclusive sync range: local today and the previous seven calendar days."""
    try:
        zone = ZoneInfo(timezone_name or "UTC")
    except (ZoneInfoNotFoundError, TypeError, ValueError):
        zone = ZoneInfo("UTC")
    local_today = _aware_utc(now).astimezone(zone).date()
    return local_today - timedelta(days=7), local_today


def auto_sync_is_due(last_auto_sync_at: datetime | None, now: datetime) -> bool:
    """Treat legacy naive timestamps as UTC and require a full six hours between attempts."""
    if last_auto_sync_at is None:
        return True
    last = _aware_utc(last_auto_sync_at)
    current = _aware_utc(now)
    return current - last >= AUTO_SYNC_INTERVAL


def _claim_auto_sync_in_worker(user_id: int) -> bool:
    """Serialize sync work across workers and reserve the next six-hour slot."""
    from .sync import _claim_sync_progress

    session = SessionLocal()
    try:
        if not _claim_sync_progress(session, user_id, 1):
            return False
        user = session.query(User).filter(User.id == user_id).first()
        if user is None:
            return False
        # This timestamp is deliberately an attempt timestamp: a broken key or
        # upstream outage must not cause retries every 30-minute cron tick.
        user.last_auto_sync_at = datetime.utcnow()
        session.commit()
        return True
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _write_progress(user_id: int, status: str, message: str | None = None) -> None:
    from .sync import _write_sync_progress

    _write_sync_progress(user_id, {
        "active": status not in {"complete", "error"},
        "status": status,
        "phase": status,
        "current_month": None,
        "message": message,
    })


async def _sync_one(candidate: dict, now: datetime) -> dict:
    """Fetch and persist a short local-time window for one eligible athlete."""
    user_id = int(candidate["id"])
    if not await run_in_threadpool(_claim_auto_sync_in_worker, user_id):
        return {"status": "skipped"}

    status = "error"
    message = "Автоматическая синхронизация не завершена."
    try:
        api_key = decrypt_secret(candidate["api_key_encrypted"])
        oldest, newest = local_sync_window(candidate.get("timezone_name"), now)
        from ..services.intervals import fetch_activities_for_user, fetch_wellness_for_user

        def report_progress(phase: str, done: int, total: int, _chunk_start: date):
            progress_status = "fetching_activities" if phase == "activities" else "fetching_wellness"
            return run_in_threadpool(
                _write_progress, user_id, progress_status,
                f"Синхронизация Intervals: {phase} ({done}/{total}).",
            )

        await run_in_threadpool(
            _write_progress, user_id, "fetching_activities",
            "Проверяем тренировки за последние 8 местных календарных дней.",
        )
        activities = await fetch_activities_for_user(
            api_key=api_key,
            athlete_id=candidate["intervals_id"],
            oldest=oldest.isoformat(),
            newest=newest.isoformat(),
            progress_callback=report_progress,
        )
        await run_in_threadpool(
            _write_progress, user_id, "fetching_wellness",
            "Обновляем сон и восстановление.",
        )
        try:
            wellness = await fetch_wellness_for_user(
                api_key=api_key,
                athlete_id=candidate["intervals_id"],
                oldest=oldest.isoformat(),
                newest=newest.isoformat(),
                progress_callback=report_progress,
            )
        except Exception:
            # Same as manual sync: wellness can be unavailable while activities are valid.
            wellness = []

        await run_in_threadpool(
            _write_progress, user_id, "processing",
            "Сохраняем изменения и пересчитываем производные данные.",
        )
        from .sync import _persist_sync_payload
        result = await run_in_threadpool(
            _persist_sync_payload,
            user_id,
            activities,
            wellness,
            False,   # no week notifications from background refreshes
            False,   # not a historical/full sync
            1,
        )
        status = "complete"
        message = "Автоматическая синхронизация успешна."
        return {
            "status": "synced",
            "synced_count": int(result.get("synced_count", 0)),
            "updated_count": int(result.get("updated_count", 0)),
        }
    finally:
        try:
            await run_in_threadpool(_write_progress, user_id, status, message)
        except Exception:
            # The work result is more important than a best-effort progress label.
            pass


@router.post("/tick")
@limiter.limit("4/minute")
async def intervals_sync_tick(
    request: Request,
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
    db: Session = Depends(get_db),
):
    _authorize_cron_secret(x_cron_secret)
    now = datetime.now(timezone.utc)
    cutoff = now.replace(tzinfo=None) - AUTO_SYNC_INTERVAL
    candidates = (
        db.query(User)
        .filter(
            User.api_key_encrypted.isnot(None),
            User.intervals_id.isnot(None),
            or_(
                User.last_auto_sync_at.is_(None),
                User.last_auto_sync_at <= cutoff,
            ),
        )
        .order_by(User.id.asc())
        .limit(MAX_USERS_PER_TICK)
        .all()
    )
    payloads = [{
        "id": user.id,
        "api_key_encrypted": user.api_key_encrypted,
        "intervals_id": user.intervals_id,
        "timezone_name": user.timezone_name,
    } for user in candidates]

    synced = failed = skipped = 0
    new_activities = updated_activities = 0
    for candidate in payloads:
        try:
            result = await _sync_one(candidate, now)
            if result["status"] == "synced":
                synced += 1
                new_activities += result.get("synced_count", 0)
                updated_activities += result.get("updated_count", 0)
            else:
                skipped += 1
        except Exception:
            failed += 1

    return {
        "ok": failed == 0,
        "eligible_users": len(payloads),
        "synced_users": synced,
        "failed_users": failed,
        "skipped_users": skipped,
        "new_activities": new_activities,
        "updated_activities": updated_activities,
        "checked_at": now.isoformat(),
    }
