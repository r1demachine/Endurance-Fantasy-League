from datetime import date, timedelta

from app.services import deload as D
from app.services import xp_v6 as X6


def test_manual_deload_requires_both_immediately_previous_weeks():
    baseline = 400.0
    assert D.previous_two_weeks_qualify([360.0, 400.0], baseline)
    assert not D.previous_two_weeks_qualify([360.0], baseline)
    assert not D.previous_two_weeks_qualify([None, 400.0], baseline)
    assert not D.previous_two_weeks_qualify([359.99, 400.0], baseline)


def test_manual_deload_blocks_pause_high_load_and_manual_decision():
    current = date(2026, 10, 12)
    common = dict(
        current_week_start=current, current_load=320.0, baseline=400.0,
        previous_two_loads=[400.0, 400.0], last_deload_week_start=None,
        paused=False, manual_decision=False,
    )
    assert D.manual_deload_block_reason(**common) is None
    assert "85%" in D.manual_deload_block_reason(**{**common, "current_load": 340.0})
    assert "паузе" in D.manual_deload_block_reason(**{**common, "paused": True})
    assert "решение" in D.manual_deload_block_reason(**{**common, "manual_decision": True})


def test_deload_cooldown_applies_to_manual_and_automatic_weeks():
    current = date(2026, 10, 12)
    assert not D.cooldown_passed(current, current - timedelta(weeks=2))
    assert D.cooldown_passed(current, current - timedelta(weeks=3))
    reason = D.manual_deload_block_reason(
        current_week_start=current, current_load=300.0, baseline=400.0,
        previous_two_loads=[400.0, 400.0],
        last_deload_week_start=current - timedelta(weeks=2),
        paused=False, manual_decision=False,
    )
    assert "3 недели" in reason


def test_suggestion_uses_actual_range_or_day_four_projection():
    baseline = 400.0
    current = date(2026, 10, 12)
    common = dict(
        current_week_start=current, baseline=baseline, previous_two_loads=[400.0, 380.0],
        last_deload_week_start=None, paused=False, manual_decision=False, already_deload=False,
    )
    assert D.suggestion_is_appropriate(current_load=300.0, current_day_index=0, **common)
    assert D.suggestion_is_appropriate(current_load=180.0, current_day_index=3, **common)
    assert not D.suggestion_is_appropriate(current_load=180.0, current_day_index=2, **common)
    assert not D.suggestion_is_appropriate(current_load=300.0, current_day_index=3, **{**common, "paused": True})


def test_deload_goal_xp_is_capped_at_the_85_percent_floor():
    assert X6.effective_goal_ratio(0.10, True) == 0.85
    assert X6.effective_goal_ratio(0.95, True) == 0.85
    assert X6.effective_goal_ratio(0.95, False) == 0.95
    assert X6.weekly_goal_xp(X6.effective_goal_ratio(0.10, True)) == X6.weekly_goal_xp(0.85)


def test_automatic_rule_now_requires_two_previous_weeks():
    assert X6.is_deload_week(320.0, 400.0, [400.0, 360.0])
    assert not X6.is_deload_week(320.0, 400.0, [400.0])
    assert not X6.is_deload_week(344.0, 400.0, [400.0, 360.0])
    assert not X6.is_deload_week(200.0, 400.0, [400.0, 360.0])
