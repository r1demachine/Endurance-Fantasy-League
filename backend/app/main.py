import os
os.environ.setdefault("PGCLIENTENCODING", "UTF8")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .database import engine, Base
from .config import get_settings
from .routers import sync, auth, intervals_key, friends

Base.metadata.create_all(bind=engine)

# Автоматическая миграция при старте (добавляет колонки если их нет)
from sqlalchemy import text, inspect
with engine.begin() as conn:
    inspector = inspect(engine)
    cols = [c["name"] for c in inspector.get_columns("users")]
    
    if "username" not in cols:
        conn.execute(text("ALTER TABLE users ADD COLUMN username VARCHAR(64)"))
    if "password_hash" not in cols:
        conn.execute(text("ALTER TABLE users ADD COLUMN password_hash VARCHAR(255)"))
    if "display_name" not in cols:
        conn.execute(text("ALTER TABLE users ADD COLUMN display_name VARCHAR(100)"))
    if "api_key_encrypted" not in cols:
        conn.execute(text("ALTER TABLE users ADD COLUMN api_key_encrypted VARCHAR(500)"))
    
    conn.execute(text("ALTER TABLE users ALTER COLUMN intervals_id DROP NOT NULL"))
    conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username ON users(username)"))

print("✅ Auto-migration complete")

app = FastAPI(
    title="Fantasy League for Endurance Athletes",
    description="API для геймифицированной спортивной платформы (Intervals.icu)",
    version="0.2.0",
)

settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://endurance-fantasy-league.vercel.app",
        "https://*.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sync.router)
app.include_router(auth.router)
app.include_router(intervals_key.router)
app.include_router(friends.router)

from .routers import admin
app.include_router(admin.router)


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


@app.get("/config-check")
async def config_check():
    return {
        "api_url": settings.INTERVALS_API_URL,
        "has_secret_key": bool(settings.SECRET_KEY),
    }