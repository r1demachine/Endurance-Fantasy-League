"""Tests for manual streak rest-day policy."""
import unittest
from datetime import date, timedelta

from app.services.streak import rest_day_decision


class StreakRestDayTests(unittest.TestCase):
    def setUp(self):
        self.today = date(2026, 10, 20)  # Tuesday
        self.yesterday = self.today - timedelta(days=1)

    def test_can_claim_after_qualifying_day_when_today_is_empty(self):
        self.assertEqual(
            rest_day_decision(
                today=self.today, used_dates=set(), has_activity_today=False,
                previous_day_credited=True,
            ),
            (True, None),
        )

    def test_cannot_claim_when_today_has_an_activity(self):
        available, reason = rest_day_decision(
            today=self.today, used_dates=set(), has_activity_today=True,
            previous_day_credited=True,
        )
        self.assertFalse(available)
        self.assertIn("без тренировок", reason)

    def test_cannot_start_or_resurrect_an_expired_streak(self):
        available, reason = rest_day_decision(
            today=self.today, used_dates=set(), has_activity_today=False,
            previous_day_credited=False,
        )
        self.assertFalse(available)
        self.assertIn("нечего продлевать", reason)

    def test_only_one_credit_per_calendar_week(self):
        earlier_this_week = self.today - timedelta(days=1)
        available, reason = rest_day_decision(
            today=self.today, used_dates={earlier_this_week}, has_activity_today=False,
            previous_day_credited=True,
        )
        self.assertFalse(available)
        self.assertIn("один день отдыха", reason)

    def test_used_today_is_not_offered_again(self):
        available, reason = rest_day_decision(
            today=self.today, used_dates={self.today}, has_activity_today=False,
            previous_day_credited=True,
        )
        self.assertFalse(available)
        self.assertIn("сегодня", reason)


if __name__ == "__main__":
    unittest.main()
