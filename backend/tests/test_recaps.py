import unittest
from datetime import date, datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.dependencies import get_current_user
from app.services.day_ledger import build_day_ledger
from app.models import (
    Activity,
    Duel,
    DuelStatus,
    LeagueMembership,
    User,
    WeeklySummary,
    XPEvent,
)
from app.routers import season as season_router
from app.routers import recaps as recaps_router
from app.services.seasons import current_season, longest_consecutive_streak


class RecapTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(
            bind=self.engine,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )
        self.db = self.Session()
        self.owner = self.make_user("recap-owner", "Recap Owner")
        self.other = self.make_user("recap-other", "Another Athlete")

        self.app = FastAPI()
        self.app.include_router(recaps_router.router)
        self.app.include_router(season_router.router)

        def override_db():
            yield self.db

        self.app.dependency_overrides[get_db] = override_db
        self.app.dependency_overrides[get_current_user] = lambda: self.owner
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()
        self.db.close()
        self.engine.dispose()

    def make_user(self, username, display_name):
        user = User(
            username=username,
            password_hash="test-hash",
            display_name=display_name,
            profile_visibility="authenticated",
            activity_visibility="friends",
            timezone_name="UTC",
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def add_week(self, user, monday, *, finalized=True, total_xp=100.0, **values):
        row = WeeklySummary(
            user_id=user.id,
            week_start=datetime.combine(monday, datetime.min.time()),
            finalized=finalized,
            total_xp=total_xp,
            actual_load=values.get("actual_load", 240),
            target_load=values.get("target_load", 300),
            completion_ratio=values.get("completion_ratio", 0.8),
            training_days=values.get("training_days", 3),
            effort_xp=values.get("effort_xp", 40),
            goal_xp=values.get("goal_xp", 15),
            consistency_xp=values.get("consistency_xp", 12),
            quality_xp=values.get("quality_xp", 8),
            recovery_xp=values.get("recovery_xp", 5),
            quest_xp=values.get("quest_xp", 20),
            division=values.get("division", "Division 2"),
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def add_activity(self, user, stamp, external_id, xp=25, distance=25000):
        row = Activity(
            user_id=user.id,
            intervals_activity_id=external_id,
            name="Morning ride",
            sport_type="Ride",
            moving_time=3600,
            distance=distance,
            elevation_gain=300,
            xp_earned=xp,
            start_date=stamp,
            start_date_local=stamp,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def last_completed_monday(self):
        today = date.today()
        monday = today - timedelta(days=today.weekday() + 7)
        return monday

    def test_week_recap_contains_only_finalized_personal_summary_and_context(self):
        monday = self.last_completed_monday()
        week_dt = datetime.combine(monday, datetime.min.time())
        self.add_week(
            self.owner,
            monday,
            finalized=True,
            total_xp=280,
            completion_ratio=0.875,
            training_days=4,
            effort_xp=120,
            goal_xp=30,
            consistency_xp=35,
            quality_xp=25,
            recovery_xp=20,
            quest_xp=50,
        )
        self.add_activity(self.owner, datetime.combine(monday + timedelta(days=1), datetime.min.time()).replace(hour=9), "recap-a", xp=40)
        self.add_activity(self.owner, datetime.combine(monday + timedelta(days=3), datetime.min.time()).replace(hour=9), "recap-b", xp=60)
        self.db.add(XPEvent(
            user_id=self.owner.id,
            week_start=week_dt,
            date=week_dt + timedelta(days=3, hours=12),
            event_type="achievement",
            event_key="recap-achievement-1",
            amount=20,
            title="Четыре тренировочных дня",
        ))
        self.db.add(LeagueMembership(
            user_id=self.owner.id,
            week_start=week_dt,
            division="Division 2",
            division_source="ctl",
            league_score=80,
            rank=2,
            group_key="D2-A",
        ))
        self.db.add(Duel(
            challenger_id=self.owner.id,
            opponent_id=self.other.id,
            week_start=week_dt,
            status=DuelStatus.FINISHED.value,
            challenger_xp=280,
            opponent_xp=250,
            winner_id=self.owner.id,
            pair_low_id=min(self.owner.id, self.other.id),
            pair_high_id=max(self.owner.id, self.other.id),
            finished_at=week_dt + timedelta(days=7),
        ))
        self.db.commit()

        response = self.client.get("/api/week-recap", params={"week_start": monday.isoformat()})
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result["available"])
        self.assertTrue(result["finalized"])
        self.assertEqual(result["total_xp"], 280)
        self.assertEqual(result["goal_percent"], 87.5)
        self.assertEqual(result["workout_days"], 2)
        self.assertEqual(result["workouts_count"], 2)
        self.assertEqual(result["league_rank"], 2)
        self.assertEqual(result["achievements_count"], 1)
        self.assertEqual(result["achievements"][0]["title"], "Четыре тренировочных дня")
        self.assertEqual(result["duel"]["outcome"], "win")
        self.assertEqual(result["tiles"]["effort"], 120)
        expected_days = [
            build_day_ledger(self.db, self.owner, monday + timedelta(days=offset))
            for offset in range(7)
        ]
        candidates = [
            day for day in expected_days
            if day["activities"] or day["xp"]["total"] > 0
        ]
        expected_best = max(candidates, key=lambda day: day["xp"]["total"])
        self.assertEqual(result["best_day"]["date"], expected_best["date"])
        self.assertEqual(result["best_day"]["xp"], expected_best["xp"]["total"])

    def test_week_recap_is_unavailable_until_week_is_finalized(self):
        monday = self.last_completed_monday()
        self.add_week(self.owner, monday, finalized=False, total_xp=77)
        response = self.client.get("/api/week-recap", params={"week_start": monday.isoformat()})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["available"])
        self.assertEqual(response.json()["reason"], "week_not_finalized")

    def test_week_recap_requires_authentication(self):
        self.app.dependency_overrides.pop(get_current_user, None)
        response = self.client.get("/api/week-recap")
        self.assertEqual(response.status_code, 401)
        self.app.dependency_overrides[get_current_user] = lambda: self.owner

    def test_week_recap_never_reads_another_users_summary(self):
        monday = self.last_completed_monday()
        self.add_week(self.other, monday, finalized=True, total_xp=999)
        response = self.client.get("/api/week-recap", params={"week_start": monday.isoformat()})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["available"])
        self.assertEqual(response.json()["reason"], "summary_missing")

    def test_season_xp_is_sum_of_weekly_summary_totals_not_activity_xp(self):
        season = current_season("UTC")
        first_monday = season.start + timedelta(days=(7 - season.start.weekday()) % 7)
        week_starts = []
        cursor = first_monday
        while cursor < season.next_start and len(week_starts) < 2:
            week_starts.append(cursor)
            cursor += timedelta(days=7)
        self.assertGreaterEqual(len(week_starts), 1)
        values = [123.5, 22.5]
        for index, monday in enumerate(week_starts):
            self.add_week(self.owner, monday, total_xp=values[index], finalized=True)
        self.add_activity(
            self.owner,
            datetime.combine(season.start + timedelta(days=1), datetime.min.time()).replace(hour=9),
            "season-activity-xp-not-season-xp",
            xp=999,
        )

        response = self.client.get("/api/season/recap")
        self.assertEqual(response.status_code, 200)
        metrics = response.json()["metrics"]
        persisted_rows = (
            self.db.query(WeeklySummary)
            .filter(
                WeeklySummary.user_id == self.owner.id,
                WeeklySummary.week_start >= datetime.combine(season.start, datetime.min.time()),
                WeeklySummary.week_start < datetime.combine(season.next_start, datetime.min.time()),
            )
            .all()
        )
        self.assertEqual(metrics["total_xp"], round(sum(float(row.total_xp or 0) for row in persisted_rows), 1))
        self.assertNotEqual(metrics["total_xp"], 999)
        self.assertEqual(metrics["total_workouts"], 1)
        self.assertEqual(metrics["total_km"], 25.0)

    def test_season_recap_can_load_a_completed_season(self):
        season = current_season("UTC")
        previous_month = date(season.start.year if season.start.month > 1 else season.start.year - 1,
                              season.start.month - 1 if season.start.month > 1 else 12, 1)
        response = self.client.get("/api/season/recap", params={"season_start": previous_month.isoformat()})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["is_final"])
        self.assertEqual(response.json()["season"]["start"], previous_month.isoformat())

    def test_longest_consecutive_streak_uses_unique_calendar_days(self):
        self.assertEqual(
            longest_consecutive_streak([
                date(2026, 10, 1),
                date(2026, 10, 2),
                date(2026, 10, 2),
                date(2026, 10, 4),
                date(2026, 10, 5),
                date(2026, 10, 6),
            ]),
            3,
        )
        self.assertEqual(longest_consecutive_streak([]), 0)


if __name__ == "__main__":
    unittest.main()
