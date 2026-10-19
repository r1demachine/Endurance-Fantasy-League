"""One source of truth for who may see an activity's details."""
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from ..models import Activity, Friendship, FriendshipStatus, User


def can_view_activity(db: Session, viewer: User, activity: Activity | User) -> bool:
    """Allow the owner or an accepted friend when profile/activity visibility permits it.

    Passing a User is supported for list endpoints that authorize a profile before
    fetching activities, including when the user has no activities yet.
    """
    if isinstance(activity, User):
        owner = activity
    else:
        owner = db.query(User).filter(User.id == activity.user_id).first()

    if owner is None:
        return False
    if viewer.id == owner.id:
        return True
    if (owner.profile_visibility or "authenticated") == "private":
        return False
    if (owner.activity_visibility or "friends") != "friends":
        return False

    return db.query(Friendship.id).filter(
        Friendship.status == FriendshipStatus.ACCEPTED,
        or_(
            and_(Friendship.from_user_id == viewer.id, Friendship.to_user_id == owner.id),
            and_(Friendship.from_user_id == owner.id, Friendship.to_user_id == viewer.id),
        ),
    ).first() is not None
