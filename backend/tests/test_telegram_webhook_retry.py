"""Regression tests for Telegram webhook retry and late weekly summaries."""
import ast
import os
from datetime import timedelta
from pathlib import Path
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from cryptography.fernet import Fernet

os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/efl-telegram-retry-tests.db")
os.environ.setdefault("JWT_SECRET", "unit-test-jwt-secret-value-longer-than-32-characters")
os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
os.environ.setdefault("REDIS_URL", "")

from app.routers.telegram import (
    TelegramWebhookUpdate,
    _advance_week_marker_on_link,
    _unmark_update_processed,
)
from app.services.telegram_week import latest_completed_week_start, notify_week_results


class TelegramWebhookRetryTests(unittest.TestCase):
    def test_failed_webhook_claim_can_be_released(self):
        db = MagicMock()
        _unmark_update_processed(db, 123456)
        db.query.assert_called_once_with(TelegramWebhookUpdate)
        db.query.return_value.filter.assert_called_once()
        db.query.return_value.filter.return_value.delete.assert_called_once_with(
            synchronize_session=False
        )
        db.commit.assert_called_once()

    def test_webhook_failure_path_unmarks_update_for_retry(self):
        path = Path(__file__).resolve().parents[1] / "app" / "routers" / "telegram.py"
        module = ast.parse(path.read_text(encoding="utf-8"))
        endpoint = next(
            node for node in module.body
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "telegram_webhook"
        )
        source = ast.get_source_segment(path.read_text(encoding="utf-8"), endpoint)
        self.assertIn("run_in_threadpool(_mark_update_processed", source)
        self.assertIn("run_in_threadpool(_unmark_update_processed", source)
        self.assertIn("except Exception:", source)
        self.assertIn("raise", source)

    def test_webhook_db_and_xp_work_is_offloaded(self):
        path = Path(__file__).resolve().parents[1] / "app" / "routers" / "telegram.py"
        source = path.read_text(encoding="utf-8")
        self.assertIn("await run_in_threadpool(_failed_link_attempts", source)
        self.assertIn("await run_in_threadpool(_record_failed_link_attempt", source)
        self.assertIn("await run_in_threadpool(\n        create_activity_from_upload", source)


class TelegramLinkMarkerTests(unittest.TestCase):
    def test_link_does_not_mark_an_unfinalized_week_as_delivered(self):
        from datetime import date

        last_completed = date(2026, 10, 5)
        user = SimpleNamespace(id=12, telegram_last_notified_week=last_completed)
        db = MagicMock()
        query = db.query.return_value
        query.filter.return_value = query
        query.first.return_value = SimpleNamespace(finalized=False)

        with patch("app.routers.telegram._latest_completed_week_start", return_value=last_completed):
            _advance_week_marker_on_link(db, user)

        self.assertEqual(user.telegram_last_notified_week, last_completed - timedelta(days=7))

    def test_link_skips_backfill_when_latest_week_is_already_finalized(self):
        from datetime import date

        last_completed = date(2026, 10, 5)
        user = SimpleNamespace(id=12, telegram_last_notified_week=None)
        db = MagicMock()
        query = db.query.return_value
        query.filter.return_value = query
        query.first.return_value = SimpleNamespace(finalized=True)

        with patch("app.routers.telegram._latest_completed_week_start", return_value=last_completed):
            _advance_week_marker_on_link(db, user)

        self.assertEqual(user.telegram_last_notified_week, last_completed)


class TelegramLateSummaryTests(unittest.TestCase):
    def test_past_completed_week_can_be_delivered_after_late_finalization(self):
        week_start = latest_completed_week_start() - timedelta(days=7)
        summary = SimpleNamespace(total_xp=125.5, training_days=3, league_score=42.25)
        user = SimpleNamespace(
            telegram_chat_id="12345",
            telegram_notify=True,
            telegram_last_notified_week=None,
        )
        db = MagicMock()
        query = db.query.return_value
        query.join.return_value = query
        query.filter.return_value = query
        query.all.return_value = [(summary, user)]
        send_message = AsyncMock(return_value=True)

        with patch("app.services.telegram_week.get_settings", return_value=SimpleNamespace(TELEGRAM_BOT_TOKEN="token")):
            with patch("app.services.telegram_week.send_message", send_message):
                delivered = notify_week_results(db, week_start)

        self.assertEqual(delivered, 1)
        self.assertEqual(user.telegram_last_notified_week, week_start)
        db.commit.assert_called_once()
        send_message.assert_awaited_once()
        self.assertIn(week_start.isoformat(), send_message.await_args.args[1])


if __name__ == "__main__":
    unittest.main()
