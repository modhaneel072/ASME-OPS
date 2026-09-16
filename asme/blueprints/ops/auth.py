"""JSON account flows for the ASME Ops SPA: sign in / out, forgot password,
reset (or first-time set) password from an e-mailed or invite link, and change
password. Same identity service, rate limiter and session cookie as the rest
of the application.

Reset links point at the SPA route ``/app/auth/reset-password#token=<token>``;
the token lives in the URL fragment so it never reaches a server log. The SPA
checks it with ``POST /auth/reset-password/status`` (token in the body, never
in a URL). No endpoint returns a reset token or link: tokens reach people only
through e-mail (forgot password) or through the one-time invite link handed to
the inviter for an account that invite created.
"""

from __future__ import annotations

from datetime import datetime

from flask import current_app, jsonify, request

from asme.auth.session import current_auth_user, rate_limiter, refresh_session_credential, sign_in_user, sign_out_user
from asme.blueprints.ops import bp, json_body, ok
from asme.extensions import db
from asme.jobs.outbox import enqueue
from asme.models import PasswordResetToken, User
from asme.ops import policy
from asme.ops.serializers import iso, user_ref
from asme.ops.validation import Field, ValidationErrors, validate
from asme.services import identity, password_reset
from asme.services.errors import Validation
from asme.utils.http import request_client_ip

RESET_PATH = password_reset.RESET_PATH
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 400

# Limiter namespaces keep each flow's counters apart from the login counters
# (and from each other), so no request to one flow can lock anyone out of
# another. The namespace is never derived from client input.
FORGOT_NAMESPACE = "forgot-password"
RESET_NAMESPACE = "reset-password"
CHANGE_NAMESPACE = "change-password"

LOGIN_SPEC = {
    "identifier": Field("str", required=True, max_len=160),
    "password": Field("str", required=True, max_len=PASSWORD_MAX_LENGTH, strip=False),
}

FORGOT_SPEC = {
    "email": Field("email", required=True, max_len=160),
}

TOKEN_SPEC = {
    "token": Field("str", required=True, max_len=200),
}

RESET_SPEC = {
    "token": Field("str", required=True, max_len=200),
    "password": Field("str", required=True, max_len=PASSWORD_MAX_LENGTH, strip=False),
    "confirm_password": Field("str", required=True, max_len=PASSWORD_MAX_LENGTH, strip=False),
}

CHANGE_SPEC = {
    "current_password": Field("str", required=True, max_len=PASSWORD_MAX_LENGTH, strip=False),
    "new_password": Field("str", required=True, max_len=PASSWORD_MAX_LENGTH, strip=False),
    "confirm_password": Field("str", required=True, max_len=PASSWORD_MAX_LENGTH, strip=False),
}


# --------------------------------------------------------------------------- helpers


def invite_link(token: str) -> str:
    """Link returned to the administrator who invited a new account. Only a
    signed-in ``user.manage`` holder receives it, in the response to their own
    request, so their request host is an acceptable fallback origin."""
    origin = current_app.config["SETTINGS"].public_base_url or request.host_url
    return password_reset.reset_link(origin, token)


def mask_email(email: str) -> str:
    """``mo.member@uiowa.edu`` -> ``m***@uiowa.edu``: enough for someone to
    recognise their own address, not enough to harvest it from a link."""
    local, _, domain = (email or "").partition("@")
    if not domain:
        return "***"
    return f"{local[:1]}***@{domain}"


def _rate_limited(message: str, retry_after: int):
    return jsonify({"ok": False, "code": "rate_limited", "error": message, "retry_after": retry_after}), 429


def _invalid_token():
    return jsonify({
        "ok": False,
        "code": "invalid_token",
        "error": "This link is invalid, has already been used or has expired. Request a new one.",
    }), 404


def _usable_reset(token: str) -> PasswordResetToken | None:
    """A reset row that is unused, unexpired and belongs to an active account."""
    row = identity.find_valid_reset(token)
    if row is None:
        return None
    user = db.session.get(User, row.user_id)
    if user is None or not user.is_active:
        return None
    return row


def _password_errors(password: str, confirm: str, *, password_field: str) -> dict[str, str]:
    errors: dict[str, str] = {}
    if len(password) < PASSWORD_MIN_LENGTH:
        errors[password_field] = f"Password must be at least {PASSWORD_MIN_LENGTH} characters."
    if password != confirm:
        errors["confirm_password"] = "Passwords do not match."
    return errors


def _retire_outstanding_resets(user_id: int, *, keep_id: int | None = None) -> None:
    """Mark every other unused reset token for ``user_id`` as used, so a link
    issued before a password change cannot be replayed afterwards."""
    query = PasswordResetToken.query.filter(PasswordResetToken.user_id == user_id, PasswordResetToken.used_at.is_(None))
    if keep_id is not None:
        query = query.filter(PasswordResetToken.id != keep_id)
    query.update({PasswordResetToken.used_at: datetime.utcnow()}, synchronize_session=False)


# --------------------------------------------------------------------------- sign in / out


@bp.post("/auth/login")
def login():
    data = validate(json_body(), LOGIN_SPEC)
    identifier = data["identifier"].lower()
    limiter = rate_limiter()
    ip = request_client_ip()
    blocked, retry_after = limiter.is_limited(ip, identifier)
    if blocked:
        return _rate_limited("Too many login attempts. Try again later.", retry_after)
    user = identity.authenticate(identifier, data["password"])
    if not user:
        limiter.record_failure(ip, identifier)
        return jsonify({"ok": False, "code": "invalid_credentials", "error": "Invalid email, username or password."}), 401
    limiter.clear(ip, identifier)
    sign_in_user(user)
    ctx = policy.load_context(user)
    if ctx is None:
        return ok({"user": user_ref(user), "session": None, "membership": None})
    from asme.blueprints.ops.session import build_session_payload

    return ok({"user": user_ref(user), "session": build_session_payload(ctx)})


@bp.post("/auth/logout")
def logout():
    if current_auth_user():
        sign_out_user()
    response, status = ok({"logged_out": True})
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0, private"
    return response, status


# --------------------------------------------------------------------------- forgot password


@bp.post("/auth/forgot-password")
def forgot_password():
    data = validate(json_body(), FORGOT_SPEC)
    email = data["email"]
    limiter = rate_limiter()
    ip = request_client_ip()
    blocked, retry_after = limiter.is_limited(ip, email, FORGOT_NAMESPACE)
    if blocked:
        return _rate_limited("Too many password reset requests. Try again later.", retry_after)
    # Every request counts and queues the same job whether or not the address
    # has an account: the account lookup happens in the worker, so status,
    # body, limiter behaviour and database work are identical either way.
    limiter.record_failure(ip, email, FORGOT_NAMESPACE)
    enqueue(password_reset.JOB_KIND, {"email": email, "origin": password_reset.mail_origin(request.host_url)})
    db.session.commit()
    return ok({"sent": True})


# --------------------------------------------------------------------------- reset password


@bp.post("/auth/reset-password/status")
def reset_password_status():
    token = validate(json_body(), TOKEN_SPEC)["token"]
    row = _usable_reset(token)
    if row is None:
        return _invalid_token()
    user = db.session.get(User, row.user_id)
    return ok({
        "valid": True,
        "purpose": "invite" if user.last_login_at is None else "reset",
        "email": mask_email(user.email),
        "expires_at": iso(row.expires_at),
    })


@bp.post("/auth/reset-password")
def reset_password():
    data = validate(json_body(), RESET_SPEC)
    errors = _password_errors(data["password"], data["confirm_password"], password_field="password")
    if errors:
        raise ValidationErrors(errors)

    limiter = rate_limiter()
    ip = request_client_ip()
    counter = ip  # per address: tokens differ on every guess

    # The limiter exists to stop token guessing, so only a failed attempt is
    # counted and only a failed attempt is refused. A member holding a real link
    # is never turned away because other people on the same campus address
    # clicked links that had already been used.
    row = _usable_reset(data["token"])
    if row is None:
        blocked, retry_after = limiter.is_limited(ip, counter, RESET_NAMESPACE)
        if blocked:
            return _rate_limited("Too many password reset attempts. Try again later.", retry_after)
        limiter.record_failure(ip, counter, RESET_NAMESPACE)
        return _invalid_token()

    # Claim the token with a conditional UPDATE before touching the password, so
    # two concurrent submissions of the same link cannot both succeed.
    claimed = (
        PasswordResetToken.query.filter(PasswordResetToken.id == row.id, PasswordResetToken.used_at.is_(None))
        .update({PasswordResetToken.used_at: datetime.utcnow()}, synchronize_session=False)
    )
    if claimed != 1:
        db.session.rollback()
        limiter.record_failure(ip, counter, RESET_NAMESPACE)
        return _invalid_token()
    _retire_outstanding_resets(row.user_id, keep_id=row.id)
    try:
        identity.consume_password_reset(row, data["password"], data["confirm_password"])
    except Validation as exc:
        db.session.rollback()
        raise ValidationErrors({exc.extra.get("field") or "password": exc.message})
    except Exception:
        db.session.rollback()
        raise
    return ok({"reset": True})


# --------------------------------------------------------------------------- change password


@bp.post("/auth/change-password")
def change_password():
    user = current_auth_user()
    if user is None:
        return jsonify({"ok": False, "code": "login_required", "error": "Login required."}), 401
    data = validate(json_body(), CHANGE_SPEC)

    limiter = rate_limiter()
    ip = request_client_ip()
    counter = str(user.id)
    blocked, retry_after = limiter.is_limited(ip, counter, CHANGE_NAMESPACE)
    if blocked:
        return _rate_limited("Too many password change attempts. Try again later.", retry_after)

    try:
        identity.change_password(user, data["current_password"], data["new_password"], data["confirm_password"])
    except Validation as exc:
        field = exc.extra.get("field") or "new_password"
        if field == "current_password":
            limiter.record_failure(ip, counter, CHANGE_NAMESPACE)
        raise ValidationErrors({field: exc.message})
    limiter.clear(ip, counter, CHANGE_NAMESPACE)
    _retire_outstanding_resets(user.id)
    db.session.commit()
    # The new password hash ends every other session; keep this one.
    refresh_session_credential(user)
    return ok({"changed": True})
