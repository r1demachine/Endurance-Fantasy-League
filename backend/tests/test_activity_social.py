import asyncio
import unittest
from datetime import datetime
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.database import Base, get_db
from app.dependencies import get_current_user
from app.models import Activity, ActivityReaction, Friendship, FriendshipStatus, Notification, User
from app.rate_limit import limiter
from app.routers import sync as sync_router
from app.routers.social import router as social_router
from app.services.activity_visibility import can_view_activity
from app.services.notifications import notify_user


class ActivitySocialTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

        @event.listens_for(self.engine, "connect")
        def enable_foreign_keys(connection, _record):
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(
            bind=self.engine,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )
        self.db = self.Session()
        self.owner = self.make_user("activity-owner", "Activity Owner")
        self.viewer = self.make_user("activity-viewer", "Viewer")
        self.outsider = self.make_user("activity-outsider", "Outsider")
        self.activity = self.make_activity(self.owner, "owner-ride")

        self.app = FastAPI()
        self.app.state.limiter = limiter
        self.app.add_middleware(SlowAPIMiddleware)
        self.app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
        self.app.include_router(social_router)

        def override_db():
            yield self.db

        self.app.dependency_overrides[get_db] = override_db
        self.app.dependency_overrides[get_current_user] = lambda: self.viewer
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()
        self.db.close()
        self.engine.dispose()

    def make_user(self, username, display_name):
        user = User(
            username=username,
            password_hash="test-hash",
            display_name=display_name,
            profile_visibility="authenticated",
            activity_visibility="friends",
            timezone_name="UTC",
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def make_activity(self, owner, external_id):
        activity = Activity(
            user_id=owner.id,
            intervals_activity_id=external_id,
            name="Morning ride",
            sport_type="Ride",
            moving_time=3600,
            start_date=datetime(2026, 10, 12, 9, 0),
            start_date_local=datetime(2026, 10, 12, 9, 0),
        )
        self.db.add(activity)
        self.db.commit()
        self.db.refresh(activity)
        return activity

    def accept_friendship(self, first, second):
        self.db.add(Friendship(
            from_user_id=first.id,
            to_user_id=second.id,
            status=FriendshipStatus.ACCEPTED,
        ))
        self.db.commit()

    def test_visibility_allows_owner_and_accepted_friend_only(self):
        self.assertTrue(can_view_activity(self.db, self.owner, self.activity))
        self.assertFalse(can_view_activity(self.db, self.outsider, self.activity))

        self.accept_friendship(self.owner, self.viewer)
        self.assertTrue(can_view_activity(self.db, self.viewer, self.activity))

        self.owner.profile_visibility = "private"
        self.db.commit()
        self.assertFalse(can_view_activity(self.db, self.viewer, self.activity))
        self.assertTrue(can_view_activity(self.db, self.owner, self.activity))

    def test_social_endpoints_return_403_for_nonfriend_and_private_profile(self):
        self.viewer = self.outsider
        response = self.client.get(f"/api/activities/{self.activity.id}/social")
        self.assertEqual(response.status_code, 403)
        response = self.client.put(f"/api/activities/{self.activity.id}/reaction")
        self.assertEqual(response.status_code, 403)

        self.accept_friendship(self.owner, self.outsider)
        self.owner.profile_visibility = "private"
        self.db.commit()
        response = self.client.get(f"/api/activities/{self.activity.id}/social")
        self.assertEqual(response.status_code, 403)
        response = self.client.put(f"/api/activities/{self.activity.id}/reaction")
        self.assertEqual(response.status_code, 403)

    def test_public_activities_uses_the_same_visibility_policy(self):
        self.viewer = self.outsider
        with self.assertRaises(HTTPException) as context:
            asyncio.run(sync_router.public_activities(
                username=self.owner.username,
                offset=0,
                limit=20,
                viewer=self.viewer,
                db=self.db,
            ))
        self.assertEqual(context.exception.status_code, 403)

        self.accept_friendship(self.owner, self.outsider)
        payload = asyncio.run(sync_router.public_activities(
            username=self.owner.username,
            offset=0,
            limit=20,
            viewer=self.viewer,
            db=self.db,
        ))
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["activities"][0]["id"], self.activity.id)

    def test_toggle_likes_add_and_remove_one_unique_reaction(self):
        self.accept_friendship(self.owner, self.viewer)
        with patch("app.services.notifications.publish", new_callable=AsyncMock):
            first = self.client.put(f"/api/activities/{self.activity.id}/reaction")
            self.assertEqual(first.status_code, 200)
            self.assertTrue(first.json()["liked"])
            self.assertEqual(first.json()["likes_count"], 1)

            rows = self.db.query(ActivityReaction).filter(
                ActivityReaction.activity_id == self.activity.id,
                ActivityReaction.user_id == self.viewer.id,
            ).count()
            self.assertEqual(rows, 1)

            second = self.client.put(f"/api/activities/{self.activity.id}/reaction")
            self.assertEqual(second.status_code, 200)
            self.assertFalse(second.json()["liked"])
            self.assertEqual(second.json()["likes_count"], 0)

        self.assertEqual(
            self.db.query(Notification).filter(
                Notification.user_id == self.owner.id,
                Notification.type == "activity_like",
            ).count(),
            1,
        )

    def test_self_like_does_not_create_notification(self):
        self.viewer = self.owner
        with patch("app.services.notifications.publish", new_callable=AsyncMock):
            response = self.client.put(f"/api/activities/{self.activity.id}/reaction")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["liked"])
        self.assertEqual(
            self.db.query(Notification).filter(Notification.user_id == self.owner.id).count(),
            0,
        )

    def test_database_unique_constraint_and_foreign_key_cascades(self):
        self.db.add(ActivityReaction(activity_id=self.activity.id, user_id=self.viewer.id))
        self.db.commit()
        self.db.add(ActivityReaction(activity_id=self.activity.id, user_id=self.viewer.id))
        with self.assertRaises(IntegrityError):
            self.db.commit()
        self.db.rollback()
        self.assertEqual(
            self.db.query(ActivityReaction).filter(
                ActivityReaction.activity_id == self.activity.id,
                ActivityReaction.user_id == self.viewer.id,
            ).count(),
            1,
        )

        self.db.delete(self.activity)
        self.db.commit()
        self.assertEqual(self.db.query(ActivityReaction).count(), 0)

        second_activity = self.make_activity(self.owner, "owner-ride-2")
        self.db.add(ActivityReaction(activity_id=second_activity.id, user_id=self.outsider.id))
        self.db.commit()
        self.db.delete(self.outsider)
        self.db.commit()
        self.assertEqual(self.db.query(ActivityReaction).count(), 0)

    def test_activity_like_notifications_roll_up_for_same_unread_activity(self):
        link = f"/dashboard?activity_id={self.activity.id}&week_start=2026-10-12"
        with patch("app.services.notifications.publish", new_callable=AsyncMock):
            asyncio.run(notify_user(
                self.db, self.owner.id, "activity_like",
                "Иван оценил твою тренировку", link=link, send_telegram=False,
            ))
            asyncio.run(notify_user(
                self.db, self.owner.id, "activity_like",
                "Мария оценил твою тренировку", link=link, send_telegram=False,
            ))
            asyncio.run(notify_user(
                self.db, self.owner.id, "activity_like",
                "Пётр оценил твою тренировку", link=link, send_telegram=False,
            ))

        rows = self.db.query(Notification).filter(
            Notification.user_id == self.owner.id,
            Notification.type == "activity_like",
            Notification.link == link,
        ).all()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].text, "Иван и ещё 2 оценили твою тренировку")
        self.assertEqual(rows[0].link, link)


if __name__ == "__main__":
    unittest.main()
