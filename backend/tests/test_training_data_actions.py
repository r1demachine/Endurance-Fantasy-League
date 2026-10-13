"""Regression tests for separating Intervals unlink from source-specific deletion."""

import os
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from cryptography.fernet import Fernet

os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/efl-training-data-action-tests.db")
os.environ.setdefault("JWT_SECRET", "unit-test-jwt-secret-value-longer-than-32-characters")
os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
os.environ.setdefault("REDIS_URL", "")

from app.routers import sync
from app.routers.intervals_key import disconnect_key
from app.services.activity_dedupe import UPLOAD_SOURCES
from app.models import Activity, Wellness, XPEvent, WeeklySummary, LeagueMembership


def _unwrapped(function):
    while hasattr(function, "__wrapped__"):
        function = function.__wrapped__
    return function


class IntervalsUnlinkTests(unittest.TestCase):
    def test_unlink_only_clears_credentials_and_preserves_xp(self):
        user = SimpleNamespace(
            api_key_encrypted="encrypted-key",
            intervals_id="i12345",
            firstname="Athlete",
            lastname="Example",
            total_xp=1234.5,
            level=4,
            legacy_xp_offset=125.0,
            xp_migrated_at=datetime(2026, 1, 1),
        )
        db = MagicMock()

        response = disconnect_key(current=user, db=db)

        self.assertIsNone(user.api_key_encrypted)
        self.assertIsNone(user.intervals_id)
        self.assertIsNone(user.firstname)
        self.assertIsNone(user.lastname)
        self.assertEqual(user.total_xp, 1234.5)
        self.assertEqual(user.level, 4)
        self.assertEqual(user.legacy_xp_offset, 125.0)
        self.assertEqual(user.xp_migrated_at, datetime(2026, 1, 1))
        db.query.assert_not_called()
        self.assertTrue(response["data_preserved"])
        db.commit.assert_called_once_with()


class TrainingDataDeletionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.current = SimpleNamespace(
            id=71,
            total_xp=840.0,
            level=4,
            xp_migrated_at=datetime(2026, 1, 1),
            legacy_xp_offset=100.0,
        )
        self.db = MagicMock()
        self.queries = {}

        counts = {
            Activity: 3,
            Wellness: 4,
            XPEvent: 5,
            WeeklySummary: 6,
            LeagueMembership: 2,
        }

        def make_query(model):
            query = MagicMock()
            query.filter.return_value = query
            query.delete.return_value = counts.get(model, 0)
            self.queries[model] = query
            return query

        self.db.query.side_effect = make_query
        self.db.commit.return_value = None
        self.db.refresh.return_value = None

    async def _run(self, scope):
        payload = sync.TrainingDataDeleteIn(scope=scope)
        endpoint = _unwrapped(sync.delete_training_data_source)
        with (
            patch.object(sync, "get_settings", return_value=SimpleNamespace(XP_ENGINE="v6")),
            patch.object(sync, "_recalculate_user_xp_v6") as recalculate,
            patch.object(sync, "_recalculate_user_xp") as recalculate_legacy,
        ):
            response = await endpoint(MagicMock(), payload, self.current, self.db)
        return response, recalculate, recalculate_legacy

    async def test_intervals_scope_deletes_only_intervals_activities_and_wellness_then_recalculates(self):
        response, recalculate, recalculate_legacy = await self._run("intervals")

        activity_filters = self.queries[Activity].filter.call_args.args
        compiled_params = [
            value
            for expression in activity_filters
            for value in getattr(expression.compile(), "params", {}).values()
        ]
        self.assertIn("INTERVALS", compiled_params)
        self.assertEqual(response["deleted_activities"], 3)
        self.assertEqual(response["deleted_wellness"], 4)
        self.assertEqual(recalculate.call_count, 2)
        recalculate_legacy.assert_not_called()
        self.db.commit.assert_called_once_with()

    async def test_upload_scope_filters_to_site_and_telegram_uploads_and_keeps_wellness(self):
        response, recalculate, recalculate_legacy = await self._run("uploads")

        self.assertNotIn(Wellness, self.queries)
        filter_expressions = self.queries[Activity].filter.call_args.args
        self.assertTrue(any("source IN" in str(expression) for expression in filter_expressions))
        compiled_values = []
        for expression in filter_expressions:
            compiled_values.extend(getattr(expression.compile(), "params", {}).values())
        self.assertTrue(any(tuple(value) == UPLOAD_SOURCES for value in compiled_values if isinstance(value, (tuple, list))))
        self.assertEqual(response["deleted_activities"], 3)
        self.assertEqual(response["deleted_wellness"], 0)
        self.assertEqual(recalculate.call_count, 2)
        recalculate_legacy.assert_not_called()


if __name__ == "__main__":
    unittest.main()
