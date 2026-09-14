"""``GET /api/v1/session`` – who am I, in which chapter, with which permissions –
plus ``PATCH /api/v1/session/profile`` for the signed-in person's own profile."""

from __future__ import annotations

import re

from flask import current_app

from asme.blueprints.ops import bp, json_body, ok
from asme.ops import policy
from asme.ops.serializers import session_payload
from asme.ops.services import preferences
from asme.ops.validation import Field, ValidationErrors, validate
from asme.services import identity

PHONE_RE = re.compile(r"^[0-9+().\-\s/xX#]*$")


def _phone_check(value):
    if value and not PHONE_RE.match(value):
        return "Enter a valid phone number."
    if value and sum(ch.isdigit() for ch in value) < 7:
        return "Enter a phone number with at least 7 digits."
    return None


# E-mail is deliberately absent: it is the sign-in identifier and the address
# password-reset links are sent to, so changing it is an administrator action
# (PATCH /users/:id), not something a hijacked session can do silently.
PROFILE_SPEC = {
    "name": Field("str", nullable=False, min_len=2, max_len=160),
    "major": Field("str", max_len=120),
    "graduation_year": Field("int", minimum=1900, maximum=2100),
    "phone": Field("str", max_len=40, check=_phone_check),
}


def build_session_payload(ctx) -> dict:
    cfg = current_app.config["SETTINGS"]
    dismissed = bool(preferences.get_preference(ctx, preferences.SETUP_BANNER_DISMISSED, False))
    return session_payload(ctx, banner_dismissed=dismissed, poll_seconds=cfg.ops_changes_poll_seconds)


@bp.get("/session")
@policy.require_permission()
def get_session():
    ctx = policy.current_context()
    return ok(build_session_payload(ctx))


@bp.patch("/session/profile")
@policy.require_permission()
def patch_profile():
    ctx = policy.current_context()
    body = json_body()
    if "email" in body:
        raise ValidationErrors({"email": "Your e-mail address can only be changed by a chapter administrator."})
    data = validate(body, PROFILE_SPEC, partial=True)
    user = ctx.user
    # identity.update_profile leaves a field unchanged when given None and clears
    # it when given an empty value, so map "absent" to None and "null" to empty.
    identity.update_profile(
        user,
        data.get("name") or user.name,
        user.email,
        major=(data["major"] or "") if "major" in data else None,
        graduation_year=(data["graduation_year"] or 0) if "graduation_year" in data else None,
        phone=(data["phone"] or "") if "phone" in data else None,
    )
    return ok({"session": build_session_payload(ctx)})


@bp.get("/preferences")
@policy.require_permission()
def get_preferences():
    ctx = policy.current_context()
    return ok({"preferences": preferences.all_preferences(ctx)})


@bp.put("/preferences/<key>")
@policy.require_permission()
def put_preference(key):
    ctx = policy.current_context()
    data = validate(json_body(), {"value": Field("any", required=True, nullable=True)})
    if key not in preferences.ALLOWED_KEYS:
        from asme.services.errors import Validation

        raise Validation("Unknown preference.", field="key", code="bad_preference")
    row = preferences.set_preference(ctx, key, data.get("value"))
    return ok({"key": row.key, "value": row.value_json})
