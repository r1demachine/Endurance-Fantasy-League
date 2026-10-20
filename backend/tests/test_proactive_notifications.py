"""Regression tests for timezone-aware proactive Telegram notifications."""
import os
import unittest
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from cryptography.fernet import Fernet

os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/efl-proactive-notifications-tests.db")
os.environ.setdefault("JWT_SECRET", "unit-test-jwt-secret-value-longer-than-32-characters")
os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
os.environ.setdefault("REDIS_URL", "")

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models import Activity, Friendship, FriendshipStatus, NotificationLog, User
from app.routers import internal_notify
from app.rate_limit import limiter
from app.services.proactive import (
    format_overtaken_message,
    is_daily_reminder_window,
    is_quiet_hours,
    profile_visible_on_leaderboard,
    reminder_decay_active,
    send_proactive,
    user_local_datetime,
)


class FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        fixed = datetime(2026, 10, 20, 14, 30, tzinfo=timezone.utc)
        return fixed.astimezone(tz) if tz else fixed.replace(tzinfo=None)


class ProactiveNotificationTests(unittest.IsolatedAsyncioTestCase):
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
        self.owner = self.make_user(
            "proactive-owner",
            telegram_chat_id="1001",
            telegram_notify=True,
            timezone_name="Asia/Bangkok",
            timezone_confirmed=True,
        )
        self.app = FastAPI()
        self.app.state.limiter = limiter
        self.app.include_router(internal_notify.router)

        def override_db():
            yield self.db

        self.app.dependency_overrides[get_db] = override_db
        self.client = TestClient(self.app)
        self.settings = SimpleNamespace(
            CRON_SECRET="s" * 40,
            TELEGRAM_BOT_TOKEN="test-token",
        )
        self.settings_patches = [
            patch("app.routers.internal_notify.get_settings", return_value=self.settings),
            patch("app.services.proactive.get_settings", return_value=self.settings),
            patch("app.services.proactive.send_message", new_callable=AsyncMock),
            patch("app.routers.internal_notify.datetime", FrozenDateTime),
        ]
        self.mockers = [patcher.start() for patcher in self.settings_patches]
        self.send_mock = self.mockers[2]

    def tearDown(self):
        for patcher in reversed(self.settings_patches):
            patcher.stop()
        self.client.close()
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def make_user(self, username, **kwargs):
        user = User(
            username=username,
            password_hash="test-hash",
            display_name=username.title(),
            profile_visibility=kwargs.pop("profile_visibility", "authenticated"),
            activity_visibility="friends",
            **kwargs,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def add_activity(self, user, stamp):
        activity = Activity(
            user_id=user.id,
            intervals_activity_id=f"test-{user.id}-{stamp.isoformat()}",
            source="INTERVALS",
            name="Morning ride",
            sport_type="Ride",
            moving_time=1800,
            distance=12000,
            training_load=30,
            tss=30,
            start_date=stamp,
            start_date_local=stamp,
        )
        self.db.add(activity)
        self.db.commit()
        return activity

    def test_local_window_handles_utc_plus_seven_and_day_rollover(self):
        local_evening = user_local_datetime(
            self.owner, datetime(2026, 10, 20, 14, 30, tzinfo=timezone.utc)
        )
        self.assertEqual(local_evening.strftime("%Y-%m-%d %H:%M"), "2026-10-20 21:30")
        self.assertTrue(is_daily_reminder_window(local_evening))
        self.assertFalse(is_quiet_hours(local_evening))

        after_midnight = user_local_datetime(
            self.owner, datetime(2026, 10, 20, 17, 30, tzinfo=timezone.utc)
        )
        self.assertEqual(after_midnight.date(), date(2026, 10, 21))
        self.assertEqual(after_midnight.hour, 0)
        self.assertTrue(is_quiet_hours(after_midnight))
        self.assertFalse(is_daily_reminder_window(after_midnight))

    async def test_proactive_gate_is_idempotent_and_limits_all_kinds_to_one_per_day(self):
        now = datetime(2026, 10, 20, 14, 30, tzinfo=timezone.utc)
        first = await send_proactive(self.db, self.owner, "activity_social", "Новое событие", now=now)
        second_kind_same_day = await send_proactive(
            self.db, self.owner, "weekly_results", "Итоги недели", now=now
        )
        duplicate = await send_proactive(
            self.db, self.owner, "activity_social", "Повтор", now=now
        )
        self.assertTrue(first)
        self.assertFalse(second_kind_same_day)
        self.assertFalse(duplicate)
        self.assertEqual(self.db.query(NotificationLog).filter_by(user_id=self.owner.id).count(), 1)
        self.assertEqual(self.send_mock.await_count, 1)
        self.assertIn("/notify off", self.send_mock.await_args.args[1])

    async def test_weekly_limit_stops_after_four_messages_in_same_local_week(self):
        outcomes = []
        for offset in range(5):
            now = datetime(2026, 10, 19 + offset, 10, 0, tzinfo=timezone.utc)
            outcomes.append(await send_proactive(
                self.db, self.owner, "weekly_results", f"Итоги {offset}", now=now
            ))
        self.assertEqual(outcomes, [True, True, True, True, False])
        self.assertEqual(self.db.query(NotificationLog).filter_by(user_id=self.owner.id).count(), 4)

    async def test_quiet_hours_block_proactive_messages(self):
        allowed = await send_proactive(
            self.db, self.owner, "activity_social", "Комментарий",
            now=datetime(2026, 10, 20, 16, 0, tzinfo=timezone.utc),
        )
        self.assertFalse(allowed)
        self.assertEqual(self.send_mock.await_count, 0)
        self.assertEqual(self.db.query(NotificationLog).count(), 0)

    async def test_failed_telegram_delivery_does_not_consume_a_message_slot(self):
        now = datetime(2026, 10, 20, 14, 30, tzinfo=timezone.utc)
        self.send_mock.return_value = False
        first = await send_proactive(self.db, self.owner, "activity_social", "Сбой доставки", now=now)
        self.assertFalse(first)
        self.assertEqual(self.db.query(NotificationLog).count(), 0)

        self.send_mock.return_value = True
        retry = await send_proactive(self.db, self.owner, "activity_social", "Повтор", now=now)
        self.assertTrue(retry)
        self.assertEqual(self.db.query(NotificationLog).count(), 1)
        self.assertEqual(self.send_mock.await_count, 2)

    def test_three_consecutive_reminders_decay_until_new_activity(self):
        for day in (date(2026, 10, 17), date(2026, 10, 18), date(2026, 10, 19)):
            self.db.add(NotificationLog(
                user_id=self.owner.id,
                kind="daily_bonus_reminder",
                local_date=day,
                created_at=datetime.combine(day, datetime.min.time()),
            ))
        self.db.commit()
        self.assertTrue(reminder_decay_active(self.db, self.owner, date(2026, 10, 20)))

        self.add_activity(self.owner, datetime(2026, 10, 20, 9, 0))
        self.assertFalse(reminder_decay_active(self.db, self.owner, date(2026, 10, 20)))

    def test_names_are_only_used_when_leaderboard_profile_is_visible(self):
        friend = self.make_user("visible-friend", profile_visibility="friends")
        hidden = self.make_user("hidden-user", profile_visibility="private")
        self.db.add(Friendship(
            from_user_id=self.owner.id,
            to_user_id=friend.id,
            status=FriendshipStatus.ACCEPTED,
        ))
        self.db.commit()

        self.assertTrue(profile_visible_on_leaderboard(self.db, self.owner, friend))
        self.assertFalse(profile_visible_on_leaderboard(self.db, self.owner, hidden))
        named = format_overtaken_message(rank=4, delta=12, visible_name=friend.display_name)
        anonymous = format_overtaken_message(rank=4, delta=12, visible_name=None)
        self.assertIn(friend.display_name, named)
        self.assertIn("12 очков", named)
        self.assertIn("Кто-то обошёл тебя", anonymous)
        self.assertNotIn(hidden.display_name, anonymous)

    async def test_tick_is_idempotent_without_manual_sync(self):
        self.add_activity(self.owner, datetime(2026, 10, 20, 10, 0))
        headers = {"X-Cron-Secret": self.settings.CRON_SECRET}
        first = self.client.post("/api/internal/notify/tick", headers=headers)
        second = self.client.post("/api/internal/notify/tick", headers=headers)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()["sent"]["daily_bonus_reminder"], 1)
        self.assertEqual(second.json()["sent"]["daily_bonus_reminder"], 0)
        self.assertEqual(self.db.query(NotificationLog).filter_by(
            user_id=self.owner.id, kind="daily_bonus_reminder"
        ).count(), 1)
        self.assertEqual(self.send_mock.await_count, 1)

    def test_tick_returns_404_when_secret_is_not_configured(self):
        with patch(
            "app.routers.internal_notify.get_settings",
            return_value=SimpleNamespace(CRON_SECRET=None),
        ):
            response = self.client.post("/api/internal/notify/tick")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.send_mock.await_count, 0)

    def test_bad_cron_secret_is_rejected(self):
        response = self.client.post(
            "/api/internal/notify/tick",
            headers={"X-Cron-Secret": "wrong" * 8},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.send_mock.await_count, 0)


if __name__ == "__main__":
    unittest.main()
