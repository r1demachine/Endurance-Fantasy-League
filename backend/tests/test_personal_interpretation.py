"""Tests for Groq interpretation validation and privacy-minimized input."""
import json
import unittest
from unittest.mock import Mock, patch

import httpx

from app.services.personal_interpretation import (
    GROQ_CHAT_COMPLETIONS_URL,
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
            sample_trends(), api_key="test-secret", model="openai/gpt-oss-20b"
        )

        self.assertEqual(result.headline, VALID_ANALYSIS["headline"])
        self.assertEqual(post.call_args.args[0], GROQ_CHAT_COMPLETIONS_URL)
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer test-secret")
        request_body = post.call_args.kwargs["json"]
        self.assertEqual(request_body["response_format"], {"type": "json_object"})
        user_content = json.loads(request_body["messages"][1]["content"])
        serialized = json.dumps(user_content, ensure_ascii=False)
        self.assertNotIn("private-user", serialized)
        self.assertNotIn('"user_id"', serialized)
        self.assertNotIn("skipped_dates", serialized)
        self.assertNotIn("private_daily_dates", serialized)
        self.assertIn("observations", user_content)
        self.assertIn("data_gaps", user_content)

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
        with self.assertRaisesRegex(PersonalInterpretationError, "Groq failed or returned invalid JSON"):
            generate_personal_interpretation(sample_trends(), api_key="test-secret")

    @patch("app.services.personal_interpretation.httpx.post")
    def test_empty_api_key_never_calls_provider(self, post):
        with self.assertRaises(PersonalInterpretationError):
            generate_personal_interpretation(sample_trends(), api_key=" ")
        post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
