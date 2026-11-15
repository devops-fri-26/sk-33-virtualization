"""Accounts: sign-up (email verification + admin approval), login/logout, password reset, current_user."""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from fastapi import APIRouter, BackgroundTasks, Cookie, Depends, HTTPException, Request, Response
from itsdangerous import BadSignature, URLSafeTimedSerializer
from pwdlib import PasswordHash
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .db import SessionDep
from .mail import admin_emails, send_mail
from .models import Track, User
from .ratelimit import Limiter, client_ip

router = APIRouter(prefix="/api/auth", tags=["auth"])
hasher = PasswordHash.recommended()
# Checked when the email is unknown, so a login takes equally long whether or not the account exists.
DUMMY_HASH = hasher.hash("no such account")
COOKIE = "session"
SESSION_DAYS = 30
HOUR, DAY = 3600, 86400

# Signed, expiring tokens for email links. Each kind has its own salt, so one can't be used as another.
verify_tokens = URLSafeTimedSerializer(settings.secret_key, salt="verify-email")
reset_tokens = URLSafeTimedSerializer(settings.secret_key, salt="reset-password")
email_tokens = URLSafeTimedSerializer(settings.secret_key, salt="change-email")

# Rate limits against password guessing and using Varsis to send spam.
login_ip = Limiter(30, 15 * 60)
login_email = Limiter(10, 15 * 60)  # also guards the password checks in account settings
signup_ip = Limiter(5, HOUR)
signup_all = Limiter(30, HOUR)
mail_ip = Limiter(10, HOUR)
mail_to = Limiter(3, HOUR)
mail_all = Limiter(50, HOUR)

# Plain addresses only: no spaces, commas, quotes or brackets, which mail software could read as several
# recipients or as a display name.
Email = Annotated[
    str,
    Field(pattern=r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$", max_length=320),
]
Password = Annotated[str, Field(min_length=8, max_length=256)]
# A password that is only checked, not set (older accounts keep working whatever the rules for new ones are).
PasswordIn = Annotated[str, Field(min_length=1, max_length=256)]


class Credentials(BaseModel):
    email: Email
    password: Password


class Login(BaseModel):
    email: Email
    password: PasswordIn


class EmailIn(BaseModel):
    email: Email


class NewPassword(BaseModel):
    token: str
    password: Password


async def hash_password(password: str) -> str:
    """Argon2 takes ~100 ms of CPU: run it in a thread so it doesn't freeze every other request (and playback)."""
    return await asyncio.to_thread(hasher.hash, password)


async def verify_password(password: str, password_hash: str) -> bool:
    return await asyncio.to_thread(hasher.verify, password, password_hash)


def limit_mail(request: Request, to: str):
    """Rate limits for endpoints that send an email to an address the caller typed."""
    mail_ip.hit(client_ip(request))
    mail_to.hit(to)
    mail_all.hit("all")


def invalid_link():
    return HTTPException(400, "This link is invalid or has expired")


# ---------- sessions ----------


def start_session(response: Response, user: User):
    exp = datetime.now(UTC) + timedelta(days=SESSION_DAYS)
    claims = {"sub": str(user.id), "ver": user.session_version, "exp": exp}
    response.set_cookie(
        COOKIE,
        jwt.encode(claims, settings.secret_key, algorithm="HS256"),
        max_age=SESSION_DAYS * DAY,
        httponly=True,
        samesite="lax",
        secure=settings.app_url.startswith("https"),
    )


def end_session(response: Response):
    response.delete_cookie(COOKIE, httponly=True, samesite="lax", secure=settings.app_url.startswith("https"))


def can_log_in(user: User) -> bool:
    return user.is_verified and user.is_approved and not user.is_disabled


async def current_user(db: SessionDep, session: Annotated[str | None, Cookie()] = None) -> User:
    try:
        claims = jwt.decode(session or "", settings.secret_key, algorithms=["HS256"])
        uid, version = int(claims["sub"]), claims.get("ver", 0)
    except (jwt.PyJWTError, KeyError, ValueError, TypeError):
        raise HTTPException(401, "Not logged in")
    user = await db.get(User, uid)
    # A changed session_version means "logged out everywhere" or a password change.
    if not user or not can_log_in(user) or user.session_version != version:
        raise HTTPException(401, "Not logged in")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


async def current_admin(user: CurrentUser) -> User:
    if not user.is_admin:
        raise HTTPException(403, "Only admins can do this")
    return user


AdminUser = Annotated[User, Depends(current_admin)]


async def storage_used(db: AsyncSession, user_id: int) -> int:
    """Bytes of audio this user uploaded (counts against their quota)."""
    return await db.scalar(select(func.coalesce(func.sum(Track.size), 0)).where(Track.uploaded_by == user_id))


async def user_out(db: AsyncSession, user: User) -> dict:
    out = {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "is_admin": user.is_admin,
        "quota": user.quota,
        "used": await storage_used(db, user.id),
        "storage_requested": user.storage_requested,
    }
    if user.is_admin:  # things waiting for an admin: verified sign-ups and storage requests
        waiting = or_(User.is_verified & ~User.is_approved & ~User.is_disabled, User.storage_requested)
        out["admin_alerts"] = await db.scalar(select(func.count()).select_from(User).where(waiting))
    return out


# ---------- routes ----------


async def send_verification(email: str):
    link = f"{settings.app_url}/verify?token={verify_tokens.dumps(email)}"
    await send_mail(email, "Verify your Varsis account", f"Confirm your email: {link}\n\nThe link works for 24 hours.")


@router.post("/register", status_code=201)
async def register(data: Credentials, request: Request, db: SessionDep, tasks: BackgroundTasks):
    signup_ip.hit(client_ip(request))
    signup_all.hit("all")
    email = data.email.lower()
    mail_to.hit(email)
    mail_all.hit("all")
    done = {"detail": "Check your email to verify your account"}
    existing = await db.scalar(select(User).where(User.email == email))
    if existing:
        # Same answer as for a new account, so this form can't be used to find out who has an account.
        # The owner of the address is told by email instead.
        if existing.is_verified:
            tasks.add_task(
                send_mail,
                email,
                "You already have a Varsis account",
                f"Someone (hopefully you) tried to sign up with {email}, but it already has an account.\n\n"
                f"Log in: {settings.app_url}/login\nForgot the password? {settings.app_url}/forgot-password\n\n"
                "If this wasn't you, you can ignore this email.",
            )
        else:
            tasks.add_task(send_verification, email)
        return done
    admin = email in settings.admins  # still has to verify the email, so nobody else can claim it
    db.add(User(email=email, password_hash=await hash_password(data.password), is_admin=admin, is_approved=admin))
    try:
        await db.commit()
    except IntegrityError:  # the same email signed up twice at the same moment
        return done
    tasks.add_task(send_verification, email)
    return done


@router.post("/verify")
async def verify(token: str, db: SessionDep, tasks: BackgroundTasks):
    try:
        email = verify_tokens.loads(token, max_age=DAY)
    except BadSignature:  # includes SignatureExpired
        raise invalid_link()
    user = await db.scalar(select(User).where(User.email == email)) if isinstance(email, str) else None
    if not user:
        raise invalid_link()
    first_time = not user.is_verified
    user.is_verified = True
    await db.commit()
    if user.is_approved:
        return {"detail": "Your email is verified. You can log in now.", "approved": True}
    if first_time:
        for admin in await admin_emails(db):
            tasks.add_task(
                send_mail,
                admin,
                "Varsis: new account waiting for approval",
                f"{email} signed up and verified their email.\n\nApprove or reject them: {settings.app_url}/admin",
            )
    return {
        "detail": "Your email is verified. An admin still has to approve your account; we'll email you when they do.",
        "approved": False,
    }


@router.post("/resend-verification")
async def resend_verification(data: EmailIn, request: Request, db: SessionDep, tasks: BackgroundTasks):
    email = data.email.lower()
    limit_mail(request, email)
    user = await db.scalar(select(User).where(User.email == email))
    if user and not user.is_verified:
        tasks.add_task(send_verification, email)
    return {"detail": "If that account exists and isn't verified yet, we sent a new link."}


@router.post("/login")
async def login(data: Login, request: Request, db: SessionDep, response: Response):
    email = data.email.lower()
    login_ip.hit(client_ip(request))
    login_email.hit(email)
    user = await db.scalar(select(User).where(User.email == email))
    if not await verify_password(data.password, user.password_hash if user else DUMMY_HASH) or not user:
        raise HTTPException(401, "Wrong email or password")
    if not user.is_verified:
        raise HTTPException(403, "Email not verified")
    if user.is_disabled:
        raise HTTPException(403, "Your account has been disabled by an admin")
    if not user.is_approved:
        raise HTTPException(403, "Your account is waiting for an admin to approve it")
    start_session(response, user)
    return await user_out(db, user)


@router.post("/logout")
async def logout(response: Response):
    end_session(response)
    return {"detail": "Logged out"}


@router.get("/me")
async def me(db: SessionDep, user: CurrentUser):
    return await user_out(db, user)


@router.post("/forgot-password")
async def forgot_password(data: EmailIn, request: Request, db: SessionDep, tasks: BackgroundTasks):
    email = data.email.lower()
    limit_mail(request, email)
    user = await db.scalar(select(User).where(User.email == email))
    if user:
        # session_version makes the link single-use: resetting the password bumps it.
        token = reset_tokens.dumps({"uid": user.id, "ver": user.session_version})
        tasks.add_task(
            send_mail,
            email,
            "Reset your Varsis password",
            f"Set a new password: {settings.app_url}/reset-password?token={token}\n\n"
            "The link works for 1 hour. If you didn't ask for this, you can ignore this email.",
        )
    return {"detail": "If an account with that email exists, we sent it a link to reset the password."}


@router.post("/reset-password")
async def reset_password(data: NewPassword, db: SessionDep):
    try:
        claims = reset_tokens.loads(data.token, max_age=HOUR)
    except BadSignature:
        raise invalid_link()
    user = await db.get(User, claims["uid"])
    if not user or user.session_version != claims["ver"]:
        raise invalid_link()
    user.password_hash = await hash_password(data.password)
    user.session_version += 1  # logs out every device
    user.is_verified = True  # they got the email, so they own the address
    await db.commit()
    return {"detail": "Your password was changed. You can log in now."}


@router.post("/confirm-email")
async def confirm_email(token: str, db: SessionDep):
    """Second step of changing the email (account settings): the link sent to the new address."""
    try:
        claims = email_tokens.loads(token, max_age=DAY)
    except BadSignature:
        raise invalid_link()
    user = await db.get(User, claims["uid"])
    if not user or user.email != claims["from"]:  # already used, or the email changed since
        raise invalid_link()
    if await db.scalar(select(User.id).where(User.email == claims["email"])):
        raise HTTPException(400, "That email is already used by another account")
    user.email = claims["email"]
    try:
        await db.commit()
    except IntegrityError:  # someone took the address between the check and the commit
        raise HTTPException(400, "That email is already used by another account")
    return {"detail": f"Your email is now {user.email}."}
