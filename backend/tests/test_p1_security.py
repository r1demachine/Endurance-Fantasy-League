"""Regression tests for authentication hashing, validation, and token versions.

Run from backend/: python -m unittest discover -s tests -v
"""
import hashlib
import os
import secrets
import unittest

from cryptography.fernet import Fernet

# These settings must be in place before importing app modules.
os.environ["DATABASE_URL"] = "sqlite:////tmp/efl-p1-auth-tests.db"
os.environ["JWT_SECRET"] = "unit-test-jwt-secret-value-longer-than-32-characters"
os.environ["ENCRYPTION_KEY"] = Fernet.generate_key().decode("ascii")
os.environ["REDIS_URL"] = ""

from app.auth import (
    LEGACY_PASSWORD_HASH_ITERATIONS,
    PASSWORD_HASH_ITERATIONS,
    create_access_token,
    decode_access_token_claims,
    hash_password,
    password_needs_rehash,
    verify_password,
)
from app.routers.auth import LoginIn, RegisterIn
from app.routers.intervals_key import KeyIn
from app.routers.sync import PauseIn
from pydantic import ValidationError


class PasswordHashTests(unittest.TestCase):
    def test_new_hash_verifies_and_does_not_need_rehash(self):
        password = "a-long-test-password"
        stored = hash_password(password)

        self.assertTrue(verify_password(password, stored))
        self.assertFalse(verify_password("wrong-password", stored))
        self.assertFalse(password_needs_rehash(stored))
        self.assertEqual(stored.split("$")[0], "pbkdf2_sha256")
        self.assertEqual(int(stored.split("$")[1]), PASSWORD_HASH_ITERATIONS)
        self.assertEqual(PASSWORD_HASH_ITERATIONS, 600_000)

    def test_legacy_hash_verifies_and_requests_upgrade(self):
        password = "existing-account-password"
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, LEGACY_PASSWORD_HASH_ITERATIONS
        )
        stored = salt.hex() + ":" + digest.hex()

        self.assertTrue(verify_password(password, stored))
        self.assertTrue(password_needs_rehash(stored))
        self.assertFalse(verify_password("wrong-password", stored))

    def test_malformed_hash_is_rejected(self):
        self.assertFalse(verify_password("password", "not-a-valid-hash"))
        self.assertTrue(password_needs_rehash("not-a-valid-hash"))


class TokenVersionTests(unittest.TestCase):
    def test_token_contains_session_version(self):
        token = create_access_token(123, token_version=7)
        self.assertEqual(decode_access_token_claims(token), (123, 7))

    def test_old_token_without_version_defaults_to_zero(self):
        token = create_access_token(123)
        self.assertEqual(decode_access_token_claims(token), (123, 0))


class InputValidationTests(unittest.TestCase):
    def test_username_is_normalized_before_pattern_validation(self):
        data = RegisterIn(
            username="  Bob_42  ",
            password="long-enough",
            display_name="Bob",
            privacy_consent=True,
        )
        self.assertEqual(data.username, "bob_42")

    def test_username_rejects_spaces_and_punctuation(self):
        with self.assertRaises(ValidationError):
            RegisterIn(
                username="bad-name",
                password="long-enough",
                display_name="Bob",
                privacy_consent=True,
            )

    def test_password_has_maximum_length(self):
        with self.assertRaises(ValidationError):
            RegisterIn(
                username="valid_user",
                password="x" * 129,
                display_name="User",
                privacy_consent=True,
            )

    def test_athlete_id_must_be_numeric_with_optional_i_prefix(self):
        self.assertEqual(KeyIn(api_key="valid-key", athlete_id="I12345").athlete_id, "i12345")
        with self.assertRaises(ValidationError):
            KeyIn(api_key="valid-key", athlete_id="123; DROP TABLE users")

    def test_pause_rejects_non_numeric_and_out_of_range_weeks(self):
        with self.assertRaises(ValidationError):
            PauseIn(weeks="not-a-number")
        with self.assertRaises(ValidationError):
            PauseIn(weeks=9)


if __name__ == "__main__":
    unittest.main()
