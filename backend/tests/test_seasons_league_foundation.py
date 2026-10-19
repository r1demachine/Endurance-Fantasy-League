"""Regression tests for monthly season calculation and weekly league ordering."""
import unittest
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from app.services.league import league_ranking_key
from app.services.seasons import SEASONS, current_season, season_for_date
from app.services import xp_v6 as X6


class SeasonServiceTests(unittest.TestCase):
    def test_september_2026_is_season_001(self):
        season = season_for_date(date(2026, 9, 1))
        self.assertEqual(season.num, 1)
        self.assertEqual(season.start, date(2026, 9, 1))
        self.assertEqual(season.end, date(2026, 9, 30))
        self.assertEqual(season.flower, SEASONS[1]["flower"])
        self.assertEqual(season.color, SEASONS[1]["color"])

    def test_one_calendar_month_is_one_season(self):
        september = season_for_date(date(2026, 9, 30))
        october = season_for_date(date(2026, 10, 1))
        december = season_for_date(date(2026, 12, 31))
        january = season_for_date(date(2027, 1, 1))

        self.assertEqual(september.num, 1)
        self.assertEqual(october.num, 2)
        self.assertEqual(december.num, 4)
        self.assertEqual(january.num, 5)
        self.assertEqual(october.start, date(2026, 10, 1))
        self.assertEqual(october.end, date(2026, 10, 31))
        self.assertEqual(december.end, date(2026, 12, 31))
        self.assertEqual(january.end, date(2027, 1, 31))

    def test_current_season_uses_users_local_date(self):
        moment = datetime(2026, 9, 30, 12, 30, tzinfo=timezone.utc)
        utc_season = current_season("UTC", now=moment)
        kiribati_season = current_season("Pacific/Kiritimati", now=moment)

        self.assertEqual(utc_season.num, 1)
        self.assertEqual(kiribati_season.num, 2)

    def test_naive_now_is_interpreted_as_utc_and_bad_zone_falls_back_safely(self):
        moment = datetime(2026, 10, 1, 1, 0)
        self.assertEqual(current_season("UTC", now=moment).num, 2)
        self.assertEqual(current_season("not/a-real-zone", now=moment).num, 2)


class LeagueRankingTests(unittest.TestCase):
    def test_equal_league_score_is_broken_by_weekly_xp(self):
        better_xp = league_ranking_key(90, 501, 300, 4)
        worse_xp = league_ranking_key(90, 500, 800, 1)
        self.assertLess(better_xp, worse_xp)

    def test_equal_score_and_xp_is_broken_by_actual_load(self):
        better_load = league_ranking_key(90, 500, 301, 10)
        worse_load = league_ranking_key(90, 500, 300, 1)
        self.assertLess(better_load, worse_load)

    def test_user_id_is_final_stable_tie_breaker(self):
        self.assertLess(
            league_ranking_key(90, 500, 300, 3),
            league_ranking_key(90, 500, 300, 4),
        )

    def test_beta_league_threshold_and_minimum_are_configurable(self):
        self.assertEqual(X6.MIN_LEAGUE_SIZE, 1)
        self.assertEqual(X6.BETA_SINGLE_LEAGUE_UNTIL_USERS, 20)


if __name__ == "__main__":
    unittest.main()
