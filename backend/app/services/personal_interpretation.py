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
