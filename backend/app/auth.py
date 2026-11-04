"""Register, email verification, login/logout, current_user dependency."""

from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from typing import Annotated

import aiosmtplib
import jwt
from fastapi import APIRouter, BackgroundTasks, Cookie, Depends, HTTPException, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pwdlib import PasswordHash
from pydantic import BaseModel, Field
from sqlalchemy import select

from .config import settings
from .db import SessionDep
from .models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])
hasher = PasswordHash.recommended()
signer = URLSafeTimedSerializer(settings.secret_key, salt="verify-email")
COOKIE = "session"
SESSION_DAYS = 30


class Credentials(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=320)
    password: str = Field(min_length=8)


async def send_verification(email: str):
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = settings.smtp_from, email, "Verify your Varsis account"
    msg.set_content(f"Confirm your email: {settings.app_url}/verify?token={signer.dumps(email)}")
    await aiosmtplib.send(
        msg,
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_user or None,
        password=settings.smtp_pass or None,
        start_tls=settings.smtp_tls,
    )


async def current_user(db: SessionDep, session: Annotated[str | None, Cookie()] = None) -> User:
    try:
        uid = int(jwt.decode(session or "", settings.secret_key, algorithms=["HS256"])["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(401, "Not logged in")
    user = await db.get(User, uid)
    if not user or not user.is_verified:
        raise HTTPException(401, "Not logged in")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


@router.post("/register", status_code=201)
async def register(data: Credentials, db: SessionDep, tasks: BackgroundTasks):
    email = data.email.lower()
    if await db.scalar(select(User).where(User.email == email)):
        raise HTTPException(400, "Email already registered")
    db.add(User(email=email, password_hash=hasher.hash(data.password)))
    await db.commit()
    tasks.add_task(send_verification, email)
    return {"detail": "Check your email to verify your account"}


@router.post("/verify")
async def verify(token: str, db: SessionDep):
    try:
        email = signer.loads(token, max_age=60 * 60 * 24)
    except (SignatureExpired, BadSignature):
        raise HTTPException(400, "Invalid or expired link")
    user = await db.scalar(select(User).where(User.email == email))
    if not user:
        raise HTTPException(400, "Invalid or expired link")
    user.is_verified = True
    await db.commit()
    return {"detail": "Email verified"}


@router.post("/login")
async def login(data: Credentials, db: SessionDep, response: Response):
    user = await db.scalar(select(User).where(User.email == data.email.lower()))
    if not user or not hasher.verify(data.password, user.password_hash):
        raise HTTPException(401, "Wrong email or password")
    if not user.is_verified:
        raise HTTPException(403, "Email not verified")
    exp = datetime.now(UTC) + timedelta(days=SESSION_DAYS)
    token = jwt.encode({"sub": str(user.id), "exp": exp}, settings.secret_key, algorithm="HS256")
    response.set_cookie(
        COOKIE,
        token,
        max_age=SESSION_DAYS * 86400,
        httponly=True,
        samesite="lax",
        secure=settings.app_url.startswith("https"),
    )
    return {"id": user.id, "email": user.email}


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(COOKIE)
    return {"detail": "Logged out"}


@router.get("/me")
async def me(user: CurrentUser):
    return {"id": user.id, "email": user.email}
