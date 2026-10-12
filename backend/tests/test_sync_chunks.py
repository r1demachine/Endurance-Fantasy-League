"""Tests for bounded Intervals sync ranges and shared progress."""
import os
import unittest
from datetime import date
from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/efl-sync-chunk-tests.db")
os.environ.setdefault("JWT_SECRET", "unit-test-jwt-secret-value-longer-than-32-characters")
os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
os.environ.setdefault("REDIS_URL", "")

from app.database import Base
from app.models import SyncProgress, User
from app.services.intervals import _month_ranges, _split_range, _records
from app.routers.sync import (
    _claim_sync_progress,
    _earliest_sync_date,
    _has_invalid_since_query,
    _progress_payload,
)


class SyncChunkTests(unittest.TestCase):
    def test_month_ranges_cover_range(self):
        self.assertEqual(_month_ranges(date(2026, 1, 20), date(2026, 3, 7)), [
            (date(2026, 1, 20), date(2026, 1, 31)),
            (date(2026, 2, 1), date(2026, 2, 28)),
            (date(2026, 3, 1), date(2026, 3, 7)),
        ])

    def test_allowed_range_is_at_most_24_calendar_months(self):
        today = date(2026, 10, 12)
        earliest = _earliest_sync_date(today)
        self.assertEqual(earliest, date(2024, 11, 1))
        self.assertEqual(len(_month_ranges(earliest, today)), 24)
        self.assertEqual(len(_month_ranges(date(2024, 10, 31), today)), 25)

    def test_week_and_day_splits_are_contiguous(self):
        self.assertEqual(_split_range(date(2026, 1, 29), date(2026, 2, 10), 7), [
            (date(2026, 1, 29), date(2026, 2, 4)),
            (date(2026, 2, 5), date(2026, 2, 10)),
        ])
        self.assertEqual(len(_split_range(date(2026, 2, 1), date(2026, 2, 3), 1)), 3)

    def test_payload_shapes(self):
        self.assertEqual(_records([{"id": "1"}, None]), [{"id": "1"}])
        self.assertEqual(_records({"data": [{"id": "2"}]}), [{"id": "2"}])
        self.assertEqual(_records({"unexpected": []}), [])

    def test_invalid_since_query_is_identified_for_http_400(self):
        self.assertTrue(_has_invalid_since_query([{
            "loc": ("query", "since"), "type": "date_from_datetime_parsing"
        }]))
        self.assertFalse(_has_invalid_since_query([{
            "loc": ("query", "limit"), "type": "int_parsing"
        }]))
        self.assertFalse(_has_invalid_since_query([{
            "loc": ("body", "name"), "type": "missing"
        }]))

    def test_sync_progress_is_shared_through_database(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        first = Session()
        second = Session()
        try:
            user = User(
                username="sync-progress-user",
                password_hash="test-hash",
                display_name="Sync progress",
                timezone_name="UTC",
            )
            first.add(user)
            first.commit()
            first.refresh(user)

            self.assertTrue(_claim_sync_progress(first, user.id, 24))
            shared = second.query(SyncProgress).filter_by(user_id=user.id).one()
            self.assertTrue(shared.active)
            self.assertEqual(shared.months_total, 24)
            self.assertEqual(_progress_payload(shared)["phase"], "activities")

            # A second worker must not claim the same active user's sync.
            self.assertFalse(_claim_sync_progress(second, user.id, 24))
            second.expire_all()
            still_active = second.query(SyncProgress).filter_by(user_id=user.id).one()
            self.assertTrue(still_active.active)
        finally:
            first.close()
            second.close()
            Base.metadata.drop_all(engine)
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
