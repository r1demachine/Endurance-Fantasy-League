"""Account deletion cleans user-owned tables and enforces a rate limit."""
import ast
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.database import Base
from app.routers.privacy import (
    _USER_FK_TABLES_CLEANED_EXPLICITLY,
    _cleanup_remaining_user_fk_rows,
    _cleanup_social_for_user,
    DeleteAccountInput,
    delete_account,
)
from app.models import ClubMemberRole


class CleanupSocialTests(unittest.TestCase):
    def test_cleanup_deletes_duels_requests_and_transfers_club(self):
        db = MagicMock()
        uid = 10
        other_member = SimpleNamespace(user_id=20, role=ClubMemberRole.MEMBER.value, joined_at=datetime.utcnow())
        club = SimpleNamespace(id=1, owner_id=uid, name="North Shore")

        duel_q = MagicMock()
        db.query.return_value = duel_q
        duel_q.filter.return_value = duel_q
        duel_q.delete.return_value = 1
        duel_q.update.return_value = 1
        duel_q.count.return_value = 0
        duel_q.first.return_value = None
        duel_q.order_by.return_value = duel_q
        duel_q.all.side_effect = [
            [club],
            [other_member],
        ]

        _cleanup_social_for_user(db, uid)
        self.assertEqual(club.owner_id, 20)
        self.assertEqual(other_member.role, ClubMemberRole.OWNER.value)
        self.assertTrue(db.query.called)

    def test_cleanup_deletes_empty_owned_club(self):
        db = MagicMock()
        uid = 10
        club = SimpleNamespace(id=5, owner_id=uid)
        q = MagicMock()
        db.query.return_value = q
        q.filter.return_value = q
        q.delete.return_value = 0
        q.update.return_value = 0
        q.order_by.return_value = q
        q.all.side_effect = [[club], []]
        _cleanup_social_for_user(db, uid)
        db.delete.assert_called()

    def test_dynamic_cleanup_covers_every_users_fk_table(self):
        users_table_name = "users"
        all_user_fk_tables = {
            table.name
            for table in Base.metadata.tables.values()
            if any(
                fk.column.table.name == users_table_name and fk.column.name == "id"
                for column in table.columns
                for fk in column.foreign_keys
            )
        }
        self.assertIn("sync_progress", all_user_fk_tables)
        self.assertIn("heart_rate_settings_history", all_user_fk_tables)

        db = MagicMock()
        cleaned = _cleanup_remaining_user_fk_rows(db, 987)
        executed = {
            call.args[0].table.name
            for call in db.execute.call_args_list
        }

        # Domain-specific tables are cleaned by _cleanup_social_for_user and
        # the explicit delete statements in delete_account.
        self.assertEqual(cleaned, executed)
        self.assertEqual(
            all_user_fk_tables,
            _USER_FK_TABLES_CLEANED_EXPLICITLY | executed,
        )
        self.assertIn("sync_progress", executed)
        self.assertIn("heart_rate_settings_history", executed)

    def test_account_delete_endpoint_has_rate_limit(self):
        source_path = Path(__file__).resolve().parents[1] / "app" / "routers" / "privacy.py"
        module = ast.parse(source_path.read_text(encoding="utf-8"))
        endpoint = next(
            node for node in module.body
            if isinstance(node, ast.FunctionDef) and node.name == "delete_account"
        )
        rate_limits = [
            decorator.args[0].value
            for decorator in endpoint.decorator_list
            if isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and decorator.func.attr == "limit"
            and decorator.args
            and isinstance(decorator.args[0], ast.Constant)
        ]
        self.assertIn("5/hour", rate_limits)

    def test_delete_account_requires_password(self):
        user = SimpleNamespace(id=1, password_hash="x", api_key_encrypted=None, intervals_id=None)
        data = DeleteAccountInput(confirmation="DELETE", password="wrong")
        db = MagicMock()
        with patch("app.routers.privacy.verify_password", return_value=False):
            from fastapi import HTTPException
            with self.assertRaises(HTTPException) as ctx:
                delete_account.__wrapped__(MagicMock(), data, user, db)
            self.assertEqual(ctx.exception.status_code, 403)

    def test_delete_account_happy_path_commits(self):
        user = SimpleNamespace(id=7, password_hash="hash", api_key_encrypted="k", intervals_id="i")
        data = DeleteAccountInput(confirmation="DELETE", password="secret")
        db = MagicMock()
        q = MagicMock()
        db.query.return_value = q
        q.filter.return_value = q
        q.delete.return_value = 0
        q.update.return_value = 0
        q.order_by.return_value = q
        q.all.return_value = []
        with patch("app.routers.privacy.verify_password", return_value=True):
            with patch("app.routers.privacy._cleanup_social_for_user") as clean:
                result = delete_account.__wrapped__(MagicMock(), data, user, db)
                clean.assert_called_once()
                db.delete.assert_called_once_with(user)
                db.commit.assert_called_once()
                self.assertTrue(result["deleted"])


if __name__ == "__main__":
    unittest.main()
