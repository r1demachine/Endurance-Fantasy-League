"""Integration checks for a one-person beta league and deterministic tiebreaks."""
import os
import unittest
from datetime import date, datetime

from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/efl-beta-league-tests.db")
os.environ.setdefault("JWT_SECRET", "unit-test-jwt-secret-value-longer-than-32-characters")
os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
os.environ.setdefault("REDIS_URL", "")

from app.database import Base
from app.models import LeagueMembership, LeagueWeek, User, WeeklySummary
from app.routers.sync import _close_league_week


class BetaLeagueWeekTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.db = self.Session()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def add_participant(self, suffix, *, score, weekly_xp, load):
        user = User(
            username=f"beta-user-{suffix}",
            password_hash="test-hash",
            display_name=f"Beta User {suffix}",
            timezone_name="UTC",
            timezone_confirmed=True,
            total_xp=weekly_xp,
            level=1,
        )
        self.db.add(user)
        self.db.flush()
        week = date(2026, 10, 5)
        self.db.add(WeeklySummary(
            user_id=user.id,
            week_start=datetime.combine(week, datetime.min.time()),
            actual_load=load,
            target_load=100,
            completion_ratio=1.0,
            training_days=3,
            target_training_days=3,
            total_xp=weekly_xp,
            league_score=score,
            finalized=True,
        ))
        self.db.flush()
        return user

    def test_one_participant_forms_beta_league(self):
        week = date(2026, 10, 5)
        user = self.add_participant("solo", score=100, weekly_xp=50, load=100)
        self.db.commit()

        formed = _close_league_week(self.db, week)
        self.assertTrue(formed)
        membership = self.db.query(LeagueMembership).filter_by(user_id=user.id).one()
        league_week = self.db.query(LeagueWeek).filter_by(
            week_start=datetime.combine(week, datetime.min.time())
        ).one()
        self.assertEqual(league_week.status, "closed")
        self.assertEqual(membership.group_key, "beta")
        self.assertEqual(membership.division, "Бета-лига")
        self.assertEqual(membership.rank, 1)
        self.assertFalse(membership.promoted)
        self.assertFalse(membership.demoted)

    def test_small_field_shares_beta_group_and_uses_weekly_xp_tiebreak(self):
        week = date(2026, 10, 5)
        lower_xp = self.add_participant("a", score=90, weekly_xp=100, load=500)
        higher_xp = self.add_participant("b", score=90, weekly_xp=120, load=100)
        same_xp_better_load = self.add_participant("c", score=90, weekly_xp=120, load=200)
        self.db.commit()

        self.assertTrue(_close_league_week(self.db, week))
        rows = self.db.query(LeagueMembership).filter_by(
            week_start=datetime.combine(week, datetime.min.time())
        ).order_by(LeagueMembership.rank.asc()).all()
        self.assertEqual([row.user_id for row in rows], [
            same_xp_better_load.id, higher_xp.id, lower_xp.id,
        ])
        self.assertEqual({row.group_key for row in rows}, {"beta"})
        self.assertEqual({row.division for row in rows}, {"Бета-лига"})
        self.assertTrue(all(not row.promoted and not row.demoted for row in rows))


if __name__ == "__main__":
    unittest.main()
