"""Tests for Intervals sync chunk boundaries and payload parsing."""
import os
import unittest
from datetime import date
from cryptography.fernet import Fernet
os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/efl-sync-chunk-tests.db")
os.environ.setdefault("JWT_SECRET", "unit-test-jwt-secret-value-longer-than-32-characters")
os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
os.environ.setdefault("REDIS_URL", "")
from app.services.intervals import _month_ranges, _split_range, _records
from app.routers.sync import _sync_month_ranges

class SyncChunkTests(unittest.TestCase):
    def test_month_ranges_cover_range(self):
        self.assertEqual(_month_ranges(date(2026, 1, 20), date(2026, 3, 7)), [
            (date(2026, 1, 20), date(2026, 1, 31)), (date(2026, 2, 1), date(2026, 2, 28)),
            (date(2026, 3, 1), date(2026, 3, 7))])
    def test_router_and_service_ranges_match(self):
        start, end = date(2025, 12, 15), date(2026, 2, 3)
        self.assertEqual(_sync_month_ranges(start, end), _month_ranges(start, end))
    def test_week_and_day_splits_are_contiguous(self):
        self.assertEqual(_split_range(date(2026, 1, 29), date(2026, 2, 10), 7), [
            (date(2026, 1, 29), date(2026, 2, 4)), (date(2026, 2, 5), date(2026, 2, 10))])
        self.assertEqual(len(_split_range(date(2026, 2, 1), date(2026, 2, 3), 1)), 3)
    def test_payload_shapes(self):
        self.assertEqual(_records([{"id": "1"}, None]), [{"id": "1"}])
        self.assertEqual(_records({"data": [{"id": "2"}]}), [{"id": "2"}])
        self.assertEqual(_records({"unexpected": []}), [])

if __name__ == "__main__":
    unittest.main()
