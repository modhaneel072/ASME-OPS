"""JSON shapes for the ASME Ops API.

This package holds the small, stable reference shapes (``*_ref``), the session
payload and audit events. Each resource has its own module next to this file
(``asme/ops/serializers/<resource>.py``) so verticals never edit a shared file.
Keep field names aligned with ``apps/ops-web/src/api/contracts``.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from asme.ops.types import as_utc


def iso(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return as_utc(value).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def money(value) -> float | None:
    """Money as a JSON number. Non-finite values (which validation rejects, but
    which historical rows may still hold) serialize as ``null`` rather than the
    bare ``NaN``/``Infinity`` literals, which are not valid JSON."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value) if value.is_finite() else None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and number not in (float("inf"), float("-inf")) else None


def uid(value) -> str | None:
    if value is None:
        return None
    return str(value) if isinstance(value, UUID) else str(value)


# --------------------------------------------------------------------------- refs


def user_ref(user) -> dict | None:
    if user is None:
        return None
    return {
        "id": user.id,
        "name": user.display_name if hasattr(user, "display_name") else user.name,
        "email": user.email,
        "avatar_url": getattr(user, "headshot_url", None),
    }


def team_ref(team) -> dict | None:
    if team is None:
        return None
    return {"id": uid(team.id), "name": team.name}


def project_ref(project) -> dict | None:
    if project is None:
        return None
    return {"id": uid(project.id), "name": project.name, "code": project.code, "visibility": project.visibility}


def location_ref(location) -> dict | None:
    if location is None:
        return None
    return {"id": uid(location.id), "name": location.name}


def asset_ref(asset) -> dict | None:
    if asset is None:
        return None
    return {"id": uid(asset.id), "name": asset.name, "code": asset.code, "status": asset.status}


def category_ref(category) -> dict | None:
    if category is None:
        return None
    return {"id": uid(category.id), "name": category.name, "color": category.color, "icon": category.icon}


def vendor_ref(vendor) -> dict | None:
    if vendor is None:
        return None
    return {"id": uid(vendor.id), "name": vendor.name}


def role_ref(role) -> dict | None:
    if role is None:
        return None
    return {"id": uid(role.id), "name": role.name, "system_key": role.system_key, "is_custom": bool(role.is_custom)}


# --------------------------------------------------------------------------- organization / session


def organization(org) -> dict:
    return {
        "id": uid(org.id),
        "name": org.name,
        "slug": org.slug,
        "logo_url": org.logo_url,
        "timezone": org.timezone,
        "academic_year_start_month": org.academic_year_start_month,
        "settings": org.settings,
        "setup_completed_at": iso(org.setup_completed_at),
        "created_at": iso(org.created_at),
        "updated_at": iso(org.updated_at),
    }


def membership(m) -> dict:
    return {
        "id": uid(m.id),
        "role": role_ref(m.role),
        "status": m.member_status,
        "title": m.title,
        "joined_at": iso(m.joined_at),
    }


def session_payload(ctx, *, banner_dismissed: bool = False, poll_seconds: int = 15) -> dict:
    user = ctx.user
    return {
        "user": {
            **user_ref(user),
            "username": user.username or "",
            "legacy_role": user.role,
            "major": user.major,
            "graduation_year": user.graduation_year,
            "last_login_at": iso(user.last_login_at),
        },
        "organization": organization(ctx.org),
        "membership": membership(ctx.membership),
        "permissions": ctx.permission_map(),
        "scope": {
            "project_ids": [uid(p) for p in sorted(ctx.project_ids, key=str)],
            "team_ids": [uid(t) for t in sorted(ctx.team_ids, key=str)],
            "lead_team_ids": [uid(t) for t in sorted(ctx.lead_team_ids, key=str)],
        },
        "setup": {"banner_dismissed": bool(banner_dismissed), "completed": ctx.org.setup_completed_at is not None},
        "features": {"realtime": "polling", "poll_seconds": int(poll_seconds)},
    }


def audit_event(event) -> dict:
    return {
        "id": uid(event.id),
        "event_type": event.event_type,
        "entity_type": event.entity_type,
        "entity_id": event.entity_id,
        "actor": user_ref(event.actor),
        "summary": event.summary,
        "before": event.before_json,
        "after": event.after_json,
        "metadata": event.metadata_json,
        "occurred_at": iso(event.occurred_at),
    }
