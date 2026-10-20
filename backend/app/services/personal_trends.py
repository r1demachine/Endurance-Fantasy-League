"""Transparent, non-medical trends from a user's saved check-ins and training history.

Values are grouped by the athlete's local calendar day. Missing source values remain
missing; no zeros or population norms are invented. The service has no LLM dependency.
"""
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from math import isfinite
from statistics import mean, median
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


MIN_DAYS_PER_COMPARISON = 3
COMPARISON_WINDOW_DAYS = 7
MIN_PAIRED_LOAD_RPE_DAYS = 8
MIN_DAYS_PER_LOAD_GROUP = 3


def resolve_timezone(timezone_name: str | None) -> tuple[ZoneInfo, bool]:
    """Return a valid IANA zone; report when the stored value must fall back to UTC."""
    try:
        return ZoneInfo(timezone_name or "UTC"), False
    except (ZoneInfoNotFoundError, TypeError, ValueError):
        return ZoneInfo("UTC"), True


def local_today(timezone_name: str | None, now: datetime | None = None) -> date:
    """Current date in the user's configured timezone."""
    zone, _ = resolve_timezone(timezone_name)
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant.astimezone(zone).date()


def activity_local_date(activity, zone: ZoneInfo) -> date | None:
    """Prefer Intervals/local activity time; interpret a missing local timestamp as UTC."""
    local_stamp = getattr(activity, "start_date_local", None)
    if local_stamp is not None:
        if local_stamp.tzinfo is None:
            return local_stamp.date()
        return local_stamp.astimezone(zone).date()

    stamp = getattr(activity, "start_date", None)
    if stamp is None:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(zone).date()


def _as_date(value) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value is None:
        return None
    try:
        # Wellness.date is stored as an ISO calendar date string.
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _number(value) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if isfinite(result) else None


def _bounded_number(value, minimum: float, maximum: float) -> float | None:
    result = _number(value)
    if result is None or result < minimum or result > maximum:
        return None
    return result


def _nonnegative_number(value) -> float | None:
    result = _number(value)
    if result is None or result < 0:
        return None
    return result


def _is_user_row(row, user_id: int) -> bool:
    return getattr(row, "user_id", user_id) == user_id


def _dates_between(start: date, end: date) -> list[date]:
    result = []
    current = start
    while current <= end:
        result.append(current)
        current += timedelta(days=1)
    return result


def _daily_stats(values_by_day: dict[date, list[float]], start: date, end: date) -> dict:
    daily_means: list[float] = []
    sample_count = 0
    for day in _dates_between(start, end):
        values = values_by_day.get(day, [])
        if not values:
            continue
        daily_means.append(mean(values))
        sample_count += len(values)

    return {
        "mean": round(mean(daily_means), 2) if daily_means else None,
        "days_with_data": len(daily_means),
        "samples": sample_count,
    }


def _metric_result(
    *,
    key: str,
    label: str,
    unit: str,
    source: str,
    values_by_day: dict[date, list[float]],
    current_start: date,
    current_end: date,
    previous_start: date,
    previous_end: date,
    stability_tolerance: float,
    source_field: str | None = None,
) -> dict:
    current = _daily_stats(values_by_day, current_start, current_end)
    previous = _daily_stats(values_by_day, previous_start, previous_end)
    enough_data = (
        current["days_with_data"] >= MIN_DAYS_PER_COMPARISON
        and previous["days_with_data"] >= MIN_DAYS_PER_COMPARISON
    )

    change = None
    trend = "insufficient_data"
    if enough_data:
        change = round(current["mean"] - previous["mean"], 2)
        if abs(change) < stability_tolerance:
            trend = "stable"
        elif change > 0:
            trend = "upward"
        else:
            trend = "downward"

    result = {
        "key": key,
        "label": label,
        "source": source,
        "unit": unit,
        "status": "ready" if enough_data else "insufficient_data",
        "trend": trend,
        "current": current,
        "previous": previous,
        "change": change,
        "stability_tolerance": stability_tolerance,
        "minimum_days_required_per_period": MIN_DAYS_PER_COMPARISON,
        "comparison_rule": (
            "Среднее арифметическое дневных средних: каждая локальная календарная дата "
            "имеет одинаковый вес. Порог стабильности — только правило отображения, "
            "не статистическая или медицинская граница."
        ),
    }
    if source_field is not None:
        result["source_field"] = source_field
    return result


def _load_rpe_relationship(
    *,
    activity_days: dict[date, list],
    rpe_by_day: dict[date, list[float]],
    period_start: date,
    period_end: date,
) -> dict:
    paired_days: list[tuple[date, float, float]] = []
    days_with_missing_tss = 0

    for day in _dates_between(period_start, period_end):
        day_activities = activity_days.get(day, [])
        if not day_activities:
            continue
        rpe_values = rpe_by_day.get(day, [])
        if not rpe_values:
            continue

        loads = [_nonnegative_number(getattr(activity, "tss", None)) for activity in day_activities]
        # A daily total is not complete if even one recorded session has no usable TSS.
        if any(load is None for load in loads):
            days_with_missing_tss += 1
            continue
        paired_days.append((day, sum(loads), mean(rpe_values)))

    common = {
        "key": "daily_tss_vs_rpe",
        "status": "insufficient_data",
        "period": {"start": period_start.isoformat(), "end": period_end.isoformat()},
        "paired_days": len(paired_days),
        "days_excluded_due_to_missing_tss": days_with_missing_tss,
        "median_daily_tss": None,
        "lower_or_equal_load": {"days": 0, "mean_daily_rpe": None},
        "above_median_load": {"days": 0, "mean_daily_rpe": None},
        "rpe_difference_high_minus_low": None,
        "minimum_paired_days": MIN_PAIRED_LOAD_RPE_DAYS,
        "minimum_days_per_group": MIN_DAYS_PER_LOAD_GROUP,
        "method": (
            "Сравнивается средний RPE по локальным дням с полной суммой TSS всех "
            "сохранённых тренировок в этот день. Группы делятся по медиане TSS "
            "среди парных дней: ниже или равно медиане и выше медианы."
        ),
        "limitations": [
            "Это описательная совместная динамика, а не доказательство причинно-следственной связи.",
            "День исключается, если хотя бы у одной сохранённой тренировки этого дня нет корректного TSS.",
            "Полнота последней синхронизации Intervals.icu этим расчётом не проверяется.",
        ],
    }

    if not paired_days:
        common["reason"] = "Нет локальных дней одновременно с RPE и полным TSS всех тренировок."
        return common

    threshold = median(pair[1] for pair in paired_days)
    lower = [pair[2] for pair in paired_days if pair[1] <= threshold]
    higher = [pair[2] for pair in paired_days if pair[1] > threshold]
    common["median_daily_tss"] = round(threshold, 2)
    common["lower_or_equal_load"] = {
        "days": len(lower),
        "mean_daily_rpe": round(mean(lower), 2) if lower else None,
    }
    common["above_median_load"] = {
        "days": len(higher),
        "mean_daily_rpe": round(mean(higher), 2) if higher else None,
    }

    if (
        len(paired_days) < MIN_PAIRED_LOAD_RPE_DAYS
        or len(lower) < MIN_DAYS_PER_LOAD_GROUP
        or len(higher) < MIN_DAYS_PER_LOAD_GROUP
    ):
        common["reason"] = (
            "Нужно не менее 8 парных дней и не менее 3 дней в каждой группе нагрузки."
        )
        return common

    difference = round(mean(higher) - mean(lower), 2)
    common["status"] = "ready"
    common["rpe_difference_high_minus_low"] = difference
    common["interpretation"] = (
        f"В дни с TSS выше медианы средний дневной RPE составил {mean(higher):.2f}; "
        f"в дни с TSS ниже или равно медиане — {mean(lower):.2f}. "
        f"Разница: {difference:+.2f} пункта RPE по {len(paired_days)} парным дням."
    )
    return common


def build_personal_trends(
    *,
    user_id: int,
    timezone_name: str | None,
    today: date,
    days: int,
    morning_checkins,
    wellness_records,
    activities,
    activity_checkins,
) -> dict:
    """Build a machine-readable, source-backed comparison without recommendations or LLM."""
    if days < 14 or days > 90:
        raise ValueError("days must be between 14 and 90")

    zone, timezone_fallback = resolve_timezone(timezone_name)
    period_start = today - timedelta(days=days - 1)
    current_start = today - timedelta(days=COMPARISON_WINDOW_DAYS - 1)
    previous_start = today - timedelta(days=2 * COMPARISON_WINDOW_DAYS - 1)
    previous_end = today - timedelta(days=COMPARISON_WINDOW_DAYS)

    metrics: dict[str, dict[date, list[float]]] = {
        "readiness": defaultdict(list),
        "fatigue": defaultdict(list),
        "soreness": defaultdict(list),
        "wellbeing": defaultdict(list),
        "sleep_quality": defaultdict(list),
        "sleep_duration_hours": defaultdict(list),
        "rpe": defaultdict(list),
        "harder_than_expected_share": defaultdict(list),
    }

    period_dates = set(_dates_between(period_start, today))
    morning_status_by_day: dict[date, str] = {}
    completed_days: set[date] = set()

    for row in morning_checkins:
        if not _is_user_row(row, user_id):
            continue
        day = _as_date(getattr(row, "local_date", None))
        if day not in period_dates:
            continue
        status = str(getattr(row, "status", "") or "")
        if status in {"pending", "completed", "skipped"}:
            morning_status_by_day[day] = status
        if status != "completed":
            continue
        completed_days.add(day)
        for field in ("readiness", "fatigue", "soreness", "wellbeing"):
            value = _bounded_number(getattr(row, field, None), 1, 5)
            if value is not None:
                metrics[field][day].append(value)

    filtered_wellness = []
    for row in wellness_records:
        if not _is_user_row(row, user_id):
            continue
        day = _as_date(getattr(row, "date", None))
        if day in period_dates:
            filtered_wellness.append((day, row))

    # Never mix Intervals fields that may use different scales within one trend.
    if any(_nonnegative_number(getattr(row, "sleep_score", None)) is not None for _, row in filtered_wellness):
        sleep_quality_field = "sleep_score"
        sleep_quality_tolerance = 2.0
    elif any(_nonnegative_number(getattr(row, "sleep_quality", None)) is not None for _, row in filtered_wellness):
        sleep_quality_field = "sleep_quality"
        sleep_quality_tolerance = 0.5
    else:
        sleep_quality_field = "sleep_score"
        sleep_quality_tolerance = 2.0

    wellness_record_days: set[date] = set()
    sleep_score_days: set[date] = set()
    sleep_duration_days: set[date] = set()
    for day, row in filtered_wellness:
        wellness_record_days.add(day)
        quality = _nonnegative_number(getattr(row, sleep_quality_field, None))
        if quality is not None:
            metrics["sleep_quality"][day].append(quality)
            sleep_score_days.add(day)
        duration = _nonnegative_number(getattr(row, "sleep_secs", None))
        if duration is not None:
            metrics["sleep_duration_hours"][day].append(duration / 3600.0)
            sleep_duration_days.add(day)

    activity_days: dict[date, list] = defaultdict(list)
    activity_by_id: dict[int, object] = {}
    for activity in activities:
        if not _is_user_row(activity, user_id):
            continue
        day = activity_local_date(activity, zone)
        activity_id = getattr(activity, "id", None)
        if day not in period_dates or activity_id is None:
            continue
        activity_by_id[activity_id] = activity
        activity_days[day].append(activity)

    rpe_by_day: dict[date, list[float]] = defaultdict(list)
    expectation_by_day: dict[date, list[float]] = defaultdict(list)
    rpe_activity_ids: set[int] = set()
    expectation_activity_ids: set[int] = set()

    for checkin in activity_checkins:
        if not _is_user_row(checkin, user_id):
            continue
        activity_id = getattr(checkin, "activity_id", None)
        activity = activity_by_id.get(activity_id)
        if activity is None:
            continue
        day = activity_local_date(activity, zone)
        rpe = _bounded_number(getattr(checkin, "rpe", None), 1, 10)
        if rpe is not None:
            rpe_by_day[day].append(rpe)
            rpe_activity_ids.add(activity_id)

        expectation = getattr(checkin, "load_expectation", None)
        if expectation in {"easier", "as_expected", "harder"}:
            expectation_by_day[day].append(100.0 if expectation == "harder" else 0.0)
            expectation_activity_ids.add(activity_id)

    # Multiple activities on one date are summarized within the date; dates have equal weight.
    for day, answers in expectation_by_day.items():
        metrics["harder_than_expected_share"][day].append(mean(answers))
    for day, answers in rpe_by_day.items():
        metrics["rpe"][day].extend(answers)

    metric_definitions = [
        ("readiness", "Готовность к тренировке", "пункта по шкале 1–5", "ручной утренний чек-ин", 0.25, None),
        ("fatigue", "Усталость", "пункта по шкале 1–5", "ручной утренний чек-ин", 0.25, None),
        ("soreness", "Мышечная болезненность", "пункта по шкале 1–5", "ручной утренний чек-ин", 0.25, None),
        ("wellbeing", "Общее самочувствие", "пункта по шкале 1–5", "ручной утренний чек-ин", 0.25, None),
        (
            "sleep_quality",
            "Качество сна (автоматический показатель)",
            "балла по шкале источника",
            "Intervals.icu Wellness",
            sleep_quality_tolerance,
            sleep_quality_field,
        ),
        ("sleep_duration_hours", "Продолжительность сна", "часа", "Intervals.icu Wellness", 0.25, "sleep_secs"),
        ("rpe", "Воспринимаемая тяжесть тренировки", "пункта RPE по шкале 1–10", "ручной послетренировочный чек-ин", 0.5, None),
        (
            "harder_than_expected_share",
            "Доля занятий тяжелее ожиданий",
            "% занятий с указанным сравнением",
            "ручной послетренировочный чек-ин",
            10.0,
            "load_expectation",
        ),
    ]

    observations = []
    for key, label, unit, source, tolerance, source_field in metric_definitions:
        observations.append(_metric_result(
            key=key,
            label=label,
            unit=unit,
            source=source,
            values_by_day=metrics[key],
            current_start=current_start,
            current_end=today,
            previous_start=previous_start,
            previous_end=previous_end,
            stability_tolerance=tolerance,
            source_field=source_field,
        ))

    completed_set = {day for day, status in morning_status_by_day.items() if status == "completed"}
    skipped_dates = sorted(day for day, status in morning_status_by_day.items() if status == "skipped")
    pending_dates = sorted(day for day, status in morning_status_by_day.items() if status == "pending")
    no_record_dates = sorted(period_dates - set(morning_status_by_day))
    no_completed_dates = sorted(period_dates - completed_set)

    total_activities = len(activity_by_id)
    tss_activity_ids = {
        activity_id
        for activity_id, activity in activity_by_id.items()
        if _nonnegative_number(getattr(activity, "tss", None)) is not None
    }
    no_tss_activity_count = total_activities - len(tss_activity_ids)
    no_rpe_activity_count = total_activities - len(rpe_activity_ids)
    no_expectation_activity_count = total_activities - len(expectation_activity_ids)

    relationship = _load_rpe_relationship(
        activity_days=activity_days,
        rpe_by_day=rpe_by_day,
        period_start=period_start,
        period_end=today,
    )

    data_gaps: list[str] = []
    if skipped_dates:
        data_gaps.append(f"Утренний чек-ин явно пропущен за {len(skipped_dates)} дн.")
    if pending_dates:
        data_gaps.append(f"Есть незавершённый утренний чек-ин за {len(pending_dates)} дн.")
    if no_record_dates:
        data_gaps.append(f"Нет записи о статусе утреннего чек-ина за {len(no_record_dates)} дн.")
    if not sleep_score_days:
        data_gaps.append("В выбранном периоде нет пригодных автоматических значений качества сна.")
    elif len(sleep_score_days) < days:
        data_gaps.append(
            f"Автоматическое качество сна доступно за {len(sleep_score_days)} из {days} календарных дней."
        )
    if not sleep_duration_days:
        data_gaps.append("В выбранном периоде нет сохранённых значений продолжительности сна.")
    elif len(sleep_duration_days) < days:
        data_gaps.append(
            f"Продолжительность сна доступна за {len(sleep_duration_days)} из {days} календарных дней."
        )
    if no_tss_activity_count:
        data_gaps.append(
            f"У {no_tss_activity_count} из {total_activities} сохранённых тренировок нет пригодного значения TSS."
        )
    if no_rpe_activity_count:
        data_gaps.append(
            f"Нет послетренировочного RPE для {no_rpe_activity_count} из {total_activities} сохранённых тренировок в периоде."
        )
    if no_expectation_activity_count:
        data_gaps.append(
            f"Для {no_expectation_activity_count} из {total_activities} тренировок не указано сравнение нагрузки с ожиданиями."
        )
    if relationship["status"] != "ready":
        data_gaps.append(
            "Связь TSS и RPE не рассчитана: " + relationship.get("reason", "недостаточно парных дней.")
        )
    if timezone_fallback:
        data_gaps.append("В настройках указан некорректный часовой пояс; для расчёта использован UTC.")
    data_gaps.append(
        "Полнота и актуальность последней синхронизации Intervals.icu не проверяются; "
        "расчёты относятся к данным, уже сохранённым в EFL."
    )

    any_ready_metric = any(item["status"] == "ready" for item in observations)
    return {
        "status": "ready" if any_ready_metric or relationship["status"] == "ready" else "insufficient_data",
        "timezone": zone.key,
        "period": {
            "start": period_start.isoformat(),
            "end": today.isoformat(),
            "days": days,
        },
        "comparison_windows": {
            "current": {"start": current_start.isoformat(), "end": today.isoformat(), "days": 7},
            "previous": {"start": previous_start.isoformat(), "end": previous_end.isoformat(), "days": 7},
        },
        "observations": observations,
        "training_load_relationship": relationship,
        "coverage": {
            "morning_checkins": {
                "period_days": days,
                "completed_days": len(completed_set),
                "skipped_days": len(skipped_dates),
                "pending_days": len(pending_dates),
                "days_without_completed_checkin": len(no_completed_dates),
                "no_record_days": len(no_record_dates),
                "skipped_dates": [day.isoformat() for day in skipped_dates],
                "pending_dates": [day.isoformat() for day in pending_dates],
                "no_record_dates": [day.isoformat() for day in no_record_dates],
            },
            "sleep": {
                "source": "Intervals.icu Wellness",
                "quality_field_used": sleep_quality_field,
                "days_with_wellness_record": len(wellness_record_days),
                "days_with_quality_value": len(sleep_score_days),
                "days_with_duration_value": len(sleep_duration_days),
            },
            "activities": {
                "activities_in_period": total_activities,
                "activities_with_tss": len(tss_activity_ids),
                "activities_without_tss": no_tss_activity_count,
                "activities_with_rpe": len(rpe_activity_ids),
                "activities_without_rpe": no_rpe_activity_count,
                "activities_with_load_expectation": len(expectation_activity_ids),
                "activities_without_load_expectation": no_expectation_activity_count,
                "days_with_activities": len(activity_days),
            },
        },
        "data_gaps": data_gaps,
        "methodology": [
            "Утренние субъективные оценки берутся только из завершённых ручных чек-инов; статусы pending и skipped не являются оценками.",
            "Автоматические данные сна из Wellness не смешиваются с ручными оценками самочувствия.",
            "Для трендов сравниваются последние 7 локальных календарных дней и предшествующие 7; нужно минимум 3 дня с реальными значениями в каждом окне.",
            "При нескольких тренировках в один локальный день их RPE усредняется внутри дня; в недельном среднем каждый день имеет одинаковый вес.",
            "Пропущенные значения исключаются из расчёта и отдельно отражаются в покрытии; нули и средние вместо пропусков не подставляются.",
            "Связь TSS и RPE описательная, основана на днях с полными значениями и не доказывает причинность.",
            "Порог стабильности — только правило отображения изменений, а не статистическая или медицинская граница.",
        ],
        "disclaimer": "Это описательная тренировочная аналитика, не медицинская оценка, диагноз или прогноз.",
    }
