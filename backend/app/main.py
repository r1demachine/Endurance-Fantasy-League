import os
import secrets
os.environ.setdefault("PGCLIENTENCODING", "UTF8")

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from .database import engine, Base
from .config import get_settings
from .rate_limit import limiter
from .routers import sync, auth, intervals_key, friends, notifications, admin, privacy, upload, duels, clubs, telegram, season, social, recaps, internal_notify, internal_sync, checkins

Base.metadata.create_all(bind=engine)

# Автоматическая миграция при старте (добавляет колонки если их нет)
from sqlalchemy import text, inspect
try:
    with engine.begin() as conn:
        inspector = inspect(engine)
        tables = inspector.get_table_names()

        # ── users ──
        if "users" in tables:
            cols = {c["name"] for c in inspector.get_columns("users")}
            if "username" not in cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN username VARCHAR(64)"))
            if "password_hash" not in cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN password_hash VARCHAR(255)"))
            if "token_version" not in cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN token_version INTEGER NOT NULL DEFAULT 0"))
            if "display_name" not in cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN display_name VARCHAR(100)"))
            if "api_key_encrypted" not in cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN api_key_encrypted VARCHAR(500)"))
            if "last_full_sync_at" not in cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN last_full_sync_at TIMESTAMP"))
            if "last_auto_sync_at" not in cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN last_auto_sync_at TIMESTAMP"))
            if "lthr" not in cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN lthr INTEGER"))
            if "max_hr" not in cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN max_hr INTEGER"))
            if "resting_hr" not in cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN resting_hr INTEGER"))
            if "timezone_name" not in cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN timezone_name VARCHAR(64) NOT NULL DEFAULT 'UTC'"))
            if "timezone_confirmed" not in cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN timezone_confirmed BOOLEAN NOT NULL DEFAULT FALSE"))
                conn.execute(text("UPDATE users SET timezone_confirmed = TRUE WHERE timezone_name IS NOT NULL AND timezone_name <> 'UTC'"))
            if "legacy_xp_offset" not in cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN legacy_xp_offset FLOAT DEFAULT 0"))
            if "xp_migrated_at" not in cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN xp_migrated_at TIMESTAMP"))
            if "division_current" not in cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN division_current INTEGER"))
            if "division_placed_at" not in cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN division_placed_at TIMESTAMP"))
            if "pause_set_at" not in cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN pause_set_at TIMESTAMP"))
            if "paused_until" not in cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN paused_until TIMESTAMP"))
            if "profile_visibility" not in cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN profile_visibility VARCHAR(20) NOT NULL DEFAULT 'authenticated'"))
            if "activity_visibility" not in cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN activity_visibility VARCHAR(20) NOT NULL DEFAULT 'friends'"))
            if "privacy_consent_version" not in cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN privacy_consent_version VARCHAR(64)"))
            if "privacy_consent_at" not in cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN privacy_consent_at TIMESTAMP"))
            if "telegram_chat_id" not in cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN telegram_chat_id VARCHAR(32)"))
            if "telegram_notify" not in cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN telegram_notify BOOLEAN NOT NULL DEFAULT FALSE"))
            if "telegram_link_code" not in cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN telegram_link_code VARCHAR(64)"))
            else:
                conn.execute(text("ALTER TABLE users ALTER COLUMN telegram_link_code TYPE VARCHAR(64)"))
                # Invalidate legacy plaintext short codes; only SHA-256 hashes remain valid.
                conn.execute(text("UPDATE users SET telegram_link_code = NULL, telegram_link_expires = NULL WHERE telegram_link_code IS NOT NULL AND length(telegram_link_code) < 64"))
            if "telegram_link_expires" not in cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN telegram_link_expires TIMESTAMP"))
            if "telegram_last_notified_week" not in cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN telegram_last_notified_week DATE"))
            if "notify_prefs" not in cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN notify_prefs TEXT NOT NULL DEFAULT '{}'"))
            if "last_deload_week_start" not in cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN last_deload_week_start DATE"))
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_telegram_chat_id ON users(telegram_chat_id)"))
            conn.execute(text("ALTER TABLE users ALTER COLUMN intervals_id DROP NOT NULL"))
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username ON users(username)"))

        # ── activities (v5.0 + v6 + PR8) ──
        if "activities" in tables:
            acols = {c["name"] for c in inspector.get_columns("activities")}
            if "intensity_category" not in acols:
                conn.execute(text("ALTER TABLE activities ADD COLUMN intensity_category VARCHAR"))
            if "intensity_reason" not in acols:
                conn.execute(text("ALTER TABLE activities ADD COLUMN intensity_reason VARCHAR"))
            if "streak_multiplier" not in acols:
                conn.execute(text("ALTER TABLE activities ADD COLUMN streak_multiplier FLOAT DEFAULT 1.0"))
            if "streak_reason" not in acols:
                conn.execute(text("ALTER TABLE activities ADD COLUMN streak_reason VARCHAR"))
            if "rate_per_hour" not in acols:
                conn.execute(text("ALTER TABLE activities ADD COLUMN rate_per_hour FLOAT DEFAULT 0.0"))
            if "tss" not in acols:
                conn.execute(text("ALTER TABLE activities ADD COLUMN tss FLOAT"))
            if "tss_estimated" not in acols:
                conn.execute(text("ALTER TABLE activities ADD COLUMN tss_estimated BOOLEAN DEFAULT FALSE"))
            if "is_long" not in acols:
                conn.execute(text("ALTER TABLE activities ADD COLUMN is_long BOOLEAN DEFAULT FALSE"))
            if "is_manual" not in acols:
                conn.execute(text("ALTER TABLE activities ADD COLUMN is_manual BOOLEAN DEFAULT FALSE"))
            if "source" not in acols:
                conn.execute(text("ALTER TABLE activities ADD COLUMN source VARCHAR(32) NOT NULL DEFAULT 'INTERVALS'"))
            if "start_date_local" not in acols:
                conn.execute(text("ALTER TABLE activities ADD COLUMN start_date_local TIMESTAMP"))
            conn.execute(text("UPDATE activities AS a SET start_date_local = (a.start_date AT TIME ZONE 'UTC') AT TIME ZONE COALESCE(u.timezone_name, 'UTC') FROM users AS u WHERE a.user_id = u.id AND a.start_date_local IS NULL AND a.start_date IS NOT NULL"))
            if "hard_secs" not in acols:
                conn.execute(text("ALTER TABLE activities ADD COLUMN hard_secs INTEGER NOT NULL DEFAULT 0"))
            if "is_indoor" not in acols:
                conn.execute(text("ALTER TABLE activities ADD COLUMN is_indoor BOOLEAN NOT NULL DEFAULT FALSE"))
                if "indoor" in acols:
                    conn.execute(text("UPDATE activities SET is_indoor = indoor WHERE indoor = TRUE"))

        # ── weekly_summaries (v6 + PR8) ──
        if "weekly_summaries" in tables:
            wcols = {c["name"] for c in inspector.get_columns("weekly_summaries")}
            if "is_deload" not in wcols:
                conn.execute(text("ALTER TABLE weekly_summaries ADD COLUMN is_deload BOOLEAN DEFAULT FALSE"))
            if "paused" not in wcols:
                conn.execute(text("ALTER TABLE weekly_summaries ADD COLUMN paused BOOLEAN DEFAULT FALSE"))
            if "deload_source" not in wcols:
                conn.execute(text("ALTER TABLE weekly_summaries ADD COLUMN deload_source VARCHAR(10)"))
            if "deload_manual_decision" not in wcols:
                conn.execute(text("ALTER TABLE weekly_summaries ADD COLUMN deload_manual_decision BOOLEAN NOT NULL DEFAULT FALSE"))
            conn.execute(text("UPDATE weekly_summaries SET deload_source = 'auto' WHERE is_deload = TRUE AND deload_source IS NULL"))

        # ── notifications (живые уведомления v4.2) ──
        if "notifications" in tables:
            ncols = {c["name"] for c in inspector.get_columns("notifications")}
            if "read" not in ncols:
                conn.execute(text("ALTER TABLE notifications ADD COLUMN read BOOLEAN DEFAULT FALSE"))
            if "link" not in ncols:
                conn.execute(text("ALTER TABLE notifications ADD COLUMN link VARCHAR(500)"))

        # ── duels ──
        if "duels" not in tables:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS duels (
                    id SERIAL PRIMARY KEY,
                    challenger_id INTEGER NOT NULL REFERENCES users(id),
                    opponent_id INTEGER NOT NULL REFERENCES users(id),
                    week_start TIMESTAMP NOT NULL,
                    status VARCHAR(20) NOT NULL DEFAULT 'pending',
                    challenger_xp FLOAT,
                    opponent_xp FLOAT,
                    winner_id INTEGER REFERENCES users(id),
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP,
                    responded_at TIMESTAMP,
                    finished_at TIMESTAMP,
                    pair_low_id INTEGER,
                    pair_high_id INTEGER,
                    is_no_activity_draw BOOLEAN NOT NULL DEFAULT FALSE
                )
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_duels_challenger ON duels(challenger_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_duels_opponent ON duels(opponent_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_duels_week ON duels(week_start)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_duels_status_week ON duels(status, week_start)"))

        duel_columns = {col["name"] for col in inspect(engine).get_columns("duels")}
        if "pair_low_id" not in duel_columns:
            conn.execute(text("ALTER TABLE duels ADD COLUMN pair_low_id INTEGER"))
        if "pair_high_id" not in duel_columns:
            conn.execute(text("ALTER TABLE duels ADD COLUMN pair_high_id INTEGER"))
        if "is_no_activity_draw" not in duel_columns:
            conn.execute(text("ALTER TABLE duels ADD COLUMN is_no_activity_draw BOOLEAN NOT NULL DEFAULT FALSE"))
        conn.execute(text("""
            UPDATE duels
            SET pair_low_id = LEAST(challenger_id, opponent_id),
                pair_high_id = GREATEST(challenger_id, opponent_id)
            WHERE pair_low_id IS NULL OR pair_high_id IS NULL
        """))
        conn.execute(text("""
            WITH ranked AS (
                SELECT id, ROW_NUMBER() OVER (
                    PARTITION BY pair_low_id, pair_high_id, week_start
                    ORDER BY CASE WHEN status = 'active' THEN 0 ELSE 1 END,
                             created_at NULLS LAST, id
                ) AS pair_rank
                FROM duels
                WHERE status IN ('pending', 'active')
            )
            UPDATE duels AS d
            SET status = 'declined',
                responded_at = COALESCE(d.responded_at, CURRENT_TIMESTAMP)
            FROM ranked AS r
            WHERE d.id = r.id AND r.pair_rank > 1
        """))
        conn.execute(text("""
            UPDATE duels AS d
            SET is_no_activity_draw = TRUE
            WHERE d.status = 'finished'
              AND d.winner_id IS NULL
              AND COALESCE(d.challenger_xp, 0) = 0
              AND COALESCE(d.opponent_xp, 0) = 0
              AND NOT EXISTS (
                  SELECT 1
                  FROM activities AS a
                  WHERE a.user_id IN (d.challenger_id, d.opponent_id)
                    AND COALESCE(a.start_date_local, a.start_date) >= d.week_start
                    AND COALESCE(a.start_date_local, a.start_date) < d.week_start + INTERVAL '7 days'
              )
        """))
        conn.execute(text("ALTER TABLE duels ALTER COLUMN pair_low_id SET NOT NULL"))
        conn.execute(text("ALTER TABLE duels ALTER COLUMN pair_high_id SET NOT NULL"))
        conn.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_duel_pair_week_active
            ON duels(pair_low_id, pair_high_id, week_start)
            WHERE status IN ('pending', 'active')
        """))

        # ── clubs ──
        if "clubs" not in tables:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS clubs (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(40) NOT NULL,
                    invite_code VARCHAR(12) NOT NULL UNIQUE,
                    owner_id INTEGER NOT NULL REFERENCES users(id),
                    instant_join BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at TIMESTAMP
                )
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_clubs_name ON clubs(name)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_clubs_invite ON clubs(invite_code)"))

        club_columns = {col["name"] for col in inspect(engine).get_columns("clubs")}
        if "instant_join" not in club_columns:
            conn.execute(text("ALTER TABLE clubs ADD COLUMN instant_join BOOLEAN NOT NULL DEFAULT FALSE"))

        # Legacy invitations were 8-char hexadecimal strings. Rotate them before
        # enforcing the fixed-length Base32 format expected by the API.
        invalid_invites = conn.execute(text("""
            SELECT id FROM clubs
            WHERE length(invite_code) <> 12 OR invite_code ~ '[^A-Z2-7]'
            ORDER BY id
        """)).fetchall()
        for (club_id,) in invalid_invites:
            for _ in range(32):
                code = "".join(secrets.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567") for _ in range(12))
                collision = conn.execute(
                    text("SELECT 1 FROM clubs WHERE invite_code = :code LIMIT 1"),
                    {"code": code},
                ).first()
                if not collision:
                    conn.execute(
                        text("UPDATE clubs SET invite_code = :code WHERE id = :club_id"),
                        {"code": code, "club_id": club_id},
                    )
                    break
            else:
                raise RuntimeError("Could not rotate a legacy club invite code")

        if "club_members" not in tables:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS club_members (
                    id SERIAL PRIMARY KEY,
                    club_id INTEGER NOT NULL REFERENCES clubs(id),
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    role VARCHAR(20) NOT NULL DEFAULT 'member',
                    joined_at TIMESTAMP
                )
            """))
        conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_club_member ON club_members(club_id, user_id)"
        ))

        if "club_join_requests" not in tables:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS club_join_requests (
                    id SERIAL PRIMARY KEY,
                    club_id INTEGER NOT NULL REFERENCES clubs(id),
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    status VARCHAR(20) NOT NULL DEFAULT 'pending',
                    created_at TIMESTAMP,
                    responded_at TIMESTAMP
                )
            """))
        conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_club_join_pending ON club_join_requests(club_id, user_id)"
        ))

        # Create attempt audit table on existing installations too.
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS club_join_attempts (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                code_digest VARCHAR(64) NOT NULL,
                succeeded BOOLEAN NOT NULL DEFAULT FALSE,
                attempted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_club_join_attempt_user_time
            ON club_join_attempts(user_id, attempted_at)
        """))

        # Normalize legacy club names before enforcing owner-scoped, case-insensitive uniqueness.
        conn.execute(text("""
            UPDATE clubs
            SET name = LEFT(regexp_replace(trim(name), '[[:space:]]+', ' ', 'g'), 40)
            WHERE name IS DISTINCT FROM LEFT(regexp_replace(trim(name), '[[:space:]]+', ' ', 'g'), 40)
        """))
        conn.execute(text("""
            WITH duplicate_names AS (
                SELECT id, ROW_NUMBER() OVER (
                    PARTITION BY owner_id, lower(name)
                    ORDER BY id
                ) AS duplicate_rank
                FROM clubs
            )
            UPDATE clubs AS c
            SET name = LEFT(c.name, 27) || ' #' || c.id::text
            FROM duplicate_names AS d
            WHERE c.id = d.id AND d.duplicate_rank > 1
        """))
        conn.execute(text("ALTER TABLE clubs ALTER COLUMN name TYPE VARCHAR(40)"))
        conn.execute(text("ALTER TABLE clubs ALTER COLUMN invite_code TYPE VARCHAR(12)"))
        conn.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_club_owner_name_lower
            ON clubs(owner_id, lower(name))
        """))

    print("✅ Auto-migration complete (users + activities + weekly_summaries + notifications + duels + clubs + telegram)")
except Exception as e:
    print(f"❌ Critical database migration failure: {type(e).__name__}: {e}")
    raise RuntimeError(
        "Critical database migration failed; application startup aborted."
    ) from e

settings = get_settings()
_is_prod = settings.APP_ENV == "production"

app = FastAPI(
    title="Fantasy League for Endurance Athletes",
    description="API для геймифицированной спортивной платформы (Intervals.icu)",
    version="0.2.0",
    docs_url=None if _is_prod else "/docs",
    redoc_url=None if _is_prod else "/redoc",
    openapi_url=None if _is_prod else "/openapi.json",
)

@app.exception_handler(RequestValidationError)
async def _request_validation_error_handler(request: Request, exc: RequestValidationError):
    # Keep FastAPI's normal 422 validation contract elsewhere, but make bad sync dates a client 400.
    if request.url.path == "/api/sync" and sync._has_invalid_since_query(exc.errors()):
        return JSONResponse(
            status_code=400,
            content={"detail": "Параметр since должен быть датой в формате YYYY-MM-DD."},
        )
    return await request_validation_exception_handler(request, exc)


app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip().rstrip("/")
        for origin in settings.CORS_ORIGINS.split(",")
        if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sync.router)
app.include_router(auth.router)
app.include_router(intervals_key.router)
app.include_router(friends.router)
app.include_router(notifications.router)
app.include_router(admin.router)
app.include_router(privacy.router)
app.include_router(upload.router)
app.include_router(duels.router)
app.include_router(clubs.router)
app.include_router(telegram.router)
app.include_router(season.router)
app.include_router(social.router)
app.include_router(recaps.router)
app.include_router(internal_notify.router)
app.include_router(internal_sync.router)
app.include_router(checkins.router)

@app.on_event("startup")
async def _init_broker():
    from .broker import init_broker
    await init_broker()

@app.get("/")
async def root():
    return {
        "message": "Fantasy League API is running!",
        "version": "0.2.0",
        "data_source": "Intervals.icu (per-user)",
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
