"""JSON shape for saved filters (``ops_saved_filters``)."""

from __future__ import annotations

from asme.extensions import db
from asme.ops.models import Team
from asme.ops.serializers import iso, team_ref, uid, user_ref


def saved_filter(row, *, team=None) -> dict:
    """``team`` may be passed by callers that already loaded it; otherwise the
    team is resolved through the session identity map."""
    if team is None and row.team_id is not None:
        team = db.session.get(Team, row.team_id)
    return {
        "id": uid(row.id),
        "entity_type": row.entity_type,
        "name": row.name,
        "visibility": row.visibility,
        "team": team_ref(team) if row.team_id is not None else None,
        "owner": user_ref(row.owner),
        "filter": dict(row.filter_json or {}),
        "sort": row.sort_json,
        "view_type": row.view_type,
        "is_default": bool(row.is_default),
        "created_at": iso(row.created_at),
        "updated_at": iso(row.updated_at),
    }
