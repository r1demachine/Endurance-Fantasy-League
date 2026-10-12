import os
os.environ.setdefault("PGCLIENTENCODING", "UTF8")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from .database import engine, Base
from .config import get_settings
from .rate_limit import limiter
from .routers import sync, auth, intervals_key, friends, notifications, admin, privacy, upload, duels, clubs, telegram

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
            if "lthr" not in cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN lthr INTEGER"))
            if "max_hr" not in cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN max_hr INTEGER"))
            if "resting_hr" not in cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN resting_hr INTEGER"))
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
                conn.execute(text("ALTER TABLE users ADD COLUMN telegram_link_code VARCHAR(16)"))
            if "telegram_link_expires" not in cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN telegram_link_expires TIMESTAMP"))
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

        # ── notifications (живые уведомления v4.2) ──
        if "notifications" in tables:
            ncols = {c["name"] for c in inspector.get_columns("notifications")}
            if "read" not in ncols:
                conn.execute(text("ALTER TABLE notifications ADD COLUMN read BOOLEAN DEFAULT FALSE"))

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
                    finished_at TIMESTAMP
                )
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_duels_challenger ON duels(challenger_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_duels_opponent ON duels(opponent_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_duels_week ON duels(week_start)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_duels_status_week ON duels(status, week_start)"))

        # ── clubs ──
        if "clubs" not in tables:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS clubs (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(64) NOT NULL,
                    invite_code VARCHAR(16) NOT NULL UNIQUE,
                    owner_id INTEGER NOT NULL REFERENCES users(id),
                    created_at TIMESTAMP
                )
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_clubs_name ON clubs(name)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_clubs_invite ON clubs(invite_code)"))

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

# Дуэли закрываются в тот же момент, что и лиги (wrap без правки огромного sync.py)
_orig_close_league_week = sync._close_league_week

def _close_league_week_with_duels(db, week_start_d):
    _orig_close_league_week(db, week_start_d)
    try:
        from .routers.duels import finalize_duels_for_week
        finalize_duels_for_week(db, week_start_d)
    except Exception as _duel_err:  # noqa: BLE001
        print(f"⚠️ finalize_duels_for_week failed: {_duel_err}")
    try:
        from .services.telegram_week import notify_week_results
        notify_week_results(db, week_start_d)
    except Exception as _tg_err:  # noqa: BLE001
        print(f"⚠️ telegram week notify failed: {_tg_err}")

sync._close_league_week = _close_league_week_with_duels

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
