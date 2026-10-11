"""Regression tests for email-code validation and one-time-code lifecycle."""
import os
import unittest
from datetime import datetime, timedelta

from cryptography.fernet import Fernet

os.environ["DATABASE_URL"] = "sqlite:////tmp/efl-email-auth-tests.db"
os.environ["JWT_SECRET"] = "unit-test-jwt-secret-value-longer-than-32-characters"
os.environ["ENCRYPTION_KEY"] = Fernet.generate_key().decode("ascii")
os.environ["REDIS_URL"] = ""

from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import EmailCode
from app.routers.auth import (
    RegisterIn,
    RegistrationVerifyIn,
    PasswordResetConfirmIn,
)
from app.services.email_auth import code_digest, verify_email_code


class EmailInputValidationTests(unittest.TestCase):
    def test_registration_email_is_trimmed_and_lowercased(self):
        data = RegisterIn(
            username="test_user",
            email=" Test@Example.COM ",
            password="secure-password",
            display_name="Test User",
            privacy_consent=True,
        )
        self.assertEqual(str(data.email), "test@example.com")

    def test_invalid_registration_email_is_rejected(self):
        with self.assertRaises(ValidationError):
            RegisterIn(
                username="test_user",
                email="not-an-email",
                password="secure-password",
                display_name="Test User",
                privacy_consent=True,
            )

    def test_confirmation_code_must_be_six_digits(self):
        with self.assertRaises(ValidationError):
            RegistrationVerifyIn(email="test@example.com", code="12345")
        with self.assertRaises(ValidationError):
            PasswordResetConfirmIn(
                email="test@example.com",
                code="12ab56",
                new_password="new-password",
            )


class EmailCodeLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        EmailCode.__table__.create(self.engine)
        self.session = sessionmaker(bind=self.engine)()
        self.email = "test@example.com"
        self.purpose = "registration"
        self.code = "001234"
        self.session.add(
            EmailCode(
                user_id=1,
                email=self.email,
                purpose=self.purpose,
                code_hash=code_digest(self.email, self.purpose, self.code),
                expires_at=datetime.utcnow() + timedelta(minutes=10),
                attempts=0,
                created_at=datetime.utcnow(),
            )
        )
        self.session.commit()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_digest_is_keyed_and_normalizes_email(self):
        expected = code_digest("TEST@EXAMPLE.COM", self.purpose, self.code)
        self.assertEqual(expected, code_digest(self.email, self.purpose, self.code))
        self.assertNotEqual(expected, self.code)

    def test_valid_code_is_consumed_once(self):
        self.assertTrue(verify_email_code(self.session, self.email, self.purpose, self.code))
        self.assertFalse(verify_email_code(self.session, self.email, self.purpose, self.code))
        self.assertEqual(self.session.query(EmailCode).count(), 0)

    def test_five_wrong_attempts_exhaust_code(self):
        for _ in range(5):
            self.assertFalse(verify_email_code(self.session, self.email, self.purpose, "999999"))
        self.assertFalse(verify_email_code(self.session, self.email, self.purpose, self.code))
        row = self.session.query(EmailCode).one()
        self.assertEqual(row.attempts, 5)

    def test_expired_code_is_rejected(self):
        row = self.session.query(EmailCode).one()
        row.expires_at = datetime.utcnow() - timedelta(seconds=1)
        self.session.commit()
        self.assertFalse(verify_email_code(self.session, self.email, self.purpose, self.code))


if __name__ == "__main__":
    unittest.main()
