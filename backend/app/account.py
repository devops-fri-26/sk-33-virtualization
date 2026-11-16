"""The logged-in user's own settings: name, email, password, sessions, storage requests, deleting the account."""

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from . import plugins
from .auth import (
    CurrentUser,
    Email,
    Password,
    PasswordIn,
    email_tokens,
    end_session,
    hash_password,
    limit_mail,
    login_email,
    start_session,
    storage_used,
    user_out,
    verify_password,
)
from .config import settings
from .db import SessionDep
from .mail import admin_emails, send_mail
from .models import GB, Track, User

router = APIRouter(prefix="/api/account", tags=["account"])


class Profile(BaseModel):
    """The display name to set. Empty removes it."""

    name: str = Field(max_length=100)


class PasswordChange(BaseModel):
    """A new password, plus the current one to prove who is asking."""

    current: PasswordIn
    new: Password


class EmailChange(BaseModel):
    """A new email address, plus the current password to prove who is asking."""

    email: Email
    password: PasswordIn


async def check_password(user: User, password: str):
    """Make sure the caller knows the account's current password, before a change that needs it.

    Args:
        user: The logged-in user.
        password: The password they typed.

    Raises:
        HTTPException: 400 when the password is wrong, 429 after too many attempts.
    """
    login_email.hit(user.email)  # same limit as logging in, so a stolen session can't guess the password
    if not await verify_password(password, user.password_hash):
        raise HTTPException(400, "Your current password is wrong")


@router.patch("")
async def update_profile(data: Profile, db: SessionDep, user: CurrentUser):
    """Change the user's display name.

    Args:
        data: The new name.
        db: Database session.
        user: The logged-in user.

    Returns:
        The updated account (see user_out()).
    """
    user.name = data.name.strip() or None
    await db.commit()
    return await user_out(db, user)


@router.post("/password")
async def change_password(data: PasswordChange, response: Response, db: SessionDep, user: CurrentUser):
    """Change the user's password and log out their other devices.

    Args:
        data: The current and the new password.
        response: Gets a fresh session cookie, so this device stays logged in.
        db: Database session.
        user: The logged-in user.

    Returns:
        A confirmation message.

    Raises:
        HTTPException: 400 when the current password is wrong, 429 after too many attempts.
    """
    await check_password(user, data.current)
    user.password_hash = await hash_password(data.new)
    user.session_version += 1  # logs out other devices
    await db.commit()
    start_session(response, user)  # but keeps this one logged in
    return {"detail": "Password changed. Your other devices were logged out."}


@router.post("/email")
async def change_email(data: EmailChange, request: Request, db: SessionDep, user: CurrentUser, tasks: BackgroundTasks):
    """Send a confirmation link to the new address; the email changes when it's opened.

    The second step is confirm_email() in auth.py.

    Args:
        data: The new email and the current password.
        request: The incoming request, for the limit per IP address.
        db: Database session.
        user: The logged-in user.
        tasks: Sends the email after the response has gone out.

    Returns:
        A message that says where the link was sent.

    Raises:
        HTTPException: 400 when the password is wrong, the email is the current one or another account uses
            it. 429 after too many attempts or emails.
    """
    await check_password(user, data.password)
    email = data.email.lower()
    if email == user.email:
        raise HTTPException(400, "That's already your email")
    limit_mail(request, email)
    if await db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(400, "That email is already used by another account")
    token = email_tokens.dumps({"uid": user.id, "from": user.email, "email": email})
    tasks.add_task(
        send_mail,
        email,
        "Confirm your new Varsis email",
        f"Confirm {email} as the email of your Varsis account: {settings.app_url}/confirm-email?token={token}\n\n"
        "The link works for 24 hours. If you didn't ask for this, you can ignore this email.",
    )
    return {"detail": f"We sent a confirmation link to {email}. Your email changes when you open it."}


@router.post("/logout-everywhere")
async def logout_everywhere(response: Response, db: SessionDep, user: CurrentUser):
    """End every session of the user, this one included.

    Args:
        response: Tells this browser to delete its session cookie.
        db: Database session.
        user: The logged-in user.

    Returns:
        A confirmation message.
    """
    user.session_version += 1  # every cookie handed out so far carries the old number and stops working
    await db.commit()
    end_session(response)
    return {"detail": "Logged out on all devices"}


class AccountDelete(BaseModel):
    """The current password, to prove who is asking for the account to be deleted."""

    password: PasswordIn


async def remove_user(db: AsyncSession, user: User):
    """Delete an account and its playlists. Its uploads stay in the library, without an uploader. Commits.

    Args:
        db: Database session.
        user: The account to delete.
    """
    for delete_user in plugins.each("delete_user"):  # e.g. stop what the user has running
        await delete_user(db, user.id)
    # tracks.uploaded_by has no ON DELETE rule, so the database would refuse the delete while tracks point here.
    await db.execute(update(Track).where(Track.uploaded_by == user.id).values(uploaded_by=None))
    await db.delete(user)  # the database deletes the playlists along with it
    await db.commit()


@router.post("/delete", status_code=204)
async def delete_account(data: AccountDelete, response: Response, db: SessionDep, user: CurrentUser):
    """Delete the user's own account and playlists, and log this browser out.

    The music they uploaded stays in the shared library (then only admins can edit it).

    Args:
        data: The current password.
        response: Tells this browser to delete its session cookie.
        db: Database session.
        user: The logged-in user.

    Raises:
        HTTPException: 400 when the password is wrong or the user is the only admin, 429 after too many attempts.
    """
    await check_password(user, data.password)
    other_admin = select(User.id).where(User.is_admin, ~User.is_disabled, User.id != user.id).limit(1)
    if user.is_admin and not await db.scalar(other_admin):
        raise HTTPException(400, "You are the only admin. Make someone else an admin first.")
    await remove_user(db, user)
    end_session(response)


@router.post("/storage-request")
async def request_storage(db: SessionDep, user: CurrentUser, tasks: BackgroundTasks):
    """Ask the admins for more upload space.

    Every admin gets an email. The request stays open until an admin changes the limit.

    Args:
        db: Database session.
        user: The logged-in user.
        tasks: Sends the emails after the response has gone out.

    Returns:
        The account (see user_out()), now with `storage_requested` set.

    Raises:
        HTTPException: 400 when the user's storage has no limit.
    """
    if user.quota is None:
        raise HTTPException(400, "Your storage has no limit")
    if not user.storage_requested:  # asking again while a request is open sends nothing
        user.storage_requested = True
        await db.commit()
        used = await storage_used(db, user.id)
        who = f"{user.name} ({user.email})" if user.name else user.email
        for admin in await admin_emails(db):
            tasks.add_task(
                send_mail,
                admin,
                "Varsis: request for more storage",
                f"{who} has used {used / GB:.1f} GB of {user.quota / GB:.1f} GB and asks for more space.\n\n"
                f"Change their limit: {settings.app_url}/admin",
            )
    return await user_out(db, user)
