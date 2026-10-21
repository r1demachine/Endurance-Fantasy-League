"""Generate a cautious, source-grounded interpretation using the Groq API.

Only aggregate trends are sent to the provider. No account identifiers, raw activities,
per-day dates, or check-in records are included in the model input.
"""
import json
import logging
import re
from typing import Annotated, Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError


GROQ_CHAT_COMPLETIONS_URL = "https://api.groq.com/openai/v1/chat/completions"
logger = logging.getLogger(__name__)


class PersonalInterpretationError(RuntimeError):
    """Sanitized provider failure details safe for server logs and UI messages."""

    def __init__(
        self,
        message: str,
        *,
        category: str = "unknown",
        upstream_status: int | None = None,
        quality_check: str | None = None,
    ):
        super().__init__(message)
        self.category = category
        self.upstream_status = upstream_status
        # Fixed identifier only; never stores generated text or user data.
        self.quality_check = quality_check


class PersonalInterpretation(BaseModel):
    """Strict, UI-ready output contract for personal trend interpretation."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    headline: Annotated[str, Field(min_length=3, max_length=100)]
    summary: Annotated[str, Field(min_length=1, max_length=700)]
    positive_signals: list[Annotated[str, Field(min_length=1, max_length=240)]] = Field(max_length=4)
    caution_signals: list[Annotated[str, Field(min_length=1, max_length=240)]] = Field(max_length=5)
    practical_next_steps: list[Annotated[str, Field(min_length=1, max_length=240)]] = Field(max_length=4)
    data_limitations: list[Annotated[str, Field(min_length=1, max_length=240)]] = Field(max_length=5)


# Keep the provider-side schema intentionally to basic, strict-compatible JSON Schema
# types. Pydantic applies additional length/list limits after the response is received.
PERSONAL_INTERPRETATION_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"},
        "summary": {"type": "string"},
        "positive_signals": {"type": "array", "items": {"type": "string"}},
        "caution_signals": {"type": "array", "items": {"type": "string"}},
        "practical_next_steps": {"type": "array", "items": {"type": "string"}},
        "data_limitations": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "headline",
        "summary",
        "positive_signals",
        "caution_signals",
        "practical_next_steps",
        "data_limitations",
    ],
    "additionalProperties": False,
}

_PERSONAL_INTERPRETATION_FIELDS = {
    "headline",
    "summary",
    "positive_signals",
    "caution_signals",
    "practical_next_steps",
    "data_limitations",
}


def _schema_quality_check(exc: ValidationError) -> str:
    """Return field/type codes only; never include invalid values or error messages."""
    issue_codes: list[str] = []
    for error in exc.errors(include_url=False):
        location = error.get("loc", ())
        field = location[0] if location and location[0] in _PERSONAL_INTERPRETATION_FIELDS else "unknown"
        error_type = re.sub(r"[^a-z0-9_]", "", str(error.get("type", "validation_error")).lower())
        error_type = error_type[:32] or "validation_error"
        code = f"{field}_{error_type}"
        if code not in issue_codes:
            issue_codes.append(code)
    return "schema_" + "_".join(issue_codes[:3])


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
- Если data_gaps не пуст, кратко назови соответствующий пробел в data_limitations, даже если
  другие показатели стабильны. Не отрицай пробелы и не утверждай полноту данных.
- В data_limitations отмечай только реальные пробелы из входных данных. Не повторяй дисклеймер
  дословно и не добавляй лишнего.
- Точно соблюдай размеры: headline — 3–100 символов; summary — 1–700 символов;
  каждый элемент массивов — 1–240 символов. positive_signals и practical_next_steps —
  максимум 4 пункта; caution_signals и data_limitations — максимум 5 пунктов.
- Всегда возвращай все шесть ключей, даже если по какому-то списку нечего добавить: используй [].
  Не возвращай null, вложенные объекты вместо строк, дополнительные ключи или обёртку вокруг объекта.
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


_NUMBER_TOKEN = re.compile(r"\d+(?:[.,]\d+)?")
_MISSINGNESS_TERMS = re.compile(
    r"пропуск|пропущ|непол|недостат|нет\s+(?:достаточно\s+)?данн|"
    r"отсутств|не хватает|ограниченн|без\s+(?:полных?\s+)?данных",
    re.IGNORECASE,
)
_GAP_DENIAL_TERMS = re.compile(
    r"пропуск\w*\s+нет|нет\s+(?:никаких\s+)?пропуск\w*|"
    r"отсутствуют?\s+(?:любые\s+)?пропуск\w*|"
    r"(?:данные|покрытие)\s+(?:полностью\s+)?(?:полны|достаточны)",
    re.IGNORECASE,
)
_METRIC_TERMS = re.compile(
    r"сон|нагрузк|готовност|усталост|самочувств|восстановлен|"
    r"\bRPE\b|\bTSS\b",
    re.IGNORECASE,
)
_CAUSAL_TERMS = re.compile(
    r"из[ -]за|вследстви[ея]|вызвал(?:о|а|и)?|прив[её]л(?:о|а|и)?\s+к|"
    r"повлиял(?:о|а|и)?\s+на|обусловил(?:о|а|и)?|спровоцировал(?:о|а|и)?|"
    r"объясня\w*|caused? by|due to|resulted in|led to",
    re.IGNORECASE,
)


def _normalise_number(token: str) -> str:
    """Compare numeric literals independent of decimal comma and trailing zeroes."""
    from decimal import Decimal, InvalidOperation

    cleaned = token.replace(",", ".").replace("%", "").strip()
    try:
        number = Decimal(cleaned).normalize()
    except InvalidOperation:
        return cleaned
    if number == number.to_integral_value():
        return str(int(number))
    return format(number, "f")


def _source_numbers(value: Any) -> set[str]:
    """Collect numeric tokens from aggregate values while ignoring ISO date strings."""
    if isinstance(value, bool) or value is None:
        return set()
    if isinstance(value, (int, float)):
        return {_normalise_number(str(value))}
    if isinstance(value, str):
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value.strip()):
            return set()
        return {
            _normalise_number(match.group(0))
            for match in _NUMBER_TOKEN.finditer(value)
        }
    if isinstance(value, dict):
        tokens: set[str] = set()
        for child in value.values():
            tokens.update(_source_numbers(child))
        return tokens
    if isinstance(value, (list, tuple)):
        tokens: set[str] = set()
        for child in value:
            tokens.update(_source_numbers(child))
        return tokens
    return set()


def _response_fields(analysis: PersonalInterpretation) -> dict[str, list[str] | str]:
    """Map fixed schema field names to text without retaining or logging field values."""
    return {
        "headline": analysis.headline,
        "summary": analysis.summary,
        "positive_signals": analysis.positive_signals,
        "caution_signals": analysis.caution_signals,
        "practical_next_steps": analysis.practical_next_steps,
        "data_limitations": analysis.data_limitations,
    }


def _response_text(analysis: PersonalInterpretation) -> str:
    values: list[str] = []
    for value in _response_fields(analysis).values():
        values.extend(value if isinstance(value, list) else [value])
    return "\n".join(values)


def _validate_interpretation_claims(
    analysis: PersonalInterpretation,
    trends: dict[str, Any],
) -> None:
    """Reject obvious ungrounded numerals, ignored gaps, and causal assertions.

    This is a conservative deterministic gate, not a general natural-language fact
    checker. The source prompt and the UI disclaimer remain necessary safeguards.
    """
    allowed_numbers = _source_numbers(_model_input(trends))
    unsupported_fields = []
    for field_name, value in _response_fields(analysis).items():
        field_text = " ".join(value if isinstance(value, list) else [value])
        unsupported_numbers = {
            _normalise_number(match.group(0))
            for match in _NUMBER_TOKEN.finditer(field_text)
        } - allowed_numbers
        if unsupported_numbers:
            unsupported_fields.append(field_name)

    if unsupported_fields:
        # Field names are fixed identifiers; never include the offending values or text.
        raise PersonalInterpretationError(
            "Groq returned a numeric claim not present in the source data",
            category="unsupported_claim",
            quality_check="unsupported_numeric_" + "_".join(unsupported_fields[:3]),
        )

    # The response must not silently present a complete picture when source gaps exist.
    relevant_context = "\n".join(
        [analysis.summary, *analysis.caution_signals, *analysis.data_limitations]
    )
    if trends.get("data_gaps") and (
        _GAP_DENIAL_TERMS.search(relevant_context)
        or not _MISSINGNESS_TERMS.search(relevant_context)
    ):
        raise PersonalInterpretationError(
            "Groq ignored source data gaps",
            category="unsupported_claim",
            quality_check="ignored_data_gaps",
        )

    # Check individual statements so a disclaimer elsewhere cannot excuse a causal claim.
    text = _response_text(analysis)
    for statement in re.split(r"[.!?;\n]+", text):
        if _CAUSAL_TERMS.search(statement) and _METRIC_TERMS.search(statement):
            raise PersonalInterpretationError(
                "Groq returned an unsupported causal assertion",
                category="unsupported_claim",
                quality_check="causal_assertion",
            )


def _request_interpretation(
    request_body: dict[str, Any],
    *,
    api_key: str,
    timeout_seconds: float,
) -> PersonalInterpretation:
    """Make one Groq request and apply JSON/Pydantic contract validation."""
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
    except httpx.HTTPStatusError as exc:
        # Keep only the HTTP status. Never log the response body or authorization header.
        raise PersonalInterpretationError(
            "Groq rejected the request",
            category="upstream_http_error",
            upstream_status=exc.response.status_code,
        ) from exc
    except httpx.TimeoutException as exc:
        raise PersonalInterpretationError(
            "Groq request timed out",
            category="timeout",
        ) from exc
    except httpx.HTTPError as exc:
        raise PersonalInterpretationError(
            "Groq connection failed",
            category="connection_error",
        ) from exc

    try:
        body = response.json()
        content = body["choices"][0]["message"]["content"]
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Groq returned an empty message")
        decoded = json.loads(content)
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise PersonalInterpretationError(
            "Groq returned an invalid response",
            category="invalid_response",
        ) from exc

    try:
        return PersonalInterpretation.model_validate(decoded)
    except ValidationError as exc:
        raise PersonalInterpretationError(
            "Groq returned an unexpected JSON schema",
            category="invalid_schema",
            quality_check=_schema_quality_check(exc),
        ) from exc


def generate_personal_interpretation(
    trends: dict[str, Any],
    *,
    api_key: str,
    model: str = "qwen/qwen3.8-27b",
    timeout_seconds: float = 20.0,
) -> PersonalInterpretation:
    """Call Groq, with one number-free repair attempt if its first answer invents numbers."""
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
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "personal_interpretation",
                "strict": True,
                "schema": PERSONAL_INTERPRETATION_JSON_SCHEMA,
            },
        },
        # Return only the constrained final answer, not reasoning text.
        "reasoning_format": "hidden",
        "max_completion_tokens": 1100,
        "temperature": 0.2,
    }

    analysis = _request_interpretation(
        request_body,
        api_key=api_key,
        timeout_seconds=timeout_seconds,
    )
    try:
        _validate_interpretation_claims(analysis, trends)
        return analysis
    except PersonalInterpretationError as exc:
        if exc.category != "unsupported_claim" or not (exc.quality_check or "").startswith("unsupported_numeric_"):
            raise

    # A single repair is attempted only for unsupported numeric claims. Keep the
    # source input and schema unchanged; ask for qualitative wording with no digits.
    retry_body = {
        **request_body,
        "messages": [
            {
                "role": "system",
                "content": SYSTEM_PROMPT
                + "\n\nПовторная попытка: предыдущий ответ содержал числовые утверждения, "
                + "которые нельзя подтвердить точными числовыми значениями во входных данных. "
                + "Сформируй новый полный JSON по той же схеме. В этот раз не используй "
                + "арабские цифры, даты, проценты, длительности или числовые диапазоны ни в одном "
                + "текстовом поле. Передай те же выводы качественно, без чисел. Не меняй данные "
                + "и не добавляй новые факты.",
            },
            request_body["messages"][1],
        ],
    }
    analysis = _request_interpretation(
        retry_body,
        api_key=api_key,
        timeout_seconds=timeout_seconds,
    )
    _validate_interpretation_claims(analysis, trends)
    return analysis
