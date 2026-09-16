"""Projects service: listing with visibility, create/update, archive/restore,
membership replacement (mirrored to the legacy ``project_memberships`` table
when a project is linked to a public-site project), health and activity.

``visible_projects_query`` / ``get_visible_project`` are the cross-slice
contract used by work orders, search and reporting.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, case, func, or_, select

from asme.extensions import db
from asme.models.content import Project as LegacyProject
from asme.models.content import ProjectMembership as LegacyProjectMembership
from asme.ops import policy
from asme.ops.models import AuditEvent, CostEntry, Membership, Milestone, OpsProject, ProjectMember, Team, WorkOrder
from asme.ops.models.projects import PROJECT_ROLES, PROJECT_STATUSES, PROJECT_VISIBILITIES, RISK_LEVELS
from asme.ops.models.work import OPEN_STATUSES
from asme.ops.serializers import team_ref
from asme.ops.serializers.projects import effective_milestone_status, milestone as serialize_milestone
from asme.ops.services import audit_events, notifications, purchase_requests
from asme.ops.types import org_today, parse_uuid, utcnow
from asme.ops.validation import Field, ValidationErrors, validate
from asme.services.errors import Conflict, NotFound, Validation

PROJECT_FIELDS = (
    "name",
    "code",
    "description",
    "status",
    "visibility",
    "risk_level",
    "lead_user_id",
    "faculty_advisor_user_id",
    "start_date",
    "target_date",
    "budget_amount",
    "repository_url",
    "cad_url",
    "requirements_url",
    "competition",
    "academic_year",
    "public_project_id",
    "archived_at",
)

VIEWS = ("active", "all", "archived")
LIST_FILTERS = {"lead": "multi", "status": "multi", "risk": "multi", "team": "multi", "academic_year": "multi", "competition": "single"}
SORTS = ("name", "target_date", "updated_at", "risk")
DEFAULT_SORT = "name"
RISK_RANK = {level: index for index, level in enumerate(RISK_LEVELS)}
# "archived" is reached through the archive action only, so both views stay consistent.
EDITABLE_STATUSES = tuple(s for s in PROJECT_STATUSES if s != "archived")

CODE_RE = re.compile(r"^[A-Z0-9][A-Z0-9_-]{0,19}$")
ACADEMIC_YEAR_RE = re.compile(r"^\d{4}-\d{2}$")
MAX_CODE_LEN = 20


def _check_code(value: str) -> str | None:
    if not CODE_RE.match(value.upper()):
        return "Use up to 20 letters, digits, dashes or underscores."
    return None


def _check_academic_year(value: str) -> str | None:
    if not ACADEMIC_YEAR_RE.match(value):
        return "Use the form YYYY-YY, for example 2026-27."
    return None


PROJECT_SPEC = {
    "name": Field("str", required=True, nullable=False, max_len=200, min_len=1),
    "code": Field("str", max_len=MAX_CODE_LEN, check=_check_code),
    "description": Field("text"),
    "status": Field("choice", choices=EDITABLE_STATUSES, default="active", nullable=False),
    "visibility": Field("choice", choices=PROJECT_VISIBILITIES, default="chapter", nullable=False),
    "risk_level": Field("choice", choices=RISK_LEVELS, default="low", nullable=False),
    "lead_user_id": Field("int"),
    "faculty_advisor_user_id": Field("int"),
    "start_date": Field("date"),
    "target_date": Field("date"),
    "budget_amount": Field("decimal", minimum=0),
    "repository_url": Field("url", max_len=500),
    "cad_url": Field("url", max_len=500),
    "requirements_url": Field("url", max_len=500),
    "competition": Field("str", max_len=200),
    "academic_year": Field("str", max_len=12, check=_check_academic_year),
    "public_project_id": Field("int"),
}

# On update a null code would violate NOT NULL; report it like any other bad field.
UPDATE_SPEC = {**PROJECT_SPEC, "code": Field("str", max_len=MAX_CODE_LEN, nullable=False, check=_check_code)}

MEMBER_ITEM_SPEC = {
    "user_id": Field("int", required=True, nullable=False),
    "project_role": Field("choice", choices=PROJECT_ROLES, default="member", nullable=False),
    "team_id": Field("uuid"),
}
MEMBERS_SPEC = {"members": Field("list", required=True, nullable=False, item=Field("any"))}

LEAD_MUST_REMAIN = "The project lead must remain a member."


# --------------------------------------------------------------------------- visibility


def visible_projects_query(ctx):
    """Projects in ``ctx.org`` the user may read: chapter-visible ones, the ones
    they are a member of, and every project for ``project.read_private`` holders."""
    query = OpsProject.query.filter(OpsProject.organization_id == ctx.org.id)
    if ctx.has("project.read_private"):
        return query
    criterion = OpsProject.visibility == "chapter"
    if ctx.project_ids:
        criterion = or_(criterion, OpsProject.id.in_(list(ctx.project_ids)))
    return query.filter(criterion)


def get_visible_project(ctx, project_id) -> OpsProject:
    """Load a project by id (string or UUID); 404 when missing, foreign or hidden."""
    pid = parse_uuid(project_id)
    if pid is None:
        raise NotFound()
    project = policy.get_or_404(ctx, OpsProject, pid)
    if not policy.can_read_project(ctx, project):
        raise NotFound()
    return project


# --------------------------------------------------------------------------- listing


def _parse_int_list(values: list[str], name: str) -> list[int]:
    out: list[int] = []
    for raw in values:
        try:
            out.append(int(raw))
        except (TypeError, ValueError):
            raise Validation(f"Invalid {name} id '{raw}'.", field="filter", code="bad_filter")
    return out


def _parse_uuid_list(values: list[str], name: str) -> list[UUID]:
    out: list[UUID] = []
    for raw in values:
        parsed = parse_uuid(raw)
        if parsed is None:
            raise Validation(f"Invalid {name} id '{raw}'.", field="filter", code="bad_filter")
        out.append(parsed)
    return out


def list_query(ctx, *, view: str = "active", q: str = "", filters: dict[str, list[str]] | None = None, sort: str = DEFAULT_SORT):
    """Return an ordered query of visible projects for the list endpoint."""
    if view not in VIEWS:
        raise Validation("view must be one of active, all, archived.", field="view", code="bad_view")
    filters = filters or {}
    query = visible_projects_query(ctx)
    if view == "active":
        query = query.filter(OpsProject.archived_at.is_(None), OpsProject.status != "archived")
    elif view == "archived":
        query = query.filter(OpsProject.archived_at.is_not(None))
    if q:
        needle = f"%{q.lower()}%"
        query = query.filter(or_(func.lower(OpsProject.name).like(needle), func.lower(OpsProject.code).like(needle)))
    if filters.get("lead"):
        query = query.filter(OpsProject.lead_user_id.in_(_parse_int_list(filters["lead"], "lead")))
    if filters.get("status"):
        query = query.filter(OpsProject.status.in_(filters["status"]))
    if filters.get("risk"):
        query = query.filter(OpsProject.risk_level.in_(filters["risk"]))
    if filters.get("team"):
        team_ids = _parse_uuid_list(filters["team"], "team")
        via_team = select(Team.project_id).where(Team.id.in_(team_ids), Team.project_id.is_not(None))
        via_member = select(ProjectMember.project_id).where(ProjectMember.team_id.in_(team_ids))
        query = query.filter(or_(OpsProject.id.in_(via_team), OpsProject.id.in_(via_member)))
    if filters.get("academic_year"):
        query = query.filter(OpsProject.academic_year.in_(filters["academic_year"]))
    if filters.get("competition"):
        query = query.filter(func.lower(OpsProject.competition) == filters["competition"][0].lower())
    return query.order_by(*_order_clauses(sort))


def _order_clauses(sort: str):
    descending = sort.startswith("-")
    key = sort[1:] if descending else sort
    if key not in SORTS:
        raise Validation(f"Unknown sort '{sort}'.", field="sort", code="bad_sort")
    if key == "name":
        column = func.lower(OpsProject.name)
    elif key == "target_date":
        column = OpsProject.target_date
    elif key == "updated_at":
        column = OpsProject.updated_at
    else:
        column = case(RISK_RANK, value=OpsProject.risk_level, else_=0)
    primary = column.desc() if descending else column.asc()
    if key == "target_date":
        primary = primary.nulls_last()
    return (primary, OpsProject.id.asc())


# --------------------------------------------------------------------------- stats


def _completion_percent(done: int, total: int, canceled: int) -> int:
    denominator = total - canceled
    if denominator <= 0:
        return 0
    return int(round(done / denominator * 100))


def stats_for(ctx, projects) -> dict[UUID, dict]:
    """``stats`` blocks for a page of projects, computed with grouped aggregates."""
    ids = [p.id for p in projects]
    if not ids:
        return {}
    now = utcnow()
    today = org_today(ctx.org, now)
    stats = {
        pid: {"open_work_orders": 0, "overdue_work_orders": 0, "completion_percent": 0, "next_milestone": None, "member_count": 0}
        for pid in ids
    }
    work_rows = db.session.execute(
        select(
            WorkOrder.project_id,
            func.count(WorkOrder.id),
            func.sum(case((WorkOrder.status.in_(OPEN_STATUSES), 1), else_=0)),
            func.sum(case((and_(WorkOrder.status.in_(OPEN_STATUSES), WorkOrder.due_at < now), 1), else_=0)),
            func.sum(case((WorkOrder.status == "done", 1), else_=0)),
            func.sum(case((WorkOrder.status == "canceled", 1), else_=0)),
        )
        .where(WorkOrder.organization_id == ctx.org.id, WorkOrder.project_id.in_(ids))
        .group_by(WorkOrder.project_id)
    ).all()
    for project_id, total, open_count, overdue, done, canceled in work_rows:
        block = stats[project_id]
        block["open_work_orders"] = int(open_count or 0)
        block["overdue_work_orders"] = int(overdue or 0)
        block["completion_percent"] = _completion_percent(int(done or 0), int(total or 0), int(canceled or 0))
    member_rows = db.session.execute(
        select(ProjectMember.project_id, func.count(ProjectMember.id)).where(ProjectMember.project_id.in_(ids)).group_by(ProjectMember.project_id)
    ).all()
    for project_id, count in member_rows:
        stats[project_id]["member_count"] = int(count or 0)
    pending = db.session.scalars(
        select(Milestone)
        .where(Milestone.project_id.in_(ids), Milestone.status != "done")
        .order_by(Milestone.project_id, Milestone.due_date.asc().nulls_last(), Milestone.order_index.asc(), Milestone.created_at.asc())
    ).all()
    for row in pending:
        block = stats[row.project_id]
        if block["next_milestone"] is None:
            block["next_milestone"] = serialize_milestone(row, today)
    return stats


# --------------------------------------------------------------------------- helpers


def _active_membership_ids(ctx, user_ids) -> set[int]:
    wanted = {int(u) for u in user_ids if u is not None}
    if not wanted:
        return set()
    rows = db.session.execute(
        select(Membership.user_id).where(
            Membership.organization_id == ctx.org.id, Membership.member_status == "active", Membership.user_id.in_(list(wanted))
        )
    ).all()
    return {row[0] for row in rows}


def _code_taken(org_id, code: str, exclude_id=None) -> bool:
    query = OpsProject.query.filter(OpsProject.organization_id == org_id, OpsProject.code == code)
    if exclude_id is not None:
        query = query.filter(OpsProject.id != exclude_id)
    return db.session.query(query.exists()).scalar()


def generate_code(org_id, name: str) -> str:
    """Initials of the name ("Crater Cruncher Rover" -> "CCR"), or the first three
    letters for a one-word name, made unique per organization with a numeric suffix."""
    words = re.findall(r"[A-Za-z0-9]+", name or "")
    initials = "".join(word[0] for word in words).upper()
    if len(initials) < 2:
        letters = re.sub(r"[^A-Za-z0-9]", "", name or "").upper()
        initials = letters[:3] or "PRJ"
    base = initials[:MAX_CODE_LEN]
    if not _code_taken(org_id, base):
        return base
    suffix = 2
    while True:
        candidate = f"{base[: MAX_CODE_LEN - len(str(suffix))]}{suffix}"
        if not _code_taken(org_id, candidate):
            return candidate
        suffix += 1


def _business_checks(ctx, data: dict, project: OpsProject | None) -> dict[str, str]:
    """Cross-field and reference checks that need cleaned values. Returns errors."""
    errors: dict[str, str] = {}
    start = data.get("start_date", project.start_date if project else None)
    target = data.get("target_date", project.target_date if project else None)
    if start and target and target < start:
        errors["target_date"] = "The target date must be on or after the start date."
    people = {key: data[key] for key in ("lead_user_id", "faculty_advisor_user_id") if data.get(key) is not None}
    if people:
        active = _active_membership_ids(ctx, people.values())
        for key, user_id in people.items():
            if user_id not in active:
                errors[key] = "Choose an active member of this chapter."
    if data.get("public_project_id") is not None and db.session.get(LegacyProject, data["public_project_id"]) is None:
        errors["public_project_id"] = "That public-site project does not exist."
    if data.get("code"):
        data["code"] = data["code"].upper()
        if _code_taken(ctx.org.id, data["code"], exclude_id=project.id if project else None):
            errors["code"] = "That code is already used by another project."
    return errors


def _upsert_member(project: OpsProject, user_id: int, role: str, team_id=None) -> ProjectMember:
    for row in project.members:
        if row.user_id == user_id:
            row.project_role = role
            if team_id is not None:
                row.team_id = team_id
            return row
    row = ProjectMember(user_id=user_id, project_role=role, team_id=team_id)
    project.members.append(row)
    return row


def _member_snapshot(project: OpsProject) -> list[dict]:
    return sorted(
        ({"user_id": m.user_id, "project_role": m.project_role, "team_id": str(m.team_id) if m.team_id else None} for m in project.members),
        key=lambda m: m["user_id"],
    )


def _notify_added(ctx, project: OpsProject, user_ids) -> None:
    notifications.notify(
        ctx,
        user_ids,
        "project.added",
        f"You were added to {project.name}",
        f"{ctx.user.display_name} added you to the project {project.name} ({project.code}).",
        entity=project,
    )


# --------------------------------------------------------------------------- create / update


def create(ctx, payload: dict) -> OpsProject:
    from asme import events

    policy.authorize(ctx, "project.create")
    data = validate(payload, PROJECT_SPEC)
    errors = _business_checks(ctx, data, None)
    if errors:
        raise ValidationErrors(errors)
    code = data.get("code") or generate_code(ctx.org.id, data["name"])
    project = OpsProject(
        organization_id=ctx.org.id,
        name=data["name"],
        code=code,
        description=data.get("description"),
        status=data["status"],
        visibility=data["visibility"],
        risk_level=data["risk_level"],
        lead_user_id=data.get("lead_user_id"),
        faculty_advisor_user_id=data.get("faculty_advisor_user_id"),
        start_date=data.get("start_date"),
        target_date=data.get("target_date"),
        budget_amount=data.get("budget_amount"),
        repository_url=data.get("repository_url"),
        cad_url=data.get("cad_url"),
        requirements_url=data.get("requirements_url"),
        competition=data.get("competition"),
        academic_year=data.get("academic_year"),
        public_project_id=data.get("public_project_id"),
        created_by_user_id=ctx.user.id,
        updated_by_user_id=ctx.user.id,
    )
    db.session.add(project)
    db.session.flush()
    roles: dict[int, str] = {}
    if project.lead_user_id:
        roles[project.lead_user_id] = "lead"
    if project.faculty_advisor_user_id:
        roles.setdefault(project.faculty_advisor_user_id, "advisor")
    roles.setdefault(ctx.user.id, "member")
    for user_id, role in roles.items():
        _upsert_member(project, user_id, role)
    db.session.flush()
    audit_events.record(
        ctx,
        "project.created",
        project,
        after=audit_events.snapshot(project, PROJECT_FIELDS),
        summary=f"Created project {project.name} ({project.code})",
        members=_member_snapshot(project),
    )
    if project.lead_user_id:
        _notify_added(ctx, project, [project.lead_user_id])
    db.session.commit()
    ctx.project_ids.add(project.id)
    events.emit(events.PROJECT_CREATED, project_id=str(project.id), organization_id=str(ctx.org.id))
    return project


def update(ctx, project: OpsProject, payload: dict) -> OpsProject:
    policy.authorize(ctx, "project.manage", project)
    data = validate(payload, UPDATE_SPEC, partial=True)
    errors = _business_checks(ctx, data, project)
    if errors:
        raise ValidationErrors(errors)
    before = audit_events.snapshot(project, PROJECT_FIELDS)
    previous_lead = project.lead_user_id
    previous_advisor = project.faculty_advisor_user_id
    for key, value in data.items():
        setattr(project, key, value)
    if "lead_user_id" in data and project.lead_user_id != previous_lead:
        if previous_lead:
            for row in project.members:
                if row.user_id == previous_lead and row.project_role == "lead":
                    row.project_role = "member"
        if project.lead_user_id:
            _upsert_member(project, project.lead_user_id, "lead")
    if "faculty_advisor_user_id" in data and project.faculty_advisor_user_id != previous_advisor:
        if previous_advisor:
            for row in project.members:
                if row.user_id == previous_advisor and row.project_role == "advisor":
                    row.project_role = "member"
        if project.faculty_advisor_user_id:
            _upsert_member(project, project.faculty_advisor_user_id, "advisor")
    project.updated_by_user_id = ctx.user.id
    db.session.flush()
    audit_events.record(
        ctx,
        "project.updated",
        project,
        before=before,
        after=audit_events.snapshot(project, PROJECT_FIELDS),
        summary=f"Updated project {project.name}",
        changed=sorted(data.keys()),
    )
    db.session.commit()
    return project


# --------------------------------------------------------------------------- archive / restore


def archive(ctx, project: OpsProject) -> OpsProject:
    policy.authorize(ctx, "project.archive", project)
    if project.archived_at is not None:
        raise Conflict("This project is already archived.", code="already_archived")
    before = audit_events.snapshot(project, ("status", "archived_at"))
    project.status = "archived"
    project.archived_at = utcnow()
    project.updated_by_user_id = ctx.user.id
    audit_events.record(
        ctx,
        "project.archived",
        project,
        before=before,
        after=audit_events.snapshot(project, ("status", "archived_at")),
        summary=f"Archived project {project.name}",
    )
    db.session.commit()
    return project


def restore(ctx, project: OpsProject) -> OpsProject:
    policy.authorize(ctx, "project.archive", project)
    if project.archived_at is None:
        raise Conflict("This project is not archived.", code="not_archived")
    before = audit_events.snapshot(project, ("status", "archived_at"))
    project.status = "active"
    project.archived_at = None
    project.updated_by_user_id = ctx.user.id
    audit_events.record(
        ctx,
        "project.restored",
        project,
        before=before,
        after=audit_events.snapshot(project, ("status", "archived_at")),
        summary=f"Restored project {project.name}",
    )
    db.session.commit()
    return project


# --------------------------------------------------------------------------- members


def _clean_members(ctx, payload: dict) -> list[dict]:
    data = validate(payload, MEMBERS_SPEC)
    errors: dict[str, str] = {}
    cleaned: list[dict] = []
    seen: set[int] = set()
    for index, raw in enumerate(data["members"]):
        if not isinstance(raw, dict):
            errors[f"members[{index}]"] = "Each member must be an object."
            continue
        try:
            item = validate(raw, MEMBER_ITEM_SPEC)
        except ValidationErrors as exc:
            for field_name, message in exc.errors.items():
                errors[f"members[{index}].{field_name}"] = message
            continue
        if item["user_id"] in seen:
            errors[f"members[{index}].user_id"] = "This member is listed more than once."
            continue
        seen.add(item["user_id"])
        cleaned.append(item)
    if errors:
        raise ValidationErrors(errors)
    return cleaned


def replace_members(ctx, project: OpsProject, payload: dict) -> OpsProject:
    from asme import events

    policy.authorize(ctx, "project.manage", project)
    wanted = _clean_members(ctx, payload)
    errors: dict[str, str] = {}
    user_ids = [m["user_id"] for m in wanted]
    active = _active_membership_ids(ctx, user_ids)
    inactive = [str(uid) for uid in user_ids if uid not in active]
    if inactive:
        errors["members"] = "Every member must be an active member of this chapter (invalid: " + ", ".join(inactive) + ")."
    team_ids = {m["team_id"] for m in wanted if m.get("team_id")}
    if team_ids:
        known = {
            row[0] for row in db.session.execute(select(Team.id).where(Team.organization_id == ctx.org.id, Team.id.in_(list(team_ids)))).all()
        }
        if team_ids - known:
            errors["members"] = "One or more teams do not belong to this chapter."
    if project.lead_user_id and project.lead_user_id not in set(user_ids):
        errors["members"] = LEAD_MUST_REMAIN
    if errors:
        raise ValidationErrors(errors)

    before = _member_snapshot(project)
    previous_ids = {m.user_id for m in project.members}
    wanted_ids = set(user_ids)
    removed_ids = previous_ids - wanted_ids
    added_ids = wanted_ids - previous_ids
    for row in list(project.members):
        if row.user_id in removed_ids:
            project.members.remove(row)
    for item in wanted:
        # lead_user_id is the source of truth for who leads the project
        role = "lead" if item["user_id"] == project.lead_user_id else item["project_role"]
        member = _upsert_member(project, item["user_id"], role, item.get("team_id"))
        if item.get("team_id") is None:
            member.team_id = None
    project.updated_by_user_id = ctx.user.id
    db.session.flush()

    legacy_id = project.public_project_id
    if legacy_id is not None:
        _mirror_legacy_memberships(project, legacy_id, removed_ids)

    audit_events.record(
        ctx,
        "project.members_changed",
        project,
        before={"members": before},
        after={"members": _member_snapshot(project)},
        summary=f"Updated members of {project.name} (+{len(added_ids)} / -{len(removed_ids)})",
        added=sorted(added_ids),
        removed=sorted(removed_ids),
    )
    if added_ids:
        _notify_added(ctx, project, sorted(added_ids))
    db.session.commit()
    if legacy_id is not None:
        for user_id in sorted(added_ids):
            events.emit(events.TEAM_JOINED, user_id=user_id, project_id=legacy_id)
    return project


def _mirror_legacy_memberships(project: OpsProject, legacy_id: int, removed_ids: set[int]) -> None:
    """Keep the public-site ``project_memberships`` table in step with ops members.
    Legacy columns are naive UTC datetimes."""
    now = datetime.utcnow()
    existing = {row.user_id: row for row in LegacyProjectMembership.query.filter_by(project_id=legacy_id).all()}
    for member in project.members:
        role = "lead" if member.project_role == "lead" else "member"
        row = existing.get(member.user_id)
        if row is None:
            db.session.add(LegacyProjectMembership(project_id=legacy_id, user_id=member.user_id, role=role, joined_at=now, left_at=None))
            continue
        if row.left_at is not None:
            row.joined_at = now
        row.left_at = None
        row.role = role
    for user_id in removed_ids:
        row = existing.get(user_id)
        if row is not None and row.left_at is None:
            row.left_at = now


# --------------------------------------------------------------------------- health / activity


def _related_entity_criterion(ctx, project: OpsProject):
    """Audit events belonging to the project, its milestones and the work orders
    the caller may actually read.

    Work-order audit rows carry ``before``/``after`` snapshots (titles,
    descriptions, assignments, cancel reasons, completion notes), so they are
    restricted to ``visible_work_orders_query`` and to callers who hold a
    work-order read permission at all. Without that the feed would be a way
    around the work-order endpoints' own checks.
    """
    from asme.ops.services.work_orders import visible_work_orders_query

    milestone_ids = [str(row[0]) for row in db.session.execute(select(Milestone.id).where(Milestone.project_id == project.id)).all()]
    parts = [and_(AuditEvent.entity_type == "project", AuditEvent.entity_id == str(project.id))]
    if milestone_ids:
        parts.append(and_(AuditEvent.entity_type == "milestone", AuditEvent.entity_id.in_(milestone_ids)))
    if ctx.has("work_order.read_all") or ctx.has("work_order.read_assigned"):
        readable = visible_work_orders_query(ctx).filter(WorkOrder.project_id == project.id).with_entities(WorkOrder.id)
        work_order_ids = [str(row[0]) for row in readable.all()]
        if work_order_ids:
            parts.append(and_(AuditEvent.entity_type == "work_order", AuditEvent.entity_id.in_(work_order_ids)))
    return and_(AuditEvent.organization_id == project.organization_id, or_(*parts))


def activity_query(ctx, project: OpsProject):
    """Audit events for the project, its milestones and its readable work orders, newest first."""
    return AuditEvent.query.filter(_related_entity_criterion(ctx, project)).order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc())


def health(ctx, project: OpsProject) -> dict:
    now = utcnow()
    today = org_today(ctx.org, now)
    status_rows = db.session.execute(
        select(WorkOrder.status, func.count(WorkOrder.id)).where(WorkOrder.project_id == project.id).group_by(WorkOrder.status)
    ).all()
    by_status = {status: int(count) for status, count in status_rows}
    total = sum(by_status.values())
    overdue = int(
        db.session.scalar(
            select(func.count(WorkOrder.id)).where(WorkOrder.project_id == project.id, WorkOrder.status.in_(OPEN_STATUSES), WorkOrder.due_at < now)
        )
        or 0
    )
    blocked = int(
        db.session.scalar(
            select(func.count(WorkOrder.id)).where(
                WorkOrder.project_id == project.id, WorkOrder.status.in_(OPEN_STATUSES), WorkOrder.is_blocked.is_(True)
            )
        )
        or 0
    )
    done = by_status.get("done", 0)
    canceled = by_status.get("canceled", 0)

    milestones = list(
        db.session.scalars(
            select(Milestone).where(Milestone.project_id == project.id).order_by(Milestone.due_date.asc().nulls_last(), Milestone.order_index.asc())
        )
    )
    effective = [(row, effective_milestone_status(row, today)) for row in milestones]
    upcoming = [serialize_milestone(row, today) for row, status in effective if status not in ("done", "missed")][:3]

    used = db.session.scalar(
        select(func.coalesce(func.sum(CostEntry.amount), 0)).join(WorkOrder, WorkOrder.id == CostEntry.work_order_id).where(WorkOrder.project_id == project.id)
    )
    used = Decimal(str(used or 0))
    amount = project.budget_amount
    remaining = (Decimal(amount) - used) if amount is not None else None
    # Money already promised to this project through approved purchase requests.
    committed = purchase_requests.committed_total(project)

    member_count = int(db.session.scalar(select(func.count(ProjectMember.id)).where(ProjectMember.project_id == project.id)) or 0)
    teams = list(db.session.scalars(select(Team).where(Team.project_id == project.id).order_by(Team.name.asc())))
    since = now - timedelta(days=7)
    activity_7d = int(
        db.session.scalar(select(func.count(AuditEvent.id)).where(_related_entity_criterion(ctx, project), AuditEvent.occurred_at >= since)) or 0
    )
    return {
        "completion_percent": _completion_percent(done, total, canceled),
        "work": {
            "total": total,
            "open": by_status.get("open", 0),
            "in_progress": by_status.get("in_progress", 0),
            "on_hold": by_status.get("on_hold", 0),
            "done": done,
            "canceled": canceled,
            "overdue": overdue,
            "blocked": blocked,
        },
        "milestones": {
            "total": len(milestones),
            "done": sum(1 for _, status in effective if status == "done"),
            "missed": sum(1 for _, status in effective if status == "missed"),
            "upcoming": upcoming,
        },
        "budget": {
            "amount": float(amount) if amount is not None else None,
            "used": float(used),
            "committed": float(committed),
            "remaining": float(remaining) if remaining is not None else None,
        },
        "members": member_count,
        "teams": [team_ref(team) for team in teams],
        "activity_7d": activity_7d,
    }
