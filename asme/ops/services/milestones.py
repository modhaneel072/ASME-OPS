"""Milestones service (``ops_milestones``).

Milestones belong to exactly one project; every lookup goes through the
project so a milestone id from another project (or organization) is a 404.
``done`` sets ``completed_at``; leaving ``done`` clears it. The ``missed``
status is computed on read by the serializer.
"""

from __future__ import annotations

from sqlalchemy import func, select

from asme.extensions import db
from asme.ops import policy
from asme.ops.models import Membership, Milestone, OpsProject
from asme.ops.models.projects import MILESTONE_STATUSES
from asme.ops.services import audit_events
from asme.ops.types import parse_uuid, utcnow
from asme.ops.validation import Field, ValidationErrors, validate
from asme.services.errors import NotFound

MILESTONE_FIELDS = ("project_id", "name", "description", "due_date", "status", "owner_user_id", "weight", "order_index", "completed_at")

MILESTONE_SPEC = {
    "name": Field("str", required=True, nullable=False, max_len=200, min_len=1),
    "description": Field("text"),
    "due_date": Field("date"),
    "owner_user_id": Field("int"),
    "weight": Field("int", minimum=1, default=1, nullable=False),
    "status": Field("choice", choices=MILESTONE_STATUSES, default="planned", nullable=False),
    "order_index": Field("int", minimum=0),
}
# On update a null order_index would violate NOT NULL; report it like any other bad field.
UPDATE_SPEC = {**MILESTONE_SPEC, "order_index": Field("int", minimum=0, nullable=False)}


def list_for_project(ctx, project: OpsProject) -> list[Milestone]:
    stmt = select(Milestone).where(Milestone.project_id == project.id).order_by(Milestone.order_index.asc(), Milestone.created_at.asc(), Milestone.id.asc())
    return list(db.session.scalars(stmt))


def get_or_404(ctx, project: OpsProject, milestone_id) -> Milestone:
    mid = parse_uuid(milestone_id)
    if mid is None:
        raise NotFound()
    milestone = policy.get_or_404(ctx, Milestone, mid)
    if milestone.project_id != project.id:
        raise NotFound()
    return milestone


def _check_owner(ctx, data: dict) -> dict[str, str]:
    owner_id = data.get("owner_user_id")
    if owner_id is None:
        return {}
    active = db.session.scalar(
        select(Membership.id).where(Membership.organization_id == ctx.org.id, Membership.user_id == owner_id, Membership.member_status == "active")
    )
    if active is None:
        return {"owner_user_id": "Choose an active member of this chapter."}
    return {}


def _next_order_index(project: OpsProject) -> int:
    current = db.session.scalar(select(func.max(Milestone.order_index)).where(Milestone.project_id == project.id))
    return int(current) + 1 if current is not None else 0


def create(ctx, project: OpsProject, payload: dict) -> Milestone:
    policy.authorize(ctx, "milestone.manage", project)
    data = validate(payload, MILESTONE_SPEC)
    errors = _check_owner(ctx, data)
    if errors:
        raise ValidationErrors(errors)
    order_index = data.get("order_index")
    milestone = Milestone(
        organization_id=ctx.org.id,
        project_id=project.id,
        name=data["name"],
        description=data.get("description"),
        due_date=data.get("due_date"),
        owner_user_id=data.get("owner_user_id"),
        weight=data["weight"],
        status=data["status"],
        order_index=order_index if order_index is not None else _next_order_index(project),
        completed_at=utcnow() if data["status"] == "done" else None,
        created_by_user_id=ctx.user.id,
        updated_by_user_id=ctx.user.id,
    )
    db.session.add(milestone)
    db.session.flush()
    audit_events.record(
        ctx,
        "milestone.created",
        milestone,
        after=audit_events.snapshot(milestone, MILESTONE_FIELDS),
        summary=f"Added milestone {milestone.name} to {project.name}",
        project_id=str(project.id),
    )
    db.session.commit()
    return milestone


def update(ctx, project: OpsProject, milestone: Milestone, payload: dict) -> Milestone:
    policy.authorize(ctx, "milestone.manage", project)
    data = validate(payload, UPDATE_SPEC, partial=True)
    errors = _check_owner(ctx, data)
    if errors:
        raise ValidationErrors(errors)
    before = audit_events.snapshot(milestone, MILESTONE_FIELDS)
    previous_status = milestone.status
    for key, value in data.items():
        setattr(milestone, key, value)
    if milestone.status != previous_status:
        if milestone.status == "done":
            milestone.completed_at = utcnow()
        elif previous_status == "done":
            milestone.completed_at = None
    milestone.updated_by_user_id = ctx.user.id
    db.session.flush()
    audit_events.record(
        ctx,
        "milestone.updated",
        milestone,
        before=before,
        after=audit_events.snapshot(milestone, MILESTONE_FIELDS),
        summary=f"Updated milestone {milestone.name}",
        project_id=str(project.id),
        changed=sorted(data.keys()),
    )
    db.session.commit()
    return milestone


def delete(ctx, project: OpsProject, milestone: Milestone) -> None:
    policy.authorize(ctx, "milestone.manage", project)
    before = audit_events.snapshot(milestone, MILESTONE_FIELDS)
    audit_events.record(
        ctx,
        "milestone.deleted",
        milestone,
        before=before,
        summary=f"Deleted milestone {milestone.name} from {project.name}",
        project_id=str(project.id),
    )
    db.session.delete(milestone)
    db.session.commit()
