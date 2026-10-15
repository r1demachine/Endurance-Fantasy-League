"""Regression tests for Telegram webhook security, linking, uploads and week notices."""
import hashlib
import os
import unittest
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/efl-telegram-tests.db")
os.environ.setdefault("JWT_SECRET", "unit-test-jwt-secret-value-longer-than-32-characters")
os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
os.environ.setdefault("REDIS_URL", "")

from app.database import Base, get_db
from app.models import Activity, TelegramLinkAttempt, TelegramWebhookUpdate, User, WeeklySummary
from app.routers import telegram as telegram_router
from app.routers.sync import _close_league_week
from app.services.telegram_week import latest_completed_week_start, notify_week_results
from app.routers.telegram import (
    _hash_link_code, _new_link_code, _telegram_deep_link,
    LINK_TTL_MINUTES, UPLOAD_SOURCE,
)

TCX_BYTES = b"""<?xml version="1.0"?>
<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2">
  <Activities><Activity Sport="Biking"><Id>2026-10-01T10:00:00Z</Id><Lap StartTime="2026-10-01T10:00:00Z">
    <TotalTimeSeconds>20</TotalTimeSeconds><DistanceMeters>200</DistanceMeters>
    <Track><Trackpoint><Time>2026-10-01T10:00:00Z</Time><AltitudeMeters>100</AltitudeMeters><HeartRateBpm><Value>170</Value></HeartRateBpm></Trackpoint>
    <Trackpoint><Time>2026-10-01T10:00:10Z</Time><AltitudeMeters>102</AltitudeMeters><HeartRateBpm><Value>175</Value></HeartRateBpm></Trackpoint>
    <Trackpoint><Time>2026-10-01T10:00:20Z</Time><AltitudeMeters>101</AltitudeMeters><HeartRateBpm><Value>180</Value></HeartRateBpm></Trackpoint></Track>
  </Lap></Activity></Activities>
</TrainingCenterDatabase>"""


class TelegramSecurityTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        self.settings = SimpleNamespace(
            TELEGRAM_WEBHOOK_SECRET="valid_webhook_secret-123456",
            TELEGRAM_BOT_TOKEN="test-token",
            TELEGRAM_BOT_USERNAME="test_bot",
            PRIVACY_CONSENT_VERSION="consent-v1",
            XP_ENGINE="v6",
        )
        app = FastAPI()
        app.include_router(telegram_router.router)

        def override_get_db():
            db = self.Session()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)
        self.patches = [
            patch("app.routers.telegram.get_settings", return_value=self.settings),
            patch("app.routers.telegram.bot_configured", return_value=True),
            patch("app.routers.telegram.send_message", new_callable=AsyncMock),
        ]
        self.mockers = [p.start() for p in self.patches]
        self.send_mock = self.mockers[2]
        self.headers = {"X-Telegram-Bot-Api-Secret-Token": self.settings.TELEGRAM_WEBHOOK_SECRET}

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.client.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def create_user(self, **kwargs):
        db = self.Session()
        user = User(
            username=kwargs.pop("username", "athlete"),
            password_hash="test-hash",
            display_name="Athlete",
            **kwargs,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        user_id = user.id
        db.close()
        return user_id

    def post_update(self, update_id, message, *, secret=None):
        return self.client.post(
            "/api/telegram/webhook",
            headers={"X-Telegram-Bot-Api-Secret-Token": secret or self.settings.TELEGRAM_WEBHOOK_SECRET},
            json={"update_id": update_id, **message},
        )

    def test_wrong_webhook_secret_returns_403(self):
        response = self.post_update(
            100,
            {"message": {"chat": {"id": 123, "type": "private"}, "text": "/start"}},
            secret="wrong_secret-123456",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.send_mock.await_count, 0)

    def test_link_code_is_long_base32_and_only_hash_is_stored(self):
        code = _new_link_code()
        self.assertGreaterEqual(len(code), 8)
        self.assertRegex(code, r"^[A-Z2-7]+$")
        self.assertEqual(len(_hash_link_code(code)), 64)
        user_id = self.create_user(
            telegram_link_code=_hash_link_code(code),
            telegram_link_expires=datetime.utcnow() + timedelta(minutes=LINK_TTL_MINUTES),
        )
        db = self.Session()
        self.assertEqual(db.get(User, user_id).telegram_link_code, _hash_link_code(code))
        self.assertNotEqual(db.get(User, user_id).telegram_link_code, code)
        db.close()

    def test_telegram_deep_link_uses_valid_start_payload(self):
        code = "ABCDEFGH234567AB"
        self.assertEqual(
            _telegram_deep_link("@test_bot", code),
            f"https://t.me/test_bot?start=link_{code}",
        )
        self.assertIsNone(_telegram_deep_link("bad username", code))
        self.assertIsNone(_telegram_deep_link("test_bot", "contains/slash"))

    def test_start_deep_link_links_account_without_manual_command(self):
        code = "ABCDEFGH234567AB"
        user_id = self.create_user(
            username="deeplink",
            telegram_link_code=_hash_link_code(code),
            telegram_link_expires=datetime.utcnow() + timedelta(minutes=5),
        )
        response = self.post_update(
            104,
            {"message": {
                "chat": {"id": 321, "type": "private"},
                "text": f"/start link_{code}",
            }},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Готово! Привязан аккаунт @deeplink", self.send_mock.await_args.args[1])
        db = self.Session()
        user = db.get(User, user_id)
        self.assertEqual(user.telegram_chat_id, "321")
        self.assertFalse(user.telegram_notify)
        self.assertIsNone(user.telegram_link_code)
        self.assertIsNone(user.telegram_link_expires)
        db.close()

    def test_expired_link_code_is_rejected_and_counted(self):
        user_id = self.create_user(
            username="expired",
            telegram_link_code=_hash_link_code("ABCDEFGH"),
            telegram_link_expires=datetime.utcnow() - timedelta(seconds=1),
        )
        response = self.post_update(
            101,
            {"message": {"chat": {"id": 456, "type": "private"}, "text": "/link ABCDEFGH"}},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("неверный или истёк", self.send_mock.await_args.args[1])
        db = self.Session()
        self.assertIsNone(db.get(User, user_id).telegram_chat_id)
        self.assertEqual(db.query(TelegramLinkAttempt).filter_by(chat_id="456").count(), 1)
        db.close()

    def test_link_from_non_private_chat_is_rejected(self):
        user_id = self.create_user(
            username="grouplink",
            telegram_link_code=_hash_link_code("ABCDEFGH"),
            telegram_link_expires=datetime.utcnow() + timedelta(minutes=5),
        )
        response = self.post_update(
            102,
            {"message": {"chat": {"id": -200, "type": "group"}, "text": "/link ABCDEFGH"}},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("только в личном чате", self.send_mock.await_args.args[1])
        db = self.Session()
        self.assertIsNone(db.get(User, user_id).telegram_chat_id)
        db.close()

    def test_sixth_invalid_link_attempt_is_rate_limited(self):
        for index in range(5):
            response = self.post_update(
                200 + index,
                {"message": {"chat": {"id": 457, "type": "private"}, "text": "/link INVALID123"}},
            )
            self.assertEqual(response.status_code, 200)
        self.send_mock.reset_mock()
        response = self.post_update(
            205,
            {"message": {"chat": {"id": 457, "type": "private"}, "text": "/link INVALID123"}},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Слишком много", self.send_mock.await_args.args[1])
        db = self.Session()
        self.assertEqual(db.query(TelegramLinkAttempt).filter_by(chat_id="457").count(), 5)
        db.close()

    def test_chat_bound_to_another_user_is_not_silently_stolen(self):
        owner_id = self.create_user(username="chatowner", telegram_chat_id="789", telegram_notify=True)
        self.create_user(
            username="targetuser",
            telegram_link_code=_hash_link_code("ABCDEFGH"),
            telegram_link_expires=datetime.utcnow() + timedelta(minutes=5),
        )
        response = self.post_update(
            206,
            {"message": {"chat": {"id": 789, "type": "private"}, "text": "/link ABCDEFGH"}},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("уже привязан к другому аккаунту", self.send_mock.await_args.args[1])
        db = self.Session()
        self.assertEqual(db.get(User, owner_id).telegram_chat_id, "789")
        db.close()

    def test_same_upload_twice_creates_one_activity_and_reports_duplicate(self):
        user_id = self.create_user(
            username="uploaduser",
            telegram_chat_id="555",
            telegram_notify=False,
            privacy_consent_version=self.settings.PRIVACY_CONSENT_VERSION,
            privacy_consent_at=datetime.utcnow(),
            lthr=165,
            max_hr=195,
            resting_hr=50,
        )
        with patch("app.routers.telegram.download_telegram_file", new_callable=AsyncMock, return_value=(TCX_BYTES, "activity.tcx")), \
             patch("app.services.activity_upload.get_settings", return_value=self.settings), \
             patch("app.routers.sync._recalculate_user_xp_v6"), \
             patch("app.routers.sync._recalculate_user_xp"):
            first = self.post_update(
                300,
                {"message": {"chat": {"id": 555, "type": "private"},
                             "document": {"file_id": "file-1", "file_name": "ride.tcx", "file_size": 1}}},
            )
            self.assertEqual(first.status_code, 200)
            self.assertIn("Сохранено:", self.send_mock.await_args.args[1])
            self.send_mock.reset_mock()
            second = self.post_update(
                301,
                {"message": {"chat": {"id": 555, "type": "private"},
                             "document": {"file_id": "file-1", "file_name": "ride.tcx", "file_size": 1}}},
            )
            self.assertEqual(second.status_code, 200)
            self.assertIn("Эта тренировка уже есть", self.send_mock.await_args.args[1])
            db = self.Session()
            activities = db.query(Activity).filter_by(user_id=user_id).all()
            self.assertEqual(len(activities), 1)
            expected_sha = hashlib.sha256(TCX_BYTES).hexdigest()
            self.assertEqual(activities[0].intervals_activity_id, f"UPLOAD_TELEGRAM:{expected_sha}")
            self.assertEqual(activities[0].source, "UPLOAD_TELEGRAM")
            db.close()

    def test_duplicate_update_id_and_edited_message_are_ignored(self):
        self.post_update(400, {"message": {"chat": {"id": 123, "type": "private"}, "text": "/start"}})
        first_count = self.send_mock.await_count
        duplicate = self.post_update(400, {"message": {"chat": {"id": 123, "type": "private"}, "text": "/start"}})
        edited = self.post_update(401, {"edited_message": {"chat": {"id": 123, "type": "private"}, "text": "/start"}})
        self.assertTrue(duplicate.json().get("duplicate"))
        self.assertEqual(edited.status_code, 200)
        self.assertEqual(self.send_mock.await_count, first_count)
        db = self.Session()
        self.assertEqual(db.query(TelegramWebhookUpdate).count(), 2)
        db.close()

    def test_week_notification_is_reserved_before_send_and_not_repeated(self):
        last_week = latest_completed_week_start()
        user_id = self.create_user(
            username="weekly",
            telegram_chat_id="900",
            telegram_notify=True,
            telegram_last_notified_week=None,
        )
        db = self.Session()
        db.add(WeeklySummary(
            user_id=user_id,
            week_start=datetime.combine(last_week, datetime.min.time()),
            finalized=True,
            total_xp=123,
            training_days=4,
            league_score=92.3,
        ))
        db.commit()
        with patch("app.services.telegram_week.get_settings", return_value=self.settings), \
             patch("app.services.telegram_week.send_message", new_callable=AsyncMock) as send:
            sent_first = notify_week_results(db, last_week)
            marker_after_first = db.get(User, user_id).telegram_last_notified_week
            sent_second = notify_week_results(db, last_week)
            self.assertEqual(sent_first, 1)
            self.assertEqual(sent_second, 0)
            self.assertEqual(marker_after_first, last_week)
            self.assertEqual(send.await_count, 1)
        db.close()

    def test_first_sync_importing_twenty_weeks_sends_nothing(self):
        # Historical weeks are closed without a Telegram notification allowance on first sync/import.
        from app.models import LeagueWeek
        users = [self.create_user(username=f"hist{i}", division_current=2) for i in range(5)]
        current_monday = date.today() - timedelta(days=date.today().weekday())
        weeks = [current_monday - timedelta(days=7 * i) for i in range(20, 0, -1)]
        db = self.Session()
        for week_start in weeks:
            for user_id in users:
                db.add(WeeklySummary(
                    user_id=user_id,
                    week_start=datetime.combine(week_start, datetime.min.time()),
                    finalized=True,
                    total_xp=10,
                    training_days=1,
                    actual_load=10,
                    league_score=10,
                ))
        db.commit()
        with patch("app.services.telegram_week.get_settings", return_value=self.settings), \
             patch("app.services.telegram_week.send_message", new_callable=AsyncMock) as send:
            for week_start in weeks:
                _close_league_week(db, week_start, allow_week_notifications=False)
            self.assertEqual(send.await_count, 0)
        self.assertEqual(db.query(LeagueWeek).count(), 20)
        db.close()


if __name__ == "__main__":
    unittest.main()
