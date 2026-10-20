"""API tests for private daily and activity check-ins."""
import os
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/efl-checkins-tests.db")
os.environ.setdefault("JWT_SECRET", "unit-test-jwt-secret-value-longer-than-32-characters")
os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
os.environ.setdefault("REDIS_URL", "")

from app.database import Base, get_db
from app.dependencies import get_current_user
from app.models import Activity, ActivityCheckIn, MorningCheckIn, User
from app.routers import checkins

TEST_ENGINE = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = sessionmaker(autocommit=False, autoflush=False, bind=TEST_ENGINE)


class CheckInApiTests(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(bind=TEST_ENGINE)
        Base.metadata.create_all(bind=TEST_ENGINE)
        with TestSession() as db:
            user = User(
                username="checkin-owner",
                password_hash="test-hash",
                display_name="Owner",
                timezone_name="Asia/Tokyo",
            )
            other = User(
                username="checkin-other",
                password_hash="test-hash",
                display_name="Other",
                timezone_name="UTC",
            )
            db.add_all([user, other])
            db.flush()
            self.user_id = user.id
            self.other_user_id = other.id
            self.activity_id = None
            self.other_activity_id = None
            activity = Activity(
                user_id=user.id,
                intervals_activity_id="owner-workout",
                name="Owner workout",
                sport_type="Ride",
                moving_time=3600,
            )
            other_activity = Activity(
                user_id=other.id,
                intervals_activity_id="other-workout",
                name="Other workout",
                sport_type="Ride",
                moving_time=2400,
            )
            db.add_all([activity, other_activity])
            db.flush()
            self.activity_id = activity.id
            self.other_activity_id = other_activity.id
            db.commit()

        self.current_user = SimpleNamespace(id=self.user_id, timezone_name="Asia/Tokyo")
        self.app = FastAPI()
        self.app.include_router(checkins.router)

        def override_db():
            db = TestSession()
            try:
                yield db
            finally:
                db.close()

        self.app.dependency_overrides[get_db] = override_db
        self.app.dependency_overrides[get_current_user] = lambda: self.current_user
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()
        Base.metadata.drop_all(bind=TEST_ENGINE)

    def _count(self, model):
        with TestSession() as db:
            return db.query(func.count(model.id)).scalar()

    def test_prompt_is_idempotent_and_uses_local_date(self):
        now = datetime(2026, 10, 20, 23, 30)
        with patch("app.routers.checkins._utc_now", return_value=now):
            first = self.client.post("/api/check-ins/morning/prompt")
            second = self.client.post("/api/check-ins/morning/prompt")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()["checkin"]["id"], second.json()["checkin"]["id"])
        self.assertEqual(first.json()["checkin"]["local_date"], "2026-10-21")
        self.assertEqual(self._count(MorningCheckIn), 1)

    def test_skip_requires_fifteen_seconds_then_five_second_warning(self):
        start = datetime(2026, 10, 20, 23, 30)
        with patch("app.routers.checkins._utc_now", return_value=start):
            self.assertEqual(self.client.post("/api/check-ins/morning/prompt").status_code, 200)

        with patch("app.routers.checkins._utc_now", return_value=start.replace(second=14, microsecond=900000)):
            too_early = self.client.post("/api/check-ins/morning/skip-warning")
        self.assertEqual(too_early.status_code, 409)

        warning_start = datetime(2026, 10, 20, 23, 30, 15)
        with patch("app.routers.checkins._utc_now", return_value=warning_start):
            warning = self.client.post("/api/check-ins/morning/skip-warning")
        self.assertEqual(warning.status_code, 200)
        self.assertIsNotNone(warning.json()["checkin"]["skip_warning_at"])

        with patch("app.routers.checkins._utc_now", return_value=datetime(2026, 10, 20, 23, 30, 19, 999000)):
            too_soon = self.client.post("/api/check-ins/morning/skip")
        self.assertEqual(too_soon.status_code, 409)

        with patch("app.routers.checkins._utc_now", return_value=datetime(2026, 10, 20, 23, 30, 20)):
            skipped = self.client.post("/api/check-ins/morning/skip")
        self.assertEqual(skipped.status_code, 200)
        payload = skipped.json()["checkin"]
        self.assertEqual(payload["status"], "skipped")
        self.assertIsNone(payload["readiness"])
        self.assertIsNone(payload["fatigue"])
        self.assertIsNone(payload["soreness"])
        self.assertIsNone(payload["wellbeing"])
        self.assertEqual(self._count(MorningCheckIn), 1)

    def test_morning_answers_can_be_edited_and_unknown_values_stay_null(self):
        now = datetime(2026, 10, 20, 23, 30)
        with patch("app.routers.checkins._utc_now", return_value=now):
            prompt = self.client.post("/api/check-ins/morning/prompt")
            first = self.client.post("/api/check-ins/morning", json={
                "readiness": 4, "fatigue": 2, "soreness": 1, "wellbeing": 5,
            })
        self.assertEqual(prompt.status_code, 200)
        self.assertEqual(first.status_code, 200)
        first_id = first.json()["checkin"]["id"]

        with patch("app.routers.checkins._utc_now", return_value=now.replace(minute=45)):
            edited = self.client.post("/api/check-ins/morning", json={"readiness": 3})
        self.assertEqual(edited.status_code, 200)
        payload = edited.json()["checkin"]
        self.assertEqual(payload["id"], first_id)
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["readiness"], 3)
        self.assertIsNone(payload["fatigue"])
        self.assertIsNone(payload["soreness"])
        self.assertIsNone(payload["wellbeing"])
        self.assertEqual(self._count(MorningCheckIn), 1)

    def test_invalid_or_empty_morning_answers_are_rejected(self):
        with patch("app.routers.checkins._utc_now", return_value=datetime(2026, 10, 20, 23, 30)):
            self.client.post("/api/check-ins/morning/prompt")
            invalid = self.client.post("/api/check-ins/morning", json={"readiness": 6})
            empty = self.client.post("/api/check-ins/morning", json={})
            unknown_field = self.client.post("/api/check-ins/morning", json={"readiness": 4, "sleep_secs": 0})
        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(empty.status_code, 422)
        self.assertEqual(unknown_field.status_code, 422)

    def test_activity_checkin_upserts_without_duplicates_and_validates_rpe(self):
        first = self.client.post(
            "/api/check-ins/activities/" + str(self.activity_id),
            json={"rpe": 7, "load_expectation": "as_expected", "discomfort": "none"},
        )
        second = self.client.post(
            "/api/check-ins/activities/" + str(self.activity_id),
            json={"rpe": 8, "load_expectation": "harder", "discomfort": "mild"},
        )
        invalid = self.client.post(
            "/api/check-ins/activities/" + str(self.activity_id),
            json={"rpe": 11},
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(second.json()["checkin"]["rpe"], 8)
        self.assertEqual(self._count(ActivityCheckIn), 1)

        listed = self.client.get("/api/check-ins/activities")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()["checkins"]), 1)

    def test_activity_checkin_cannot_read_or_change_another_users_activity(self):
        response = self.client.post(
            "/api/check-ins/activities/" + str(self.other_activity_id),
            json={"rpe": 5},
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self._count(ActivityCheckIn), 0)

    def test_local_day_rollover_creates_a_new_daily_status(self):
        with patch("app.routers.checkins._utc_now", return_value=datetime(2026, 10, 20, 23, 30)):
            first = self.client.post("/api/check-ins/morning/prompt")
        with patch("app.routers.checkins._utc_now", return_value=datetime(2026, 10, 21, 15, 0)):
            second = self.client.post("/api/check-ins/morning/prompt")
        self.assertEqual(first.json()["checkin"]["local_date"], "2026-10-21")
        self.assertEqual(second.json()["checkin"]["local_date"], "2026-10-22")
        self.assertNotEqual(first.json()["checkin"]["id"], second.json()["checkin"]["id"])
        self.assertEqual(self._count(MorningCheckIn), 2)

    def test_endpoints_require_authentication(self):
        unauthenticated_app = FastAPI()
        unauthenticated_app.include_router(checkins.router)
        unauthenticated_app.dependency_overrides[get_db] = self.app.dependency_overrides[get_db]
        with TestClient(unauthenticated_app) as client:
            response = client.post("/api/check-ins/morning/prompt")
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
