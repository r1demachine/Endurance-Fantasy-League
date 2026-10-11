"""Regression tests for weekly interface, trainer parsing and seasonal quest rules."""
import os
import unittest
from datetime import date, datetime
from types import SimpleNamespace
from cryptography.fernet import Fernet

os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/efl-interface-package-tests.db")
os.environ.setdefault("JWT_SECRET", "unit-test-jwt-secret-value-longer-than-32-characters")
os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
os.environ.setdefault("REDIS_URL", "")

from app.routers.sync import _parse_activity, _monday_for_day, _sync_month_ranges
from app.services.quests import (
    _is_qualifying_trainer_activity,
    _trainer_season_active,
    _trainer_week_key,
)


class TrainerQuestRulesTests(unittest.TestCase):
    def activity(self, **updates):
        values = {
            "start_date": datetime(2026, 10, 5, 10, 0),
            "moving_time": 1800,
            "is_manual": False,
            "is_indoor": True,
            "indoor": True,
        }
        values.update(updates)
        return SimpleNamespace(**values)

    def test_trainer_season_includes_october_to_april_only(self):
        for day in (date(2026, 10, 1), date(2026, 12, 31), date(2027, 1, 1), date(2027, 4, 30)):
            self.assertTrue(_trainer_season_active(day))
        for day in (date(2026, 9, 30), date(2027, 5, 1), date(2027, 8, 31)):
            self.assertFalse(_trainer_season_active(day))

    def test_trainer_requires_indoor_non_manual_and_30_minutes(self):
        self.assertTrue(_is_qualifying_trainer_activity(self.activity()))
        self.assertFalse(_is_qualifying_trainer_activity(self.activity(is_manual=True)))
        self.assertFalse(_is_qualifying_trainer_activity(self.activity(moving_time=1799)))
        self.assertFalse(_is_qualifying_trainer_activity(self.activity(is_indoor=False, indoor=False)))
        self.assertFalse(_is_qualifying_trainer_activity(self.activity(start_date=datetime(2026, 5, 1))))

    def test_week_key_is_stable(self):
        self.assertEqual(_trainer_week_key(date(2026, 10, 5)), "quest:trainer_week:2026-10-05")
        self.assertEqual(_monday_for_day(date(2026, 10, 11)), date(2026, 10, 5))

    def test_intervals_trainer_flag_is_persisted_as_indoor(self):
        parsed = _parse_activity({
            "id": "trainer-test-1",
            "name": "Indoor ride",
            "type": "RIDE",
            "moving_time": 1800,
            "start_date_local": "2026-10-05T10:00:00",
            "trainer": True,
        })
        self.assertIsNotNone(parsed)
        self.assertTrue(parsed["is_indoor"])
        manual = _parse_activity({
            "id": "trainer-test-2", "type": "RIDE", "moving_time": 1800,
            "start_date_local": "2026-10-05T10:00:00", "trainer": "false",
        })
        self.assertFalse(manual["is_indoor"])


if __name__ == "__main__":
    unittest.main()
