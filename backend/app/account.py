"""The logged-in user's own settings: name, email, password, sessions, storage requests."""

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

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
from .models import GB, User

router = APIRouter(prefix="/api/account", tags=["account"])


class Profile(BaseModel):
    name: str = Field(max_length=100)


class PasswordChange(BaseModel):
    current: PasswordIn
    new: Password


class EmailChange(BaseModel):
    email: Email
    password: PasswordIn


async def check_password(user: User, password: str):
    login_email.hit(user.email)  # same limit as logging in, so a stolen session can't guess the password
    if not await verify_password(password, user.password_hash):
        raise HTTPException(400, "Your current password is wrong")


@router.patch("")
async def update_profile(data: Profile, db: SessionDep, user: CurrentUser):
    user.name = data.name.strip() or None
    await db.commit()
    return await user_out(db, user)


@router.post("/password")
async def change_password(data: PasswordChange, response: Response, db: SessionDep, user: CurrentUser):
    await check_password(user, data.current)
    user.password_hash = await hash_password(data.new)
    user.session_version += 1  # logs out other devices
    await db.commit()
    start_session(response, user)  # but keeps this one logged in
    return {"detail": "Password changed. Your other devices were logged out."}


@router.post("/email")
async def change_email(data: EmailChange, request: Request, db: SessionDep, user: CurrentUser, tasks: BackgroundTasks):
    """Send a confirmation link to the new address; the email changes when it's opened."""
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
    user.session_version += 1
    await db.commit()
    end_session(response)
    return {"detail": "Logged out on all devices"}


@router.post("/storage-request")
async def request_storage(db: SessionDep, user: CurrentUser, tasks: BackgroundTasks):
    """Ask the admins for more upload space."""
    if user.quota is None:
        raise HTTPException(400, "Your storage has no limit")
    if not user.storage_requested:
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
