"""JSON login/logout for the ASME Ops SPA. Same identity service, same rate
limiter and same session cookie as the HTML login page."""

from __future__ import annotations

from flask import jsonify

from asme.auth.session import current_auth_user, rate_limiter, sign_in_user, sign_out_user
from asme.blueprints.ops import bp, json_body, ok
from asme.ops import policy
from asme.ops.serializers import user_ref
from asme.ops.validation import Field, validate
from asme.services import identity
from asme.utils.http import request_client_ip

LOGIN_SPEC = {
    "identifier": Field("str", required=True, max_len=160),
    "password": Field("str", required=True, max_len=400, strip=False),
}


@bp.post("/auth/login")
def login():
    data = validate(json_body(), LOGIN_SPEC)
    identifier = data["identifier"].lower()
    limiter = rate_limiter()
    ip = request_client_ip()
    blocked, retry_after = limiter.is_limited(ip, identifier)
    if blocked:
        return jsonify({"ok": False, "code": "rate_limited", "error": "Too many login attempts. Try again later.", "retry_after": retry_after}), 429
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
