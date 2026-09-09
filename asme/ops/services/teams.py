"""Teams service (``ops_teams``, ``ops_team_members``).

Permissions: ``team.read`` to see teams, ``team.manage`` to create or change
them. ``team.manage`` at *team* scope (the ``team_lead`` role) means "teams you
lead", so a team lead who creates a team is made one of its leads; otherwise
the team would be unmanageable by its creator the moment it exists.

Visibility follows projects: a team attached to a private project is hidden
(404, never 403) from anyone who may not read that project.
"""

from __future__ import annotations

from sqlalchemy import false, func, or_, select
from sqlalchemy.orm import joinedload

from asme.extensions import db
from asme.ops import policy
from asme.ops.models import (
    Asset,
    Membership,
    OpsProject,
    ProjectMember,
    SavedFilter,
    Team,
    TeamMember,
    WorkOrder,
    WorkOrderAssignee,
)
from asme.ops.services import audit_events, notifications
from asme.ops.types import parse_uuid
from asme.ops.validation import Field, ValidationErrors, validate
from asme.services.errors import Conflict, NotFound, Validation

TEAM_FIELDS = ("name", "description", "parent_team_id", "project_id", "is_active")
SORTS = ("name", "created_at")
DEFAULT_SORT = "name"
FILTERS = {"project": "multi", "active": "single"}
ACTIVE_FILTER_TRUE = ("true", "1", "yes")
ACTIVE_FILTER_FALSE = ("false", "0", "no")
ACTIVE_FILTER_ALL = ("all",)
MAX_MEMBERS = 500

NAME_TAKEN = "A team with this name already exists."
UNKNOWN_TEAM = "Unknown team."
UNKNOWN_PROJECT = "Unknown project."
OWN_PARENT = "A team cannot be its own parent."
PARENT_CYCLE = "That parent is already a descendant of this team."
NOTHING_TO_UPDATE = "Nothing to update."

CREATE_SPEC = {
    "name": Field("str", required=True, nullable=False, max_len=160, min_len=1),
    "description": Field("text", max_len=4000),
    "parent_team_id": Field("uuid"),
    "project_id": Field("uuid"),
    "members": Field("list", item=Field("json"), max_len=MAX_MEMBERS),
}
UPDATE_SPEC = {
    "name": Field("str", nullable=False, max_len=160, min_len=1),
    "description": Field("text", max_len=4000),
    "parent_team_id": Field("uuid"),
    "project_id": Field("uuid"),
    "is_active": Field("bool", nullable=False),
}
MEMBERS_SPEC = {"members": Field("list", item=Field("json"), required=True, max_len=MAX_MEMBERS)}


# --------------------------------------------------------------------------- visibility


def visible_teams_query(ctx):
    """Teams in ``ctx.org`` the user may read, honouring the scope of their
    ``team.read`` grant and project visibility."""
    query = Team.query.filter(Team.organization_id == ctx.org.id)
    scopes = ctx.scopes("team.read")
    if not scopes:
        return query.filter(false())
    query = query.filter(policy.visible_project_filter(ctx, Team.project_id))
    if "chapter" in scopes:
        return query
    criteria = []
    if "team" in scopes and ctx.team_ids:
        criteria.append(Team.id.in_(list(ctx.team_ids)))
    if "project" in scopes and ctx.project_ids:
        criteria.append(Team.project_id.in_(list(ctx.project_ids)))
    if "own" in scopes:
        criteria.append(Team.created_by_user_id == ctx.user.id)
    if not criteria:
        return query.filter(false())
    return query.filter(or_(*criteria))


def can_read_team(ctx, team: Team) -> bool:
    if team.organization_id != ctx.org.id:
        return False
    if not policy.can(ctx, "team.read", team):
        return False
    if team.project is not None and not policy.can_read_project(ctx, team.project):
        return False
    return True


def get(ctx, team_id) -> Team:
    """Load one team the user may read; foreign, hidden or malformed ids are 404."""
    parsed = parse_uuid(team_id)
    if parsed is None:
        raise NotFound()
    team = policy.get_or_404(ctx, Team, parsed)
    if not can_read_team(ctx, team):
        raise NotFound()
    return team


def _parse_active(raw: str | None) -> bool | None:
    value = (raw or "true").strip().lower()
    if value in ACTIVE_FILTER_TRUE:
        return True
    if value in ACTIVE_FILTER_FALSE:
        return False
    if value in ACTIVE_FILTER_ALL:
        return None
    raise Validation("filter[active] must be true, false or all.", field="filter", code="bad_filter")


def _parse_uuid_list(values, field: str) -> list:
    parsed = []
    for raw in values or ():
        value = parse_uuid(raw)
        if value is None:
            raise Validation(f"filter[{field}] must contain identifiers.", field="filter", code="bad_filter")
        parsed.append(value)
    return parsed


def list_query(ctx, *, q: str = "", project_ids=None, active: str | None = "true", sort: str = DEFAULT_SORT):
    """Ordered query behind ``GET /teams``. ``project_ids`` and ``active`` arrive as
    raw filter strings; ``sort`` is one of ``SORTS`` with an optional ``-`` prefix."""
    query = visible_teams_query(ctx).options(joinedload(Team.project))
    is_active = _parse_active(active)
    if is_active is not None:
        query = query.filter(Team.is_active.is_(is_active))
    projects = _parse_uuid_list(project_ids, "project")
    if projects:
        query = query.filter(Team.project_id.in_(projects))
    text = (q or "").strip().lower()
    if text:
        like = f"%{text}%"
        query = query.filter(or_(func.lower(Team.name).like(like), func.lower(func.coalesce(Team.description, "")).like(like)))
    descending = sort.startswith("-")
    key = sort[1:] if descending else sort
    if key not in SORTS:
        raise Validation(f"Unknown sort '{sort}'.", field="sort", code="bad_sort")
    column = func.lower(Team.name) if key == "name" else Team.created_at
    order = column.desc() if descending else column.asc()
    return query.order_by(order, Team.id.asc())


# --------------------------------------------------------------------------- helpers


def _validate_collecting(payload: dict, spec: dict, *, partial: bool = False) -> tuple[dict, dict[str, str]]:
    """``validate`` that keeps going: returns the cleaned values of the fields that
    passed plus the format errors, so semantic checks can add theirs and the
    client sees every bad field in one response."""
    try:
        return validate(payload, spec, partial=partial), {}
    except ValidationErrors as exc:
        payload = payload if isinstance(payload, dict) else {}
        good_spec = {name: field for name, field in spec.items() if name not in exc.errors}
        good_payload = {name: value for name, value in payload.items() if name in good_spec}
        return validate(good_payload, good_spec, partial=True), dict(exc.errors)


def _name_taken(ctx, name: str, *, exclude_id=None) -> bool:
    query = Team.query.filter(Team.organization_id == ctx.org.id, func.lower(Team.name) == name.lower())
    if exclude_id is not None:
        query = query.filter(Team.id != exclude_id)
    return db.session.query(query.exists()).scalar()


def _resolve_parent(ctx, parent_id, team: Team | None = None) -> tuple[Team | None, str | None]:
    parent = db.session.get(Team, parent_id)
    if parent is None or parent.organization_id != ctx.org.id:
        return None, UNKNOWN_TEAM
    if team is not None:
        if parent.id == team.id:
            return None, OWN_PARENT
        node, seen = parent, set()
        while node is not None and node.id not in seen:
            if node.id == team.id:
                return None, PARENT_CYCLE
            seen.add(node.id)
            node = node.parent
    return parent, None


def _resolve_project(ctx, project_id) -> tuple[OpsProject | None, str | None]:
    project = db.session.get(OpsProject, project_id)
    if project is None or not policy.can_read_project(ctx, project):
        return None, UNKNOWN_PROJECT
    return project, None


def _parse_members(raw_members) -> tuple[dict[int, bool], str | None]:
    """``[{"user_id": int, "is_lead": bool}]`` -> ``{user_id: is_lead}`` or an error message."""
    wanted: dict[int, bool] = {}
    for index, entry in enumerate(raw_members or ()):
        if not isinstance(entry, dict):
            return {}, f"members[{index}] must be an object with user_id and is_lead."
        user_id = entry.get("user_id")
        if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id < 1:
            return {}, f"members[{index}].user_id must be a positive whole number."
        is_lead = entry.get("is_lead", False)
        if not isinstance(is_lead, bool):
            return {}, f"members[{index}].is_lead must be true or false."
        if user_id in wanted:
            return {}, f"members[{index}].user_id {user_id} is listed more than once."
        wanted[user_id] = is_lead
    return wanted, None


def _inactive_user_ids(ctx, user_ids) -> list[int]:
    """User ids from ``user_ids`` that are not ACTIVE members of ``ctx.org``."""
    ids = sorted(set(user_ids))
    if not ids:
        return []
    active = set(
        db.session.scalars(
            select(Membership.user_id).where(
                Membership.organization_id == ctx.org.id, Membership.member_status == "active", Membership.user_id.in_(ids)
            )
        )
    )
    return [user_id for user_id in ids if user_id not in active]


def _members_problem(ctx, wanted: dict[int, bool]) -> str | None:
    missing = _inactive_user_ids(ctx, wanted)
    if missing:
        return "Only active chapter members can join a team (user ids: " + ", ".join(str(i) for i in missing) + ")."
    return None


def _membership_snapshot(team: Team) -> dict:
    return {"member_ids": sorted(team.member_user_ids), "lead_ids": sorted(team.lead_user_ids)}


def _notify_added(ctx, team: Team, user_ids) -> None:
    if not user_ids:
        return
    notifications.notify(
        ctx,
        user_ids,
        "team.added",
        f"You were added to the {team.name} team",
        f"{ctx.user.display_name} added you to {team.name}.",
        entity=team,
    )


def _references(team: Team) -> dict[str, int]:
    """Rows that still point at ``team``; any non-zero count blocks deletion."""
    counts = {
        "child_teams": select(func.count(Team.id)).where(Team.parent_team_id == team.id),
        "work_orders": select(func.count(WorkOrder.id)).where(WorkOrder.team_id == team.id),
        "work_order_assignments": select(func.count(WorkOrderAssignee.id)).where(WorkOrderAssignee.team_id == team.id),
        "assets": select(func.count(Asset.id)).where(Asset.responsible_team_id == team.id),
        "project_members": select(func.count(ProjectMember.id)).where(ProjectMember.team_id == team.id),
        "saved_filters": select(func.count(SavedFilter.id)).where(SavedFilter.team_id == team.id),
    }
    return {name: int(db.session.scalar(stmt) or 0) for name, stmt in counts.items()}


# --------------------------------------------------------------------------- mutations


def create(ctx, payload: dict) -> Team:
    policy.authorize(ctx, "team.manage")
    data, errors = _validate_collecting(payload, CREATE_SPEC)
    if "name" in data and _name_taken(ctx, data["name"]):
        errors["name"] = NAME_TAKEN
    parent = project = None
    if data.get("parent_team_id") is not None:
        parent, problem = _resolve_parent(ctx, data["parent_team_id"])
        if problem:
            errors["parent_team_id"] = problem
    if data.get("project_id") is not None:
        project, problem = _resolve_project(ctx, data["project_id"])
        if problem:
            errors["project_id"] = problem
    wanted: dict[int, bool] = {}
    if data.get("members") is not None:
        wanted, problem = _parse_members(data["members"])
        problem = problem or _members_problem(ctx, wanted)
        if problem:
            errors["members"] = problem
    if errors:
        raise ValidationErrors(errors)
    if "chapter" not in ctx.scopes("team.manage"):
        # Scoped managers (team leads, project leads) keep control of what they create.
        wanted[ctx.user.id] = True

    team = Team(
        organization_id=ctx.org.id,
        name=data["name"],
        description=data.get("description"),
        parent_team_id=parent.id if parent is not None else None,
        project_id=project.id if project is not None else None,
        created_by_user_id=ctx.user.id,
        updated_by_user_id=ctx.user.id,
    )
    db.session.add(team)
    db.session.flush()
    for user_id, is_lead in wanted.items():
        team.members.append(TeamMember(user_id=user_id, is_lead=is_lead))
    db.session.flush()
    audit_events.record(
        ctx,
        "team.created",
        team,
        after={**audit_events.snapshot(team, TEAM_FIELDS), **_membership_snapshot(team)},
        summary=f"Created team {team.name}",
    )
    _notify_added(ctx, team, list(wanted))
    db.session.commit()
    return team


def update(ctx, team_id, payload: dict) -> Team:
    team = get(ctx, team_id)
    policy.authorize(ctx, "team.manage", team)
    data, errors = _validate_collecting(payload, UPDATE_SPEC, partial=True)
    if not data and not errors:
        raise ValidationErrors({"payload": NOTHING_TO_UPDATE})
    if "name" in data and data["name"].lower() != team.name.lower() and _name_taken(ctx, data["name"], exclude_id=team.id):
        errors["name"] = NAME_TAKEN
    parent = project = None
    if data.get("parent_team_id") is not None:
        parent, problem = _resolve_parent(ctx, data["parent_team_id"], team)
        if problem:
            errors["parent_team_id"] = problem
    if data.get("project_id") is not None:
        project, problem = _resolve_project(ctx, data["project_id"])
        if problem:
            errors["project_id"] = problem
    if errors:
        raise ValidationErrors(errors)

    before = audit_events.snapshot(team, TEAM_FIELDS)
    for key in ("name", "description", "is_active"):
        if key in data:
            setattr(team, key, data[key])
    if "parent_team_id" in data:
        team.parent_team_id = parent.id if parent is not None else None
    if "project_id" in data:
        team.project_id = project.id if project is not None else None
    after = audit_events.snapshot(team, TEAM_FIELDS)
    if after != before:
        team.updated_by_user_id = ctx.user.id
        audit_events.record(ctx, "team.updated", team, before=before, after=after, summary=f"Updated team {team.name}")
        db.session.commit()
    return team


def delete(ctx, team_id) -> Team:
    team = get(ctx, team_id)
    policy.authorize(ctx, "team.manage", team)
    references = {name: count for name, count in _references(team).items() if count}
    if references:
        raise Conflict(
            "This team is still referenced by other records; reassign them or deactivate the team instead.",
            code="team_in_use",
            references=references,
        )
    audit_events.record(
        ctx,
        "team.deleted",
        team,
        before={**audit_events.snapshot(team, TEAM_FIELDS), **_membership_snapshot(team)},
        summary=f"Deleted team {team.name}",
    )
    db.session.delete(team)
    db.session.commit()
    return team


def set_members(ctx, team_id, payload: dict) -> Team:
    """Replace the team's membership with ``payload["members"]``."""
    team = get(ctx, team_id)
    policy.authorize(ctx, "team.manage", team)
    data = validate(payload, MEMBERS_SPEC)
    wanted, problem = _parse_members(data["members"])
    problem = problem or _members_problem(ctx, wanted)
    if problem:
        raise ValidationErrors({"members": problem})

    before = _membership_snapshot(team)
    existing = {row.user_id: row for row in team.members}
    for user_id, row in existing.items():
        if user_id in wanted:
            row.is_lead = wanted[user_id]
        else:
            team.members.remove(row)
    added = [user_id for user_id in wanted if user_id not in existing]
    for user_id in added:
        team.members.append(TeamMember(user_id=user_id, is_lead=wanted[user_id]))
    db.session.flush()
    after = _membership_snapshot(team)
    if after != before:
        team.updated_by_user_id = ctx.user.id
        audit_events.record(
            ctx,
            "team.members_changed",
            team,
            before=before,
            after=after,
            summary=f"Changed members of {team.name}",
            added=sorted(added),
            removed=sorted(set(before["member_ids"]) - set(after["member_ids"])),
        )
        _notify_added(ctx, team, added)
        db.session.commit()
    return team
