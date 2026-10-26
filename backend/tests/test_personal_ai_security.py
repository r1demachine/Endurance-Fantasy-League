"""Consent, provider-key privacy and SSRF regression tests for personal AI."""
import os
import unittest
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/efl-personal-ai-security.db")
os.environ.setdefault("JWT_SECRET", "unit-test-jwt-secret-value-longer-than-32-characters")
os.environ.setdefault("ENCRYPTION_KEY", "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=")
os.environ.setdefault("REDIS_URL", "")

import httpcore
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import decrypt_secret
from app.database import Base, get_db
from app.dependencies import get_current_user
from app.models import MorningCheckIn, User
from app.routers import personal_analysis
from app.rate_limit import limiter
from app.services.personal_ai_provider import (
    _PinnedNetworkBackend,
    _request_json,
    resolve_public_addresses,
    validate_provider_base_url,
)
from app.services.personal_interpretation import PersonalInterpretationError, _model_input

TEST_ENGINE = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestSession = sessionmaker(autocommit=False, autoflush=False, bind=TEST_ENGINE)


def sample_trends():
    return {
        "user_id": 712,
        "username": "private-username",
        "email": "private@example.invalid",
        "display_name": "Private Display Name",
        "api_key": "secret-api-key-value",
        "period": {"start": "2026-10-01", "end": "2026-10-14", "days": 14},
        "comparison_windows": {
            "current": {"start": "2026-10-08", "end": "2026-10-14", "days": 7},
            "previous": {"start": "2026-10-01", "end": "2026-10-07", "days": 7},
        },
        "observations": [{
            "key": "sleep_quality", "label": "Качество сна", "source": "Wellness",
            "unit": "балл", "status": "ready", "trend": "stable",
            "current": {"mean": 80, "days_with_data": 6, "samples": 6, "private_date": "2026-10-10"},
            "previous": {"mean": 78, "days_with_data": 5, "samples": 5},
            "change": 2, "minimum_days_required_per_period": 3,
            "activity_name": "Секретная тренировка", "notes": "секретная заметка",
        }],
        "training_load_relationship": {"status": "insufficient_data", "reason": "no pairs", "activity_id": 999},
        "coverage": {
            "morning_checkins": {"period_days": 14, "completed_days": 7, "private_name": "secret"},
            "sleep": {"days_with_wellness_record": 7, "days_with_quality_value": 6, "days_with_duration_value": 7},
            "activities": {"activities_in_period": 4, "activities_with_measured_tss": 3, "activity_names": ["secret ride"]},
        },
        "data_gaps": ["Нет записи за 2026-10-10."],
        "methodology": ["Средние считаются по доступным значениям."],
        "disclaimer": "Описательная аналитика, не медицинская оценка.",
    }


class TestPersonalAIConsent(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(bind=TEST_ENGINE)
        Base.metadata.create_all(bind=TEST_ENGINE)
        self.db = TestSession()
        self.user = User(
            username="ai-consent-test", password_hash="test-hash", display_name="AI Consent",
            timezone_name="UTC", ai_analysis_consent=False, ai_provider="server",
        )
        self.db.add(self.user)
        self.db.commit()
        self.user_id = self.user.id
        self.db.close()
        self.app = FastAPI()
        self.app.state.limiter = limiter
        self.app.include_router(personal_analysis.router)

        def override_db():
            db = TestSession()
            try:
                yield db
            finally:
                db.close()

        def override_user(db=__import__("fastapi").Depends(get_db)):
            return db.query(User).filter(User.id == self.user_id).one()

        self.app.dependency_overrides[get_db] = override_db
        self.app.dependency_overrides[get_current_user] = override_user
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()
        self.app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=TEST_ENGINE)
        limiter._storage.reset()

    @patch("app.routers.personal_analysis.generate_personal_interpretation")
    @patch("app.routers.personal_analysis.generate_custom_interpretation")
    @patch("httpx.post")
    def test_interpretation_without_consent_is_403_and_never_calls_http(self, http_post, custom, server):
        response = self.client.post("/api/personal-analysis/interpretation")
        assert response.status_code == 403
        assert "соглас" in response.json()["detail"].lower() or "разреш" in response.json()["detail"].lower()
        http_post.assert_not_called()
        custom.assert_not_called()
        server.assert_not_called()

    @patch("app.routers.personal_analysis.local_today", return_value=date(2026, 10, 26))
    def test_payload_preview_is_aggregate_and_contains_no_identifiers_dates_or_activity_details(self, _today):
        response = self.client.get("/api/personal-analysis/payload-preview?days=14")
        assert response.status_code == 200
        body = response.json()
        assert body["period"] == {"days": 14}
        assert "start" not in body["period"] and "end" not in body["period"]
        assert "user_id" not in str(body)
        assert "username" not in str(body)
        assert "private-username" not in str(body)
        assert "private@example.invalid" not in str(body)
        assert "Private Display Name" not in str(body)
        assert "secret-api-key-value" not in str(body)
        assert "Секретная тренировка" not in str(body)
        assert "секретная заметка" not in str(body)
        assert "2026-10-10" not in str(body)
        assert "observations" in body

    def test_provider_key_is_encrypted_and_never_returned(self):
        key = "sk-user-private-key-1234"
        response = self.client.put("/api/personal-analysis/provider", json={
            "provider": "openai_compatible",
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-test-model",
            "api_key": key,
        })
        assert response.status_code == 200
        body = response.json()
        assert body["has_key"] is True
        assert body["key_last4"] == "1234"
        assert key not in response.text
        assert "ai_api_key_encrypted" not in response.text
        with TestSession() as db:
            user = db.query(User).filter(User.id == self.user_id).one()
            assert user.ai_api_key_encrypted != key
            assert decrypt_secret(user.ai_api_key_encrypted) == key

    @patch("app.routers.personal_analysis.test_custom_provider")
    def test_provider_error_does_not_leak_api_key_in_response_or_logs(self, test_provider):
        key = "sk-super-secret-credential"
        self.client.put("/api/personal-analysis/provider", json={
            "provider": "openai_compatible", "base_url": "https://api.openai.com/v1",
            "model": "gpt-test", "api_key": key,
        })
        test_provider.side_effect = PersonalInterpretationError(
            "provider failure included " + key, category="connection_error"
        )
        with self.assertLogs("app.routers.personal_analysis", level="WARNING") as captured:
            response = self.client.post("/api/personal-analysis/provider/test")
        assert response.status_code == 502
        assert key not in response.text
        assert all(key not in line for line in captured.output)
        assert "connection_error" in "\n".join(captured.output)

    def test_revoking_consent_deletes_key_and_provider_configuration(self):
        enabled = self.client.put("/api/personal-analysis/consent", json={"consent": True})
        assert enabled.status_code == 200 and enabled.json()["consent"] is True
        configured = self.client.put("/api/personal-analysis/provider", json={
            "provider": "openai_compatible", "base_url": "https://api.openai.com/v1",
            "model": "gpt-test", "api_key": "secret-revoke-key",
        })
        assert configured.status_code == 200
        revoked = self.client.put("/api/personal-analysis/consent", json={"consent": False})
        assert revoked.status_code == 200 and revoked.json()["consent"] is False
        with TestSession() as db:
            user = db.query(User).filter(User.id == self.user_id).one()
            assert user.ai_analysis_consent is False
            assert user.ai_analysis_consent_at is None
            assert user.ai_api_key_encrypted is None
            assert user.ai_provider == "server"
            assert user.ai_base_url is None
            assert user.ai_model is None



class TestPersonalAISSRF(unittest.TestCase):
    def test_model_input_whitelists_only_aggregate_fields(self):
        payload = _model_input(sample_trends())
        serialised = __import__("json").dumps(payload, ensure_ascii=False)
        for forbidden in (
            "user_id", "username", "email", "display_name", "private-username",
            "private@example.invalid", "Private Display Name", "secret-api-key-value",
            "activity_name", "activity_id", "activity_names", "notes", "Секретная тренировка",
            "секретная заметка", "2026-10-01", "2026-10-10",
        ):
            assert forbidden not in serialised
        assert payload["period"] == {"days": 14}
        assert payload["comparison_windows"] == {"current": {"days": 7}, "previous": {"days": 7}}
    
    
    def test_provider_url_validation_rejects_unsafe_schemes_hosts_and_ports(self):
        bad_urls = [
            "http://api.openai.com/v1",
            "https://localhost/v1",
            "https://service.localhost/v1",
            "https://127.0.0.1/v1",
            "https://10.1.2.3/v1",
            "https://169.254.169.254/latest/meta-data",
            "https://[::1]/v1",
            "https://[::ffff:127.0.0.1]/v1",
            "https://user:password@api.openai.com/v1",
            "https://api.openai.com:8443/v1",
        ]
        for url in bad_urls:
            try:
                validate_provider_base_url(url)
            except ValueError:
                pass
            else:
                raise AssertionError(f"unsafe URL accepted: {url}")
    
    
    @patch("app.services.personal_ai_provider.socket.getaddrinfo")
    def test_domain_resolving_to_private_ip_is_rejected_before_client_creation(self, getaddrinfo):
        getaddrinfo.return_value = [(None, None, None, None, ("10.0.0.5", 443))]
        with patch("app.services.personal_ai_provider.httpx.Client") as client:
            try:
                _request_json("https://metadata.example/v1/chat/completions", headers={}, payload={}, timeout_seconds=2)
            except Exception as exc:
                assert getattr(exc, "category", None) == "unsafe_destination"
            else:
                raise AssertionError("private DNS destination accepted")
            client.assert_not_called()
    
    
    @patch("app.services.personal_ai_provider.socket.create_connection")
    @patch("app.services.personal_ai_provider.resolve_public_addresses")
    def test_pinned_transport_rechecks_dns_at_connect_time(self, resolve, create_connection):
        resolve.return_value = ("127.0.0.1",)
        backend = _PinnedNetworkBackend("example.com", ("93.184.216.34",))
        try:
            backend.connect_tcp("example.com", 443, timeout=1)
        except httpcore.ConnectError:
            pass
        else:
            raise AssertionError("DNS rebinding was not rejected")
        create_connection.assert_not_called()
    
    
    def test_redirect_response_is_rejected_without_following_internal_location(self):
        response = Mock()
        response.status_code = 302
        response.headers = {"content-type": "application/json", "location": "http://127.0.0.1/admin"}
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        client = Mock()
        client.__enter__ = Mock(return_value=client)
        client.__exit__ = Mock(return_value=False)
        client.stream.return_value = response
        with patch("app.services.personal_ai_provider.resolve_public_addresses", return_value=("93.184.216.34",)):
            with patch("app.services.personal_ai_provider.httpx.Client", return_value=client) as client_factory:
                try:
                    _request_json("https://example.com/v1/chat/completions", headers={}, payload={}, timeout_seconds=2)
                except Exception as exc:
                    assert getattr(exc, "category", None) == "redirect_blocked"
                else:
                    raise AssertionError("redirect response was accepted")
        assert client_factory.call_args.kwargs["follow_redirects"] is False
        client.stream.assert_called_once()
    