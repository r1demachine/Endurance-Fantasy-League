"""Deterministic stage-6 scenario suite for personal analysis.

No real Groq requests are made here: provider responses and failures are mocked.
"""
import json
import os
import unittest
from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

from cryptography.fernet import Fernet
import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/efl-personal-analysis-stage6.db")
os.environ.setdefault("JWT_SECRET", "unit-test-jwt-secret-value-longer-than-32-characters")
os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
os.environ.setdefault("REDIS_URL", "")

from app.database import Base, get_db
from app.dependencies import get_current_user
from app.models import Activity, ActivityCheckIn, MorningCheckIn, User, Wellness
from app.routers import personal_analysis
from app.rate_limit import limiter
from app.services.personal_interpretation import (
    GROQ_CHAT_COMPLETIONS_URL,
    PersonalInterpretation,
    PersonalInterpretationError,
    generate_personal_interpretation,
)
from app.services.personal_trends import activity_local_date, build_personal_trends, local_today


TODAY = date(2026, 10, 20)
TEST_ENGINE = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = sessionmaker(autocommit=False, autoflush=False, bind=TEST_ENGINE)


def row(**values):
    return SimpleNamespace(**values)


def morning(user_id, day, *, status="completed", readiness=4, fatigue=2, soreness=1, wellbeing=4):
    return row(
        user_id=user_id,
        local_date=day,
        status=status,
        readiness=readiness,
        fatigue=fatigue,
        soreness=soreness,
        wellbeing=wellbeing,
    )


def wellness(user_id, day, *, sleep_score=80, sleep_secs=8 * 3600):
    return row(
        user_id=user_id,
        date=day.isoformat(),
        sleep_score=sleep_score,
        sleep_quality=None,
        sleep_secs=sleep_secs,
    )


def activity(user_id, activity_id, day, *, tss=40, estimated=False):
    return row(
        id=activity_id,
        user_id=user_id,
        tss=tss,
        tss_estimated=estimated,
        start_date_local=datetime.combine(day, time.min),
        start_date=datetime.combine(day, time.min),
    )


def activity_checkin(user_id, activity_id, *, rpe=5, expectation="as_expected"):
    return row(user_id=user_id, activity_id=activity_id, rpe=rpe, load_expectation=expectation)


def calculate(*, timezone_name="UTC", days=28, mornings=None, wellness_rows=None, activities=None, activity_checkins=None):
    return build_personal_trends(
        user_id=1,
        timezone_name=timezone_name,
        today=TODAY,
        days=days,
        morning_checkins=mornings or [],
        wellness_records=wellness_rows or [],
        activities=activities or [],
        activity_checkins=activity_checkins or [],
    )


def metric(result, key):
    return next(item for item in result["observations"] if item["key"] == key)


def stable_full_history():
    mornings, sleep, activities, checkins = [], [], [], []
    for offset in range(27, -1, -1):
        day = TODAY - timedelta(days=offset)
        mornings.append(morning(1, day, readiness=4, fatigue=2, soreness=1, wellbeing=4))
        sleep.append(wellness(1, day, sleep_score=80, sleep_secs=8 * 3600))
        session = activity(1, 1000 + offset, day, tss=20 + (offset % 9) * 5)
        activities.append(session)
        checkins.append(activity_checkin(1, session.id, rpe=5))
    return mornings, sleep, activities, checkins


def valid_analysis(**overrides):
    result = {
        "headline": "Динамика без резких изменений",
        "summary": "Средние субъективные оценки в сравниваемых окнах близки; выводы относятся только к сохранённым наблюдениям.",
        "positive_signals": ["Оба окна содержат завершённые субъективные оценки."],
        "caution_signals": ["Покрытие сна неполное, а часть данных отсутствует."],
        "practical_next_steps": ["Продолжай отмечать самочувствие, сон и RPE."],
        "data_limitations": ["Есть пропуски; полнота синхронизации отдельно не проверена."],
    }
    result.update(overrides)
    return result


def provider_response(content):
    response = Mock()
    response.json.return_value = {
        "choices": [{"message": {"content": content}}],
    }
    response.raise_for_status.return_value = None
    return response


class PersonalAnalysisScenarioTests(unittest.TestCase):
    def test_01_complete_history_with_stable_wellbeing(self):
        mornings, sleep, activities, checkins = stable_full_history()
        result = calculate(
            mornings=mornings,
            wellness_rows=sleep,
            activities=activities,
            activity_checkins=checkins,
        )
        self.assertEqual(result["status"], "ready")
        self.assertEqual(metric(result, "wellbeing")["trend"], "stable")
        self.assertEqual(metric(result, "sleep_quality")["trend"], "stable")
        self.assertEqual(result["coverage"]["morning_checkins"]["completed_days"], 28)
        self.assertEqual(result["coverage"]["sleep"]["days_with_quality_value"], 28)
        self.assertEqual(result["coverage"]["activities"]["activities_in_period"], 28)

    def test_02_sleep_deteriorates_while_training_load_is_maintained(self):
        mornings, sleep, activities, checkins = [], [], [], []
        for offset in range(27, -1, -1):
            day = TODAY - timedelta(days=offset)
            mornings.append(morning(1, day, wellbeing=4))
            recent_bad_sleep = offset < 4
            sleep.append(wellness(1, day, sleep_score=40 if recent_bad_sleep else 80))
            session = activity(1, 2000 + offset, day, tss=45 + (offset % 3))
            activities.append(session)
            checkins.append(activity_checkin(1, session.id, rpe=5))
        result = calculate(
            mornings=mornings,
            wellness_rows=sleep,
            activities=activities,
            activity_checkins=checkins,
        )
        self.assertEqual(metric(result, "sleep_quality")["trend"], "downward")
        self.assertEqual(metric(result, "wellbeing")["trend"], "stable")
        self.assertEqual(result["coverage"]["activities"]["activities_in_period"], 28)

    def test_03_sharp_wellbeing_drop_is_reported_as_a_downward_observation(self):
        mornings = []
        for offset in range(27, -1, -1):
            day = TODAY - timedelta(days=offset)
            mornings.append(morning(1, day, wellbeing=2 if offset < 7 else 5))
        result = calculate(mornings=mornings)
        wellbeing_metric = metric(result, "wellbeing")
        self.assertEqual(wellbeing_metric["status"], "ready")
        self.assertEqual(wellbeing_metric["trend"], "downward")
        self.assertEqual(wellbeing_metric["change"], -3.0)

    def test_04_missing_morning_checkins_are_not_filled_with_zero(self):
        mornings = []
        for offset in range(13, 6, -1):
            mornings.append(morning(1, TODAY - timedelta(days=offset), wellbeing=4))
        mornings.extend([
            morning(1, TODAY - timedelta(days=6), wellbeing=4),
            morning(1, TODAY - timedelta(days=4), status="skipped", wellbeing=None),
            morning(1, TODAY - timedelta(days=3), status="pending", wellbeing=None),
            morning(1, TODAY, wellbeing=3),
        ])
        result = calculate(mornings=mornings)
        item = metric(result, "wellbeing")
        self.assertEqual(item["status"], "insufficient_data")
        self.assertEqual(item["trend"], "insufficient_data")
        self.assertEqual(item["current"]["days_with_data"], 2)
        self.assertEqual(item["current"]["mean"], 3.5)
        self.assertEqual(result["coverage"]["morning_checkins"]["skipped_days"], 1)
        self.assertEqual(result["coverage"]["morning_checkins"]["pending_days"], 1)
        self.assertTrue(result["data_gaps"])

    def test_05_missing_post_workout_checkins_reduce_rpe_coverage(self):
        activities = [
            activity(1, 3000 + offset, TODAY - timedelta(days=offset), tss=35)
            for offset in range(6)
        ]
        result = calculate(activities=activities, activity_checkins=[])
        self.assertEqual(metric(result, "rpe")["status"], "insufficient_data")
        self.assertEqual(result["coverage"]["activities"]["activities_without_rpe"], 6)
        self.assertTrue(any("RPE" in gap for gap in result["data_gaps"]))

    def test_06_short_history_does_not_claim_a_personal_baseline(self):
        mornings = [
            morning(1, TODAY - timedelta(days=1), wellbeing=4),
            morning(1, TODAY, wellbeing=4),
        ]
        result = calculate(mornings=mornings)
        self.assertEqual(result["status"], "insufficient_data")
        self.assertEqual(metric(result, "wellbeing")["trend"], "insufficient_data")
        self.assertIsNone(metric(result, "wellbeing")["change"])

    def test_07_conflicting_sleep_and_subjective_state_remain_separate(self):
        mornings, sleep = [], []
        for offset in range(13, -1, -1):
            day = TODAY - timedelta(days=offset)
            recent = offset < 7
            mornings.append(morning(1, day, wellbeing=5 if recent else 3))
            sleep.append(wellness(1, day, sleep_score=40 if recent else 80))
        result = calculate(mornings=mornings, wellness_rows=sleep)
        self.assertEqual(metric(result, "wellbeing")["trend"], "upward")
        self.assertEqual(metric(result, "sleep_quality")["trend"], "downward")
        self.assertNotIn("combined_score", result)

    def test_08_return_after_several_empty_days_preserves_gaps_and_uses_only_real_values(self):
        mornings = []
        for offset in range(13, 6, -1):
            mornings.append(morning(1, TODAY - timedelta(days=offset), wellbeing=4))
        mornings.extend([
            morning(1, TODAY - timedelta(days=6), wellbeing=4),
            morning(1, TODAY - timedelta(days=5), wellbeing=4),
            morning(1, TODAY - timedelta(days=4), wellbeing=4),
            morning(1, TODAY, wellbeing=5),
        ])
        result = calculate(mornings=mornings)
        item = metric(result, "wellbeing")
        self.assertEqual(item["current"]["days_with_data"], 4)
        self.assertEqual(item["current"]["mean"], 4.25)
        self.assertEqual(result["coverage"]["morning_checkins"]["no_record_days"], 17)
        self.assertTrue(any("Нет записи" in gap for gap in result["data_gaps"]))

    def test_09_multiple_sessions_same_day_are_aggregated_by_local_day(self):
        activities, checkins = [], []
        first_day = TODAY - timedelta(days=24)
        for index in range(8):
            day = first_day + timedelta(days=index)
            tss = 20 if index < 4 else 60
            session = activity(1, 4000 + index, day, tss=tss)
            activities.append(session)
            checkins.append(activity_checkin(1, session.id, rpe=3 if index < 4 else 7))
            if index == 1:
                second = activity(1, 5000, day, tss=10)
                activities.append(second)
                checkins.append(activity_checkin(1, second.id, rpe=9))
        result = calculate(activities=activities, activity_checkins=checkins)
        relationship = result["training_load_relationship"]
        self.assertEqual(relationship["status"], "ready")
        self.assertEqual(relationship["paired_days"], 8)
        self.assertEqual(relationship["lower_or_equal_load"]["mean_daily_rpe"], 3.75)
        self.assertEqual(result["coverage"]["activities"]["activities_in_period"], 9)
        self.assertEqual(result["coverage"]["activities"]["days_with_activities"], 8)

    def test_10_duplicate_morning_checkin_is_rejected_without_changing_saved_value(self):
        Base.metadata.drop_all(bind=TEST_ENGINE)
        Base.metadata.create_all(bind=TEST_ENGINE)
        try:
            with TestSession() as db:
                user = User(
                    username="duplicate-checkin-user",
                    password_hash="test-hash",
                    display_name="Duplicate test",
                    timezone_name="UTC",
                )
                db.add(user)
                db.flush()
                db.add(MorningCheckIn(
                    user_id=user.id, local_date=TODAY, status="completed",
                    readiness=4, fatigue=2, soreness=1, wellbeing=4,
                ))
                db.commit()
                with self.assertRaises(IntegrityError):
                    db.add(MorningCheckIn(
                        user_id=user.id, local_date=TODAY, status="completed",
                        readiness=1, fatigue=5, soreness=5, wellbeing=1,
                    ))
                    db.commit()
                db.rollback()
                entries = db.query(MorningCheckIn).filter(
                    MorningCheckIn.user_id == user.id,
                    MorningCheckIn.local_date == TODAY,
                ).all()
                self.assertEqual(len(entries), 1)
                self.assertEqual(entries[0].wellbeing, 4)
        finally:
            Base.metadata.drop_all(bind=TEST_ENGINE)

    def test_11_local_day_boundary_respects_selected_timezone(self):
        stamp = datetime(2026, 10, 20, 23, 30, tzinfo=timezone.utc).replace(tzinfo=None)
        item = row(start_date_local=None, start_date=stamp)
        self.assertEqual(activity_local_date(item, ZoneInfo("Europe/Stockholm")), date(2026, 10, 21))
        self.assertEqual(activity_local_date(item, ZoneInfo("America/Los_Angeles")), date(2026, 10, 20))
        instant = datetime(2026, 10, 20, 23, 30, tzinfo=timezone.utc)
        self.assertEqual(local_today("Europe/Stockholm", instant), date(2026, 10, 21))
        self.assertEqual(local_today("America/Los_Angeles", instant), date(2026, 10, 20))

    @patch("app.services.personal_interpretation.httpx.post")
    def test_12_timeout_network_provider_limit_and_malformed_json_are_handled(self, post):
        for exception, category, status in [
            (httpx.TimeoutException("private timeout detail"), "timeout", None),
            (httpx.ConnectError("private connection detail"), "connection_error", None),
        ]:
            with self.subTest(category=category):
                post.reset_mock()
                post.side_effect = exception
                with self.assertRaises(PersonalInterpretationError) as raised:
                    generate_personal_interpretation(
                        {"data_gaps": ["Есть пропуски"], "observations": []},
                        api_key="test-secret",
                    )
                self.assertEqual(raised.exception.category, category)
                self.assertNotIn("private", str(raised.exception))

        for status in (429, 503):
            with self.subTest(upstream_status=status):
                post.reset_mock()
                response = Mock()
                response.status_code = status
                response.raise_for_status.side_effect = httpx.HTTPStatusError(
                    f"HTTP {status}", request=Mock(), response=response
                )
                post.return_value = response
                post.side_effect = None
                with self.assertRaises(PersonalInterpretationError) as raised:
                    generate_personal_interpretation(
                        {"data_gaps": ["Есть пропуски"], "observations": []},
                        api_key="test-secret",
                    )
                self.assertEqual(raised.exception.upstream_status, status)

        post.reset_mock()
        post.side_effect = None
        post.return_value = provider_response("{not-json")
        with self.assertRaises(PersonalInterpretationError) as raised:
            generate_personal_interpretation(
                {"data_gaps": ["Есть пропуски"], "observations": []},
                api_key="test-secret",
            )
        self.assertEqual(raised.exception.category, "invalid_response")
        self.assertNotIn("test-secret", str(raised.exception))

    @patch("app.services.personal_interpretation.httpx.post")
    def test_14_ai_rejects_hallucinated_numbers_ignored_gaps_and_causal_claims(self, post):
        trends = {
            "period": {"start": "2026-10-01", "end": "2026-10-20", "days": 20},
            "comparison_windows": {},
            "observations": [{"key": "wellbeing", "current": {"mean": 4.0}, "change": 0.0}],
            "training_load_relationship": {"status": "insufficient_data"},
            "coverage": {},
            "data_gaps": ["Есть пропуски утренних чек-инов."],
            "methodology": [],
            "disclaimer": "Описательная аналитика.",
        }
        bad_responses = [
            valid_analysis(summary="За период у тебя было 999 тренировок."),
            valid_analysis(
                summary="Среднее самочувствие не изменилось.",
                caution_signals=["Проблем и пропусков нет."],
                data_limitations=["Данные полностью достаточны."],
            ),
            valid_analysis(summary="Повышенная нагрузка вызвала ухудшение самочувствия."),
        ]
        expected_checks = ["unsupported_numeric_summary", "ignored_data_gaps", "causal_assertion_summary"]
        for index, payload in enumerate(bad_responses):
            with self.subTest(case=index):
                post.reset_mock()
                post.return_value = provider_response(json.dumps(payload, ensure_ascii=False))
                with self.assertRaises(PersonalInterpretationError) as raised:
                    generate_personal_interpretation(trends, api_key="test-secret")
                self.assertEqual(raised.exception.category, "unsupported_claim")
                self.assertEqual(raised.exception.quality_check, expected_checks[index])

    @patch("app.services.personal_interpretation.httpx.post")
    def test_causal_gate_allows_explicit_uncertainty_and_negation(self, post):
        payload = valid_analysis(
            summary="Самочувствие пока не позволяет сделать вывод о влиянии нагрузки.",
            caution_signals=["Недостаточно данных, чтобы утверждать, что сон вызвал ухудшение самочувствия."],
        )
        post.return_value = provider_response(json.dumps(payload, ensure_ascii=False))
        result = generate_personal_interpretation(
            {
                "period": {"start": "2026-10-01", "end": "2026-10-20", "days": 20},
                "comparison_windows": {},
                "observations": [{"key": "wellbeing", "current": {"mean": 4.0}, "change": 0.0}],
                "training_load_relationship": {"status": "insufficient_data"},
                "coverage": {},
                "data_gaps": ["Есть пропуски утренних чек-инов."],
                "methodology": [],
                "disclaimer": "Описательная аналитика.",
            },
            api_key="test-secret",
        )
        self.assertEqual(result.headline, "Динамика без резких изменений")

    @patch("app.services.personal_interpretation.httpx.post")
    def test_valid_grounded_response_passes_schema_and_quality_gate(self, post):
        payload = valid_analysis(
            summary=(
                "Сон и самочувствие стоит оценивать отдельно; поэтому продолжай "
                "отмечать оба показателя."
            )
        )
        post.return_value = provider_response(json.dumps(payload, ensure_ascii=False))
        result = generate_personal_interpretation(
            {
                "period": {"start": "2026-10-01", "end": "2026-10-20", "days": 20},
                "comparison_windows": {},
                "observations": [{"key": "wellbeing", "current": {"mean": 4.0}, "change": 0.0}],
                "training_load_relationship": {"status": "insufficient_data"},
                "coverage": {},
                "data_gaps": ["Есть пропуски утренних чек-инов."],
                "methodology": [],
                "disclaimer": "Описательная аналитика.",
            },
            api_key="test-secret",
        )
        self.assertEqual(result.headline, "Динамика без резких изменений")
        self.assertEqual(post.call_args.args[0], GROQ_CHAT_COMPLETIONS_URL)


class PersonalAnalysisApiScenarioTests(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(bind=TEST_ENGINE)
        Base.metadata.create_all(bind=TEST_ENGINE)
        limiter._storage.reset()
        with TestSession() as db:
            self.owner = User(
                username="scenario-owner",
                password_hash="test-hash",
                display_name="Scenario Owner",
                timezone_name="UTC",
            )
            self.other = User(
                username="scenario-other",
                password_hash="test-hash",
                display_name="Scenario Other",
                timezone_name="UTC",
            )
            db.add_all([self.owner, self.other])
            db.flush()
            self.owner_id = self.owner.id
            self.other_id = self.other.id
            for offset in range(13, -1, -1):
                day = TODAY - timedelta(days=offset)
                db.add_all([
                    MorningCheckIn(
                        user_id=self.owner.id, local_date=day, status="completed",
                        readiness=4, fatigue=2, soreness=1, wellbeing=4,
                    ),
                    MorningCheckIn(
                        user_id=self.other.id, local_date=day, status="completed",
                        readiness=1, fatigue=5, soreness=5, wellbeing=1,
                    ),
                ])
            db.commit()

        self.current_user = SimpleNamespace(id=self.owner_id, timezone_name="UTC", ai_analysis_consent=True, ai_provider="server", ai_api_key_encrypted=None)
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
        self.app.dependency_overrides[get_current_user] = lambda: self.current_user
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()
        self.app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=TEST_ENGINE)
        limiter._storage.reset()

    def settings(self, *, enabled=True, key="test-key"):
        return SimpleNamespace(
            PERSONAL_ANALYSIS_AI_ENABLED=enabled,
            GROQ_API_KEY=key,
            GROQ_MODEL="openai/gpt-oss-20b",
            GROQ_TIMEOUT_SECONDS=20,
        )

    @patch("app.routers.personal_analysis.local_today", return_value=TODAY)
    def test_15_api_never_exposes_other_users_checkins(self, _today):
        response = self.client.get("/api/personal-analysis/trends")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        wellbeing = next(item for item in body["observations"] if item["key"] == "wellbeing")
        self.assertEqual(wellbeing["current"]["mean"], 4.0)
        self.assertEqual(wellbeing["previous"]["mean"], 4.0)
        self.assertEqual(wellbeing["current"]["samples"], 7)
        self.assertEqual(wellbeing["previous"]["samples"], 7)
        self.assertNotIn("user_id", body)
        self.assertNotEqual(wellbeing["current"]["mean"], 1.0)

    @patch("app.routers.personal_analysis.get_settings")
    @patch("app.routers.personal_analysis.generate_personal_interpretation")
    @patch("app.routers.personal_analysis.local_today", return_value=TODAY)
    def test_interpretation_returns_ui_ready_schema_and_does_not_mutate_source_records(
        self, _today, generate, get_settings
    ):
        get_settings.return_value = self.settings()
        generate.return_value = PersonalInterpretation(**valid_analysis())
        with TestSession() as db:
            before = db.query(MorningCheckIn).count()
        response = self.client.post("/api/personal-analysis/interpretation")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ready")
        self.assertEqual(
            set(body["analysis"]),
            {
                "headline", "summary", "positive_signals", "caution_signals",
                "practical_next_steps", "data_limitations",
            },
        )
        self.assertTrue(all(isinstance(value, str) and value for value in body["analysis"]["positive_signals"]))
        with TestSession() as db:
            after = db.query(MorningCheckIn).count()
        self.assertEqual(after, before)

    @patch("app.routers.personal_analysis.get_settings")
    @patch("app.routers.personal_analysis.generate_personal_interpretation")
    @patch("app.routers.personal_analysis.local_today", return_value=TODAY)
    def test_ai_disabled_returns_503_without_provider_call(self, _today, generate, get_settings):
        get_settings.return_value = self.settings(enabled=False)
        response = self.client.post("/api/personal-analysis/interpretation")
        self.assertEqual(response.status_code, 503)
        self.assertIn("отключён", response.json()["detail"])
        generate.assert_not_called()

    @patch("app.routers.personal_analysis.get_settings")
    @patch("app.routers.personal_analysis.generate_personal_interpretation")
    @patch("app.routers.personal_analysis.local_today", return_value=TODAY)
    def test_missing_api_key_returns_503_without_provider_call(
        self, _today, generate, get_settings
    ):
        get_settings.return_value = self.settings(key=None)
        response = self.client.post("/api/personal-analysis/interpretation")
        self.assertEqual(response.status_code, 503)
        self.assertIn("GROQ_API_KEY", response.json()["detail"])
        generate.assert_not_called()

    @patch("app.routers.personal_analysis.get_settings")
    @patch("app.routers.personal_analysis.generate_personal_interpretation")
    @patch("app.routers.personal_analysis.local_today", return_value=TODAY)
    def test_rate_limit_returns_429_after_five_interpretation_requests(
        self, _today, generate, get_settings
    ):
        get_settings.return_value = self.settings()
        generate.return_value = PersonalInterpretation(**valid_analysis())
        responses = [
            self.client.post("/api/personal-analysis/interpretation")
            for _ in range(6)
        ]
        self.assertEqual([r.status_code for r in responses[:5]], [200] * 5)
        self.assertEqual(responses[5].status_code, 429)
        self.assertEqual(generate.call_count, 5)

    @patch("app.routers.personal_analysis.get_settings")
    @patch("app.routers.personal_analysis.generate_personal_interpretation")
    @patch("app.routers.personal_analysis.local_today", return_value=TODAY)
    def test_provider_unavailable_returns_safe_retryable_error(
        self, _today, generate, get_settings
    ):
        get_settings.return_value = self.settings()
        generate.side_effect = PersonalInterpretationError(
            "raw upstream body and credential", category="connection_error"
        )
        response = self.client.post("/api/personal-analysis/interpretation")
        self.assertEqual(response.status_code, 502)
        self.assertIn("подключиться к Groq", response.json()["detail"])
        self.assertNotIn("credential", response.text)
        self.assertNotIn("raw upstream body", response.text)

    @patch("app.routers.personal_analysis.get_settings")
    @patch("app.routers.personal_analysis.generate_personal_interpretation")
    @patch("app.routers.personal_analysis.local_today", return_value=TODAY)
    def test_groq_rate_limit_is_returned_as_429_with_retry_after(
        self, _today, generate, get_settings
    ):
        get_settings.return_value = self.settings()
        generate.side_effect = PersonalInterpretationError(
            "sanitized rate-limit error",
            category="upstream_http_error",
            upstream_status=429,
            upstream_error_code="rate_limit_exceeded",
            retry_after_seconds=17,
        )
        response = self.client.post("/api/personal-analysis/interpretation")
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.headers.get("Retry-After"), "17")
        self.assertIn("лимит", response.json()["detail"])
        self.assertNotIn("rate_limit_exceeded", response.text)


if __name__ == "__main__":
    unittest.main()
