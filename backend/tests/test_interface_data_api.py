"""Backend interface-data endpoint regression tests.

Run from backend/: python -m unittest tests.test_interface_data_api -v
"""
import os
import unittest
from datetime import date, datetime, timedelta
from unittest.mock import patch
from types import SimpleNamespace

from cryptography.fernet import Fernet
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/efl-interface-data-api-tests.db")
os.environ.setdefault("JWT_SECRET", "unit-test-jwt-secret-value-longer-than-32-characters")
os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
os.environ.setdefault("REDIS_URL", "")

from app.database import Base
from app.models import Activity, User, Wellness, WeeklySummary, XPEvent
from app.routers import sync as sync_router
from app.services import quests as quest_service
from app.services import xp_v6 as X6


class InterfaceDataApiTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, expire_on_commit=False)
        self.db = self.Session()
        self.user = User(
            username="interface-data-user",
            password_hash="test-hash",
            display_name="Interface Data",
            timezone_name="UTC",
        )
        self.db.add(self.user)
        self.db.commit()
        self.db.refresh(self.user)

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def add_activity(
        self, key, *, user=None, stamp=datetime(2026, 10, 13, 9, 0),
        tss=0, xp=0, manual=False, sport="RIDE", distance=0,
        moving_time=1800, elevation=0, hard_secs=0, indoor=False,
        intensity=0.5, source="INTERVALS",
    ):
        owner = user or self.user
        activity = Activity(
            user_id=owner.id,
            intervals_activity_id=key,
            source=source,
            name=key,
            sport_type=sport,
            distance=distance,
            moving_time=moving_time,
            elevation_gain=elevation,
            training_load=tss,
            intensity=intensity,
            tss=tss,
            tss_estimated=False,
            xp_earned=xp,
            is_manual=manual,
            hard_secs=hard_secs,
            is_indoor=indoor,
            indoor=indoor,
            start_date=stamp,
            start_date_local=stamp,
        )
        self.db.add(activity)
        self.db.flush()
        return activity

    def add_summary(
        self, week, *, user=None, effort=0, consistency=0, quality=0, goal=0,
        recovery=0, quest=0, total=0, training_days=0, target_training_days=None, ratio=0.0,
        finalized=True, actual_load=0, target_load=100,
        paused=False, is_deload=False,
    ):
        owner = user or self.user
        row = WeeklySummary(
            user_id=owner.id,
            week_start=datetime.combine(week, datetime.min.time()),
            effort_xp=effort,
            consistency_xp=consistency,
            quality_xp=quality,
            goal_xp=goal,
            recovery_xp=recovery,
            quest_xp=quest,
            total_xp=total,
            training_days=training_days,
            target_training_days=target_training_days,
            completion_ratio=ratio,
            finalized=finalized,
            actual_load=actual_load,
            target_load=target_load,
            paused=paused,
            is_deload=is_deload,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def add_event(self, key, event_type, amount, *, day, week=None, scope="week", source_id=None, title=None):
        week = week or day - timedelta(days=day.weekday())
        event = XPEvent(
            user_id=self.user.id,
            week_start=datetime.combine(week, datetime.min.time()),
            date=datetime.combine(day, datetime.min.time()),
            event_type=event_type,
            event_key=key,
            amount=amount,
            source_type=scope,
            source_id=str(source_id) if source_id is not None else None,
            title=title or event_type,
        )
        self.db.add(event)
        self.db.flush()
        return event

    def add_sleep(self, day, *, user=None, secs=None, score=None):
        owner = user or self.user
        row = Wellness(
            user_id=owner.id,
            date=day.isoformat(),
            sleep_secs=secs,
            sleep_score=score,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def test_calendar_year_weeks_include_boundary_and_empty_future_weeks(self):
        today = date(2026, 10, 14)
        current_week = date(2026, 10, 12)
        self.add_summary(current_week, effort=42, total=42, actual_load=210, target_load=230)
        # Even if a future row exists, the public timeline must not leak its data.
        future_week = current_week + timedelta(days=7)
        self.add_summary(future_week, effort=99, total=99, actual_load=900, target_load=999)

        with patch("app.routers.sync._user_local_today", return_value=today):
            payload = sync_router.get_calendar_year_weeks(year=2026, current=self.user, db=self.db)
            default_payload = sync_router.get_calendar_year_weeks(year=None, current=self.user, db=self.db)

        self.assertEqual(default_payload["year"], 2026)
        self.assertEqual(payload["weeks"][0]["week_start"], "2025-12-29")
        self.assertEqual(payload["weeks"][0]["week_end"], "2026-01-04")
        self.assertEqual(payload["weeks"][-1]["week_start"], "2026-12-28")
        self.assertEqual(payload["weeks"][-1]["week_end"], "2027-01-03")
        current_row = next(week for week in payload["weeks"] if week["week_start"] == current_week.isoformat())
        self.assertTrue(current_row["is_current"])
        self.assertFalse(current_row["is_future"])
        self.assertEqual(current_row["total_xp"], 42)
        future_row = next(week for week in payload["weeks"] if week["week_start"] == future_week.isoformat())
        self.assertTrue(future_row["is_future"])
        self.assertFalse(future_row["has_summary"])
        self.assertEqual(future_row["total_xp"], 0)
        self.assertEqual(future_row["actual_load"], 0)
        self.assertEqual(future_row["target_load"], 0)

    def test_weekly_summary_allows_selecting_a_future_week_as_empty(self):
        current_day = date(2026, 10, 14)
        future_week = date(2026, 10, 19)
        with patch("app.routers.sync._user_local_today", return_value=current_day):
            payload = sync_router.get_weekly_summary(
                week_start=future_week,
                current=self.user,
                db=self.db,
            )

        self.assertEqual(payload["week"]["week_start"], future_week.isoformat())
        self.assertEqual(payload["week"]["state"], "no_data")
        self.assertEqual(payload["week"]["total_xp"], 0)
        self.assertFalse(payload["week"]["is_current_week"])
        self.assertEqual(payload["activities"], [])
        self.assertEqual(payload["events"], [])

    def test_xp_category_maps_weekly_achievement_slugs_and_defaults_unknown_events_to_quest(self):
        cases = [
            (SimpleNamespace(event_type="quest", event_key="quest:qualifying_days_5:2026-10-12"), "consistency"),
            (SimpleNamespace(event_type="activity_bonus", event_key="bonus:daily_workout:7:2026-10-13"), "consistency"),
            (SimpleNamespace(event_type="quest", event_key="quest:high_intensity:2026-10-12"), "quality"),
            (SimpleNamespace(event_type="quest", event_key="quest:long_workout_2h:2026-10-12"), "quality"),
            (SimpleNamespace(event_type="quest", event_key="quest:long_workout_3h:2026-10-12"), "quality"),
            (SimpleNamespace(event_type="quest", event_key="quest:good_sleep_5:2026-10-12"), "recovery"),
            (SimpleNamespace(event_type="sleep_bonus", event_key="sleep_bonus:good_night:2026-10-13"), "recovery"),
            (SimpleNamespace(event_type="quest", event_key="quest:goal_100:2026-10-12"), "quest"),
            (SimpleNamespace(event_type="quest", event_key="quest:ideal_week:2026-10-12"), "quest"),
            (SimpleNamespace(event_type="quest", event_key="quest:trainer_week:2026-10-12"), "quest"),
            (SimpleNamespace(event_type="achievement", event_key="achievement:historic:1"), "quest"),
            (SimpleNamespace(event_type="unknown", event_key="unmapped:thing"), "quest"),
        ]
        for event, expected in cases:
            with self.subTest(event_type=event.event_type, event_key=event.event_key):
                self.assertEqual(sync_router.xp_category(event), expected)

    def test_activity_xp_breakdown_caps_daily_tss_scopes_bonuses_and_matches_summary(self):
        manual = self.add_activity(
            "manual-xp", stamp=datetime(2026, 10, 13, 8, 0), tss=150,
            manual=True, source="UPLOAD_SITE", moving_time=1800, intensity=0.5,
        )
        hard = self.add_activity(
            "hard-xp", stamp=datetime(2026, 10, 13, 9, 0), tss=200,
            moving_time=3600, hard_secs=900, intensity=0.5,
        )
        self.db.flush()
        daily_xp = X6.effort_xp_day(350)
        shares = X6.allocate_daily_effort_xp([{"tss": 150}, {"tss": 200}], daily_xp)
        manual.xp_earned = shares[0]
        hard.xp_earned = shares[1]
        # Weekly tiles are categorized slices of the actual weekly total.
        total = X6.round_xp(daily_xp + 70 + 25 + 20 + 41 + 37)
        self.add_summary(
            date(2026, 10, 12), effort=daily_xp, consistency=70, quality=25,
            goal=20, recovery=41, quest=37, total=total, training_days=1,
        )
        self.add_event(
            "quest:qualifying_days_5:2026-10-12", "quest", 50,
            day=date(2026, 10, 13), title="🏆 5 дней с тренировками",
        )
        self.add_event(
            "quest:good_sleep_5:2026-10-12", "quest", 35,
            day=date(2026, 10, 13), title="🏆 5 ночей хорошего сна",
        )
        self.add_event(
            "quest:long_workout_2h:2026-10-12", "quest", 25,
            day=date(2026, 10, 13), source_id=hard.id, title="🏆 Длинная тренировка",
        )
        self.add_event(
            f"activity_bonus:45m:{hard.id}", "activity_bonus", 12,
            day=date(2026, 10, 13), scope="activity", source_id=hard.id,
            title="Тренировка ≥45 минут +12 XP",
        )
        self.add_event(
            f"bonus:daily_workout:{self.user.id}:2026-10-13", "activity_bonus", 20,
            day=date(2026, 10, 13), scope="activity", source_id=hard.id,
            title="Дневной бонус +20 XP",
        )
        self.add_event(
            "sleep_bonus:good_night:2026-10-13", "sleep_bonus", 6,
            day=date(2026, 10, 13), scope="wellness", source_id="2026-10-13",
            title="Хороший сон +6 XP",
        )
        self.add_event(
            "weekly_goal:2026-10-12", "weekly_goal", 20,
            day=date(2026, 10, 12), source_id="2026-10-12", title="Цель недели: 100%",
        )
        self.add_event(
            "quest:first-three-day-week", "quest", 25,
            day=date(2026, 10, 13), scope="quest", title="🏆 Первый шаг",
        )
        self.db.commit()

        manual_payload = sync_router.get_activity_xp_breakdown(
            activity_id=manual.id, current=self.user, db=self.db,
        )
        hard_payload = sync_router.get_activity_xp_breakdown(
            activity_id=hard.id, current=self.user, db=self.db,
        )

        self.assertTrue(manual_payload["effort"]["cap_applied"])
        self.assertEqual(manual_payload["effort"]["daily_tss_cap"], 300)
        self.assertEqual(manual_payload["effort"]["day_tss"], 350)
        self.assertEqual(manual_payload["effort"]["effective_day_tss"], 300)
        self.assertEqual(manual_payload["effort"]["manual_coefficient"], 0.5)
        self.assertEqual(manual_payload["effort"]["tss_before_manual_coefficient"], 300)
        self.assertEqual(manual_payload["related"]["activity"]["events"], [])
        self.assertEqual(manual_payload["totals"]["for_this_activity_xp"], shares[0])
        self.assertEqual(hard_payload["related"]["activity"]["total_xp"], 45)
        hard_awards = {item["title"]: item["amount"] for item in hard_payload["related"]["activity"]["events"]}
        self.assertNotIn("Тренировка ≥45 минут +12 XP", hard_awards)
        self.assertEqual(hard_awards["Дневной бонус +20 XP"], 20)
        self.assertEqual(hard_awards["🏆 Длинная тренировка"], 25)
        self.assertEqual(hard_payload["totals"]["for_this_activity_xp"], shares[1] + 45)
        self.assertNotIn("general", hard_payload["related"])
        week_payload = sync_router.get_weekly_summary(
            week_start=date(2026, 10, 12), current=self.user, db=self.db,
        )
        self.assertEqual(week_payload["week"]["daily_bonus_days"], 1)
        hard_week_activity = next(item for item in week_payload["activities"] if item["id"] == hard.id)
        self.assertEqual(hard_week_activity["effort_xp"], shares[1])
        self.assertEqual(hard_week_activity["xp"], shares[1] + 45)
        self.assertTrue(manual_payload["totals"]["weekly_summary_components_match"])
        self.assertEqual(manual_payload["totals"]["weekly_summary_components_xp"], total)
        self.assertEqual(manual_payload["totals"]["weekly_summary_total_xp"], total)

    def test_activity_xp_breakdown_is_private_to_owner(self):
        activity = self.add_activity("private-xp")
        stranger = User(
            username="other-interface-user",
            password_hash="test-hash",
            display_name="Other User",
            timezone_name="UTC",
        )
        self.db.add(stranger)
        self.db.commit()
        foreign_activity = self.add_activity(
            "foreign-xp", user=stranger, stamp=datetime(2026, 10, 13, 11, 0),
        )
        self.db.commit()
        with self.assertRaises(HTTPException) as captured:
            sync_router.get_activity_xp_breakdown(
                activity_id=foreign_activity.id, current=self.user, db=self.db,
            )
        self.assertEqual(captured.exception.status_code, 404)
        # The owner's activity still resolves normally.
        self.assertEqual(
            sync_router.get_activity_xp_breakdown(activity_id=activity.id, current=self.user, db=self.db)["activity_id"],
            activity.id,
        )

    def test_profile_stats_excludes_manual_distance_and_duration_but_keeps_xp(self):
        today = date(2026, 10, 14)
        self.add_activity(
            "measured-stats", stamp=datetime(2026, 10, 13, 10, 0), distance=10000,
            moving_time=3600, elevation=100, xp=8, manual=False,
        )
        self.add_activity(
            "manual-stats", stamp=datetime(2026, 10, 13, 11, 0), distance=7000,
            moving_time=1800, elevation=50, xp=4, manual=True, source="UPLOAD_SITE",
        )
        self.add_event(
            "day-bonus-stats", "consistency", 30, day=date(2026, 10, 13),
            scope="day", source_id="2026-10-13",
        )
        self.db.commit()

        with patch("app.routers.sync._user_local_today", return_value=today):
            weekly = sync_router.get_profile_stats(range="week", current=self.user, db=self.db)
            yearly = sync_router.get_profile_stats(range="year", current=self.user, db=self.db)
            seasonal = sync_router.get_profile_stats(range="season", current=self.user, db=self.db)

        for payload in (weekly, yearly, seasonal):
            self.assertEqual(payload["distance_km"], 10)
            self.assertEqual(payload["hours"], 1)
            self.assertEqual(payload["elevation"], 150)
            self.assertEqual(payload["workouts"], 2)
            self.assertEqual(payload["xp"], 42)
        self.assertEqual(weekly["start_date"], "2026-10-12")
        self.assertEqual(yearly["start_date"], "2026-01-01")
        self.assertEqual(seasonal["start_date"], "2026-09-01")

    def test_lifetime_achievements_ignore_records_before_activation_date(self):
        # Pre-activation source records remain available to weekly quests, not lifetime quests.
        self.add_summary(
            date(2025, 12, 29), training_days=3, ratio=1.0, finalized=True,
        )
        self.add_sleep(date(2025, 12, 29), secs=8 * 3600, score=None)
        self.add_sleep(date(2025, 12, 30), secs=7 * 3600, score=None)
        self.add_sleep(date(2025, 12, 31), secs=None, score=90)
        self.add_activity(
            "history-ride-1", stamp=datetime(2025, 12, 29, 8, 0), tss=30,
            distance=20000, moving_time=3600, indoor=True,
        )
        self.add_activity(
            "history-ride-2", stamp=datetime(2025, 12, 30, 8, 0), tss=30,
            distance=20000, moving_time=3000,
        )
        self.add_activity(
            "history-ride-3", stamp=datetime(2025, 12, 31, 8, 0), tss=30,
            distance=15000, moving_time=2400,
        )
        self.db.commit()

        with patch("app.services.quests._user_local_today", return_value=date(2026, 10, 14)):
            payload = sync_router.get_quests(current=self.user, db=self.db)
            quests = {quest["slug"]: quest for quest in payload}

            # Historical workouts/sleep before 2026-10-19 are excluded from lifetime progress.
            self.assertEqual(quests["first_three_day_week"]["progress"]["current"], 0)
            self.assertEqual(quests["first_three_day_week"]["status"], "open")
            self.assertEqual(quests["goal_met"]["progress"]["current"], 0)
            self.assertEqual(quests["goal_met"]["status"], "open")
            self.assertEqual(quests["first_50km_ride_week"]["progress"]["current"], 0)
            self.assertEqual(quests["first_50km_ride_week"]["status"], "open")
            self.assertEqual(quests["sleep_connected"]["progress"]["current"], 0)
            self.assertEqual(quests["sleep_connected"]["status"], "open")

            activities = self.db.query(Activity).filter(Activity.user_id == self.user.id).all()
            summaries = self.db.query(WeeklySummary).filter(WeeklySummary.user_id == self.user.id).all()
            granted = quest_service.grant_quests(self.db, self.user, activities, summaries)
            self.db.commit()
            self.assertGreaterEqual(granted, 1)

            # A repeated sync/recalculation is idempotent and cannot pay the same achievements twice.
            granted_again = quest_service.grant_quests(self.db, self.user, activities, summaries)
            self.db.commit()
            self.assertEqual(granted_again, 0)

        self.assertIsNone(
            self.db.query(XPEvent).filter(
                XPEvent.user_id == self.user.id,
                XPEvent.event_key == "quest:sleep_connected:lifetime",
            ).first()
        )
        # Repeatable weekly awards are not restricted by the lifetime cutoff.
        self.assertIsNotNone(
            self.db.query(XPEvent).filter(
                XPEvent.user_id == self.user.id,
                XPEvent.event_key == "quest:trainer_week:2025-12-29",
            ).first()
        )

    def test_quests_progress_and_sleep_duration_fulfill_three_nights(self):
        self.add_summary(
            date(2026, 10, 19), training_days=3, ratio=0.90, finalized=True,
        )
        self.add_sleep(date(2026, 10, 19), secs=8 * 3600, score=None)
        self.add_sleep(date(2026, 10, 20), secs=7 * 3600, score=None)
        self.add_sleep(date(2026, 10, 21), secs=6 * 3600, score=None)
        self.add_activity(
            "progress-ride-1", stamp=datetime(2026, 10, 19, 8, 0), tss=30,
            distance=20000, moving_time=3600, indoor=True,
        )
        self.add_activity(
            "progress-ride-2", stamp=datetime(2026, 10, 20, 9, 0), tss=30,
            distance=20000, moving_time=2400,
        )
        self.add_activity(
            "progress-ride-3", stamp=datetime(2026, 10, 21, 10, 0), tss=30,
            distance=15000, moving_time=1800,
        )
        self.db.commit()

        with patch("app.services.quests._user_local_today", return_value=date(2026, 10, 22)):
            payload = sync_router.get_quests(current=self.user, db=self.db)
            quests = {quest["slug"]: quest for quest in payload}
            self.assertEqual(quests["first_three_day_week"]["progress"]["current"], 3)
            self.assertEqual(quests["first_three_day_week"]["status"], "earned")
            self.assertEqual(quests["goal_met"]["progress"]["current"], 90)
            self.assertEqual(quests["goal_streak_3"]["progress"]["current"], 0)
            self.assertEqual(quests["first_50km_ride_week"]["progress"]["current"], 50)
            self.assertEqual(quests["sleep_connected"]["progress"]["current"], 3)
            self.assertEqual(len(quests["sleep_connected"]["progress"]["steps"]), 3)
            self.assertTrue(all(step["filled"] for step in quests["sleep_connected"]["progress"]["steps"]))
            self.assertEqual(quests["trainer_week"]["progress"]["current"], 1)
            self.assertEqual(quests["trainer_week"]["status"], "earned")
            self.assertTrue(quests["trainer_week"]["progress"]["season_active"])
            self.assertIsNone(quests["power_record_20m"]["progress"])
            self.assertTrue(quests["power_record_20m"]["progress_reason"])

            activities = self.db.query(Activity).filter(Activity.user_id == self.user.id).all()
            summaries = self.db.query(WeeklySummary).filter(WeeklySummary.user_id == self.user.id).all()
            quest_service.grant_quests(self.db, self.user, activities, summaries)
            self.db.commit()
            self.assertEqual(quest_service.grant_quests(self.db, self.user, activities, summaries), 0)
            self.db.commit()

        sleep_event = self.db.query(XPEvent).filter(
            XPEvent.user_id == self.user.id,
            XPEvent.event_key == "quest:sleep_connected:lifetime",
        ).first()
        self.assertIsNotNone(sleep_event)

    def test_weekly_quest_progress_counts_current_week_only_and_accepts_both_sleep_rules(self):
        today = date(2026, 10, 18)
        # Four qualifying days and one sub-floor day in this week.
        for index, day in enumerate((
            date(2026, 10, 12), date(2026, 10, 13),
            date(2026, 10, 14), date(2026, 10, 15),
        )):
            self.add_activity(
                f"weekly-qualifying-{index}", stamp=datetime.combine(day, datetime.min.time()).replace(hour=9),
                tss=30, moving_time=1800,
            )
        self.add_activity(
            "weekly-under-floor", stamp=datetime(2026, 10, 16, 9, 0),
            tss=10, moving_time=1800,
        )
        # 6h without a score and a score of 60 with less than 6h are both good nights.
        self.add_sleep(date(2026, 10, 12), secs=6 * 3600, score=None)
        self.add_sleep(date(2026, 10, 13), secs=5 * 3600, score=60)
        self.add_sleep(date(2026, 10, 14), secs=5 * 3600, score=59)
        # A qualified day from the prior week must not increase this week's counter.
        self.add_activity(
            "prior-week-ride", stamp=datetime(2026, 10, 11, 9, 0),
            tss=40, moving_time=2400,
        )
        self.db.commit()

        with patch("app.services.quests._user_local_today", return_value=today):
            payload = sync_router.get_quests(current=self.user, db=self.db)
        quests = {quest["slug"]: quest for quest in payload}
        self.assertEqual(quests["qualifying_days_5"]["kind"], "weekly")
        self.assertEqual(quests["qualifying_days_5"]["week_start"], "2026-10-12")
        self.assertEqual(quests["qualifying_days_5"]["progress"]["current"], 4)
        self.assertEqual(quests["qualifying_days_5"]["progress"]["target"], 5)
        self.assertEqual(quests["good_sleep_5"]["progress"]["current"], 2)
        self.assertEqual(quests["good_sleep_5"]["progress"]["target"], 5)
        self.assertEqual(len(quests["good_sleep_5"]["progress"]["steps"]), 5)
        self.assertTrue(quests["good_sleep_5"]["progress"]["steps"][0]["filled"])
        self.assertTrue(quests["good_sleep_5"]["progress"]["steps"][1]["filled"])
        self.assertFalse(quests["good_sleep_5"]["progress"]["steps"][2]["filled"])


    def test_execution_bonus_quests_are_included_in_existing_quests_response(self):
        week = date(2026, 10, 12)
        today = date(2026, 10, 18)
        novice = User(
            username="execution-novice",
            password_hash="test-hash",
            display_name="Execution Novice",
            timezone_name="UTC",
        )
        pro = User(
            username="execution-pro",
            password_hash="test-hash",
            display_name="Execution Pro",
            timezone_name="UTC",
        )
        self.db.add_all([novice, pro])
        self.db.commit()

        def prepare_week(owner, target_days):
            activities = []
            for offset in (0, 1):
                day = week + timedelta(days=offset)
                activities.append(self.add_activity(
                    f"{owner.username}-{offset}",
                    user=owner,
                    stamp=datetime.combine(day, datetime.min.time()).replace(hour=9),
                    tss=30,
                    moving_time=60 * 60,
                ))
            for offset in range(5):
                self.add_sleep(week + timedelta(days=offset), user=owner, secs=6 * 3600)
            summary = self.add_summary(
                week,
                user=owner,
                ratio=1.0,
                target_training_days=target_days,
                paused=False,
            )
            return activities, summary

        novice_activities, novice_summary = prepare_week(novice, target_days=2)
        pro_activities, pro_summary = prepare_week(pro, target_days=5)
        self.db.commit()

        with patch("app.services.quests._user_local_today", return_value=today):
            novice_quests = {
                item["slug"]: item
                for item in quest_service.quest_states(self.db, novice, selected_week=week)
            }
            pro_quests = {
                item["slug"]: item
                for item in quest_service.quest_states(self.db, pro, selected_week=week)
            }

        self.assertEqual(novice_quests["goal_100"]["kind"], "weekly")
        self.assertEqual(novice_quests["goal_100"]["reward"], 20)
        self.assertEqual(novice_quests["goal_100"]["status"], "earned")
        self.assertEqual(novice_quests["goal_100"]["progress"], {"current": 100.0, "target": 100, "unit": "%"})

        self.assertEqual(novice_quests["ideal_week"]["kind"], "weekly")
        self.assertEqual(novice_quests["ideal_week"]["reward"], 40)
        self.assertEqual(novice_quests["ideal_week"]["status"], "earned")
        self.assertEqual(novice_quests["ideal_week"]["progress"], {"current": 3, "target": 3, "unit": "условия"})

        # The pro still gets the goal bonus but needs five qualifying days for the ideal-week bonus.
        self.assertEqual(pro_quests["goal_100"]["status"], "earned")
        self.assertEqual(pro_quests["ideal_week"]["status"], "open")
        self.assertEqual(pro_quests["ideal_week"]["progress"], {"current": 2, "target": 3, "unit": "условия"})

    def test_weekly_summary_recalculation_persists_repeatable_bonuses_idempotently(self):
        week_start = date(2026, 10, 12)
        # Historical weeks must still recalculate Goal XP after migration activation.
        self.user.xp_migrated_at = datetime(2026, 10, 19)
        activity_ids = []
        for index, day in enumerate((
            date(2026, 10, 12), date(2026, 10, 13), date(2026, 10, 14),
            date(2026, 10, 15), date(2026, 10, 16),
        )):
            activity = self.add_activity(
                f"bonus-workout-{index}",
                stamp=datetime.combine(day, datetime.min.time()).replace(hour=9),
                tss=35, moving_time=60 * 60, intensity=0.80 if index == 0 else 0.50,
            )
            activity_ids.append(activity.id)

        manual = self.add_activity(
            "manual-bonus-excluded", stamp=datetime(2026, 10, 17, 9, 0),
            tss=100, moving_time=2 * 60 * 60, manual=True, intensity=1.0,
        )
        short = self.add_activity(
            "short-bonus-excluded", stamp=datetime(2026, 10, 17, 12, 0),
            tss=30, moving_time=44 * 60,
        )
        sunday_low = self.add_activity(
            "sunday-low-tss", stamp=datetime(2026, 10, 18, 8, 0),
            tss=40, moving_time=60 * 60,
        )
        sunday_winner = self.add_activity(
            "sunday-max-tss-first-id", stamp=datetime(2026, 10, 18, 9, 0),
            tss=50, moving_time=60 * 60,
        )
        sunday_tied = self.add_activity(
            "sunday-max-tss-tied-id", stamp=datetime(2026, 10, 18, 9, 0),
            tss=50, moving_time=60 * 60,
        )
        sunday_later = self.add_activity(
            "sunday-max-tss-later", stamp=datetime(2026, 10, 18, 10, 0),
            tss=50, moving_time=60 * 60,
        )
        sunday_activities = [sunday_low, sunday_winner, sunday_tied, sunday_later]
        good_sleep_days = (
            (date(2026, 10, 12), 6 * 3600, None),
            (date(2026, 10, 13), 5 * 3600, 60),
            (date(2026, 10, 14), 5 * 3600, 59),
            (date(2026, 10, 15), 5 * 3600, 90),
            (date(2026, 10, 16), 0, 61),
            (date(2026, 10, 17), 0, 62),
        )
        for day, secs, score in good_sleep_days:
            self.add_sleep(day, secs=secs, score=score)
        # Existing duplicate event types must be removed by recalculation.
        self.add_event("consistency:2026-10-12", "consistency", 30, day=date(2026, 10, 12))
        self.add_event("quality_hard:2026-10-12", "quality_hard", 15, day=date(2026, 10, 12))
        self.add_event("quality_long:2026-10-12", "quality_long", 15, day=date(2026, 10, 12))
        self.add_event("recovery:2026-10-12", "recovery", 5, day=date(2026, 10, 12))
        # Current week also has enough load for live goal XP and good sleep data.
        current_activity_1 = self.add_activity(
            "current-week-workout-1", stamp=datetime(2026, 10, 20, 9, 0),
            tss=40, moving_time=60 * 60,
        )
        current_activity_2 = self.add_activity(
            "current-week-workout-2", stamp=datetime(2026, 10, 22, 9, 0),
            tss=40, moving_time=60 * 60,
        )
        self.add_sleep(date(2026, 10, 20), secs=7 * 3600, score=90)
        self.db.commit()
        legacy_events_before = self.db.query(XPEvent).filter(
            XPEvent.user_id == self.user.id,
            XPEvent.event_type.in_(("consistency", "quality_hard", "quality_long", "recovery")),
        ).all()
        legacy_xp_removed_in_fixture = sum(float(event.amount or 0.0) for event in legacy_events_before)
        self.assertEqual(legacy_xp_removed_in_fixture, 65.0)

        class EmptyDuelQuery:
            def filter(self, *args):
                return self

            def distinct(self):
                return self

            def order_by(self, *args):
                return self

            def all(self):
                return []

        class EmptyDuelSession:
            def query(self, *args):
                return EmptyDuelQuery()

            def close(self):
                pass

        with (
            patch("app.routers.sync._user_local_today", return_value=date(2026, 10, 25)),
            patch("app.services.quests._user_local_today", return_value=date(2026, 10, 25)),
            patch("app.routers.sync.SessionLocal", EmptyDuelSession),
        ):
            sync_router._recalculate_user_xp_v6(self.db, self.user)
            self.db.commit()

            summary = self.db.query(WeeklySummary).filter(
                WeeklySummary.user_id == self.user.id,
                WeeklySummary.week_start == datetime.combine(week_start, datetime.min.time()),
            ).one()
            self.assertGreaterEqual(summary.completion_ratio, 1.15)
            self.assertEqual(summary.goal_xp, X6.weekly_goal_xp(summary.completion_ratio))
            self.assertEqual(summary.goal_xp, 120.0)
            event_rows = self.db.query(XPEvent).filter(
                XPEvent.user_id == self.user.id,
                XPEvent.week_start == datetime.combine(week_start, datetime.min.time()),
            ).all()
            workout_bonus_events = [event for event in event_rows if event.event_type == "activity_bonus"]
            duration_bonus_events = [
                event for event in workout_bonus_events
                if event.event_key.startswith("activity_bonus:45m:")
            ]
            daily_bonus_events = [
                event for event in workout_bonus_events
                if event.event_key.startswith("bonus:daily_workout:")
            ]
            sleep_bonus_events = [event for event in event_rows if event.event_type == "sleep_bonus"]

            expected_daily_ids = {str(value) for value in activity_ids} | {str(sunday_winner.id)}
            self.assertEqual(len(duration_bonus_events), 0)
            self.assertEqual(len(daily_bonus_events), 6)
            self.assertEqual(len(workout_bonus_events), 6)
            self.assertEqual(len(sleep_bonus_events), 5)
            self.assertEqual({event.source_id for event in daily_bonus_events}, expected_daily_ids)
            self.assertTrue(all(event.amount == X6.DAILY_WORKOUT_BONUS_XP for event in daily_bonus_events))
            self.assertTrue(all(event.amount == X6.GOOD_SLEEP_BONUS_XP for event in sleep_bonus_events))
            self.assertEqual(
                self.db.query(XPEvent).filter(
                    XPEvent.user_id == self.user.id,
                    XPEvent.event_type.in_(("consistency", "quality_hard", "quality_long", "recovery")),
                ).count(),
                0,
            )

            payload = sync_router.get_weekly_summary(
                week_start=week_start, current=self.user, db=self.db,
            )
            week = payload["week"]
            for field in ("effort_xp", "goal_xp", "consistency_xp", "quality_xp", "recovery_xp"):
                self.assertGreater(week[field], 0, field)
            # weekly_goal is deliberately excluded here because goal_xp already accounts for it.
            expected_quest_xp = sum(
                float(event.amount or 0.0)
                for event in event_rows
                if event.event_type in sync_router.WEEKLY_XP_EVENT_TYPES
                and sync_router.xp_category(event) == "quest"
            )
            self.assertAlmostEqual(week["quest_xp"], expected_quest_xp, places=1)
            components = sum(
                week[field] for field in (
                    "effort_xp", "goal_xp", "consistency_xp",
                    "quality_xp", "recovery_xp", "quest_xp",
                )
            )
            self.assertAlmostEqual(week["total_xp"], components, places=1)
            self.assertEqual(week["quest_xp"], round(summary.quest_xp, 1))
            self.assertEqual(week["daily_bonus_days"], 6)
            self.assertEqual(week["goal_xp"], 120.0)
            self.assertGreaterEqual(week["consistency_xp"], 6 * X6.DAILY_WORKOUT_BONUS_XP)
            bonus_events = {
                event.event_key: event
                for event in event_rows
                if event.event_key in {
                    "quest:goal_100:2026-10-12",
                    "quest:ideal_week:2026-10-12",
                }
            }
            self.assertEqual(bonus_events["quest:goal_100:2026-10-12"].amount, 20.0)
            self.assertEqual(bonus_events["quest:ideal_week:2026-10-12"].amount, 40.0)
            self.assertAlmostEqual(
                week["total_xp"],
                sum(week[field] for field in (
                    "effort_xp", "goal_xp", "consistency_xp",
                    "quality_xp", "recovery_xp", "quest_xp",
                )),
                places=1,
            )
            all_events_now = self.db.query(XPEvent).filter(XPEvent.user_id == self.user.id).all()
            self.assertAlmostEqual(
                self.user.total_xp,
                float(self.user.legacy_xp_offset or 0.0)
                + sum(float(activity.xp_earned or 0.0) for activity in self.db.query(Activity).filter(Activity.user_id == self.user.id).all())
                + sum(float(event.amount or 0.0) for event in all_events_now),
                places=1,
            )

            before = sorted((event.event_key, event.amount) for event in event_rows)
            sync_router._recalculate_user_xp_v6(self.db, self.user)
            self.db.commit()
            after_rows = self.db.query(XPEvent).filter(
                XPEvent.user_id == self.user.id,
                XPEvent.week_start == datetime.combine(week_start, datetime.min.time()),
            ).all()
            after = sorted((event.event_key, event.amount) for event in after_rows)
            self.assertEqual(after, before)
            self.assertEqual(
                self.db.query(XPEvent).filter(
                    XPEvent.user_id == self.user.id,
                    XPEvent.event_type == "activity_bonus",
                ).count(),
                8,
            )
            self.assertEqual(
                self.db.query(XPEvent).filter(
                    XPEvent.user_id == self.user.id,
                    XPEvent.event_type == "activity_bonus",
                    XPEvent.event_key.startswith("activity_bonus:45m:"),
                ).count(),
                0,
            )
            self.assertEqual(
                self.db.query(XPEvent).filter(
                    XPEvent.user_id == self.user.id,
                    XPEvent.event_type == "sleep_bonus",
                ).count(),
                6,
            )

            current_payload = sync_router.get_weekly_summary(
                week_start=date(2026, 10, 19), current=self.user, db=self.db,
            )
            current_week = current_payload["week"]
            self.assertEqual(current_week["state"], "in_progress")
            self.assertGreater(current_week["goal_xp"], 0)
            self.assertEqual(current_week["daily_bonus_days"], 2)
            self.assertGreater(current_week["recovery_xp"], 0)
            current_components = sum(
                current_week[field] for field in (
                    "effort_xp", "goal_xp", "consistency_xp",
                    "quality_xp", "recovery_xp", "quest_xp",
                )
            )
            self.assertAlmostEqual(current_week["total_xp"], current_components, places=1)

    def test_manual_workouts_do_not_qualify_for_weekly_long_or_intensity_quests(self):
        self.add_activity(
            "manual-long-hard", stamp=datetime(2026, 10, 14, 9, 0),
            tss=200, moving_time=4 * 3600, manual=True,
            intensity=1.0, hard_secs=3 * 3600,
        )
        self.db.commit()
        with patch("app.services.quests._user_local_today", return_value=date(2026, 10, 18)):
            payload = sync_router.get_quests(current=self.user, db=self.db)
        quests = {quest["slug"]: quest for quest in payload}
        self.assertEqual(quests["long_workout_2h"]["progress"]["current"], 0)
        self.assertEqual(quests["long_workout_3h"]["progress"]["current"], 0)
        self.assertEqual(quests["high_intensity"]["progress"]["current"], 0)
        self.assertEqual(quests["long_workout_2h"]["status"], "open")
        self.assertEqual(quests["high_intensity"]["status"], "open")

    def test_weekly_awards_are_idempotent_and_persist_with_week_specific_keys(self):
        today = date(2026, 10, 18)
        workouts = [
            ("monday-hour", datetime(2026, 10, 12, 9, 0), 30, 3600, 0.50, 0),
            ("tuesday-if", datetime(2026, 10, 13, 9, 0), 30, 3600, 0.80, 0),
            ("wednesday-three-hour", datetime(2026, 10, 14, 9, 0), 35, 3 * 3600, 0.55, 0),
            ("thursday-hard-secs", datetime(2026, 10, 15, 9, 0), 30, 1800, 0.50, 300),
            ("friday-hour", datetime(2026, 10, 16, 9, 0), 30, 1800, 0.50, 0),
        ]
        for key, stamp, tss, moving_time, intensity, hard_secs in workouts:
            self.add_activity(
                key, stamp=stamp, tss=tss, moving_time=moving_time,
                intensity=intensity, hard_secs=hard_secs,
            )
        # Three nights qualify by duration alone; two qualify by score alone.
        for day in (
            date(2026, 10, 12), date(2026, 10, 13), date(2026, 10, 14),
            date(2026, 10, 15), date(2026, 10, 16),
        ):
            if day.day in (12, 14, 16):
                self.add_sleep(day, secs=6 * 3600, score=None)
            else:
                self.add_sleep(day, secs=5 * 3600, score=60)
        self.db.commit()

        with patch("app.services.quests._user_local_today", return_value=today):
            activities = self.db.query(Activity).filter(Activity.user_id == self.user.id).all()
            summaries = self.db.query(WeeklySummary).filter(WeeklySummary.user_id == self.user.id).all()
            first_grant = quest_service.grant_quests(self.db, self.user, activities, summaries)
            self.db.commit()
            second_grant = quest_service.grant_quests(self.db, self.user, activities, summaries)
            self.db.commit()

        self.assertGreaterEqual(first_grant, 5)
        self.assertEqual(second_grant, 0)
        expected = {
            "quest:qualifying_days_5:2026-10-12": 50,
            "quest:good_sleep_5:2026-10-12": 35,
            "quest:long_workout_2h:2026-10-12": 25,
            "quest:long_workout_3h:2026-10-12": 15,
            "quest:high_intensity:2026-10-12": 30,
        }
        for event_key, amount in expected.items():
            event = self.db.query(XPEvent).filter(
                XPEvent.user_id == self.user.id,
                XPEvent.event_key == event_key,
            ).first()
            self.assertIsNotNone(event, event_key)
            self.assertEqual(event.amount, amount, event_key)

    def test_weekly_progress_resets_and_previous_week_awards_remain_queryable(self):
        self.add_activity(
            "last-week-long-ride", stamp=datetime(2026, 10, 6, 9, 0),
            tss=40, moving_time=2 * 3600,
        )
        self.db.commit()
        activities = self.db.query(Activity).filter(Activity.user_id == self.user.id).all()
        summaries = self.db.query(WeeklySummary).filter(WeeklySummary.user_id == self.user.id).all()
        quest_service.grant_quests(self.db, self.user, activities, summaries)
        self.db.commit()

        with patch("app.services.quests._user_local_today", return_value=date(2026, 10, 18)):
            old_week = sync_router.get_quests(
                week_start=date(2026, 10, 5), current=self.user, db=self.db,
            )
            current_week = sync_router.get_quests(current=self.user, db=self.db)
        old_long = next(q for q in old_week if q["slug"] == "long_workout_2h")
        current_long = next(q for q in current_week if q["slug"] == "long_workout_2h")
        self.assertEqual(old_long["week_start"], "2026-10-05")
        self.assertEqual(old_long["status"], "earned")
        self.assertIsNotNone(old_long["earned_at"])
        self.assertEqual(current_long["week_start"], "2026-10-12")
        self.assertEqual(current_long["progress"]["current"], 0)
        self.assertEqual(current_long["status"], "open")


    def test_quality_hard_requires_fifteen_minutes_and_attributes_first_qualifier(self):
        day = date(2026, 10, 13)
        rows = {
            day: [
                {
                    "id": 1, "sport_type": "RIDE", "moving_time": 1800,
                    "hard_secs": 5 * 60, "intensity": 0.5,
                    "load_source": "real", "start_date": datetime(2026, 10, 13, 8, 0),
                },
                {
                    "id": 2, "sport_type": "RIDE", "moving_time": 1800,
                    "hard_secs": 15 * 60, "intensity": 0.5,
                    "load_source": "real", "start_date": datetime(2026, 10, 13, 9, 0),
                },
            ]
        }
        sources = X6.quality_event_activity_ids(rows, {"RIDE": 9999})
        self.assertEqual(sources["quality_hard"], 2)
        self.assertIsNone(sources["quality_long"])
        self.assertEqual(X6.quality_events_week(rows, {"RIDE": 9999}), [("quality_hard", 15.0)])



    def test_goal_and_ideal_week_bonuses_use_personal_target_and_reconcile_idempotently(self):
        week = date(2026, 10, 19)
        novice = User(
            username="ideal-week-novice",
            password_hash="test-hash",
            display_name="Ideal Week Novice",
            timezone_name="UTC",
        )
        pro = User(
            username="ideal-week-pro",
            password_hash="test-hash",
            display_name="Ideal Week Pro",
            timezone_name="UTC",
        )
        self.db.add_all([novice, pro])
        self.db.commit()

        def add_week(owner, days, target_days):
            activities = []
            for index, day in enumerate(days):
                activities.append(self.add_activity(
                    f"{owner.username}-{index}",
                    user=owner,
                    stamp=datetime.combine(day, datetime.min.time()).replace(hour=9),
                    tss=30,
                    moving_time=60 * 60,
                ))
            for offset in range(5):
                self.add_sleep(
                    week + timedelta(days=offset),
                    user=owner,
                    secs=6 * 60 * 60,
                )
            summary = self.add_summary(
                week,
                user=owner,
                ratio=1.0,
                actual_load=100,
                target_load=100,
                target_training_days=target_days,
                paused=False,
            )
            return activities, summary

        novice_activities, novice_summary = add_week(
            novice, [week, week + timedelta(days=1)], target_days=2,
        )
        pro_activities, pro_summary = add_week(
            pro, [week, week + timedelta(days=1)], target_days=5,
        )
        pro_summary.league_score = 88.0
        self.db.commit()

        def get_event(owner, key):
            return self.db.query(XPEvent).filter(
                XPEvent.user_id == owner.id,
                XPEvent.event_key == key,
            ).first()

        with patch("app.services.quests._user_local_today", return_value=date(2026, 10, 26)):
            quest_service.grant_quests(self.db, novice, novice_activities, [novice_summary])
            quest_service.grant_quests(self.db, pro, pro_activities, [pro_summary])
            self.db.commit()

            self.assertEqual(get_event(novice, "quest:goal_100:2026-10-19").amount, 20.0)
            self.assertEqual(get_event(novice, "quest:ideal_week:2026-10-19").amount, 40.0)
            self.assertEqual(get_event(pro, "quest:goal_100:2026-10-19").amount, 20.0)
            self.assertIsNone(get_event(pro, "quest:ideal_week:2026-10-19"))
            self.assertEqual(pro_summary.league_score, 88.0)

            # Re-running the same recalculation must not duplicate either event.
            self.assertEqual(
                quest_service.grant_quests(self.db, novice, novice_activities, [novice_summary]),
                0,
            )
            self.db.commit()
            self.assertEqual(
                self.db.query(XPEvent).filter(
                    XPEvent.user_id == novice.id,
                    XPEvent.event_key == "quest:ideal_week:2026-10-19",
                ).count(),
                1,
            )

            # The plan target remains personal: the pro earns the +40 only after
            # reaching five qualifying days while keeping goal and sleep conditions.
            for index, offset in enumerate((2, 3, 4), start=2):
                day = week + timedelta(days=offset)
                pro_activities.append(self.add_activity(
                    f"{pro.username}-{index}",
                    user=pro,
                    stamp=datetime.combine(day, datetime.min.time()).replace(hour=9),
                    tss=30,
                    moving_time=60 * 60,
                ))
            quest_service.grant_quests(self.db, pro, pro_activities, [pro_summary])
            self.db.commit()
            self.assertEqual(get_event(pro, "quest:ideal_week:2026-10-19").amount, 40.0)
            self.assertEqual(pro_summary.league_score, 88.0)

            # If synced history invalidates goal completion, stale execution
            # bonuses are removed instead of remaining in total XP.
            novice_summary.completion_ratio = 0.99
            self.db.commit()
            quest_service.grant_quests(self.db, novice, novice_activities, [novice_summary])
            self.db.commit()
            self.assertIsNone(get_event(novice, "quest:goal_100:2026-10-19"))
            self.assertIsNone(get_event(novice, "quest:ideal_week:2026-10-19"))

if __name__ == "__main__":
    unittest.main()
