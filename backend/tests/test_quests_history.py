from datetime import datetime
from types import SimpleNamespace

from app.services.quests import (
    _best_activity_training_days,
    _cond_first_three_day_week,
    _cond_record_duration,
    _max_goal_streak,
    _quest_status,
)


def activity(day, activity_id, duration, *, tss=25.0, is_manual=False):
    return SimpleNamespace(
        id=activity_id,
        start_date_local=datetime.fromisoformat(day),
        start_date=datetime.fromisoformat(day),
        moving_time=duration,
        tss=tss,
        training_load=tss,
        is_manual=is_manual,
    )


def summary(week_start, ratio=1.0, *, finalized=True):
    return SimpleNamespace(
        week_start=datetime.fromisoformat(week_start),
        completion_ratio=ratio,
        finalized=finalized,
        training_days=0,
    )


def test_record_duration_is_evaluated_across_available_history():
    activities = [
        activity("2019-01-01T08:00:00", 1, 3600),
        activity("2019-01-03T08:00:00", 2, 4000),
        activity("2019-01-05T08:00:00", 3, 4200),
        activity("2019-01-07T08:00:00", 4, 5000),
    ]

    assert _cond_record_duration({"all_acts": activities})


def test_goal_streak_uses_best_historical_run_not_only_latest_run():
    summaries = [
        summary("2018-01-01T00:00:00"),
        summary("2018-01-08T00:00:00"),
        summary("2018-01-15T00:00:00"),
        summary("2018-02-05T00:00:00", ratio=0.4),
    ]

    assert _max_goal_streak(summaries) == 3


def test_activity_data_fills_training_days_when_historical_summary_is_missing():
    activities = [
        activity("2020-04-06T08:00:00", 1, 1800),
        activity("2020-04-07T08:00:00", 2, 1800),
        activity("2020-04-08T08:00:00", 3, 1800),
    ]

    assert _best_activity_training_days(activities) == 3


def test_achievement_status_comes_from_progress_not_xp_event_presence():
    quest = {"slug": "goal_met"}

    assert _quest_status(quest, {"current": 40, "target": 100}) == "open"
    assert _quest_status(quest, {"current": 100, "target": 100}) == "earned"
    assert _quest_status({"slug": "power_record_20m", "requires": "power"}, None) == "unavailable"

def test_three_day_achievement_can_be_recomputed_from_activity_history():
    activities = [
        activity("2020-04-06T08:00:00", 1, 1800),
        activity("2020-04-07T08:00:00", 2, 1800),
        activity("2020-04-08T08:00:00", 3, 1800),
    ]

    assert _cond_first_three_day_week({"weeks": [], "acts": activities, "all_acts": activities})
