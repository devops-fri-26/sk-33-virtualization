"""Sending email: verification and password links, admin notifications."""

import logging
from email.message import EmailMessage

import aiosmtplib
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .models import User

log = logging.getLogger("varsis.mail")


async def send_mail(to: str, subject: str, body: str):
    """Send a plain-text email.

    Runs as a background task, so failures are logged instead of raised.

    Args:
        to: The recipient's address.
        subject: The subject line.
        body: The text of the email.
    """
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = settings.smtp_from, to, subject
    msg.set_content(body)
    implicit_tls = settings.smtp_port == 465  # port 465 is TLS from the start; 587 upgrades with STARTTLS
    try:
        await aiosmtplib.send(
            msg,
            recipients=[to],  # never parsed from the header, so one address can't turn into several
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user or None,
            password=settings.smtp_pass or None,
            use_tls=implicit_tls,
            start_tls=settings.smtp_tls and not implicit_tls,
        )
    except (aiosmtplib.SMTPException, OSError, ValueError):
        log.exception("could not send %r to %s", subject, to)


async def admin_emails(db: AsyncSession) -> list[str]:
    """Find who to notify about things that need an admin.

    Args:
        db: Database session.

    Returns:
        The email addresses of the admins that are approved and not disabled.
    """
    return list(await db.scalars(select(User.email).where(User.is_admin, User.is_approved, ~User.is_disabled)))
