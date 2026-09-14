"""Delivery of "forgot password" e-mails.

The HTTP endpoint only validates the address, applies the rate limit and
queues an ``auth.password_reset`` outbox job, doing identical database work
whether or not an account exists, so neither the response nor its timing
reveals which addresses are members. The worker looks the account up, mints
the token and sends the mail.

Links carry the token in the URL fragment (``#token=...``). Browsers never send
fragments to a server, so the token cannot reach web-server, proxy or load
balancer access logs, nor a ``Referer`` header.
"""

from __future__ import annotations

import logging
from datetime import datetime
from urllib.parse import urlencode

from sqlalchemy import func

from asme.config import settings
from asme.extensions import db
from asme.integrations import mail
from asme.models import PasswordResetToken, User
from asme.services import identity

log = logging.getLogger("asme.ops.auth")

JOB_KIND = "auth.password_reset"
RESET_PATH = "/app/auth/reset-password"
MAIL_SUBJECT = "Reset your ASME Ops password"
DEV_LOG_PREFIX = "DEVELOPMENT ONLY - password reset link"


def reset_link(origin: str, token: str) -> str:
    """Absolute SPA link that lets the holder of ``token`` set a password."""
    return f"{origin.rstrip('/')}{RESET_PATH}#{urlencode({'token': token})}"


def mail_origin(request_host_url: str) -> str | None:
    """Origin for links sent by e-mail. The configured public URL wins; the
    request's own host is used only outside production, because anyone can
    send a forged ``Host`` header to a public endpoint."""
    cfg = settings()
    if cfg.public_base_url:
        return cfg.public_base_url
    if cfg.is_production:
        return None
    return request_host_url.rstrip("/")


def _mail_body(user: User, link: str) -> str:
    hours = settings().password_reset_hours
    greeting = f"Hello {user.name}," if (user.name or "").strip() else "Hello,"
    return (
        f"{greeting}\n\n"
        + "Someone asked to reset the password for your ASME Ops account.\n\n"
        + f"Set a new password here (the link works once and expires in {hours} hour{'s' if hours != 1 else ''}):\n"
        + f"{link}\n\n"
        + "If you did not ask for this, ignore this e-mail; your password stays the same.\n"
    )


def deliver(email: str, origin: str | None) -> bool:
    """Send a reset link to the active account registered to ``email``.

    Returns True when a link was issued (e-mailed, or logged in development
    without SMTP). Unknown and inactive addresses are a silent no-op. Raises
    when SMTP fails so the outbox retries; the undelivered token is retired
    first, and the raised message carries no link or token.
    """
    cfg = settings()
    normalized = (email or "").strip().lower()
    if not normalized:
        return False
    user = User.query.filter(func.lower(User.email) == normalized, User.is_active.is_(True)).first()
    if user is None:
        return False
    if not origin:
        log.error("password reset for user_id=%s not sent: ASME_PUBLIC_BASE_URL is not set", user.id)
        return False
    smtp_ready = mail.is_configured(cfg)
    if not smtp_ready and cfg.is_production:
        log.error("password reset for user_id=%s not sent: SMTP is not configured", user.id)
        return False

    token = identity.create_password_reset(user)
    link = reset_link(origin, token)
    if not smtp_ready:
        log.warning("%s for %s (SMTP is not configured): %s", DEV_LOG_PREFIX, user.email, link)
        return True
    try:
        mail.send_email(cfg, user.email, MAIL_SUBJECT, _mail_body(user, link))
    except Exception as exc:
        db.session.rollback()
        PasswordResetToken.query.filter(
            PasswordResetToken.token == identity.hash_reset_token(token), PasswordResetToken.used_at.is_(None)
        ).update({PasswordResetToken.used_at: datetime.utcnow()}, synchronize_session=False)
        db.session.commit()
        raise RuntimeError(f"password reset e-mail for user_id={user.id} failed ({type(exc).__name__})") from None
    return True
