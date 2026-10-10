import os
os.environ.setdefault("PGCLIENTENCODING", "UTF8")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .database import engine, Base
from .config import get_settings
from .routers import sync, auth, intervals_key, friends, notifications, admin

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
            if "display_name" not in cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN display_name VARCHAR(100)"))
            if "api_key_encrypted" not in cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN api_key_encrypted VARCHAR(500)"))
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

    print("✅ Auto-migration complete (users + activities + weekly_summaries + notifications)")
except Exception as e:
    print(f"⚠️ Auto-migration warning: {type(e).__name__}: {e}")

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

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https://.*\.vercel\.app",  # ✅ wildcard работает через regex
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://endurance-fantasy-league.vercel.app",
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