"""Tests for Groq interpretation validation and privacy-minimized input."""
import json
import unittest
from unittest.mock import Mock, patch

import httpx

from app.services.personal_interpretation import (
    GROQ_CHAT_COMPLETIONS_URL,
    PERSONAL_INTERPRETATION_JSON_SCHEMA,
    PersonalInterpretationError,
    generate_personal_interpretation,
)


VALID_ANALYSIS = {
    "headline": "Данных пока немного",
    "summary": "По доступным неделям есть ограниченные наблюдения; выводы стоит считать предварительными.",
    "positive_signals": ["В обоих окнах есть завершённые утренние чек-ины."],
    "caution_signals": ["Покрытие автоматического сна неполное."],
    "practical_next_steps": ["Продолжай отмечать самочувствие и RPE, чтобы увеличить число сопоставимых дней."],
    "data_limitations": ["Результат отражает только данные, сохранённые в EFL."],
}


def provider_response(content):
    response = Mock()
    response.json.return_value = {
        "choices": [{"message": {"content": content}}],
    }
    response.raise_for_status.return_value = None
    return response


def sample_trends():
    return {
        "user_id": 123,
        "username": "private-user",
        "period": {"start": "2026-09-23", "end": "2026-10-20", "days": 28},
        "comparison_windows": {
            "current": {"start": "2026-10-14", "end": "2026-10-20", "days": 7},
            "previous": {"start": "2026-10-07", "end": "2026-10-13", "days": 7},
        },
        "observations": [{
            "key": "readiness",
            "label": "Готовность",
            "status": "ready",
            "current": {"mean": 4.0, "days": 5, "samples": 5},
            "previous": {"mean": 3.5, "days": 4, "samples": 4},
            "change": 0.5,
            "trend": "increased",
        }],
        "training_load_relationship": {"status": "insufficient_data", "reason": "not enough pairs"},
        "coverage": {
            "morning_checkins": {
                "period_days": 28,
                "completed_days": 9,
                "skipped_days": 1,
                "pending_days": 0,
                "days_without_completed_checkin": 19,
                "no_record_days": 18,
                "skipped_dates": ["2026-10-08"],
                "no_record_dates": ["2026-10-01"],
            },
            "sleep": {
                "source": "Intervals.icu Wellness",
                "quality_field_used": "sleep_score",
                "days_with_wellness_record": 7,
                "days_with_quality_value": 6,
                "days_with_duration_value": 7,
                "private_daily_dates": ["2026-10-19"],
            },
            "activities": {
                "activities_in_period": 4,
                "activities_with_measured_tss": 3,
                "activities_with_estimated_tss": 1,
                "activities_without_tss": 0,
                "activities_with_rpe": 3,
                "activities_without_rpe": 1,
                "activities_with_load_expectation": 2,
                "activities_without_load_expectation": 2,
                "days_with_activities": 4,
            },
        },
        "data_gaps": ["Часть дней без утренней отметки."],
        "methodology": ["Средние рассчитываются по дням с фактическими значениями."],
        "disclaimer": "Описательная аналитика, не медицинская оценка.",
    }


class PersonalInterpretationServiceTests(unittest.TestCase):
    @patch("app.services.personal_interpretation.httpx.post")
    def test_validates_json_and_sends_only_aggregate_data(self, post):
        response = Mock()
        response.json.return_value = {
            "choices": [{"message": {"content": json.dumps(VALID_ANALYSIS, ensure_ascii=False)}}]
        }
        response.raise_for_status.return_value = None
        post.return_value = response

        result = generate_personal_interpretation(
            sample_trends(), api_key="test-secret"
        )

        self.assertEqual(result.headline, VALID_ANALYSIS["headline"])
        self.assertEqual(post.call_args.args[0], GROQ_CHAT_COMPLETIONS_URL)
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer test-secret")
        request_body = post.call_args.kwargs["json"]
        self.assertEqual(
            request_body["response_format"],
            {
                "type": "json_schema",
                "json_schema": {
                    "name": "personal_interpretation",
                    "strict": True,
                    "schema": PERSONAL_INTERPRETATION_JSON_SCHEMA,
                },
            },
        )
        schema = request_body["response_format"]["json_schema"]["schema"]
        self.assertEqual(set(schema["properties"]), {
            "headline", "summary", "positive_signals", "caution_signals",
            "practical_next_steps", "data_limitations",
        })
        self.assertEqual(set(schema["required"]), set(schema["properties"]))
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(request_body["model"], "qwen/qwen3.8-27b")
        self.assertEqual(request_body["reasoning_format"], "hidden")
        self.assertEqual(request_body["reasoning_effort"], "none")
        self.assertEqual(request_body["max_completion_tokens"], 900)
        self.assertEqual(request_body["temperature"], 0.7)
        self.assertEqual(request_body["top_p"], 0.8)
        user_content = json.loads(request_body["messages"][1]["content"])
        serialized = json.dumps(user_content, ensure_ascii=False)
        self.assertNotIn("private-user", serialized)
        self.assertNotIn('"user_id"', serialized)
        self.assertNotIn("skipped_dates", serialized)
        self.assertNotIn("private_daily_dates", serialized)
        self.assertIn("observations", user_content)
        self.assertIn("data_gaps", user_content)

    @patch("app.services.personal_interpretation.httpx.post")
    def test_unsupported_numeric_claim_gets_one_number_free_retry(self, post):
        bad = {
            **VALID_ANALYSIS,
            "summary": "За период у тебя было 999 тренировок.",
        }
        post.side_effect = [
            provider_response(json.dumps(bad, ensure_ascii=False)),
            provider_response(json.dumps(VALID_ANALYSIS, ensure_ascii=False)),
        ]

        result = generate_personal_interpretation(sample_trends(), api_key="test-secret")

        self.assertEqual(result.headline, VALID_ANALYSIS["headline"])
        self.assertEqual(post.call_count, 2)
        retry_body = post.call_args_list[1].kwargs["json"]
        self.assertIn("не используй арабские цифры", retry_body["messages"][0]["content"])
        self.assertEqual(
            retry_body["response_format"]["json_schema"]["schema"],
            PERSONAL_INTERPRETATION_JSON_SCHEMA,
        )

    @patch("app.services.personal_interpretation.httpx.post")
    def test_unsupported_numeric_retry_still_rejects_bad_response(self, post):
        bad = {
            **VALID_ANALYSIS,
            "summary": "За период у тебя было 999 тренировок.",
        }
        post.return_value = provider_response(json.dumps(bad, ensure_ascii=False))

        with self.assertRaises(PersonalInterpretationError) as raised:
            generate_personal_interpretation(sample_trends(), api_key="test-secret")

        self.assertEqual(raised.exception.category, "unsupported_claim")
        self.assertEqual(raised.exception.quality_check, "unsupported_numeric_summary")
        self.assertEqual(post.call_count, 2)

    @patch("app.services.personal_interpretation.httpx.post")
    def test_schema_errors_report_only_field_and_error_codes(self, post):
        invalid = {**VALID_ANALYSIS, "headline": "x"}
        response = Mock()
        response.json.return_value = {
            "choices": [{"message": {"content": json.dumps(invalid, ensure_ascii=False)}}]
        }
        response.raise_for_status.return_value = None
        post.return_value = response

        with self.assertRaises(PersonalInterpretationError) as raised:
            generate_personal_interpretation(sample_trends(), api_key="test-secret")

        self.assertEqual(raised.exception.category, "invalid_schema")
        self.assertEqual(raised.exception.quality_check, "schema_headline_string_too_short")
        self.assertNotIn("Данных", str(raised.exception))
        self.assertNotIn("test-secret", str(raised.exception))

    @patch("app.services.personal_interpretation.httpx.post")
    def test_rejects_invalid_json_and_schema(self, post):
        response = Mock()
        response.json.return_value = {
            "choices": [{"message": {"content": '{"headline": "broken" not-json}'}}]
        }
        response.raise_for_status.return_value = None
        post.return_value = response

        with self.assertRaises(PersonalInterpretationError):
            generate_personal_interpretation(sample_trends(), api_key="test-secret")

        response.json.return_value = {
            "choices": [{"message": {"content": json.dumps({**VALID_ANALYSIS, "surprise": "extra"})}}]
        }
        with self.assertRaises(PersonalInterpretationError):
            generate_personal_interpretation(sample_trends(), api_key="test-secret")

    @patch("app.services.personal_interpretation.httpx.post")
    def test_hides_upstream_timeout_details(self, post):
        post.side_effect = httpx.TimeoutException("request timed out with internal details")
        with self.assertRaises(PersonalInterpretationError) as raised:
            generate_personal_interpretation(sample_trends(), api_key="test-secret")
        self.assertEqual(raised.exception.category, "timeout")

    @patch("app.services.personal_interpretation.httpx.post")
    def test_upstream_http_status_is_preserved_without_provider_body(self, post):
        response = Mock()
        response.status_code = 401
        response.text = "private upstream response containing secret"
        response.headers = {}
        response.json.return_value = {
            "error": {
                "code": "auth_invalid",
                "type": "authentication_error",
                "message": "private upstream response containing secret",
            }
        }
        error = httpx.HTTPStatusError(
            "401 Unauthorized",
            request=Mock(),
            response=response,
        )
        mocked_response = Mock()
        mocked_response.raise_for_status.side_effect = error
        post.return_value = mocked_response

        with self.assertRaises(PersonalInterpretationError) as raised:
            generate_personal_interpretation(sample_trends(), api_key="test-secret")

        self.assertEqual(raised.exception.category, "upstream_http_error")
        self.assertEqual(raised.exception.upstream_status, 401)
        self.assertEqual(raised.exception.upstream_error_code, "auth_invalid_authentication_error")
        self.assertIsNone(raised.exception.retry_after_seconds)
        self.assertNotIn("private upstream response", str(raised.exception))
        self.assertNotIn("test-secret", str(raised.exception))

    @patch("app.services.personal_interpretation.httpx.post")
    def test_empty_api_key_never_calls_provider(self, post):
        with self.assertRaises(PersonalInterpretationError):
            generate_personal_interpretation(sample_trends(), api_key=" ")
        post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
