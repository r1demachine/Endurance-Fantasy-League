"""Timezone-aware scheduling helpers for incremental Intervals sync."""
import os
import unittest
from datetime import datetime, timedelta, timezone
from cryptography.fernet import Fernet

os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/efl-internal-sync-tests.db")
os.environ.setdefault("JWT_SECRET", "unit-test-jwt-secret-value-longer-than-32-characters")
os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
os.environ.setdefault("REDIS_URL", "")

from app.routers.internal_sync import auto_sync_is_due, local_sync_window


class InternalSyncScheduleTests(unittest.TestCase):
    def test_window_uses_local_date_and_includes_today_plus_seven_previous_days(self):
        # 23:30 UTC is already 08:30 the following calendar day in Tokyo.
        now = datetime(2026, 10, 20, 23, 30, tzinfo=timezone.utc)
        oldest, newest = local_sync_window("Asia/Tokyo", now)
        self.assertEqual(newest.isoformat(), "2026-10-21")
        self.assertEqual(oldest.isoformat(), "2026-10-14")
        self.assertEqual((newest - oldest).days, 7)

    def test_invalid_timezone_falls_back_to_utc(self):
        now = datetime(2026, 10, 20, 23, 30, tzinfo=timezone.utc)
        self.assertEqual(
            local_sync_window("Not/A-Timezone", now),
            local_sync_window("UTC", now),
        )

    def test_sync_interval_is_six_hours_and_handles_naive_utc_timestamps(self):
        now = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
        self.assertTrue(auto_sync_is_due(None, now))
        self.assertFalse(auto_sync_is_due(datetime(2026, 10, 20, 6, 1), now))
        self.assertTrue(auto_sync_is_due(datetime(2026, 10, 20, 6, 0), now))
        self.assertFalse(auto_sync_is_due(now - timedelta(hours=5, minutes=59), now))
        self.assertTrue(auto_sync_is_due(now - timedelta(hours=6), now))


if __name__ == "__main__":
    unittest.main()
