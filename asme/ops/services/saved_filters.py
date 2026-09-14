"""Saved filters ("My Filters") for the work-order, project and asset lists.

Rules
-----
* Any member may create private filters for themselves.
* ``visibility`` ``team`` or ``chapter`` requires ``saved_filter.share``; a team
  filter needs ``team_id`` and the requesting user must be a member of that team
  (chapter admins are exempt from the membership requirement so they can
  curate filters for any team).
* Only one default per ``(owner, entity_type)``: setting a new default clears
  the previous one.
* Owners and chapter admins may edit or delete a filter.
* Audit ``saved_filter.created|updated|deleted``.
"""

from __future__ import annotations

from sqlalchemy import and_, or_, select

from asme.extensions import db
from asme.ops import policy
from asme.ops.models import SavedFilter, Team
from asme.ops.models.shared import SAVED_FILTER_VISIBILITIES
from asme.ops.services import audit_events
from asme.ops.types import parse_uuid
from asme.ops.validation import Field, ValidationErrors, validate
from asme.services.errors import Forbidden

ENTITY_TYPES = ("work_order", "project", "asset")
SNAPSHOT_FIELDS = ("entity_type", "name", "visibility", "team_id", "filter_json", "sort_json", "view_type", "is_default")


def _object_only(value):
    return None if isinstance(value, dict) else "Must be an object."


def _sort_value(value):
    """A sort is the list endpoint's ``sort`` string (``-due_at``) or a JSON
    structure for multi-column views."""
    if isinstance(value, str):
        return None if 0 < len(value.strip()) <= 60 else "Keep this under 60 characters."
    return None if isinstance(value, (dict, list)) else "Must be text, an object or a list."


SPEC = {
    "entity_type": Field("choice", required=True, choices=ENTITY_TYPES),
    "name": Field("str", required=True, max_len=120, min_len=1, nullable=False),
    "visibility": Field("choice", choices=SAVED_FILTER_VISIBILITIES, default="private", nullable=False),
    "team_id": Field("uuid"),
    "filter": Field("json", required=True, check=_object_only),
    "sort": Field("any", check=_sort_value),
    "view_type": Field("str", max_len=20),
    "is_default": Field("bool", default=False, nullable=False),
}


# --------------------------------------------------------------------------- reads


def list_for_user(ctx, entity_type: str | None = None) -> tuple[list[SavedFilter], list[SavedFilter]]:
    """Return ``(personal, shared)``. Shared filters are other members' filters
    with ``chapter`` visibility, or ``team`` visibility for a team the user
    belongs to."""
    if entity_type is not None and entity_type not in ENTITY_TYPES:
        raise ValidationErrors({"entity_type": "Choose one of: " + ", ".join(ENTITY_TYPES) + "."})
    base = select(SavedFilter).where(SavedFilter.organization_id == ctx.org.id)
    if entity_type:
        base = base.where(SavedFilter.entity_type == entity_type)
    order = (SavedFilter.entity_type.asc(), SavedFilter.is_default.desc(), SavedFilter.name.asc())
    personal = list(db.session.scalars(base.where(SavedFilter.owner_user_id == ctx.user.id).order_by(*order)))
    shared_criteria = [SavedFilter.visibility == "chapter"]
    if ctx.team_ids:
        shared_criteria.append(and_(SavedFilter.visibility == "team", SavedFilter.team_id.in_(list(ctx.team_ids))))
    shared = list(db.session.scalars(base.where(SavedFilter.owner_user_id != ctx.user.id, or_(*shared_criteria)).order_by(*order)))
    return personal, shared


def get(ctx, filter_id) -> SavedFilter:
    row = policy.get_or_404(ctx, SavedFilter, parse_uuid(filter_id))
    if row.owner_user_id != ctx.user.id and not _is_shared_with(ctx, row) and not ctx.is_chapter_admin:
        raise Forbidden("This filter is not shared with you.")
    return row


def _is_shared_with(ctx, row: SavedFilter) -> bool:
    if row.visibility == "chapter":
        return True
    return row.visibility == "team" and row.team_id in ctx.team_ids


# --------------------------------------------------------------------------- writes


def _check_sharing(ctx, visibility: str, team_id, errors: dict) -> Team | None:
    """Permission + team checks shared by create and update. Returns the team row
    for ``team`` visibility."""
    if visibility != "private" and not ctx.has("saved_filter.share"):
        raise Forbidden("You do not have permission to share filters.", permission="saved_filter.share")
    if visibility != "team":
        return None
    if team_id is None:
        errors["team_id"] = "Choose the team to share this filter with."
        return None
    team = db.session.get(Team, team_id)
    if team is None or team.organization_id != ctx.org.id:
        errors["team_id"] = "Unknown team."
        return None
    if team.id not in ctx.team_ids and not ctx.is_chapter_admin:
        errors["team_id"] = "You can only share filters with a team you belong to."
        return None
    return team


def _clear_other_defaults(owner_user_id: int, entity_type: str, keep_id=None) -> None:
    query = SavedFilter.query.filter_by(owner_user_id=owner_user_id, entity_type=entity_type, is_default=True)
    for other in query.all():
        if keep_id is None or other.id != keep_id:
            other.is_default = False


def create(ctx, payload: dict) -> SavedFilter:
    data = validate(payload, SPEC)
    errors: dict[str, str] = {}
    visibility = data["visibility"]
    _check_sharing(ctx, visibility, data.get("team_id"), errors)
    if errors:
        raise ValidationErrors(errors)
    row = SavedFilter(
        organization_id=ctx.org.id,
        owner_user_id=ctx.user.id,
        entity_type=data["entity_type"],
        name=data["name"],
        visibility=visibility,
        team_id=data.get("team_id") if visibility == "team" else None,
        filter_json=data["filter"],
        sort_json=data.get("sort"),
        view_type=data.get("view_type"),
        is_default=bool(data.get("is_default")),
        created_by_user_id=ctx.user.id,
        updated_by_user_id=ctx.user.id,
    )
    db.session.add(row)
    db.session.flush()
    if row.is_default:
        _clear_other_defaults(ctx.user.id, row.entity_type, keep_id=row.id)
    audit_events.record(ctx, "saved_filter.created", row, after=audit_events.snapshot(row, SNAPSHOT_FIELDS), summary=f"Saved filter '{row.name}'")
    db.session.commit()
    return row


def _authorize_owner_or_admin(ctx, row: SavedFilter) -> None:
    if row.owner_user_id != ctx.user.id and not ctx.is_chapter_admin:
        raise Forbidden("Only the owner or a chapter administrator can change this filter.")


def update(ctx, filter_id, payload: dict) -> SavedFilter:
    row = policy.get_or_404(ctx, SavedFilter, parse_uuid(filter_id))
    _authorize_owner_or_admin(ctx, row)
    data = validate(payload, SPEC, partial=True)
    errors: dict[str, str] = {}
    visibility = data.get("visibility", row.visibility)
    team_id = data.get("team_id", row.team_id) if visibility == "team" else None
    if visibility != row.visibility or ("team_id" in data and visibility == "team"):
        _check_sharing(ctx, visibility, team_id, errors)
    if errors:
        raise ValidationErrors(errors)

    before = audit_events.snapshot(row, SNAPSHOT_FIELDS)
    if "entity_type" in data:
        row.entity_type = data["entity_type"]
    if "name" in data:
        row.name = data["name"]
    row.visibility = visibility
    row.team_id = team_id
    if "filter" in data:
        row.filter_json = data["filter"]
    if "sort" in data:
        row.sort_json = data["sort"]
    if "view_type" in data:
        row.view_type = data["view_type"]
    if "is_default" in data:
        row.is_default = bool(data["is_default"])
    row.updated_by_user_id = ctx.user.id
    if row.is_default:
        _clear_other_defaults(row.owner_user_id, row.entity_type, keep_id=row.id)
    audit_events.record(
        ctx,
        "saved_filter.updated",
        row,
        before=before,
        after=audit_events.snapshot(row, SNAPSHOT_FIELDS),
        summary=f"Updated saved filter '{row.name}'",
    )
    db.session.commit()
    return row


def delete(ctx, filter_id) -> None:
    row = policy.get_or_404(ctx, SavedFilter, parse_uuid(filter_id))
    _authorize_owner_or_admin(ctx, row)
    audit_events.record(ctx, "saved_filter.deleted", row, before=audit_events.snapshot(row, SNAPSHOT_FIELDS), summary=f"Deleted saved filter '{row.name}'")
    db.session.delete(row)
    db.session.commit()
