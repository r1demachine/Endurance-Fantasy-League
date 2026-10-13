"""Pure rules for manual and automatic Deload decisions."""
from __future__ import annotations

from datetime import date, timedelta

from . import xp_v6 as X6

DELOAD_COOLDOWN_WEEKS = 3


def cooldown_passed(current_week_start: date, last_deload_week_start: date | None) -> bool:
    """A new Deload is allowed when the previous one was at least three weeks ago."""
    if last_deload_week_start is None:
        return True
    return (current_week_start - last_deload_week_start).days >= 7 * DELOAD_COOLDOWN_WEEKS


def previous_two_weeks_qualify(previous_two_loads: list[float | None], baseline: float | None) -> bool:
    """Both immediately preceding calendar weeks must be complete and >=90% baseline.
    None marks a paused week, which breaks the qualifying streak.
    """
    if not baseline or baseline <= 0 or len(previous_two_loads) != 2:
        return False
    return all(load is not None and float(load) >= X6.DELOAD_PREV_RATIO * baseline for load in previous_two_loads)


def manual_deload_block_reason(
    *,
    current_week_start: date,
    current_load: float,
    baseline: float | None,
    previous_two_loads: list[float | None],
    last_deload_week_start: date | None,
    paused: bool,
    manual_decision: bool,
) -> str | None:
    if paused:
        return "Неделя уже на паузе."
    if not baseline or baseline <= 0:
        return "Недостаточно истории для расчёта baseline."
    if current_load / baseline > X6.DELOAD_MAX_RATIO + 1e-9:
        return "Текущая нагрузка уже выше 85% baseline."
    if manual_decision:
        return "Вы уже приняли решение по Deload на этой неделе."
    if not previous_two_weeks_qualify(previous_two_loads, baseline):
        return "Предыдущие 2 завершённые недели должны быть не ниже 90% baseline."
    if not cooldown_passed(current_week_start, last_deload_week_start):
        return "После последнего Deload должны пройти 3 недели."
    return None


def suggestion_is_appropriate(
    *,
    current_week_start: date,
    current_load: float,
    baseline: float | None,
    previous_two_loads: list[float | None],
    current_day_index: int,
    last_deload_week_start: date | None,
    paused: bool,
    manual_decision: bool,
    already_deload: bool,
) -> bool:
    """Suggest when actual load is in range, or on day four if projected load is in range."""
    if (
        not baseline or baseline <= 0 or paused or manual_decision or already_deload
        or not cooldown_passed(current_week_start, last_deload_week_start)
        or not previous_two_weeks_qualify(previous_two_loads, baseline)
    ):
        return False
    ratio = max(0.0, float(current_load or 0.0)) / baseline
    if X6.DELOAD_MIN_RATIO <= ratio <= X6.DELOAD_MAX_RATIO:
        return True
    if current_day_index < 3:
        return False
    days_passed = current_day_index + 1
    projected_ratio = (max(0.0, float(current_load or 0.0)) * 7.0 / days_passed) / baseline
    return X6.DELOAD_MIN_RATIO <= projected_ratio <= X6.DELOAD_MAX_RATIO
