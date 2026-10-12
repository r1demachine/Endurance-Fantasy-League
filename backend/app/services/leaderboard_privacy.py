"""Правила видимости профиля на leaderboard."""
from typing import Optional, Set

from sqlalchemy.orm import Session

from ..models import User


def viewer_friend_ids(db: Session, viewer: Optional[User]) -> Set[int]:
    if viewer is None:
        return set()
    from ..models import Friendship, FriendshipStatus
    rows = (
        db.query(Friendship.to_user_id)
        .filter(
            Friendship.from_user_id == viewer.id,
            Friendship.status == FriendshipStatus.ACCEPTED,
        )
        .union(
            db.query(Friendship.from_user_id).filter(
                Friendship.to_user_id == viewer.id,
                Friendship.status == FriendshipStatus.ACCEPTED,
            )
        )
        .all()
    )
    return {r[0] for r in rows}


def profile_visible_on_leaderboard(
    user: User, viewer: Optional[User], friend_ids: Set[int]
) -> bool:
    """private исключаем; friends — только для друзей (и себя)."""
    vis = (user.profile_visibility or "authenticated").lower()
    if vis == "private":
        return viewer is not None and viewer.id == user.id
    if vis == "friends":
        if viewer is None:
            return False
        if viewer.id == user.id:
            return True
        return user.id in friend_ids
    return True
