"""Regression tests for retiring the old per-workout duration award."""
from pathlib import Path

from app.services import xp_v6

SYNC_SOURCE = (Path(__file__).parents[1] / "app" / "routers" / "sync.py").read_text(encoding="utf-8")


def test_per_workout_45_minute_bonus_is_not_configured_or_generated():
    assert not hasattr(xp_v6, "WORKOUT_BONUS_XP")
    assert not hasattr(xp_v6, "WORKOUT_BONUS_MIN_DURATION_SECONDS")
    assert 'key = f"activity_bonus:45m:{activity.id}"' not in SYNC_SOURCE
    assert "Тренировка ≥45 минут +" not in SYNC_SOURCE


def test_legacy_per_workout_bonus_is_filtered_and_cleaned_up():
    assert "_is_retired_activity_duration_bonus" in SYNC_SOURCE
    assert "and not _is_retired_activity_duration_bonus(event)" in SYNC_SOURCE
    assert "if event.event_type == \"activity_bonus\" and event.event_key not in generated_activity_bonus_keys:" in SYNC_SOURCE
