"""Удаление аккаунта: дуэли, клубы, заявка + пароль."""
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.routers.privacy import _cleanup_social_for_user, DeleteAccountInput, delete_account
from app.models import ClubMemberRole


class CleanupSocialTests(unittest.TestCase):
    def test_cleanup_deletes_duels_requests_and_transfers_club(self):
        db = MagicMock()
        uid = 10
        other_member = SimpleNamespace(user_id=20, role=ClubMemberRole.MEMBER.value, joined_at=datetime.utcnow())
        club = SimpleNamespace(id=1, owner_id=uid)

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

    def test_delete_account_requires_password(self):
        user = SimpleNamespace(id=1, password_hash="x", api_key_encrypted=None, intervals_id=None)
        data = DeleteAccountInput(confirmation="DELETE", password="wrong")
        db = MagicMock()
        with patch("app.routers.privacy.verify_password", return_value=False):
            from fastapi import HTTPException
            with self.assertRaises(HTTPException) as ctx:
                delete_account(data, user, db)
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
                result = delete_account(data, user, db)
                clean.assert_called_once()
                db.delete.assert_called_once_with(user)
                db.commit.assert_called_once()
                self.assertTrue(result["deleted"])


if __name__ == "__main__":
    unittest.main()
