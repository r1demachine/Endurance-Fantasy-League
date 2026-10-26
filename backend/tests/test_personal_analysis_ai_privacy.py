"""Consent and BYOK privacy/security contracts for the personal AI endpoint."""
import os
import socket
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cryptography.fernet import Fernet
import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/efl-personal-analysis-ai-privacy.db")
os.environ.setdefault("JWT_SECRET", "unit-test-jwt-secret-value-longer-than-32-characters")
os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
os.environ.setdefault("REDIS_URL", "")

from app.auth import decrypt_secret, encrypt_secret
from app.database import Base, get_db
from app.dependencies import get_current_user
from app.models import User
from app.rate_limit import limiter
from app.routers import personal_analysis
from app.services.personal_interpretation import (
    PersonalInterpretationError,
    _PinnedNetworkBackend,
    _model_input,
    _resolve_public_endpoint,
    _safe_provider_post_json,
    generate_custom_personal_interpretation,
)

TEST_ENGINE = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = sessionmaker(autocommit=False, autoflush=False, bind=TEST_ENGINE)


def preview_trends():
    return {
        "user_id": 713,
        "username": "private-athlete",
        "email": "athlete@example.test",
        "display_name": "Private Athlete",
        "period": {"start": "2026-10-01", "end": "2026-10-20", "days": 20},
        "comparison_windows": {
            "current": {"start": "2026-10-14", "end": "2026-10-20", "days": 7},
            "previous": {"start": "2026-10-07", "end": "2026-10-13", "days": 7},
        },
        "observations": [
            {
                "id": 9001,
                "key": "wellbeing",
                "label": "Private Athlete — wellbeing",
                "name": "Secret workout title",
                "notes": "secret activity notes",
                "api_key": "sk-preview-secret",
                "status": "ready",
                "trend": "stable",
                "current": {"mean": 4.0, "days_with_data": 5, "samples": 5, "dates": ["2026-10-19"]},
                "previous": {"mean": 3.8, "days_with_data": 4, "samples": 4},
                "change": 0.2,
            },
            {
                "key": "unknown_private_field",
                "status": "ready",
                "current": {"mean": 999, "days_with_data": 1, "samples": 1},
                "previous": {"mean": 0, "days_with_data": 1, "samples": 1},
                "change": 999,
            },
        ],
        "training_load_relationship": {
            "key": "daily_tss_vs_rpe",
            "status": "insufficient_data",
            "period": {"start": "2026-10-01", "end": "2026-10-20"},
            "notes": "private relationship notes",
            "paired_days": 4,
            "days_excluded_due_to_missing_tss": 1,
            "days_excluded_due_to_estimated_tss": 2,
            "median_daily_tss": 90,
            "lower_or_equal_load": {"days": 2, "mean_daily_rpe": 4.5},
            "above_median_load": {"days": 2, "mean_daily_rpe": 5.0},
            "rpe_difference_high_minus_low": None,
        },
        "coverage": {
            "morning_checkins": {
                "period_days": 20,
                "completed_days": 12,
                "skipped_days": 1,
                "pending_days": 1,
                "days_without_completed_checkin": 8,
                "no_record_days": 6,
                "skipped_dates": ["2026-10-08"],
                "no_record_dates": ["2026-10-09"],
            },
            "sleep": {
                "source": "Intervals.icu Wellness",
                "quality_field_used": "sleep_score",
                "days_with_wellness_record": 9,
                "days_with_quality_value": 8,
                "days_with_duration_value": 9,
                "private_daily_dates": ["2026-10-19"],
            },
            "activities": {
                "activities_in_period": 5,
                "activities_with_measured_tss": 3,
                "activities_with_estimated_tss": 1,
                "activities_without_tss": 1,
                "activities_with_rpe": 3,
                "activities_without_rpe": 2,
                "activities_with_load_expectation": 2,
                "activities_without_load_expectation": 3,
                "days_with_activities": 4,
                "activity_names": ["Secret workout title"],
            },
        },
        "data_gaps": ["contains private activity title and should be regenerated from counts"],
        "methodology": ["internal implementation details"],
        "disclaimer": "private custom disclaimer should not override fixed disclosure",
    }


class PersonalAnalysisAIPrivacyAPITests(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(bind=TEST_ENGINE)
        Base.metadata.create_all(bind=TEST_ENGINE)
        limiter._storage.reset()
        with TestSession() as db:
            self.user = User(
                username="ai-privacy-owner",
                password_hash="test-hash",
                display_name="Private Test User",
                timezone_name="UTC",
                ai_analysis_consent=False,
                ai_provider="server",
            )
            db.add(self.user)
            db.commit()
            self.user_id = self.user.id

        self.current = SimpleNamespace(id=self.user_id, timezone_name="UTC")
        self.app = FastAPI()
        self.app.state.limiter = limiter
        self.app.include_router(personal_analysis.router)

        def override_db():
            db = TestSession()
            try:
                yield db
            finally:
                db.close()

        self.app.dependency_overrides[get_db] = override_db
        self.app.dependency_overrides[get_current_user] = lambda: self.current
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()
        self.app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=TEST_ENGINE)
        limiter._storage.reset()

    def read_user(self):
        with TestSession() as db:
            user = db.query(User).filter(User.id == self.user_id).one()
            db.expunge(user)
            return user

    def test_interpretation_without_consent_is_403_and_never_calls_any_http_client(self):
        with (
            patch("app.services.personal_interpretation.httpx.post") as groq_post,
            patch("app.services.personal_interpretation.httpx.Client") as user_provider_client,
            patch("app.routers.personal_analysis.get_personal_trends") as get_trends,
        ):
            response = self.client.post("/api/personal-analysis/interpretation")
        self.assertEqual(response.status_code, 403)
        self.assertIn("соглас", response.json()["detail"].lower())
        groq_post.assert_not_called()
        user_provider_client.assert_not_called()
        get_trends.assert_not_called()

    def test_consent_can_be_enabled_and_revocation_erases_provider_key(self):
        response = self.client.put("/api/personal-analysis/consent", json={"enabled": True})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["enabled"])
        self.assertTrue(response.json()["consent_at"])

        secret = "sk-test-private-key-4567"
        saved = self.client.put(
            "/api/personal-analysis/provider",
            json={
                "provider": "openai_compatible",
                "base_url": "https://api.example.com/v1",
                "model": "test-model",
                "api_key": secret,
            },
        )
        self.assertEqual(saved.status_code, 200)
        self.assertTrue(saved.json()["has_key"])
        self.assertEqual(saved.json()["key_last4"], "4567")
        self.assertNotIn(secret, saved.text)
        self.assertNotIn("encrypted", saved.json())
        stored = self.read_user()
        self.assertNotEqual(stored.ai_api_key_encrypted, secret)
        self.assertEqual(decrypt_secret(stored.ai_api_key_encrypted), secret)

        withdrawn = self.client.put("/api/personal-analysis/consent", json={"enabled": False})
        self.assertEqual(withdrawn.status_code, 200)
        self.assertFalse(withdrawn.json()["enabled"])
        stored = self.read_user()
        self.assertFalse(stored.ai_analysis_consent)
        self.assertIsNone(stored.ai_analysis_consent_at)
        self.assertIsNone(stored.ai_api_key_encrypted)
        self.assertEqual(stored.ai_provider, "server")
        self.assertIsNone(stored.ai_base_url)
        self.assertIsNone(stored.ai_model)

    def test_provider_get_never_returns_api_key_only_presence_and_last_four(self):
        secret = "sk-never-return-me-4821"
        with TestSession() as db:
            user = db.query(User).filter(User.id == self.user_id).one()
            user.ai_provider = "openai_compatible"
            user.ai_base_url = "https://api.example.com/v1"
            user.ai_model = "test-model"
            user.ai_api_key_encrypted = encrypt_secret(secret)
            db.commit()
        response = self.client.get("/api/personal-analysis/provider")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["has_key"])
        self.assertEqual(response.json()["key_last4"], "4821")
        self.assertNotIn(secret, response.text)
        self.assertNotIn("api_key", response.json())
        self.assertNotIn("ai_api_key_encrypted", response.json())

    def test_payload_preview_is_exact_model_input_and_contains_no_identity_dates_or_item_text(self):
        trends = preview_trends()
        with patch("app.routers.personal_analysis.get_personal_trends", return_value=trends):
            response = self.client.get("/api/personal-analysis/payload-preview?days=20")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), _model_input(trends))
        serialized = response.text
        for private_value in (
            "private-athlete",
            "athlete@example.test",
            "Private Athlete",
            "Secret workout title",
            "secret activity notes",
            "sk-preview-secret",
            "2026-10-01",
            "2026-10-20",
            "2026-10-19",
            "private_daily_dates",
            "activity_names",
            "unknown_private_field",
        ):
            self.assertNotIn(private_value, serialized)
        self.assertIn('"days": 20', serialized)
        self.assertIn('"mean": 4.0', serialized)
        self.assertIn('"activities_in_period": 5', serialized)

    def test_provider_failures_never_return_or_log_the_users_key(self):
        secret = "sk-never-log-this-key-9282"
        with TestSession() as db:
            user = db.query(User).filter(User.id == self.user_id).one()
            user.ai_analysis_consent = True
            user.ai_provider = "openai_compatible"
            user.ai_base_url = "https://api.example.com/v1"
            user.ai_model = "test-model"
            user.ai_api_key_encrypted = encrypt_secret(secret)
            db.commit()

        trends = preview_trends()
        trends["status"] = "ready"
        with (
            patch("app.routers.personal_analysis.get_personal_trends", return_value=trends),
            patch(
                "app.routers.personal_analysis.generate_custom_personal_interpretation",
                side_effect=PersonalInterpretationError(
                    "provider exception includes " + secret,
                    category="connection_error",
                ),
            ),
            self.assertLogs("app.routers.personal_analysis", level="WARNING") as captured,
        ):
            response = self.client.post("/api/personal-analysis/interpretation")
        self.assertEqual(response.status_code, 502)
        self.assertNotIn(secret, response.text)
        self.assertNotIn(secret, "\n".join(captured.output))


class SSRFPreventionTests(unittest.TestCase):
    def test_local_and_non_https_urls_are_rejected_before_http_request(self):
        urls = (
            "https://localhost/v1",
            "https://127.0.0.1/v1",
            "https://10.10.0.7/v1",
            "https://169.254.169.254/latest",
            "https://[::ffff:127.0.0.1]/v1",
            "http://api.example.com/v1",
            "https://user:pass@api.example.com/v1",
            "https://api.example.com:8443/v1",
        )
        for url in urls:
            with self.subTest(url=url), patch("app.services.personal_interpretation.httpx.Client") as client:
                with self.assertRaises(PersonalInterpretationError):
                    generate_custom_personal_interpretation(
                        preview_trends(),
                        provider="openai_compatible",
                        api_key="test-api-key",
                        model="test-model",
                        base_url=url,
                    )
                client.assert_not_called()

    @patch("app.services.personal_interpretation.socket.getaddrinfo")
    @patch("app.services.personal_interpretation.httpx.Client")
    def test_domain_resolving_to_private_ip_is_rejected_without_http_request(self, client, getaddrinfo):
        getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("10.12.0.8", 443)),
        ]
        with self.assertRaises(PersonalInterpretationError) as raised:
            generate_custom_personal_interpretation(
                preview_trends(),
                provider="openai_compatible",
                api_key="test-api-key",
                model="test-model",
                base_url="https://provider.example/v1",
            )
        self.assertEqual(raised.exception.category, "ssrf_blocked")
        client.assert_not_called()

    @patch("app.services.personal_interpretation.socket.create_connection")
    @patch("app.services.personal_interpretation.SyncStream")
    def test_connection_uses_only_the_pinned_numeric_ip(self, sync_stream, create_connection):
        create_connection.return_value = Mock()
        sync_stream.return_value = "stream"
        backend = _PinnedNetworkBackend("provider.example", ("8.8.8.8",))
        result = backend.connect_tcp("provider.example", 443, timeout=2, local_address=None)
        self.assertEqual(result, "stream")
        create_connection.assert_called_once_with(("8.8.8.8", 443), timeout=2, source_address=None)
        with self.assertRaises(Exception):
            backend.connect_tcp("other.example", 443, timeout=2, local_address=None)
        self.assertEqual(create_connection.call_count, 1)

    @patch("app.services.personal_interpretation.httpx.Client")
    def test_internal_redirect_is_rejected_and_redirect_following_is_disabled(self, client_factory):
        response = Mock()
        response.status_code = 302
        response.headers = {"Location": "http://127.0.0.1/admin"}
        response_context = Mock()
        response_context.__enter__ = Mock(return_value=response)
        response_context.__exit__ = Mock(return_value=False)
        client = Mock()
        client.__enter__ = Mock(return_value=client)
        client.__exit__ = Mock(return_value=False)
        client.stream.return_value = response_context
        client_factory.return_value = client

        with self.assertRaises(PersonalInterpretationError) as raised:
            _safe_provider_post_json(
                "https://provider.example/v1/chat/completions",
                host="provider.example",
                addresses=("8.8.8.8",),
                headers={"Authorization": "Bearer private-key"},
                payload={"messages": []},
                timeout_seconds=10,
            )
        self.assertEqual(raised.exception.category, "redirect_blocked")
        self.assertFalse(client_factory.call_args.kwargs["follow_redirects"])
        client.stream.assert_called_once()
        self.assertNotIn("127.0.0.1", str(client.stream.call_args))

    @patch("app.services.personal_interpretation.httpx.Client")
    def test_non_json_content_type_is_rejected(self, client_factory):
        response = Mock()
        response.status_code = 200
        response.headers = {"Content-Type": "text/html"}
        response_context = Mock()
        response_context.__enter__ = Mock(return_value=response)
        response_context.__exit__ = Mock(return_value=False)
        client = Mock()
        client.__enter__ = Mock(return_value=client)
        client.__exit__ = Mock(return_value=False)
        client.stream.return_value = response_context
        client_factory.return_value = client
        with self.assertRaises(PersonalInterpretationError) as raised:
            _safe_provider_post_json(
                "https://provider.example/v1/chat/completions",
                host="provider.example",
                addresses=("8.8.8.8",),
                headers={"Content-Type": "application/json"},
                payload={},
                timeout_seconds=10,
            )
        self.assertEqual(raised.exception.category, "invalid_content_type")


if __name__ == "__main__":
    unittest.main()
