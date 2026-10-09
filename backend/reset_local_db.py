"""Полный сброс ЛОКАЛЬНОЙ базы данных.
Защита: отказывается работать, если DATABASE_URL не на localhost/127.0.0.1.
После сброса таблицы пересоздадутся сами при старте uvicorn
(create_all + auto-migration в main.py)."""
import os
import sys

os.environ.setdefault("PGCLIENTENCODING", "UTF8")

from sqlalchemy import text

from app.config import get_settings
from app.database import engine

url = str(get_settings().DATABASE_URL)

# ── Предохранитель: только локальная база ──
if not any(host in url for host in ("localhost", "127.0.0.1")):
    print(f"❌ ОТКАЗ: DATABASE_URL не локальный ({url}). Прод не трогаем.")
    sys.exit(1)

print(f"⚠️  Будет ПОЛНОСТЬЮ стёрта база: {url}")
confirm = input("Введи 'yes' для подтверждения: ").strip().lower()
if confirm != "yes":
    print("Отменено.")
    sys.exit(0)

with engine.begin() as conn:
    conn.execute(text("DROP SCHEMA public CASCADE"))
    conn.execute(text("CREATE SCHEMA public"))
    conn.execute(text("GRANT ALL ON SCHEMA public TO public"))

print("✅ Схема public пересоздана с нуля.")
print("▶️  Запусти uvicorn — таблицы поднимутся автоматически:")
print("   uvicorn app.main:app --reload --port 8000")