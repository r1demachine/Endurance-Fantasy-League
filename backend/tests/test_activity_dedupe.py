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
from app.models import Activity, HeartRateSettingsHistory, User
from app.routers.upload import HeartRateSettingsUpdate, update_heart_rate_settings
from app.services.activity_upload import _apply_auto_hr_updates, create_activity_from_upload
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

    def test_database_upload_limit_rejects_sixth_upload_in_one_hour(self):
        now = datetime.utcnow().replace(microsecond=0)
        for index in range(5):
            start = now - timedelta(days=index + 2)
            self.activity(
                "UPLOAD_SITE",
                start,
                start + timedelta(hours=7),
                duration=3600,
                external_id=f"UPLOAD_TELEGRAM:{index:064x}",
            )
        # Give the five saved uploads recent DB creation timestamps, independent
        # of the activity dates in their FIT/GPX/TCX payloads.
        self.db.query(Activity).update({Activity.created_at: now}, synchronize_session=False)
        self.db.commit()
        incoming_start = now - timedelta(days=1)
        parsed = {
            "start_date": incoming_start.isoformat(),
            "start_date_local": (incoming_start + timedelta(hours=7)).isoformat(),
            "moving_time": 3600,
            "elapsed_time": 3600,
            "distance": 12000,
            "elevation_gain": 100,
            "training_load": 65,
            "intensity": 0.8,
            "sport_type": "RIDE",
        }
        status, activity, reason = create_activity_from_upload(
            self.db,
            self.user,
            parsed,
            "f" * 64,
            source="UPLOAD_SITE",
        )
        self.assertEqual(status, "rejected")
        self.assertIsNone(activity)
        self.assertIn("5 сохранённых загрузок в час", reason)

    def test_heart_rate_settings_validate_ratio_and_limit_updates_per_local_day(self):
        from fastapi import HTTPException

        with self.assertRaises(HTTPException) as caught:
            update_heart_rate_settings(HeartRateSettingsUpdate(lthr=165, max_hr=190), self.user, self.db)
        self.assertEqual(caught.exception.status_code, 422)

        invalid = HeartRateSettingsUpdate(lthr=140, max_hr=200, resting_hr=50)
        with self.assertRaises(HTTPException) as caught:
            update_heart_rate_settings(invalid, self.user, self.db)
        self.assertEqual(caught.exception.status_code, 422)

        valid = HeartRateSettingsUpdate(lthr=165, max_hr=190, resting_hr=50)
        response = update_heart_rate_settings(valid, self.user, self.db)
        self.assertTrue(response["saved"])
        self.assertEqual(self.db.query(HeartRateSettingsHistory).filter_by(user_id=self.user.id).count(), 1)

        with self.assertRaises(HTTPException) as caught:
            update_heart_rate_settings(HeartRateSettingsUpdate(lthr=166), self.user, self.db)
        self.assertEqual(caught.exception.status_code, 429)
        self.assertEqual(self.user.lthr, 165)

    def test_auto_hr_calibration_is_validated_historic_and_once_per_day(self):
        self.user.lthr = 165
        self.user.max_hr = 175
        self.user.resting_hr = 50
        self.db.commit()

        _apply_auto_hr_updates(self.db, self.user, {"max_hr": 180, "lthr": 174})
        self.db.commit()
        self.assertEqual(self.user.max_hr, 180)
        self.assertEqual(self.user.lthr, 174)
        self.assertEqual(self.db.query(HeartRateSettingsHistory).filter_by(user_id=self.user.id).count(), 1)

        _apply_auto_hr_updates(self.db, self.user, {"max_hr": 185, "lthr": 176})
        self.db.commit()
        self.assertEqual(self.user.max_hr, 180)
        self.assertEqual(self.user.lthr, 174)
        self.assertEqual(self.db.query(HeartRateSettingsHistory).filter_by(user_id=self.user.id).count(), 1)

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
