from datetime import date, timedelta
import unittest

from app.services import deload as D
from app.services import xp_v6 as X6


class DeloadRulesTests(unittest.TestCase):
    def test_manual_deload_requires_two_of_previous_three_weeks_at_75_percent(self):
        baseline = 400.0
        self.assertTrue(D.previous_three_weeks_qualify([300.0, 400.0, 300.0], baseline))
        self.assertTrue(D.previous_three_weeks_qualify([None, 300.0, 300.0], baseline))
        self.assertTrue(D.previous_three_weeks_qualify([250.0, 300.0, 300.0], baseline))
        self.assertFalse(D.previous_three_weeks_qualify([300.0, 299.99, 100.0], baseline))
        self.assertFalse(D.previous_three_weeks_qualify([None, 300.0, 299.99], baseline))
        self.assertFalse(D.previous_three_weeks_qualify([300.0, 400.0], baseline))

    def test_manual_deload_blocks_pause_high_load_and_manual_decision(self):
        current = date(2026, 10, 12)
        common = dict(
            current_week_start=current, current_load=320.0, baseline=400.0,
            previous_three_loads=[400.0, 400.0, 400.0], last_deload_week_start=None,
            paused=False, manual_decision=False,
        )
        self.assertIsNone(D.manual_deload_block_reason(**common))
        self.assertIn("85%", D.manual_deload_block_reason(**{**common, "current_load": 344.0}))
        self.assertIn("паузе", D.manual_deload_block_reason(**{**common, "paused": True}))
        self.assertIn("решение", D.manual_deload_block_reason(**{**common, "manual_decision": True}))

    def test_deload_cooldown_applies_to_manual_and_automatic_weeks(self):
        current = date(2026, 10, 12)
        self.assertFalse(D.cooldown_passed(current, current - timedelta(weeks=2)))
        self.assertTrue(D.cooldown_passed(current, current - timedelta(weeks=3)))
        reason = D.manual_deload_block_reason(
            current_week_start=current, current_load=300.0, baseline=400.0,
            previous_three_loads=[400.0, 400.0, 400.0],
            last_deload_week_start=current - timedelta(weeks=2),
            paused=False, manual_decision=False,
        )
        self.assertIn("3 недели", reason)

    def test_suggestion_uses_actual_range_or_day_four_projection(self):
        baseline = 400.0
        current = date(2026, 10, 12)
        common = dict(
            current_week_start=current, baseline=baseline, previous_three_loads=[400.0, 380.0, 300.0],
            last_deload_week_start=None, paused=False, manual_decision=False, already_deload=False,
        )
        self.assertTrue(D.suggestion_is_appropriate(current_load=300.0, current_day_index=0, **common))
        self.assertTrue(D.suggestion_is_appropriate(current_load=180.0, current_day_index=3, **common))
        self.assertFalse(D.suggestion_is_appropriate(current_load=180.0, current_day_index=2, **common))
        self.assertFalse(D.suggestion_is_appropriate(
            current_load=300.0, current_day_index=3, **{**common, "paused": True}
        ))

    def test_deload_goal_xp_is_capped_at_the_85_percent_floor(self):
        self.assertEqual(X6.effective_goal_ratio(0.10, True), 0.85)
        self.assertEqual(X6.effective_goal_ratio(0.95, True), 0.85)
        self.assertEqual(X6.effective_goal_ratio(0.95, False), 0.95)
        self.assertEqual(
            X6.weekly_goal_xp(X6.effective_goal_ratio(0.10, True)),
            X6.weekly_goal_xp(0.85),
        )

    def test_automatic_rule_requires_two_of_previous_three_weeks_at_75_percent(self):
        self.assertTrue(X6.is_deload_week(320.0, 400.0, [300.0, 300.0, 300.0]))
        self.assertTrue(X6.is_deload_week(320.0, 400.0, [100.0, 300.0, 320.0]))
        self.assertFalse(X6.is_deload_week(320.0, 400.0, [300.0, 299.99, 100.0]))
        self.assertFalse(X6.is_deload_week(344.0, 400.0, [300.0, 300.0, 300.0]))
        self.assertFalse(X6.is_deload_week(200.0, 400.0, [300.0, 300.0, 300.0]))


if __name__ == "__main__":
    unittest.main()
