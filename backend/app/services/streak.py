"""Pure policy for spending a weekly streak rest-day credit."""
from datetime import date, timedelta


def rest_day_decision(
    *,
    today: date,
    used_dates: set[date],
    has_activity_today: bool,
    previous_day_credited: bool,
) -> tuple[bool, str | None]:
    """Allow a single manual rest day per local week, only to continue an existing streak."""
    week_start = today - timedelta(days=today.weekday())
    this_week = {
        day for day in used_dates
        if week_start <= day < week_start + timedelta(days=7)
    }
    if today in this_week:
        return False, "День отдыха уже использован сегодня."
    if this_week:
        return False, "Можно использовать только один день отдыха за календарную неделю."
    if has_activity_today:
        return False, "День отдыха можно активировать только в день без тренировок."
    if not previous_day_credited:
        return False, "Вчера не было квалифицирующего дня или дня отдыха — серию нечего продлевать."
    return True, None
