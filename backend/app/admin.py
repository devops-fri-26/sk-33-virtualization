"""Admin: approve sign-ups, manage accounts (access, admin rights, storage limit), delete accounts."""

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update

from .auth import AdminUser
from .config import settings
from .db import SessionDep
from .mail import send_mail
from .models import Track, User
from .torrents import remove_user_torrents

router = APIRouter(prefix="/api/admin", tags=["admin"])


class UserPatch(BaseModel):
    """Changes to an account. Fields that are left out stay as they are."""

    is_approved: bool | None = None
    is_disabled: bool | None = None
    is_admin: bool | None = None
    quota: int | None = Field(None, ge=0, le=2**62)  # bytes; send null for no limit


async def _users(db, user_id: int | None = None) -> list[dict]:
    """List accounts with how much they have uploaded, newest account first.

    Args:
        db: Database session.
        user_id: Only this account, when given.

    Returns:
        One dict per account: its fields plus `used` (bytes uploaded) and `tracks` (number of uploads).
    """
    # Uploaded bytes and track count per uploader, joined to the users below (users without uploads get NULLs).
    usage = (
        select(Track.uploaded_by.label("uid"), func.sum(Track.size).label("used"), func.count().label("tracks"))
        .group_by(Track.uploaded_by)
        .subquery()
    )
    query = select(User, usage.c.used, usage.c.tracks).outerjoin(usage, usage.c.uid == User.id)
    if user_id is not None:
        query = query.where(User.id == user_id)
    rows = await db.execute(query.order_by(User.created_at.desc()))
    return [
        {
            "id": u.id,
            "email": u.email,
            "name": u.name,
            "is_verified": u.is_verified,
            "is_approved": u.is_approved,
            "is_disabled": u.is_disabled,
            "is_admin": u.is_admin,
            "quota": u.quota,
            "used": used or 0,
            "tracks": tracks or 0,
            "storage_requested": u.storage_requested,
            "created_at": u.created_at,
        }
        for u, used, tracks in rows
    ]


@router.get("/users")
async def users(db: SessionDep, _: AdminUser):
    """List every account for the admin page.

    Args:
        db: Database session.

    Returns:
        The accounts with their storage use, newest first (see _users()).
    """
    return await _users(db)


@router.patch("/users/{user_id}")
async def update_user(user_id: int, data: UserPatch, db: SessionDep, admin: AdminUser, tasks: BackgroundTasks):
    """Change an account's access, admin rights or storage limit.

    Approving an account also marks its email as verified and emails the user. Setting the storage limit closes
    the user's request for more space.

    Args:
        user_id: The account to change.
        data: The changes.
        db: Database session.
        admin: The logged-in admin.
        tasks: Sends the email after the response has gone out.

    Returns:
        The updated account, in the same form as in the list.

    Raises:
        HTTPException: 404 when the account doesn't exist. 400 when an admin tries to take away their own
            admin rights or access.
    """
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    if user.id == admin.id and (data.is_admin is False or data.is_disabled or data.is_approved is False):
        raise HTTPException(400, "You can't remove your own admin rights or access")
    if data.is_approved and not user.is_approved:
        user.is_verified = True  # the admin vouches for the account
        tasks.add_task(
            send_mail,
            user.email,
            "Your Varsis account is ready",
            f"An admin approved your account. Log in here: {settings.app_url}/login",
        )
    for field in ("is_approved", "is_disabled", "is_admin"):
        if getattr(data, field) is not None:
            setattr(user, field, getattr(data, field))
    if "quota" in data.model_fields_set:  # was sent at all: null is a real value here (no limit)
        user.quota = data.quota
        user.storage_requested = False  # answered
    await db.commit()
    return (await _users(db, user.id))[0]


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(user_id: int, db: SessionDep, admin: AdminUser):
    """Delete an account and its playlists. Its uploads stay in the library (then only admins can edit them).

    Args:
        user_id: The account to delete.
        db: Database session.
        admin: The logged-in admin.

    Raises:
        HTTPException: 400 when an admin tries to delete their own account, 404 when it doesn't exist.
    """
    if user_id == admin.id:
        raise HTTPException(400, "You can't delete your own account")
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    await remove_user_torrents(db, user_id)
    # tracks.uploaded_by has no ON DELETE rule, so the database would refuse the delete while tracks point here.
    await db.execute(update(Track).where(Track.uploaded_by == user_id).values(uploaded_by=None))
    await db.delete(user)
    await db.commit()
