"""Unit tests for club name/invite rules and duel pair normalization."""
import ast
import asyncio
import os
from pathlib import Path
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from cryptography.fernet import Fernet

os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/efl-club-duel-tests.db")
os.environ.setdefault("JWT_SECRET", "unit-test-jwt-secret-value-longer-than-32-characters")
os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
os.environ.setdefault("REDIS_URL", "")

from pydantic import ValidationError

from app.models import Club, Duel
from app.routers.clubs import _club_brief, _member_brief, request_join, ClubIdIn
from app.routers.clubs import (
    CreateClubIn,
    JoinCodeIn,
    UpdateClubIn,
    normalize_club_name,
    normalize_invite_code,
)
from app.routers.duels import ChallengeIn, _normalized_pair


class ClubValidationTests(unittest.TestCase):
    def test_name_whitespace_is_collapsed(self):
        self.assertEqual(normalize_club_name("   North    Shore   "), "North Shore")
        self.assertEqual(CreateClubIn(name="  Gravel   Crew ").name, "Gravel Crew")

    def test_name_length_is_between_two_and_forty_characters(self):
        with self.assertRaises(ValueError):
            normalize_club_name("x")
        with self.assertRaises(ValueError):
            normalize_club_name("x" * 41)
        self.assertEqual(len(normalize_club_name("x" * 40)), 40)

    def test_control_and_format_characters_are_rejected(self):
        for value in ("Team\nTwo", "Line\tBreak", "Bad\u200bName"):
            with self.subTest(value=repr(value)):
                with self.assertRaises(ValueError):
                    normalize_club_name(value)

    def test_update_schema_normalizes_names_and_accepts_join_setting(self):
        update = UpdateClubIn(name="  Sunday   Riders ", instant_join=True)
        self.assertEqual(update.name, "Sunday Riders")
        self.assertTrue(update.instant_join)
        with self.assertRaises(ValidationError):
            UpdateClubIn(name="")

    def test_invite_codes_are_fixed_length_base32(self):
        code = " ABCDEFGH2345 "
        self.assertEqual(normalize_invite_code(code), "ABCDEFGH2345")
        with self.assertRaises(ValueError):
            normalize_invite_code("ABC123")
        with self.assertRaises(ValueError):
            normalize_invite_code("ABCDEFGH0123")

    def test_join_endpoint_schema_retains_malformed_input_for_attempt_audit(self):
        # Shape checks run inside the handler so failed guesses are recorded.
        self.assertEqual(JoinCodeIn(code="  short  ").code, "SHORT")
        self.assertEqual(JoinCodeIn(code=" abcdefgh2345 ").code, "ABCDEFGH2345")


class ClubPrivacyTests(unittest.TestCase):
    @staticmethod
    def user(user_id, visibility="authenticated"):
        return type("TestUser", (), {
            "id": user_id,
            "username": f"user_{user_id}",
            "display_name": f"Athlete {user_id}",
            "level": 7,
            "profile_visibility": visibility,
        })()

    def test_friends_visibility_hides_profile_from_non_friends(self):
        me = self.user(1)
        athlete = self.user(2, "friends")
        row = _member_brief(athlete, "member", me, set())
        self.assertTrue(row["hidden"])
        self.assertEqual(row["display_name"], "Скрыто")
        self.assertIsNone(row["username"])
        self.assertIsNone(row["level"])

    def test_friends_visibility_allows_accepted_friend(self):
        me = self.user(1)
        athlete = self.user(2, "friends")
        row = _member_brief(athlete, "member", me, {2})
        self.assertFalse(row["hidden"])
        self.assertEqual(row["username"], "user_2")

    def test_private_visibility_hides_even_from_friend(self):
        me = self.user(1)
        athlete = self.user(2, "private")
        row = _member_brief(athlete, "member", me, {2})
        self.assertTrue(row["hidden"])
        self.assertEqual(row["display_name"], "Скрыто")

class ClubInvitePrivacyTests(unittest.TestCase):
    def test_invite_code_is_visible_only_to_owner(self):
        club = SimpleNamespace(
            id=11,
            name="North Shore",
            owner_id=7,
            invite_code="ABCDEFGH2345",
            instant_join=True,
            created_at=None,
        )
        db = MagicMock()
        with patch("app.routers.clubs._is_member", return_value=SimpleNamespace(role="member")):
            with patch("app.routers.clubs._member_count", return_value=2):
                owner_view = _club_brief(club, db, SimpleNamespace(id=7))
                member_view = _club_brief(club, db, SimpleNamespace(id=8))

        self.assertEqual(owner_view["invite_code"], "ABCDEFGH2345")
        self.assertIsNone(member_view["invite_code"])

    def test_instant_join_cannot_be_bypassed_by_public_club_id(self):
        async def run_test():
            db = MagicMock()
            request = MagicMock()
            current = SimpleNamespace(id=8, display_name="Runner")
            club = SimpleNamespace(
                id=11, owner_id=7, name="North Shore", instant_join=True
            )
            with patch("app.routers.clubs._lock_user"):
                with patch("app.routers.clubs._lock_club", return_value=club):
                    with patch("app.routers.clubs._is_member", return_value=None):
                        with patch("app.routers.clubs._ensure_membership_capacity"):
                            with patch("app.routers.clubs._member_count", return_value=2):
                                from fastapi import HTTPException
                                with self.assertRaises(HTTPException) as ctx:
                                    await request_join.__wrapped__(
                                        request, ClubIdIn(club_id=11), current, db
                                    )
            self.assertEqual(ctx.exception.status_code, 409)
            self.assertIn("код приглашения", ctx.exception.detail.lower())
            db.rollback.assert_called_once()

        asyncio.run(run_test())


class DuelRulesTests(unittest.TestCase):
    def test_username_normalization_strips_at_sign_before_pattern_check(self):
        challenge = ChallengeIn(username="  @Alice_Rider ")
        self.assertEqual(challenge.username, "alice_rider")

    def test_normalized_pair_is_order_independent(self):
        self.assertEqual(_normalized_pair(2, 9), (2, 9))
        self.assertEqual(_normalized_pair(9, 2), (2, 9))
        self.assertEqual(_normalized_pair(4, 4), (4, 4))

    def test_application_startup_module_has_valid_python_syntax_and_single_migration(self):
        main_path = Path(__file__).resolve().parents[1] / "app" / "main.py"
        source = main_path.read_text(encoding="utf-8")
        ast.parse(source, filename=str(main_path))
        self.assertEqual(source.count("settings = get_settings()"), 1)
        self.assertEqual(source.count('@app.get("/health")'), 1)
        self.assertEqual(source.count("CREATE TABLE IF NOT EXISTS club_join_attempts"), 1)

    def test_database_metadata_has_required_unique_indexes(self):
        club_index = next(i for i in Club.__table__.indexes if i.name == "uq_club_owner_name_lower")
        self.assertTrue(club_index.unique)
        self.assertIn("lower(name)", str(club_index.expressions[1]))

        duel_index = next(i for i in Duel.__table__.indexes if i.name == "uq_duel_pair_week_active")
        self.assertTrue(duel_index.unique)
        where = duel_index.dialect_options["postgresql"]["where"]
        self.assertIn("pending", str(where))
        self.assertIn("active", str(where))


if __name__ == "__main__":
    unittest.main()
