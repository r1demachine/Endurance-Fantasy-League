"""Диагностика: где теряется интенсивность."""
import os
os.environ.setdefault("PGCLIENTENCODING", "UTF8")

from collections import Counter
from app.database import SessionLocal
from app.models import Activity, User

db = SessionLocal()
try:
    users = db.query(User).all()
    print(f"Юзеров в БД: {len(users)}")
    for u in users:
        acts = db.query(Activity).filter(Activity.user_id == u.id).all()
        print(f"\n=== {u.display_name} (@{u.username}) · тренировок: {len(acts)} ===")
        if not acts:
            continue

        vals = [a.intensity for a in acts]
        nulls = sum(1 for v in vals if v is None)
        zeros = sum(1 for v in vals if v == 0)
        normal = [v for v in vals if v and v > 0]
        print(f"колонка intensity:  NULL={nulls}   0={zeros}   >0={len(normal)}")
        if normal:
            print(f"  значения >0:      min={min(normal)}  max={max(normal)}  avg={sum(normal)/len(normal):.3f}")

        mults = [a.intensity_multiplier for a in acts if a.intensity_multiplier]
        if mults:
            print(f"старая колонка intensity_multiplier: min={min(mults)}  max={max(mults)}  (есть {len(mults)} шт)")

        cats = Counter(a.intensity_category for a in acts)
        tls = [a.training_load for a in acts if a.training_load]
        print(f"training_load заполнен у {len(tls)} из {len(acts)} (min={min(tls) if tls else '—'}, max={max(tls) if tls else '—'})")
        print(f"intensity_category (что записал пересчёт): {dict(cats)}")

        print("  последние 5 тренировок:")
        for a in sorted(acts, key=lambda x: x.start_date or 0, reverse=True)[:5]:
            print(f"    {a.start_date} | {a.sport_type} | intensity={a.intensity} | TL={a.training_load} | cat={a.intensity_category} | mult={a.intensity_multiplier}")
finally:
    db.close()