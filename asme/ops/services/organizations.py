"""Chapter (organization) profile service."""

from __future__ import annotations

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from asme.extensions import db
from asme.ops import policy
from asme.ops.services import audit_events
from asme.ops.types import utcnow
from asme.ops.validation import Field, validate

PROFILE_FIELDS = ("name", "logo_url", "timezone", "academic_year_start_month", "settings_json", "setup_completed_at")


def _check_timezone(value: str) -> str | None:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        return "Unknown time zone. Use an IANA name such as America/Chicago."
    return None


UPDATE_SPEC = {
    "name": Field("str", max_len=200, min_len=2, nullable=False),
    "logo_url": Field("url", max_len=500),
    "timezone": Field("str", max_len=64, nullable=False, check=_check_timezone),
    "academic_year_start_month": Field("int", minimum=1, maximum=12, nullable=False),
    "settings": Field("json"),
    "setup_completed": Field("bool"),
}

ALLOWED_SETTINGS = {"profile_completed", "chapter_short_name", "primary_contact_email", "public_site_url", "default_due_days"}


def update(ctx, payload: dict):
    policy.authorize(ctx, "chapter.settings.manage")
    data = validate(payload, UPDATE_SPEC, partial=True)
    org = ctx.org
    before = audit_events.snapshot(org, PROFILE_FIELDS)
    for key in ("name", "logo_url", "timezone", "academic_year_start_month"):
        if key in data:
            setattr(org, key, data[key])
    if "settings" in data and isinstance(data["settings"], dict):
        merged = dict(org.settings_json or {})
        for key, value in data["settings"].items():
            if key in ALLOWED_SETTINGS:
                merged[key] = value
        org.settings_json = merged
    if "setup_completed" in data:
        org.setup_completed_at = utcnow() if data["setup_completed"] else None
    org.updated_by_user_id = ctx.user.id
    audit_events.record(ctx, "organization.updated", org, before=before, after=audit_events.snapshot(org, PROFILE_FIELDS), summary=f"Updated chapter profile")
    db.session.commit()
    return org
