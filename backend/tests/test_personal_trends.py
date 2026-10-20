"""Tests for deterministic personal trend calculations and API privacy."""
import os
import unittest
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/efl-personal-trends-tests.db")
os.environ.setdefault("JWT_SECRET", "unit-test-jwt-secret-value-longer-than-32-characters")
os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
os.environ.setdefault("REDIS_URL", "")

from app.database import Base, get_db
from app.dependencies import get_current_user
from app.models import Activity, ActivityCheckIn, MorningCheckIn, User, Wellness
from app.routers import personal_analysis
from app.services.personal_trends import activity_local_date, build_personal_trends

TEST_ENGINE = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = sessionmaker(autocommit=False, autoflush=False, bind=TEST_ENGINE)
TODAY = date(2026, 10, 20)


def row(**values):
    return SimpleNamespace(**values)


def morning(user_id, day, *, status="completed", readiness=4, fatigue=2, soreness=1, wellbeing=4):
    return row(
        user_id=user_id,
        local_date=day,
        status=status,
        readiness=readiness,
        fatigue=fatigue,
        soreness=soreness,
        wellbeing=wellbeing,
    )


def activity(user_id, activity_id, day, *, tss=40, local=True, start_date=None):
    return row(
        id=activity_id,
        user_id=user_id,
        tss=tss,
        start_date_local=datetime.combine(day, datetime.min.time()) if local else None,
        start_date=start_date or datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc).replace(tzinfo=None),
    )


def activity_checkin(user_id, activity_id, *, rpe=5, expectation="as_expected"):
    return row(user_id=user_id, activity_id=activity_id, rpe=rpe, load_expectation=expectation)


def calculate(**overrides):
    args = {
        "user_id": 1,
        "timezone_name": "UTC",
        "today": TODAY,
        "days": 28,
        "morning_checkins": [],
        "wellness_records": [],
        "activities": [],
        "activity_checkins": [],
    }
    args.update(overrides)
    return build_personal_trends(**args)


def observation(result, key):
    return next(item for item in result["observations"] if item["key"] == key)


class PersonalTrendCalculationTests(unittest.TestCase):
    def test_morning_and_sleep_compare_latest_seven_days_with_previous_seven(self):
        mornings = []
        wellness = []
        for offset in range(13, -1, -1):
            day = TODAY - timedelta(days=offset)
            recent = day >= TODAY - timedelta(days=6)
            mornings.append(morning(1, day, wellbeing=5 if recent else 3))
            wellness.append(row(
                user_id=1,
                date=day.isoformat(),
                sleep_secs=8 * 3600 if recent else 7 * 3600,
                sleep_score=80 if recent else 60,
                sleep_quality=None,
            ))

        result = calculate(morning_checkins=mornings, wellness_records=wellness)
        wellbeing = observation(result, "wellbeing")
        sleep = observation(result, "sleep_quality")
        duration = observation(result, "sleep_duration_hours")

        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["comparison_windows"]["current"], {
            "start": "2026-10-14", "end": "2026-10-20", "days": 7,
        })
        self.assertEqual(wellbeing["status"], "ready")
        self.assertEqual(wellbeing["current"]["days_with_data"], 7)
        self.assertEqual(wellbeing["previous"]["mean"], 3.0)
        self.assertEqual(wellbeing["current"]["mean"], 5.0)
        self.assertEqual(wellbeing["change"], 2.0)
        self.assertEqual(wellbeing["trend"], "upward")
        self.assertEqual(sleep["source_field"], "sleep_score")
        self.assertEqual(sleep["change"], 20.0)
        self.assertEqual(duration["change"], 1.0)

    def test_conflicting_sleep_and_wellbeing_trends_remain_separate(self):
        mornings = []
        wellness = []
        for offset in range(13, -1, -1):
            day = TODAY - timedelta(days=offset)
            recent = day >= TODAY - timedelta(days=6)
            mornings.append(morning(1, day, wellbeing=5 if recent else 4))
            wellness.append(row(
                user_id=1,
                date=day.isoformat(),
                sleep_secs=6 * 3600 if recent else 8 * 3600,
                sleep_score=50 if recent else 75,
                sleep_quality=None,
            ))

        result = calculate(morning_checkins=mornings, wellness_records=wellness)
        wellbeing = observation(result, "wellbeing")
        sleep = observation(result, "sleep_quality")

        self.assertEqual(wellbeing["trend"], "upward")
        self.assertEqual(sleep["trend"], "downward")
        self.assertEqual(wellbeing["current"]["mean"], 5.0)
        self.assertEqual(sleep["current"]["mean"], 50.0)
        self.assertNotIn("combined_score", result)

    def test_skipped_pending_and_missing_mornings_are_not_zero_values(self):
        skipped_day = TODAY
        pending_day = TODAY - timedelta(days=1)
        rows = [
            morning(1, skipped_day, status="skipped", readiness=None, fatigue=None, soreness=None, wellbeing=None),
            morning(1, pending_day, status="pending", readiness=None, fatigue=None, soreness=None, wellbeing=None),
        ]
        result = calculate(morning_checkins=rows)
        metric = observation(result, "wellbeing")
        coverage = result["coverage"]["morning_checkins"]

        self.assertEqual(metric["status"], "insufficient_data")
        self.assertIsNone(metric["current"]["mean"])
        self.assertEqual(coverage["skipped_days"], 1)
        self.assertEqual(coverage["pending_days"], 1)
        self.assertEqual(coverage["no_record_days"], 26)
        self.assertIn("2026-10-20", coverage["skipped_dates"])
        self.assertIn("2026-10-19", coverage["pending_dates"])
        self.assertTrue(any("не завершён" in gap or "пропущен" in gap for gap in result["data_gaps"]))

    def test_metric_fields_from_different_sleep_scales_are_never_mixed(self):
        wellness = []
        for offset in range(13, -1, -1):
            day = TODAY - timedelta(days=offset)
            if offset >= 7:
                wellness.append(row(
                    user_id=1, date=day.isoformat(), sleep_secs=None,
                    sleep_score=65, sleep_quality=4,
                ))
            else:
                wellness.append(row(
                    user_id=1, date=day.isoformat(), sleep_secs=None,
                    sleep_score=None, sleep_quality=5,
                ))
        result = calculate(wellness_records=wellness)
        metric = observation(result, "sleep_quality")
        self.assertEqual(metric["source_field"], "sleep_score")
        self.assertEqual(metric["previous"]["mean"], 65.0)
        self.assertIsNone(metric["current"]["mean"])
        self.assertEqual(metric["status"], "insufficient_data")

    def test_multiple_rpes_on_one_local_day_are_averaged_within_the_day(self):
        day = TODAY
        activities = [
            activity(1, 10, day, tss=20),
            activity(1, 11, day, tss=40),
        ]
        checkins = [
            activity_checkin(1, 10, rpe=3),
            activity_checkin(1, 11, rpe=9),
        ]
        result = calculate(activities=activities, activity_checkins=checkins)
        metric = observation(result, "rpe")

        self.assertEqual(metric["current"]["mean"], 6.0)
        self.assertEqual(metric["current"]["days_with_data"], 1)
        self.assertEqual(metric["current"]["samples"], 2)
        self.assertEqual(metric["status"], "insufficient_data")

    def test_load_expectation_share_counts_workouts_but_weights_calendar_days_equally(self):
        activities = [
            activity(1, 30, TODAY, tss=20),
            activity(1, 31, TODAY, tss=30),
            activity(1, 32, TODAY, tss=40),
        ]
        checkins = [
            activity_checkin(1, 30, expectation="harder"),
            activity_checkin(1, 31, expectation="harder"),
            activity_checkin(1, 32, expectation="as_expected"),
        ]

        result = calculate(activities=activities, activity_checkins=checkins)
        metric = observation(result, "harder_than_expected_share")

        self.assertEqual(metric["current"]["mean"], 66.67)
        self.assertEqual(metric["current"]["days_with_data"], 1)
        self.assertEqual(metric["current"]["samples"], 3)
        self.assertEqual(metric["status"], "insufficient_data")

    def test_tss_and_rpe_relationship_requires_enough_paired_days_and_reports_real_values(self):
        activities = []
        checkins = []
        first_day = TODAY - timedelta(days=24)
        for index in range(8):
            day = first_day + timedelta(days=index)
            activities.append(activity(1, 100 + index, day, tss=20 if index < 4 else 60))
            checkins.append(activity_checkin(1, 100 + index, rpe=3 if index < 4 else 7))

        result = calculate(activities=activities, activity_checkins=checkins)
        relationship = result["training_load_relationship"]

        self.assertEqual(relationship["status"], "ready")
        self.assertEqual(relationship["paired_days"], 8)
        self.assertEqual(relationship["median_daily_tss"], 40.0)
        self.assertEqual(relationship["lower_or_equal_load"]["days"], 4)
        self.assertEqual(relationship["lower_or_equal_load"]["mean_daily_rpe"], 3.0)
        self.assertEqual(relationship["above_median_load"]["days"], 4)
        self.assertEqual(relationship["above_median_load"]["mean_daily_rpe"], 7.0)
        self.assertEqual(relationship["rpe_difference_high_minus_low"], 4.0)
        self.assertIn("не доказательство", relationship["limitations"][0])

    def test_estimated_tss_is_reported_but_not_mixed_with_measured_tss(self):
        activities = []
        checkins = []
        first_day = TODAY - timedelta(days=24)
        for index in range(8):
            day = first_day + timedelta(days=index)
            item = activity(1, 200 + index, day, tss=25 + index, local=True)
            item.tss_estimated = True
            activities.append(item)
            checkins.append(activity_checkin(1, 200 + index, rpe=5))

        result = calculate(activities=activities, activity_checkins=checkins)
        relationship = result["training_load_relationship"]
        coverage = result["coverage"]["activities"]

        self.assertEqual(relationship["status"], "insufficient_data")
        self.assertEqual(relationship["paired_days"], 0)
        self.assertEqual(relationship["days_excluded_due_to_estimated_tss"], 8)
        self.assertEqual(coverage["activities_with_estimated_tss"], 8)
        self.assertEqual(coverage["activities_with_measured_tss"], 0)
        self.assertTrue(any("оценочный" in gap for gap in result["data_gaps"]))

    def test_missing_tss_does_not_become_zero_in_load_relationship(self):
        activities = [
            activity(1, 1, TODAY, tss=None),
            activity(1, 2, TODAY - timedelta(days=1), tss=40),
        ]
        checkins = [
            activity_checkin(1, 1, rpe=8),
            activity_checkin(1, 2, rpe=3),
        ]
        result = calculate(activities=activities, activity_checkins=checkins)
        relationship = result["training_load_relationship"]
        self.assertEqual(relationship["status"], "insufficient_data")
        self.assertEqual(relationship["paired_days"], 1)
        self.assertEqual(relationship["days_excluded_due_to_missing_tss"], 1)
        self.assertEqual(result["coverage"]["activities"]["activities_without_tss"], 1)

    def test_utc_activity_timestamp_is_converted_to_user_local_calendar_day(self):
        stamp = datetime(2026, 10, 20, 22, 30, tzinfo=timezone.utc)
        item = activity(1, 1, TODAY, local=False, start_date=stamp.replace(tzinfo=None))
        self.assertEqual(activity_local_date(item, ZoneInfo("Europe/Stockholm")), date(2026, 10, 21))

    def test_other_users_rows_are_ignored_by_the_calculation_service(self):
        mornings = []
        for offset in range(13, -1, -1):
            day = TODAY - timedelta(days=offset)
            mornings.append(morning(1, day, wellbeing=4))
            mornings.append(morning(2, day, wellbeing=1))
        result = calculate(morning_checkins=mornings)
        metric = observation(result, "wellbeing")
        self.assertEqual(metric["current"]["mean"], 4.0)
        self.assertEqual(metric["previous"]["mean"], 4.0)


class PersonalTrendApiTests(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(bind=TEST_ENGINE)
        Base.metadata.create_all(bind=TEST_ENGINE)
        self.owner_id = None
        with TestSession() as db:
            owner = User(
                username="trend-owner",
                password_hash="test-hash",
                display_name="Trend Owner",
                timezone_name="UTC",
            )
            other = User(
                username="trend-other",
                password_hash="test-hash",
                display_name="Trend Other",
                timezone_name="UTC",
            )
            db.add_all([owner, other])
            db.flush()
            self.owner_id = owner.id
            for offset in range(13, -1, -1):
                day = TODAY - timedelta(days=offset)
                recent = day >= TODAY - timedelta(days=6)
                db.add_all([
                    MorningCheckIn(
                        user_id=owner.id, local_date=day, status="completed",
                        readiness=4, fatigue=2, soreness=1, wellbeing=5 if recent else 3,
                    ),
                    MorningCheckIn(
                        user_id=other.id, local_date=day, status="completed",
                        readiness=1, fatigue=5, soreness=5, wellbeing=1,
                    ),
                ])
            db.commit()

        self.current_user = SimpleNamespace(id=self.owner_id, timezone_name="UTC")
        self.app = FastAPI()
        self.app.include_router(personal_analysis.router)

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

    def test_api_returns_only_the_authenticated_users_trends(self):
        with patch("app.routers.personal_analysis.local_today", return_value=TODAY):
            response = self.client.get("/api/personal-analysis/trends")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        metric = next(item for item in body["observations"] if item["key"] == "wellbeing")
        self.assertEqual(metric["current"]["mean"], 5.0)
        self.assertEqual(metric["previous"]["mean"], 3.0)
        self.assertEqual(body["period"]["days"], 28)
        self.assertNotIn("user_id", body)

    def test_days_query_is_bounded(self):
        response = self.client.get("/api/personal-analysis/trends?days=7")
        self.assertEqual(response.status_code, 422)

    def test_api_requires_authentication(self):
        app = FastAPI()
        app.include_router(personal_analysis.router)

        def override_db():
            db = TestSession()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_db
        with TestClient(app) as client:
            response = client.get("/api/personal-analysis/trends")
        self.assertEqual(response.status_code, 401)
