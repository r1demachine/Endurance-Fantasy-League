"""Cross-source activity deduplication tests on SQLite."""
import os
import unittest
from datetime import datetime, timedelta

from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/efl-dedupe-tests.db")
os.environ.setdefault("JWT_SECRET", "unit-test-jwt-secret-value-longer-than-32-characters")
os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
os.environ.setdefault("REDIS_URL", "")

from app.database import Base
from app.models import Activity, User
from app.services.activity_dedupe import find_matching_activity, remove_matching_upload_duplicate


class ActivityDedupeTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        self.db = self.Session()
        self.user = User(
            username="dedupe-user",
            password_hash="test-hash",
            display_name="Dedupe",
            timezone_name="Asia/Krasnoyarsk",
        )
        self.db.add(self.user)
        self.db.commit()
        self.db.refresh(self.user)

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def activity(self, source, start_utc, start_local, duration=3600, external_id=None):
        item = Activity(
            user_id=self.user.id,
            intervals_activity_id=external_id or f"{source}:{start_utc.isoformat()}",
            source=source,
            name="Test ride",
            sport_type="RIDE",
            moving_time=duration,
            start_date=start_utc,
            start_date_local=start_local,
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def test_uploaded_copy_matches_intervals_by_utc_time_and_duration(self):
        start = datetime.utcnow().replace(microsecond=0) - timedelta(days=1)
        local = start + timedelta(hours=7)
        upload = self.activity("UPLOAD_SITE", start, local, duration=3600)

        match = find_matching_activity(
            self.db,
            self.user.id,
            start + timedelta(minutes=4),
            local,
            3900,
        )
        self.assertIsNotNone(match)
        self.assertEqual(match.id, upload.id)

    def test_local_timestamp_can_match_when_utc_timestamp_does_not(self):
        start = datetime.utcnow().replace(microsecond=0) - timedelta(days=1)
        local = start + timedelta(hours=7)
        upload = self.activity("UPLOAD_TELEGRAM", start, local, duration=3600)

        # Local wall-clock is the matching fallback when providers represent
        # offset/local timestamps differently.
        match = find_matching_activity(
            self.db,
            self.user.id,
            start + timedelta(minutes=20),
            local + timedelta(minutes=4),
            3800,
        )
        self.assertIsNotNone(match)
        self.assertEqual(match.id, upload.id)

    def test_duration_outside_ten_percent_is_not_a_duplicate(self):
        start = datetime.utcnow().replace(microsecond=0) - timedelta(days=1)
        local = start + timedelta(hours=7)
        self.activity("UPLOAD_SITE", start, local, duration=3600)

        match = find_matching_activity(
            self.db,
            self.user.id,
            start,
            local,
            4100,
        )
        self.assertIsNone(match)

    def test_intervals_is_kept_and_uploaded_copy_is_deleted(self):
        start = datetime.utcnow().replace(microsecond=0) - timedelta(days=1)
        local = start + timedelta(hours=7)
        canonical = self.activity("INTERVALS", start, local, duration=3600, external_id="icu-activity-123")
        self.activity("UPLOAD_SITE", start + timedelta(minutes=2), local + timedelta(minutes=2), duration=3650, external_id="UPLOAD_TELEGRAM:" + "a" * 64)

        removed = remove_matching_upload_duplicate(
            self.db,
            self.user.id,
            start + timedelta(minutes=1),
            local + timedelta(minutes=1),
            3620,
        )
        self.db.commit()
        self.assertIsNotNone(removed)
        activities = self.db.query(Activity).filter(Activity.user_id == self.user.id).all()
        self.assertEqual(len(activities), 1)
        self.assertEqual(activities[0].id, canonical.id)
        self.assertEqual(activities[0].source, "INTERVALS")


if __name__ == "__main__":
    unittest.main()
