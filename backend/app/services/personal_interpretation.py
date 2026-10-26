"""Generate a cautious, source-grounded interpretation using the Groq API.

Only aggregate trends are sent to the provider. No account identifiers, raw activities,
per-day dates, or check-in records are included in the model input.
"""
import ipaddress
import json
import logging
import math
import re
import socket
import ssl
from typing import Annotated, Any
from urllib.parse import urlsplit, urlunsplit

import httpcore
import httpx
from httpcore._backends.sync import SyncStream
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
        upstream_error_code: str | None = None,
        retry_after_seconds: int | None = None,
    ):
        super().__init__(message)
        self.category = category
        self.upstream_status = upstream_status
        # Fixed identifiers only; never store provider messages or generated text.
        self.quality_check = quality_check
        self.upstream_error_code = upstream_error_code
        self.retry_after_seconds = retry_after_seconds


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
    """Build an allow-listed aggregate payload. Never include identities, dates, or item-level text."""
    coverage = trends.get("coverage") if isinstance(trends.get("coverage"), dict) else {}
    morning = coverage.get("morning_checkins") if isinstance(coverage.get("morning_checkins"), dict) else {}
    sleep = coverage.get("sleep") if isinstance(coverage.get("sleep"), dict) else {}
    activities = coverage.get("activities") if isinstance(coverage.get("activities"), dict) else {}
    relationship = trends.get("training_load_relationship")
    relationship = relationship if isinstance(relationship, dict) else {}
    period = trends.get("period") if isinstance(trends.get("period"), dict) else {}
    windows = trends.get("comparison_windows") if isinstance(trends.get("comparison_windows"), dict) else {}

    def count(source: dict[str, Any], name: str, default: int = 0) -> int:
        value = source.get(name, default)
        return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else default

    def number(source: dict[str, Any], name: str) -> int | float | None:
        value = source.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        if not math.isfinite(float(value)):
            return None
        return value

    def daily_stats(value: Any) -> dict[str, int | float | None]:
        stats = value if isinstance(value, dict) else {}
        return {
            "mean": number(stats, "mean"),
            "days_with_data": count(stats, "days_with_data"),
            "samples": count(stats, "samples"),
        }

    metric_labels = {
        "readiness": "readiness",
        "fatigue": "fatigue",
        "soreness": "soreness",
        "wellbeing": "wellbeing",
        "sleep_quality": "sleep_quality",
        "sleep_duration_hours": "sleep_duration_hours",
        "rpe": "rpe",
        "harder_than_expected_share": "harder_than_expected_share",
    }
    observations = []
    raw_observations = trends.get("observations")
    if isinstance(raw_observations, list):
        for item in raw_observations:
            if not isinstance(item, dict):
                continue
            key = item.get("key")
            if key not in metric_labels:
                continue
            status = item.get("status")
            trend = item.get("trend")
            observations.append({
                "key": metric_labels[key],
                "status": status if status in {"ready", "insufficient_data"} else "insufficient_data",
                "trend": trend if trend in {"upward", "downward", "stable", "insufficient_data"} else "insufficient_data",
                "current": daily_stats(item.get("current")),
                "previous": daily_stats(item.get("previous")),
                "change": number(item, "change"),
            })

    period_days = count(period, "days")
    current_window = windows.get("current") if isinstance(windows.get("current"), dict) else {}
    previous_window = windows.get("previous") if isinstance(windows.get("previous"), dict) else {}
    sleep_quality_days = count(sleep, "days_with_quality_value")
    sleep_duration_days = count(sleep, "days_with_duration_value")
    activities_total = count(activities, "activities_in_period")
    gaps: list[str] = []

    skipped = count(morning, "skipped_days")
    pending = count(morning, "pending_days")
    no_record = count(morning, "no_record_days")
    if skipped:
        gaps.append(f"Утренний чек-ин явно пропущен за {skipped} дн.")
    if pending:
        gaps.append(f"Есть незавершённый утренний чек-ин за {pending} дн.")
    if no_record:
        gaps.append(f"Нет записи о статусе утреннего чек-ина за {no_record} дн.")
    if sleep_quality_days < period_days:
        gaps.append(f"Автоматическое качество сна доступно за {sleep_quality_days} из {period_days} календарных дней.")
    if sleep_duration_days < period_days:
        gaps.append(f"Продолжительность сна доступна за {sleep_duration_days} из {period_days} календарных дней.")
    no_tss = count(activities, "activities_without_tss")
    estimated_tss = count(activities, "activities_with_estimated_tss")
    no_rpe = count(activities, "activities_without_rpe")
    no_expectation = count(activities, "activities_without_load_expectation")
    if no_tss and activities_total:
        gaps.append(f"У {no_tss} из {activities_total} сохранённых тренировок нет пригодного значения TSS.")
    if estimated_tss:
        gaps.append(f"TSS помечен как оценочный у {estimated_tss} тренировок.")
    if no_rpe and activities_total:
        gaps.append(f"Нет послетренировочного RPE для {no_rpe} из {activities_total} сохранённых тренировок в периоде.")
    if no_expectation and activities_total:
        gaps.append(f"Для {no_expectation} из {activities_total} тренировок не указано сравнение нагрузки с ожиданиями.")
    if relationship.get("status") != "ready":
        gaps.append("Связь TSS и RPE не рассчитана из-за недостаточного числа парных дней.")

    return {
        "period": {"days": period_days},
        "comparison_windows": {
            "current": {"days": count(current_window, "days")},
            "previous": {"days": count(previous_window, "days")},
        },
        "observations": observations,
        "training_load_relationship": {
            "status": relationship.get("status") if relationship.get("status") in {"ready", "insufficient_data"} else "insufficient_data",
            "paired_days": count(relationship, "paired_days"),
            "days_excluded_due_to_missing_tss": count(relationship, "days_excluded_due_to_missing_tss"),
            "days_excluded_due_to_estimated_tss": count(relationship, "days_excluded_due_to_estimated_tss"),
            "median_daily_tss": number(relationship, "median_daily_tss"),
            "lower_or_equal_load": {
                "days": count(relationship.get("lower_or_equal_load") or {}, "days"),
                "mean_daily_rpe": number(relationship.get("lower_or_equal_load") or {}, "mean_daily_rpe"),
            },
            "above_median_load": {
                "days": count(relationship.get("above_median_load") or {}, "days"),
                "mean_daily_rpe": number(relationship.get("above_median_load") or {}, "mean_daily_rpe"),
            },
            "rpe_difference_high_minus_low": number(relationship, "rpe_difference_high_minus_low"),
        },
        "coverage": {
            "morning_checkins": {
                key: count(morning, key)
                for key in (
                    "period_days", "completed_days", "skipped_days", "pending_days",
                    "days_without_completed_checkin", "no_record_days",
                )
            },
            "sleep": {
                "source": "Intervals.icu Wellness",
                "quality_field_used": sleep.get("quality_field_used") if sleep.get("quality_field_used") in {"sleep_score", "sleep_quality"} else None,
                "days_with_wellness_record": count(sleep, "days_with_wellness_record"),
                "days_with_quality_value": sleep_quality_days,
                "days_with_duration_value": sleep_duration_days,
            },
            "activities": {
                key: count(activities, key)
                for key in (
                    "activities_in_period", "activities_with_measured_tss",
                    "activities_with_estimated_tss", "activities_without_tss",
                    "activities_with_rpe", "activities_without_rpe",
                    "activities_with_load_expectation", "activities_without_load_expectation",
                    "days_with_activities",
                )
            },
        },
        "data_gaps": gaps,
        "methodology": [
            "Показаны агрегированные средние, количество наблюдений и покрытие данных; пропуски не заменяются нулями.",
            "Последние и предыдущие окна сравниваются отдельно; каждый день имеет одинаковый вес.",
            "Связь TSS и RPE носит описательный характер и не доказывает причинность.",
        ],
        "disclaimer": "Это описательная тренировочная аналитика, не медицинская оценка, диагноз или прогноз.",
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
    r"caused? by|due to|resulted in|led to",
    re.IGNORECASE,
)
_CAUSAL_QUALIFIERS = re.compile(
    r"\b(?:не|нельзя|невозможно|неясно|неизвестно|недостаточно|нет\s+оснований|"
    r"не\s+подтвержд\w*|не\s+доказыв\w*|не\s+означа\w*|"
    r"не\s+свидетельств\w*|не\s+позволяет|не\s+следует|"
    r"не\s+установлен\w*|без\s+данных)\b",
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


def _causal_claim_is_asserted(statement: str, match: re.Match[str]) -> bool:
    """Treat explicit negation/insufficient-evidence wording as a limitation, not a claim."""
    prefix = statement[max(0, match.start() - 90):match.start()]
    return not _CAUSAL_QUALIFIERS.search(prefix)


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

    # Check each field independently so logs identify the source field without exposing text.
    # Negated or explicitly uncertain statements should not be mistaken for positive causal claims.
    for field_name, value in _response_fields(analysis).items():
        field_text = " ".join(value if isinstance(value, list) else [value])
        for statement in re.split(r"[.!?;\n]+", field_text):
            match = _CAUSAL_TERMS.search(statement)
            if (
                match
                and _METRIC_TERMS.search(statement)
                and _causal_claim_is_asserted(statement, match)
            ):
                raise PersonalInterpretationError(
                    "Groq returned an unsupported causal assertion",
                    category="unsupported_claim",
                    quality_check=f"causal_assertion_{field_name}",
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
        # Extract only safe machine-readable codes and a numeric retry delay, never the body text.
        try:
            error_payload = exc.response.json().get("error", {})
        except (ValueError, AttributeError):
            error_payload = {}
        if not isinstance(error_payload, dict):
            error_payload = {}

        safe_codes = []
        for key in ("code", "type"):
            raw_code = error_payload.get(key)
            if isinstance(raw_code, str):
                code = re.sub(r"[^A-Za-z0-9_.-]", "_", raw_code)[:48].strip("_")
                if code and code not in safe_codes:
                    safe_codes.append(code)

        retry_after_seconds = None
        raw_retry_after = exc.response.headers.get("Retry-After", "")
        retry_after = raw_retry_after.strip() if isinstance(raw_retry_after, str) else ""
        if re.fullmatch(r"\d{1,5}", retry_after):
            retry_after_seconds = min(int(retry_after), 86400)

        raise PersonalInterpretationError(
            "Groq rejected the request",
            category="upstream_http_error",
            upstream_status=exc.response.status_code,
            upstream_error_code="_".join(safe_codes) or None,
            retry_after_seconds=retry_after_seconds,
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
        # Qwen recommends instruct mode for efficient general-purpose text generation.
        "reasoning_effort": "none",
        "max_completion_tokens": 900,
        "temperature": 0.7,
        "top_p": 0.8,
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


MAX_PROVIDER_RESPONSE_BYTES = 256 * 1024
MAX_PROVIDER_TIMEOUT_SECONDS = 30.0
ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


def validate_openai_base_url_syntax(base_url: str) -> str:
    """Validate a user-supplied base URL without making any network request."""
    if not isinstance(base_url, str) or not base_url.strip() or len(base_url) > 2048:
        raise PersonalInterpretationError("Invalid provider URL", category="invalid_endpoint")
    value = base_url.strip()
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise PersonalInterpretationError("Invalid provider URL", category="invalid_endpoint") from None
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or (port is not None and port != 443)
        or parsed.query
        or parsed.fragment
    ):
        raise PersonalInterpretationError("Invalid provider URL", category="invalid_endpoint")
    host = parsed.hostname.rstrip(".").lower()
    if not host or host in {"localhost"} or host.endswith((".localhost", ".local", ".internal", ".lan", ".home.arpa")):
        raise PersonalInterpretationError("Provider host is not public", category="ssrf_blocked")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        try:
            host = host.encode("idna").decode("ascii")
        except UnicodeError:
            raise PersonalInterpretationError("Invalid provider host", category="invalid_endpoint") from None
    else:
        if not _is_public_ip(ip):
            raise PersonalInterpretationError("Provider host is not public", category="ssrf_blocked")

    display_host = f"[{host}]" if ":" in host else host
    netloc = display_host if port is None else f"{display_host}:443"
    path = parsed.path.rstrip("/")
    return urlunsplit(("https", netloc, path, "", ""))


def _is_public_ip(value: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Require globally routable unicast IPs, unwrapping IPv4-mapped IPv6 explicitly."""
    ip = value
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return bool(
        ip.is_global
        and not ip.is_private
        and not ip.is_loopback
        and not ip.is_link_local
        and not ip.is_multicast
        and not ip.is_reserved
        and not ip.is_unspecified
    )


def _resolve_public_endpoint(base_url: str) -> tuple[str, str, tuple[str, ...]]:
    """Resolve and pin every public destination IP; reject mixed or non-public DNS answers."""
    normalized = validate_openai_base_url_syntax(base_url)
    parsed = urlsplit(normalized)
    host = (parsed.hostname or "").rstrip(".").lower()
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        try:
            records = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        except (OSError, socket.gaierror):
            raise PersonalInterpretationError("Provider host resolution failed", category="dns_resolution_failed") from None
        resolved: set[str] = set()
        for record in records:
            try:
                ip = ipaddress.ip_address(record[4][0])
            except (ValueError, TypeError, IndexError):
                raise PersonalInterpretationError("Provider host resolution failed", category="dns_resolution_failed") from None
            if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
                ip = ip.ipv4_mapped
            if not _is_public_ip(ip):
                raise PersonalInterpretationError("Provider host is not public", category="ssrf_blocked")
            resolved.add(ip.compressed)
        if not resolved:
            raise PersonalInterpretationError("Provider host resolution returned no addresses", category="dns_resolution_failed")
        addresses = tuple(sorted(resolved))
    else:
        if isinstance(literal, ipaddress.IPv6Address) and literal.ipv4_mapped is not None:
            literal = literal.ipv4_mapped
        if not _is_public_ip(literal):
            raise PersonalInterpretationError("Provider host is not public", category="ssrf_blocked")
        addresses = (literal.compressed,)
    return normalized, host, addresses


class _PinnedNetworkBackend(httpcore.SyncBackend):
    """Connect only to pre-resolved numeric IPs while preserving the original TLS SNI host."""

    def __init__(self, expected_host: str, addresses: tuple[str, ...]):
        self.expected_host = expected_host.lower().rstrip(".")
        self.addresses = addresses

    def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        request_host = host.decode("ascii", errors="ignore") if isinstance(host, bytes) else str(host)
        if request_host.lower().rstrip(".") != self.expected_host or port != 443:
            raise httpcore.ConnectError("Pinned host or port mismatch")
        last_error = None
        for address in self.addresses:
            sock = None
            try:
                source_address = (local_address, 0) if local_address else None
                sock = socket.create_connection(
                    (address, port),
                    timeout=timeout,
                    source_address=source_address,
                )
                if socket_options:
                    for option in socket_options:
                        sock.setsockopt(*option)
                return SyncStream(sock)
            except OSError:
                last_error = True
                if sock is not None:
                    sock.close()
        raise httpcore.ConnectError("Pinned provider connection failed" if last_error else "No pinned provider IPs")


class _PinnedHTTPTransport(httpx.HTTPTransport):
    """httpx transport whose TCP backend cannot perform a fresh, attacker-controlled DNS lookup."""

    def __init__(self, host: str, addresses: tuple[str, ...]):
        super().__init__(verify=True, trust_env=False, retries=0)
        self._pool.close()
        self._pool = httpcore.ConnectionPool(
            ssl_context=ssl.create_default_context(),
            max_connections=4,
            max_keepalive_connections=0,
            keepalive_expiry=0,
            network_backend=_PinnedNetworkBackend(host, addresses),
        )


def _safe_provider_post_json(
    url: str,
    *,
    host: str,
    addresses: tuple[str, ...],
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout_seconds: float,
) -> tuple[int, dict[str, Any], int | None]:
    """POST bounded JSON to a pre-validated, IP-pinned HTTPS endpoint, never following redirects."""
    timeout = min(max(float(timeout_seconds or 20), 1.0), MAX_PROVIDER_TIMEOUT_SECONDS)
    transport = _PinnedHTTPTransport(host, addresses)
    try:
        with httpx.Client(
            transport=transport,
            timeout=httpx.Timeout(timeout),
            follow_redirects=False,
            trust_env=False,
        ) as client:
            with client.stream("POST", url, headers=headers, json=payload) as response:
                status = response.status_code
                retry_after = None
                retry_value = response.headers.get("Retry-After", "").strip()
                if re.fullmatch(r"\d{1,5}", retry_value):
                    retry_after = min(int(retry_value), 86400)
                if 300 <= status < 400:
                    raise PersonalInterpretationError(
                        "Provider redirects are disabled",
                        category="redirect_blocked",
                        upstream_status=status,
                    )
                content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
                if content_type != "application/json":
                    raise PersonalInterpretationError(
                        "Provider must return application/json",
                        category="invalid_content_type",
                        upstream_status=status,
                    )
                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > MAX_PROVIDER_RESPONSE_BYTES:
                        raise PersonalInterpretationError(
                            "Provider response exceeded the maximum size",
                            category="response_too_large",
                            upstream_status=status,
                        )
                    chunks.append(chunk)
                try:
                    decoded = json.loads(b"".join(chunks).decode("utf-8"))
                except (UnicodeDecodeError, ValueError):
                    raise PersonalInterpretationError(
                        "Provider returned invalid JSON",
                        category="invalid_response",
                        upstream_status=status,
                    ) from None
                if not isinstance(decoded, dict):
                    raise PersonalInterpretationError(
                        "Provider returned an unexpected JSON structure",
                        category="invalid_response",
                        upstream_status=status,
                    )
                return status, decoded, retry_after
    except PersonalInterpretationError:
        raise
    except httpx.TimeoutException:
        raise PersonalInterpretationError("Provider request timed out", category="timeout") from None
    except (httpx.HTTPError, OSError, ValueError):
        raise PersonalInterpretationError("Provider connection failed", category="connection_error") from None
    finally:
        transport.close()


def _raise_safe_provider_status(status: int, retry_after: int | None) -> None:
    if status < 400:
        return
    if status == 401:
        category = "provider_unauthorized"
    elif status == 403:
        category = "provider_forbidden"
    elif status == 404:
        category = "provider_model_not_found"
    elif status == 429:
        category = "provider_rate_limited"
    elif status == 400:
        category = "provider_invalid_request"
    elif status >= 500:
        category = "provider_unavailable"
    else:
        category = "provider_http_error"
    raise PersonalInterpretationError(
        "External AI provider returned an HTTP error",
        category=category,
        upstream_status=status,
        retry_after_seconds=retry_after,
    )


def _parse_personal_interpretation(content: Any) -> PersonalInterpretation:
    if not isinstance(content, str) or not content.strip():
        raise PersonalInterpretationError("Provider returned an empty interpretation", category="invalid_response")
    try:
        decoded = json.loads(content)
    except (TypeError, ValueError):
        raise PersonalInterpretationError("Provider returned invalid interpretation JSON", category="invalid_response") from None
    try:
        return PersonalInterpretation.model_validate(decoded)
    except ValidationError as exc:
        raise PersonalInterpretationError(
            "Provider returned an unexpected interpretation schema",
            category="invalid_schema",
            quality_check=_schema_quality_check(exc),
        ) from None


def _openai_compatible_content(
    *,
    trends: dict[str, Any] | None,
    model: str,
    api_key: str,
    base_url: str,
    timeout_seconds: float,
    test_only: bool = False,
) -> tuple[str, str]:
    normalized, host, addresses = _resolve_public_endpoint(base_url)
    endpoint = normalized.rstrip("/") + "/chat/completions"
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                'Верни только JSON {"ok":true}. Это проверка подключения; данных пользователя нет.'
                if test_only
                else json.dumps(_model_input(trends or {}), ensure_ascii=False, separators=(",", ":"))
            ),
        },
    ]
    request_body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "personal_interpretation",
                "strict": True,
                "schema": PERSONAL_INTERPRETATION_JSON_SCHEMA,
            },
        },
        "max_tokens": 900 if not test_only else 64,
        "temperature": 0.7,
    }
    status, payload, retry_after = _safe_provider_post_json(
        endpoint,
        host=host,
        addresses=addresses,
        headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
        payload=request_body,
        timeout_seconds=timeout_seconds,
    )
    schema_supported = True
    if status == 400 and not test_only:
        # Some OpenAI-compatible providers do not implement json_schema; retry once as json_object.
        request_body = {
            **request_body,
            "messages": [
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT
                    + "\n\nВерни один строгий JSON-объект со всеми ключами схемы: "
                    + "headline, summary, positive_signals, caution_signals, practical_next_steps, data_limitations. "
                    + "Не добавляй дополнительных ключей.",
                },
                messages[1],
            ],
            "response_format": {"type": "json_object"},
        }
        status, payload, retry_after = _safe_provider_post_json(
            endpoint,
            host=host,
            addresses=addresses,
            headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
            payload=request_body,
            timeout_seconds=timeout_seconds,
        )
        schema_supported = False
    elif status == 400 and test_only:
        # Connection tests intentionally use json_object and contain no personal data.
        raise PersonalInterpretationError(
            "Provider rejected the connection test request",
            category="provider_invalid_request",
            upstream_status=status,
            retry_after_seconds=retry_after,
        )

    _raise_safe_provider_status(status, retry_after)
    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise PersonalInterpretationError("Provider returned an unexpected response", category="invalid_response") from None
    return content, "json_schema" if schema_supported else "json_object"


def _anthropic_content(
    *,
    trends: dict[str, Any] | None,
    model: str,
    api_key: str,
    timeout_seconds: float,
    test_only: bool = False,
) -> str:
    _, host, addresses = _resolve_public_endpoint("https://api.anthropic.com/")
    message = (
        'Верни только JSON {"ok":true}. Это проверка подключения; данных пользователя нет.'
        if test_only
        else json.dumps(_model_input(trends or {}), ensure_ascii=False, separators=(",", ":"))
    )
    status, payload, retry_after = _safe_provider_post_json(
        ANTHROPIC_MESSAGES_URL,
        host=host,
        addresses=addresses,
        headers={
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        },
        payload={
            "model": model,
            "max_tokens": 64 if test_only else 900,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": message}],
        },
        timeout_seconds=timeout_seconds,
    )
    _raise_safe_provider_status(status, retry_after)
    try:
        blocks = payload["content"]
        return "\n".join(block["text"] for block in blocks if isinstance(block, dict) and block.get("type") == "text")
    except (KeyError, TypeError):
        raise PersonalInterpretationError("Provider returned an unexpected response", category="invalid_response") from None


def generate_custom_personal_interpretation(
    trends: dict[str, Any],
    *,
    provider: str,
    api_key: str,
    model: str,
    base_url: str | None = None,
    timeout_seconds: float = 20.0,
) -> PersonalInterpretation:
    """Generate and validate an aggregate-only interpretation with the user's selected provider."""
    if not isinstance(api_key, str) or not api_key or len(api_key) > 512:
        raise PersonalInterpretationError("Provider key is missing or invalid", category="invalid_configuration")
    if not isinstance(model, str) or not model.strip() or len(model) > 128:
        raise PersonalInterpretationError("Provider model is missing or invalid", category="invalid_configuration")
    if provider == "openai_compatible":
        if not base_url:
            raise PersonalInterpretationError("Provider URL is missing", category="invalid_configuration")
        content, _ = _openai_compatible_content(
            trends=trends,
            model=model,
            api_key=api_key,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
        )
    elif provider == "anthropic":
        content = _anthropic_content(
            trends=trends,
            model=model,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
        )
    else:
        raise PersonalInterpretationError("Unsupported provider", category="invalid_configuration")

    analysis = _parse_personal_interpretation(content)
    _validate_interpretation_claims(analysis, trends)
    return analysis


def test_custom_personal_ai_provider(
    *,
    provider: str,
    api_key: str,
    model: str,
    base_url: str | None = None,
    timeout_seconds: float = 20.0,
) -> None:
    """Test credentials with a generic prompt only; never include user trends or identifiers."""
    if not isinstance(api_key, str) or not api_key or len(api_key) > 512:
        raise PersonalInterpretationError("Provider key is missing or invalid", category="invalid_configuration")
    if not isinstance(model, str) or not model.strip() or len(model) > 128:
        raise PersonalInterpretationError("Provider model is missing or invalid", category="invalid_configuration")

    if provider == "openai_compatible":
        if not base_url:
            raise PersonalInterpretationError("Provider URL is missing", category="invalid_configuration")
        content, _ = _openai_compatible_content(
            trends=None,
            model=model,
            api_key=api_key,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            test_only=True,
        )
    elif provider == "anthropic":
        content = _anthropic_content(
            trends=None,
            model=model,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            test_only=True,
        )
    else:
        raise PersonalInterpretationError("Unsupported provider", category="invalid_configuration")

    try:
        decoded = json.loads(content)
    except (TypeError, ValueError):
        raise PersonalInterpretationError("Provider test returned invalid JSON", category="invalid_response") from None
    if not isinstance(decoded, dict) or decoded.get("ok") is not True:
        raise PersonalInterpretationError("Provider test response did not match expected shape", category="invalid_response")
