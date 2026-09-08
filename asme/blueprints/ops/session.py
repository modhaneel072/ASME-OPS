"""``GET /api/v1/session`` – who am I, in which chapter, with which permissions."""

from __future__ import annotations

from flask import current_app

from asme.blueprints.ops import bp, json_body, ok
from asme.ops import policy
from asme.ops.serializers import session_payload
from asme.ops.services import preferences
from asme.ops.validation import Field, validate


def build_session_payload(ctx) -> dict:
    cfg = current_app.config["SETTINGS"]
    dismissed = bool(preferences.get_preference(ctx, preferences.SETUP_BANNER_DISMISSED, False))
    return session_payload(ctx, banner_dismissed=dismissed, poll_seconds=cfg.ops_changes_poll_seconds)


@bp.get("/session")
@policy.require_permission()
def get_session():
    ctx = policy.current_context()
    return ok(build_session_payload(ctx))


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
