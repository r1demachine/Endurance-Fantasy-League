"""Generate a cautious, source-grounded interpretation using the Groq API.

Only aggregate trends are sent to the provider. No account identifiers, raw activities,
per-day dates, or check-in records are included in the model input.
"""
import json
from typing import Annotated, Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError


GROQ_CHAT_COMPLETIONS_URL = "https://api.groq.com/openai/v1/chat/completions"


class PersonalInterpretationError(RuntimeError):
    """Raised when Groq is unavailable or returns an invalid response."""


class PersonalInterpretation(BaseModel):
    """Strict, UI-ready output contract for personal trend interpretation."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    headline: Annotated[str, Field(min_length=3, max_length=100)]
    summary: Annotated[str, Field(min_length=1, max_length=700)]
    positive_signals: list[Annotated[str, Field(min_length=1, max_length=240)]] = Field(max_length=4)
    caution_signals: list[Annotated[str, Field(min_length=1, max_length=240)]] = Field(max_length=5)
    practical_next_steps: list[Annotated[str, Field(min_length=1, max_length=240)]] = Field(max_length=4)
    data_limitations: list[Annotated[str, Field(min_length=1, max_length=240)]] = Field(max_length=5)


SYSTEM_PROMPT = """Ты — помощник по описательной аналитике тренировок Endurance Fantasy League.
Отвечай на русском. Верни только один JSON-объект с ключами:
headline, summary, positive_signals, caution_signals, practical_next_steps, data_limitations.
Поля positive_signals, caution_signals, practical_next_steps и data_limitations — массивы строк.

Правила:
- Анализируй только данные из JSON пользователя. Не пересчитывай статистику и не добавляй числа,
  даты, факты, сравнения или тренировки, которых нет во входных данных.
- Учитывай готовые расчёты в полях observations и training_load_relationship; они являются источником
  истины. Различай средние значения, количество дней/наблюдений и пропуски.
- Если данных мало, прямо сообщи об этом и не формулируй уверенных выводов.
- Не утверждай причинно-следственную связь, статистическую значимость, полноту синхронизации,
  диагнозы, травмы, перетренированность или прогнозы здоровья.
- Направление изменения само по себе не доказывает, что стало лучше или хуже. Учитывай смысл метрики
  и описывай неоднозначность, если её нельзя надёжно разрешить по данным.
- Практические шаги должны быть общими и безопасными: продолжать отмечать данные, наблюдать за
  динамикой, сопоставлять субъективное состояние с нагрузкой. Не назначай лечение, не предписывай
  конкретные тренировочные нагрузки и не советуй тренироваться через боль.
- В data_limitations отмечай только реальные пробелы из входных данных. Не повторяй дисклеймер
  дословно и не добавляй лишнего.
- Используй краткие формулировки, без Markdown, эмодзи и текста за пределами JSON.
"""


def _model_input(trends: dict[str, Any]) -> dict[str, Any]:
    """Minimize shared data: aggregate counts only, never identity or item-level dates."""
    coverage = trends.get("coverage") or {}
    morning = coverage.get("morning_checkins") or {}
    sleep = coverage.get("sleep") or {}
    activities = coverage.get("activities") or {}

    return {
        "period": trends.get("period"),
        "comparison_windows": trends.get("comparison_windows"),
        "observations": trends.get("observations") or [],
        "training_load_relationship": trends.get("training_load_relationship"),
        "coverage": {
            "morning_checkins": {
                key: morning.get(key)
                for key in (
                    "period_days",
                    "completed_days",
                    "skipped_days",
                    "pending_days",
                    "days_without_completed_checkin",
                    "no_record_days",
                )
            },
            "sleep": {
                key: sleep.get(key)
                for key in (
                    "source",
                    "quality_field_used",
                    "days_with_wellness_record",
                    "days_with_quality_value",
                    "days_with_duration_value",
                )
            },
            "activities": {
                key: activities.get(key)
                for key in (
                    "activities_in_period",
                    "activities_with_measured_tss",
                    "activities_with_estimated_tss",
                    "activities_without_tss",
                    "activities_with_rpe",
                    "activities_without_rpe",
                    "activities_with_load_expectation",
                    "activities_without_load_expectation",
                    "days_with_activities",
                )
            },
        },
        "data_gaps": trends.get("data_gaps") or [],
        "methodology": trends.get("methodology") or [],
        "disclaimer": trends.get("disclaimer"),
    }


def generate_personal_interpretation(
    trends: dict[str, Any],
    *,
    api_key: str,
    model: str = "openai/gpt-oss-20b",
    timeout_seconds: float = 20.0,
) -> PersonalInterpretation:
    """Call Groq once and validate its JSON response against a strict schema."""
    if not api_key or not api_key.strip():
        raise PersonalInterpretationError("Groq API key is not configured")

    request_body = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(_model_input(trends), ensure_ascii=False, separators=(",", ":")),
            },
        ],
        "response_format": {"type": "json_object"},
        "max_completion_tokens": 900,
        "temperature": 0.2,
    }

    try:
        response = httpx.post(
            GROQ_CHAT_COMPLETIONS_URL,
            headers={
                "Authorization": "Bearer " + api_key,
                "Content-Type": "application/json",
            },
            json=request_body,
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        body = response.json()
        content = body["choices"][0]["message"]["content"]
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Groq returned an empty message")
        decoded = json.loads(content)
        return PersonalInterpretation.model_validate(decoded)
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError, ValidationError) as exc:
        # Do not forward or log the provider body: it can contain internal request details.
        raise PersonalInterpretationError("Groq failed or returned invalid JSON") from exc
