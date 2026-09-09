"""Work-orders service.

``visible_work_orders_query`` and ``can_read_work_order`` are the cross-slice
contracts used by search, the change feed and reporting; their signatures and
semantics are stable. Everything else implements the work-orders vertical:
create / update / transitions / completion / assignment / watchers / time and
cost entries / dependencies / duplication / listing.

Every mutating function takes ``ctx`` first, authorizes through
``asme.ops.policy``, writes its audit event in the same transaction, commits,
and only then emits domain events.
"""

from __future__ import annotations

import re
from datetime import timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import case, func, or_, select

from asme import events
from asme.extensions import db
from asme.ops import policy
from asme.ops.models import (
    Asset,
    Category,
    CostEntry,
    Location,
    Membership,
    OpsProject,
    Team,
    TeamMember,
    TimeEntry,
    Vendor,
    WorkOrder,
    WorkOrderAsset,
    WorkOrderAssignee,
    WorkOrderCategory,
    WorkOrderDependency,
    WorkOrderStatusHistory,
    WorkOrderWatcher,
)
from asme.ops.models.work import (
    CLOSED_STATUSES,
    COST_TYPES,
    OPEN_STATUSES,
    PARENT_COMPLETION_POLICIES,
    PRIORITIES,
    PRIORITY_RANK,
    WORK_ORDER_STATUSES,
    WORK_TYPES,
)
from asme.ops.numbering import next_number
from asme.ops.services import audit_events, notifications
from asme.ops.types import parse_uuid, utcnow
from asme.ops.validation import Field, ValidationErrors, validate
from asme.services.errors import Conflict, Forbidden, NotFound, Validation

WORK_ORDER_SEQUENCE = "work_order"
MAX_NESTING_DEPTH = 3  # a work order may have at most this many ancestors
SAFETY_CATEGORY_NAME = "safety"
CRITICAL_PRIORITY_MESSAGE = "Critical priority requires a safety officer or lead."
STATUS_ENDPOINT_MESSAGE = "Use the action endpoints to change status."
AUTO_COMPLETE_NOTE = "All sub-work orders completed"

# action -> (allowed from-states, to-state)
TRANSITIONS: dict[str, tuple[tuple[str, ...], str]] = {
    "start": (("open",), "in_progress"),
    "hold": (("in_progress",), "on_hold"),
    "resume": (("on_hold",), "in_progress"),
    "complete": (("open", "in_progress"), "done"),
    "cancel": (("open", "in_progress", "on_hold"), "canceled"),
    "reopen": (("done", "canceled"), "open"),
}
ACTION_PERMISSIONS = {
    "start": "work_order.start",
    "hold": "work_order.start",
    "resume": "work_order.start",
    "complete": "work_order.complete",
    "cancel": "work_order.cancel",
    "reopen": "work_order.edit",
}
STATUS_LABELS = {
    "draft": "a draft",
    "open": "open",
    "in_progress": "in progress",
    "on_hold": "on hold",
    "done": "done",
    "canceled": "canceled",
    "skipped": "skipped",
}

SNAPSHOT_FIELDS = (
    "number",
    "title",
    "description",
    "status",
    "priority",
    "work_type",
    "project_id",
    "location_id",
    "primary_asset_id",
    "team_id",
    "vendor_id",
    "parent_work_order_id",
    "start_at",
    "due_at",
    "completed_at",
    "canceled_at",
    "estimated_minutes",
    "actual_minutes",
    "budget_code",
    "parent_completion_policy",
    "completion_note",
    "is_blocked",
)

# --------------------------------------------------------------------------- specs

CREATE_SPEC = {
    "title": Field("str", required=True, nullable=False, max_len=240, min_len=1),
    "description": Field("text"),
    "priority": Field("choice", choices=PRIORITIES, nullable=False, default="none"),
    "work_type": Field("choice", choices=WORK_TYPES, nullable=False, default="reactive"),
    "project_id": Field("uuid"),
    "location_id": Field("uuid"),
    "primary_asset_id": Field("uuid"),
    "team_id": Field("uuid"),
    "vendor_id": Field("uuid"),
    "parent_id": Field("uuid"),
    "start_at": Field("datetime"),
    "due_at": Field("datetime"),
    "estimated_minutes": Field("int", minimum=0),
    "budget_code": Field("str", max_len=60),
    "parent_completion_policy": Field("choice", choices=PARENT_COMPLETION_POLICIES, nullable=False, default="manual"),
    "assignee_user_ids": Field("list", item=Field("int"), default=list),
    "assignee_team_ids": Field("list", item=Field("uuid"), default=list),
    "watcher_user_ids": Field("list", item=Field("int"), default=list),
    "category_ids": Field("list", item=Field("uuid"), default=list),
    "asset_ids": Field("list", item=Field("uuid"), default=list),
    "draft": Field("bool", default=False),
}

UPDATE_SPEC = {name: spec for name, spec in CREATE_SPEC.items() if name != "draft"}
UPDATE_SPEC["status"] = Field("choice", choices=WORK_ORDER_STATUSES, nullable=False)

ASSIGNEES_SPEC = {
    "user_ids": Field("list", item=Field("int"), default=list),
    "team_ids": Field("list", item=Field("uuid"), default=list),
}
WATCHERS_SPEC = {"user_ids": Field("list", item=Field("int"), default=list)}

TIME_ENTRY_SPEC = {
    "minutes": Field("int", minimum=1),
    "started_at": Field("datetime"),
    "ended_at": Field("datetime"),
    "note": Field("str", max_len=400),
    "user_id": Field("int"),
}
COST_ENTRY_SPEC = {
    "type": Field("choice", choices=COST_TYPES, required=True, nullable=False),
    "amount": Field("decimal", required=True, nullable=False, minimum=0),
    "vendor_id": Field("uuid"),
    "description": Field("str", max_len=400),
}
ASSET_STATUS_SPEC = {
    "status": Field("str", required=True, nullable=False, max_len=30),
    "downtime_type": Field("str", max_len=20),
    "downtime_reason": Field("str", max_len=160),
    "note": Field("text"),
}
FOLLOW_UP_SPEC = {
    "title": Field("str", required=True, nullable=False, max_len=240, min_len=1),
    "description": Field("text"),
    "priority": Field("choice", choices=PRIORITIES, nullable=False),
    "due_at": Field("datetime"),
    "work_type": Field("choice", choices=WORK_TYPES, nullable=False),
}
COMPLETE_SPEC = {
    "note": Field("text"),
    "time_entries": Field("list", item=Field("json"), default=list),
    "cost_entries": Field("list", item=Field("json"), default=list),
    "asset_status": Field("json"),
    "follow_up": Field("json"),
}
DEPENDENCY_SPEC = {"blocking_work_order_id": Field("uuid", required=True, nullable=False)}
# Body of the plain transition endpoints (start/hold/resume/cancel/reopen).
TRANSITION_SPEC = {"note": Field("text", max_len=4000)}
# Payload keys that decide who works on a work order; they need work_order.assign.
ASSIGNMENT_FIELDS = frozenset({"assignee_user_ids", "assignee_team_ids", "watcher_user_ids", "team_id"})

LIST_FILTERS = {
    "status": "multi",
    "priority": "multi",
    "work_type": "multi",
    "project": "multi",
    "location": "multi",
    "asset": "multi",
    "team": "multi",
    "assignee": "multi",
    "category": "multi",
    "due": "single",
    "created_by": "multi",
    "parent": "single",
    "vendor": "multi",
}
LIST_SORTS = ("priority", "due_at", "updated_at", "created_at", "number", "title")
DEFAULT_SORT = "-updated_at"
DUE_CHOICES = ("overdue", "today", "week", "month", "none")
TABS = ("todo", "done", "all")
NUMBER_RE = re.compile(r"^#?(\d+)$")


# --------------------------------------------------------------------------- visibility (cross-slice contract)


def visible_work_orders_query(ctx):
    """Query of work orders in ``ctx.org`` that the user may read.

    * ``work_order.read_all`` -> every work order whose project is visible
      (private projects only when the user is a member or holds
      ``project.read_private``).
    * ``work_order.read_assigned`` only -> work orders the user created, watches,
      is assigned to directly, or that are assigned to one of their teams.
    * neither -> an always-empty query.
    """
    query = WorkOrder.query.filter(WorkOrder.organization_id == ctx.org.id)
    if ctx.has("work_order.read_all"):
        return query.filter(policy.visible_project_filter(ctx, WorkOrder.project_id))
    if not ctx.has("work_order.read_assigned"):
        return query.filter(WorkOrder.id.is_(None))
    assigned_direct = select(WorkOrderAssignee.work_order_id).where(WorkOrderAssignee.user_id == ctx.user.id)
    my_teams = select(TeamMember.team_id).where(TeamMember.user_id == ctx.user.id)
    assigned_team = select(WorkOrderAssignee.work_order_id).where(WorkOrderAssignee.team_id.in_(my_teams))
    watching = select(WorkOrderWatcher.work_order_id).where(WorkOrderWatcher.user_id == ctx.user.id)
    return query.filter(
        or_(
            WorkOrder.created_by_user_id == ctx.user.id,
            WorkOrder.id.in_(assigned_direct),
            WorkOrder.id.in_(assigned_team),
            WorkOrder.id.in_(watching),
        )
    ).filter(policy.visible_project_filter(ctx, WorkOrder.project_id))


def can_read_work_order(ctx, work_order: WorkOrder) -> bool:
    if work_order.organization_id != ctx.org.id:
        return False
    if work_order.project is not None and not policy.can_read_project(ctx, work_order.project):
        return False
    if ctx.has("work_order.read_all"):
        return True
    if not ctx.has("work_order.read_assigned"):
        return False
    return (
        work_order.created_by_user_id == ctx.user.id
        or ctx.user.id in work_order.assignee_user_ids
        or ctx.user.id in work_order.watcher_user_ids
        or bool(work_order.assignee_team_ids & ctx.team_ids)
    )


def get_readable(ctx, work_order_id) -> WorkOrder:
    """Load a work order the user may read; anything else is a 404."""
    wo_id = parse_uuid(work_order_id)
    if wo_id is None:
        raise NotFound()
    wo = policy.get_or_404(ctx, WorkOrder, wo_id)
    if not can_read_work_order(ctx, wo):
        raise NotFound()
    return wo


# --------------------------------------------------------------------------- internals


def _snapshot(wo: WorkOrder) -> dict:
    data = audit_events.snapshot(wo, SNAPSHOT_FIELDS)
    data["assignee_user_ids"] = sorted(wo.assignee_user_ids)
    data["assignee_team_ids"] = sorted(str(t) for t in wo.assignee_team_ids)
    data["watcher_user_ids"] = sorted(wo.watcher_user_ids)
    data["category_ids"] = sorted(str(c) for c in wo.category_ids)
    data["related_asset_ids"] = sorted(str(link.asset_id) for link in wo.asset_links if link.relationship_type == "related")
    return data


def _diff(before: dict, after: dict) -> tuple[dict, dict]:
    changed = [key for key in after if before.get(key) != after.get(key)]
    return {k: before.get(k) for k in changed}, {k: after.get(k) for k in changed}


def _depth(wo: WorkOrder | None) -> int:
    depth = 0
    current = wo
    while current is not None and current.parent_work_order_id is not None:
        depth += 1
        current = current.parent
    return depth


def _subtree_height(wo: WorkOrder) -> int:
    children = list(wo.children)
    if not children:
        return 0
    return 1 + max(_subtree_height(child) for child in children)


def _is_descendant(candidate: WorkOrder, ancestor: WorkOrder) -> bool:
    current = candidate.parent if candidate.parent_work_order_id else None
    while current is not None:
        if current.id == ancestor.id:
            return True
        current = current.parent if current.parent_work_order_id else None
    return False


def _active_member_ids(ctx, user_ids) -> set[int]:
    ids = {int(u) for u in user_ids if u is not None}
    if not ids:
        return set()
    rows = db.session.execute(
        select(Membership.user_id).where(
            Membership.organization_id == ctx.org.id,
            Membership.user_id.in_(list(ids)),
            Membership.member_status == "active",
        )
    ).all()
    return {row[0] for row in rows}


def _org_rows(ctx, model, ids) -> dict:
    wanted = [i for i in ids if i is not None]
    if not wanted:
        return {}
    rows = db.session.scalars(select(model).where(model.organization_id == ctx.org.id, model.id.in_(wanted))).all()
    return {row.id: row for row in rows}


def _team_member_ids(teams) -> set[int]:
    ids: set[int] = set()
    for team in teams:
        if team is not None:
            ids |= team.member_user_ids
    return ids


def _recipients(wo: WorkOrder, *, include_creator: bool = True, include_watchers: bool = True) -> set[int]:
    ids = set(wo.assignee_user_ids)
    ids |= _team_member_ids(a.team for a in wo.assignees if a.team_id)
    if include_watchers:
        ids |= wo.watcher_user_ids
    if include_creator and wo.created_by_user_id:
        ids.add(wo.created_by_user_id)
    return ids


def _notify_assigned(ctx, wo: WorkOrder, user_ids) -> None:
    notifications.notify(ctx, user_ids, "work_order.assigned", f"#{wo.number} {wo.title} assigned to you", entity=wo)


def _notify_status(ctx, wo: WorkOrder, previous: str, note: str | None) -> None:
    title = f"#{wo.number} {wo.title} is now {STATUS_LABELS.get(wo.status, wo.status)}"
    notifications.notify(ctx, _recipients(wo), "work_order.status_changed", title, note, entity=wo)


def _resolve_references(ctx, data: dict, *, wo: WorkOrder | None = None, errors: dict | None = None) -> dict:
    """Turn ids in ``data`` into rows. Problems are added to ``errors`` (raised
    here as one ``ValidationErrors`` when the caller did not pass a dict) so a
    client sees every bad field at once. Returns ``{name: row-or-list}`` for
    the keys present."""
    raise_here = errors is None
    errors = {} if errors is None else errors
    resolved: dict = {}

    if "project_id" in data:
        project = None
        if data["project_id"] is not None:
            project = db.session.get(OpsProject, data["project_id"])
            if project is None or not policy.can_read_project(ctx, project):
                errors["project_id"] = "Unknown project."
                project = None
        resolved["project"] = project

    for key, model, label in (
        ("location_id", Location, "location"),
        ("primary_asset_id", Asset, "asset"),
        ("team_id", Team, "team"),
        ("vendor_id", Vendor, "vendor"),
    ):
        if key in data:
            row = None
            if data[key] is not None:
                row = db.session.get(model, data[key])
                if row is None or row.organization_id != ctx.org.id:
                    errors[key] = f"Unknown {label}."
                    row = None
            resolved[key[:-3]] = row

    if "parent_id" in data:
        parent = None
        if data["parent_id"] is not None:
            parent = db.session.get(WorkOrder, data["parent_id"])
            if parent is None or not can_read_work_order(ctx, parent):
                errors["parent_id"] = "Unknown parent work order."
                parent = None
            elif wo is not None and (parent.id == wo.id or _is_descendant(parent, wo)):
                errors["parent_id"] = "A work order cannot be nested under itself."
                parent = None
        resolved["parent"] = parent

    for key, label in (("assignee_user_ids", "assignee"), ("watcher_user_ids", "watcher")):
        if key in data:
            wanted = list(dict.fromkeys(data[key] or []))
            active = _active_member_ids(ctx, wanted)
            missing = [str(u) for u in wanted if u not in active]
            if missing:
                errors[key] = f"Unknown or inactive {label}: {', '.join(missing)}."
            resolved[key] = [u for u in wanted if u in active]

    if "assignee_team_ids" in data:
        wanted = list(dict.fromkeys(data["assignee_team_ids"] or []))
        rows = _org_rows(ctx, Team, wanted)
        missing = [str(t) for t in wanted if t not in rows]
        if missing:
            errors["assignee_team_ids"] = f"Unknown team: {', '.join(missing)}."
        resolved["assignee_teams"] = [rows[t] for t in wanted if t in rows]

    if "category_ids" in data:
        wanted = list(dict.fromkeys(data["category_ids"] or []))
        rows = _org_rows(ctx, Category, wanted)
        missing = [str(c) for c in wanted if c not in rows]
        if missing:
            errors["category_ids"] = f"Unknown category: {', '.join(missing)}."
        resolved["categories"] = [rows[c] for c in wanted if c in rows]

    if "asset_ids" in data:
        wanted = list(dict.fromkeys(data["asset_ids"] or []))
        rows = _org_rows(ctx, Asset, wanted)
        missing = [str(a) for a in wanted if a not in rows]
        if missing:
            errors["asset_ids"] = f"Unknown asset: {', '.join(missing)}."
        resolved["related_assets"] = [rows[a] for a in wanted if a in rows]

    if errors and raise_here:
        raise ValidationErrors(errors)
    return resolved


def _check_business_rules(ctx, data: dict, resolved: dict, *, wo: WorkOrder | None, errors: dict) -> None:
    """Cross-field rules; problems are added to ``errors`` (no raise)."""
    start_at = data["start_at"] if "start_at" in data else (wo.start_at if wo else None)
    due_at = data["due_at"] if "due_at" in data else (wo.due_at if wo else None)
    if start_at and due_at and due_at < start_at:
        errors["due_at"] = "Due date must be on or after the start date."

    if data.get("priority") == "critical":
        categories = resolved.get("categories")
        if categories is None and wo is not None:
            categories = [link.category for link in wo.category_links]
        has_safety = any(c is not None and c.name.strip().lower() == SAFETY_CATEGORY_NAME for c in categories or ())
        if not (ctx.has("work_order.cancel") or has_safety):
            errors["priority"] = CRITICAL_PRIORITY_MESSAGE

    parent = resolved.get("parent")
    if parent is not None:
        height = _subtree_height(wo) if wo is not None else 0
        if _depth(parent) + 1 + height > MAX_NESTING_DEPTH:
            errors["parent_id"] = f"Sub-work orders can be nested at most {MAX_NESTING_DEPTH} levels deep."


def _resolve_and_check(ctx, data: dict, *, wo: WorkOrder | None) -> dict:
    errors: dict[str, str] = {}
    resolved = _resolve_references(ctx, data, wo=wo, errors=errors)
    _check_business_rules(ctx, data, resolved, wo=wo, errors=errors)
    if errors:
        raise ValidationErrors(errors)
    return resolved


def _sync_asset_links(wo: WorkOrder, related_ids: set | None) -> None:
    """Make ``wo.asset_links`` hold exactly one ``primary`` row (for the primary
    asset) plus one ``related`` row per related asset. ``related_ids=None``
    keeps the current related set. Existing rows are retyped rather than
    deleted and re-inserted so the (work_order, asset) unique key never
    collides inside a single flush."""
    if related_ids is None:
        related_ids = {link.asset_id for link in wo.asset_links if link.relationship_type == "related"}
    wanted: dict = {}
    if wo.primary_asset_id is not None:
        wanted[wo.primary_asset_id] = "primary"
    for asset_id in related_ids:
        if asset_id != wo.primary_asset_id:
            wanted[asset_id] = "related"
    for link in list(wo.asset_links):
        if link.asset_id in wanted:
            link.relationship_type = wanted.pop(link.asset_id)
        else:
            wo.asset_links.remove(link)
    for asset_id, relationship_type in wanted.items():
        wo.asset_links.append(WorkOrderAsset(asset_id=asset_id, relationship_type=relationship_type))


def _set_categories(wo: WorkOrder, categories) -> None:
    wanted = {c.id for c in categories}
    for link in list(wo.category_links):
        if link.category_id not in wanted:
            wo.category_links.remove(link)
    existing = {link.category_id for link in wo.category_links}
    for category in categories:
        if category.id not in existing:
            wo.category_links.append(WorkOrderCategory(category_id=category.id))


def _replace_assignees(wo: WorkOrder, user_ids, teams) -> tuple[set[int], set]:
    """Replace assignees; returns (newly assigned user ids, newly assigned team ids)."""
    wanted_users = set(user_ids)
    wanted_teams = {t.id for t in teams}
    before_users = wo.assignee_user_ids
    before_teams = wo.assignee_team_ids
    for row in list(wo.assignees):
        if (row.user_id and row.user_id not in wanted_users) or (row.team_id and row.team_id not in wanted_teams):
            wo.assignees.remove(row)
    for user_id in wanted_users - before_users:
        wo.assignees.append(WorkOrderAssignee(user_id=user_id))
    for team_id in wanted_teams - before_teams:
        wo.assignees.append(WorkOrderAssignee(team_id=team_id))
    return wanted_users - before_users, wanted_teams - before_teams


def _replace_watchers(wo: WorkOrder, user_ids) -> set[int]:
    wanted = set(user_ids)
    before = wo.watcher_user_ids
    for row in list(wo.watchers):
        if row.user_id not in wanted:
            wo.watchers.remove(row)
    for user_id in wanted - before:
        wo.watchers.append(WorkOrderWatcher(user_id=user_id))
    return wanted - before


def _apply_fields(wo: WorkOrder, data: dict, resolved: dict) -> None:
    for key in ("title", "description", "priority", "work_type", "start_at", "due_at", "estimated_minutes", "budget_code", "parent_completion_policy"):
        if key in data:
            setattr(wo, key, data[key])
    if "project" in resolved:
        wo.project_id = resolved["project"].id if resolved["project"] else None
    if "location" in resolved:
        wo.location_id = resolved["location"].id if resolved["location"] else None
    if "primary_asset" in resolved:
        asset = resolved["primary_asset"]
        wo.primary_asset_id = asset.id if asset else None
        if asset is not None and asset.project_id and wo.project_id is None and "project" not in resolved:
            wo.project_id = asset.project_id
    if "team" in resolved:
        wo.team_id = resolved["team"].id if resolved["team"] else None
    if "vendor" in resolved:
        wo.vendor_id = resolved["vendor"].id if resolved["vendor"] else None
    if "parent" in resolved:
        parent = resolved["parent"]
        wo.parent_work_order_id = parent.id if parent else None
        if parent is not None and wo.project_id is None and "project" not in resolved:
            wo.project_id = parent.project_id
    if "primary_asset" in resolved or "related_assets" in resolved:
        related = {a.id for a in resolved["related_assets"]} if "related_assets" in resolved else None
        _sync_asset_links(wo, related)
    if "categories" in resolved:
        _set_categories(wo, resolved["categories"])


def _create_row(ctx, payload: dict, *, parent: WorkOrder | None = None, pending: list, audit_metadata: dict | None = None) -> WorkOrder:
    """Validate + build + persist (flush, no commit) a new work order. Appends
    the events to emit after commit to ``pending``."""
    policy.authorize(ctx, "work_order.create")
    data = validate(payload, CREATE_SPEC)
    if parent is not None:
        if not can_read_work_order(ctx, parent):
            raise NotFound()
        data["parent_id"] = parent.id
    resolved = _resolve_and_check(ctx, data, wo=None)

    wo = WorkOrder(
        organization_id=ctx.org.id,
        number=next_number(ctx.org.id, WORK_ORDER_SEQUENCE),
        status="draft" if data.get("draft") else "open",
        created_by_user_id=ctx.user.id,
        updated_by_user_id=ctx.user.id,
        actual_minutes=0,
        is_blocked=False,
    )
    _apply_fields(wo, data, resolved)
    new_users, new_teams = _replace_assignees(wo, resolved.get("assignee_user_ids", []), resolved.get("assignee_teams", []))
    _replace_watchers(wo, resolved.get("watcher_user_ids", []))
    db.session.add(wo)
    db.session.flush()

    wo.status_history.append(WorkOrderStatusHistory(from_status=None, to_status=wo.status, changed_by_user_id=ctx.user.id))
    audit_events.record(
        ctx,
        "work_order.created",
        wo,
        after=_snapshot(wo),
        summary=f"Created #{wo.number} {wo.title}",
        **(audit_metadata or {}),
    )
    teams_by_id = {t.id: t for t in resolved.get("assignee_teams", [])}
    assigned = set(new_users) | _team_member_ids(teams_by_id[t] for t in new_teams)
    _notify_assigned(ctx, wo, assigned)
    watchers = set(resolved.get("watcher_user_ids", [])) - assigned
    if watchers:
        notifications.notify(
            ctx,
            watchers,
            "work_order.status_changed",
            f"#{wo.number} {wo.title} was created and you are watching it",
            entity=wo,
        )
    pending.append((events.WORK_ORDER_CREATED, {"work_order_id": str(wo.id), "organization_id": str(ctx.org.id)}))
    return wo


def _emit_all(pending: list) -> None:
    for name, payload in pending:
        events.emit(name, **payload)


def _change_status(ctx, wo: WorkOrder, action: str, *, note: str | None, pending: list, audit_metadata: dict | None = None, system: bool = False) -> str:
    """Apply ``action`` to ``wo`` inside the caller's transaction. Returns the
    previous status. ``system`` skips the permission check (parent auto-complete)."""
    allowed_from, to_status = TRANSITIONS[action]
    if not system:
        policy.authorize(ctx, ACTION_PERMISSIONS[action], wo)
    if wo.status not in allowed_from:
        raise Conflict(
            f"Cannot {action} a work order that is {STATUS_LABELS.get(wo.status, wo.status)}.",
            code="invalid_transition",
            **{"from": wo.status, "action": action},
        )
    if action == "cancel" and not (note or "").strip():
        raise ValidationErrors({"note": "A reason is required to cancel a work order."})
    if action == "start":
        blockers = recompute_blocked(wo)
        if blockers:
            numbers = sorted(b.number for b in blockers)
            raise Conflict(
                "This work order is blocked by " + ", ".join(f"#{n}" for n in numbers) + ".",
                code="blocked",
                blocking=numbers,
            )

    now = utcnow()
    previous = wo.status
    wo.status = to_status
    wo.updated_by_user_id = ctx.user.id
    if action == "start" and wo.start_at is None:
        wo.start_at = now
    if to_status == "done":
        wo.completed_at = now
        wo.canceled_at = None
        if note:
            wo.completion_note = note
        wo.actual_minutes = sum(int(e.minutes) for e in wo.time_entries)
    elif to_status == "canceled":
        wo.canceled_at = now
    elif action == "reopen":
        wo.completed_at = None
        wo.canceled_at = None
    wo.status_history.append(WorkOrderStatusHistory(from_status=previous, to_status=to_status, changed_by_user_id=ctx.user.id, note=note))
    audit_events.record(
        ctx,
        "work_order.status_changed",
        wo,
        before={"status": previous},
        after={"status": to_status},
        summary=f"#{wo.number} {wo.title}: {previous} -> {to_status}",
        action=action,
        note=note,
        **(audit_metadata or {}),
    )
    _notify_status(ctx, wo, previous, note)
    for dep in wo.blocking:
        recompute_blocked(dep.blocked)
    pending.append(
        (
            events.WORK_ORDER_STATUS_CHANGED,
            {"work_order_id": str(wo.id), "organization_id": str(ctx.org.id), "status": to_status, "previous": previous},
        )
    )
    if to_status in CLOSED_STATUSES:
        _auto_complete_parent(ctx, wo, pending)
    return previous


def _auto_complete_parent(ctx, child: WorkOrder, pending: list) -> None:
    parent = child.parent if child.parent_work_order_id else None
    if parent is None or parent.parent_completion_policy != "auto":
        return
    if parent.status not in ("open", "in_progress"):
        return
    if any(sibling.status not in CLOSED_STATUSES for sibling in parent.children):
        return
    _change_status(ctx, parent, "complete", note=AUTO_COMPLETE_NOTE, pending=pending, system=True, audit_metadata={"auto": True})


def _validate_time_entry(ctx, wo: WorkOrder, raw: dict) -> dict:
    """Clean one time-entry payload. Error keys are unprefixed; ``complete``
    prefixes them with ``time_entries[i].`` itself."""
    if not isinstance(raw, dict):
        raise ValidationErrors({"time_entry": "Must be an object."})
    data = validate(raw, TIME_ENTRY_SPEC)
    errors: dict[str, str] = {}
    started, ended = data.get("started_at"), data.get("ended_at")
    if started and ended and ended < started:
        errors["ended_at"] = "End must be after start."
    minutes = data.get("minutes")
    if minutes is None:
        if started and ended and not errors:
            minutes = int((ended - started).total_seconds() // 60)
            if minutes < 1:
                errors["minutes"] = "Must be at least 1."
        else:
            errors["minutes"] = "This field is required."
    user_id = data.get("user_id") or ctx.user.id
    if user_id != ctx.user.id:
        if not policy.can(ctx, "work_order.assign", wo):
            raise Forbidden("Only assigners can log time for other people.", permission="work_order.assign")
        if user_id not in _active_member_ids(ctx, [user_id]):
            errors["user_id"] = "Unknown or inactive user."
    if errors:
        raise ValidationErrors(errors)
    return {"user_id": user_id, "minutes": minutes, "started_at": started, "ended_at": ended, "note": data.get("note")}


def _validate_cost_entry(ctx, raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise ValidationErrors({"cost_entry": "Must be an object."})
    data = validate(raw, COST_ENTRY_SPEC)
    vendor = None
    if data.get("vendor_id") is not None:
        vendor = db.session.get(Vendor, data["vendor_id"])
        if vendor is None or vendor.organization_id != ctx.org.id:
            raise ValidationErrors({"vendor_id": "Unknown vendor."})
    return {"type": data["type"], "amount": Decimal(data["amount"]).quantize(Decimal("0.01")), "vendor_id": vendor.id if vendor else None, "description": data.get("description")}


def _prefixed(errors: dict, prefix: str) -> dict:
    return {f"{prefix}{key}": message for key, message in errors.items()}


def _add_time_entry_row(ctx, wo: WorkOrder, entry: dict) -> TimeEntry:
    row = TimeEntry(
        organization_id=ctx.org.id,
        work_order_id=wo.id,
        user_id=entry["user_id"],
        minutes=entry["minutes"],
        started_at=entry.get("started_at"),
        ended_at=entry.get("ended_at"),
        note=entry.get("note"),
        created_by_user_id=ctx.user.id,
        updated_by_user_id=ctx.user.id,
    )
    wo.time_entries.append(row)
    db.session.flush()
    wo.actual_minutes = sum(int(e.minutes) for e in wo.time_entries)
    wo.updated_by_user_id = ctx.user.id
    audit_events.record(
        ctx,
        "work_order.time_logged",
        wo,
        after={"time_entry_id": str(row.id), "user_id": row.user_id, "minutes": row.minutes, "note": row.note},
        summary=f"Logged {row.minutes} min on #{wo.number}",
    )
    return row


def _add_cost_entry_row(ctx, wo: WorkOrder, entry: dict) -> CostEntry:
    row = CostEntry(
        organization_id=ctx.org.id,
        work_order_id=wo.id,
        type=entry["type"],
        amount=entry["amount"],
        vendor_id=entry.get("vendor_id"),
        description=entry.get("description"),
        created_by_user_id=ctx.user.id,
        updated_by_user_id=ctx.user.id,
    )
    wo.cost_entries.append(row)
    db.session.flush()
    wo.updated_by_user_id = ctx.user.id
    audit_events.record(
        ctx,
        "work_order.cost_added",
        wo,
        after={"cost_entry_id": str(row.id), "type": row.type, "amount": row.amount, "vendor_id": row.vendor_id, "description": row.description},
        summary=f"Added {row.type} cost {row.amount} on #{wo.number}",
    )
    return row


# --------------------------------------------------------------------------- create / update


def create(ctx, data: dict, *, parent: WorkOrder | None = None) -> WorkOrder:
    pending: list = []
    wo = _create_row(ctx, data, parent=parent, pending=pending)
    db.session.commit()
    _emit_all(pending)
    return wo


def update(ctx, wo: WorkOrder, data: dict) -> WorkOrder:
    policy.authorize(ctx, "work_order.edit", wo)
    cleaned = validate(data, UPDATE_SPEC, partial=True)
    # Who a work order is assigned to (and which team owns it) is governed by
    # work_order.assign, not work_order.edit: a full member may edit their own
    # work order but must not put it on someone else's plate or move it under a
    # team whose lead would then inherit scope over it.
    if ASSIGNMENT_FIELDS & cleaned.keys():
        policy.authorize(ctx, "work_order.assign", wo)
    publish = False
    if "status" in cleaned:
        target = cleaned.pop("status")
        if target != wo.status:
            if wo.status == "draft" and target == "open":
                publish = True
            else:
                raise ValidationErrors({"status": STATUS_ENDPOINT_MESSAGE})
    resolved = _resolve_and_check(ctx, cleaned, wo=wo)

    pending: list = []
    before = _snapshot(wo)
    _apply_fields(wo, cleaned, resolved)
    new_users: set[int] = set()
    new_teams: set = set()
    if "assignee_user_ids" in resolved or "assignee_teams" in resolved:
        new_users, new_teams = _replace_assignees(
            wo,
            resolved.get("assignee_user_ids", sorted(wo.assignee_user_ids)),
            resolved.get("assignee_teams", [a.team for a in wo.assignees if a.team_id]),
        )
    if "watcher_user_ids" in resolved:
        _replace_watchers(wo, resolved["watcher_user_ids"])
    if publish:
        previous = wo.status
        wo.status = "open"
        wo.status_history.append(WorkOrderStatusHistory(from_status=previous, to_status="open", changed_by_user_id=ctx.user.id))
        audit_events.record(
            ctx,
            "work_order.status_changed",
            wo,
            before={"status": previous},
            after={"status": "open"},
            summary=f"#{wo.number} {wo.title}: {previous} -> open",
            action="publish",
        )
        _notify_status(ctx, wo, previous, None)
        pending.append(
            (events.WORK_ORDER_STATUS_CHANGED, {"work_order_id": str(wo.id), "organization_id": str(ctx.org.id), "status": "open", "previous": previous})
        )
    wo.updated_by_user_id = ctx.user.id
    db.session.flush()
    after = _snapshot(wo)
    before_changed, after_changed = _diff(before, after)
    if before_changed or publish:
        audit_events.record(
            ctx,
            "work_order.updated",
            wo,
            before=before_changed,
            after=after_changed,
            summary=f"Updated #{wo.number} {wo.title}",
            fields=sorted(after_changed),
        )
    teams_by_id = {a.team_id: a.team for a in wo.assignees if a.team_id}
    newly = set(new_users) | _team_member_ids(teams_by_id.get(t) for t in new_teams)
    _notify_assigned(ctx, wo, newly)
    db.session.commit()
    _emit_all(pending)
    return wo


# --------------------------------------------------------------------------- transitions


def transition(ctx, wo: WorkOrder, action: str, *, note: str | None = None, **kwargs) -> WorkOrder:
    if action not in TRANSITIONS:
        raise Validation(f"Unknown action '{action}'.", field="action", code="bad_action")
    if action == "complete":
        return complete(ctx, wo, note=note, **kwargs)["work_order"]
    if kwargs:
        raise Validation("This action does not accept extra fields.", code="bad_request")
    pending: list = []
    _change_status(ctx, wo, action, note=(note or "").strip() or None, pending=pending)
    db.session.commit()
    _emit_all(pending)
    return wo


def complete(
    ctx,
    wo: WorkOrder,
    *,
    note: str | None = None,
    time_entries=(),
    cost_entries=(),
    asset_status: dict | None = None,
    follow_up: dict | None = None,
) -> dict:
    policy.authorize(ctx, "work_order.complete", wo)
    body = validate(
        {
            # Pass the client's values through untouched so a number or boolean
            # is answered with a field error instead of a TypeError.
            "note": note,
            "time_entries": [] if time_entries is None else time_entries,
            "cost_entries": [] if cost_entries is None else cost_entries,
            "asset_status": asset_status,
            "follow_up": follow_up,
        },
        COMPLETE_SPEC,
    )
    if wo.status not in TRANSITIONS["complete"][0]:
        raise Conflict(
            f"Cannot complete a work order that is {STATUS_LABELS.get(wo.status, wo.status)}.",
            code="invalid_transition",
            **{"from": wo.status, "action": "complete"},
        )

    errors: dict[str, str] = {}
    cleaned_time: list[dict] = []
    for index, raw in enumerate(body["time_entries"]):
        try:
            cleaned_time.append(_validate_time_entry(ctx, wo, raw))
        except ValidationErrors as exc:
            errors.update(_prefixed(exc.errors, f"time_entries[{index}]."))
    cleaned_cost: list[dict] = []
    for index, raw in enumerate(body["cost_entries"]):
        try:
            cleaned_cost.append(_validate_cost_entry(ctx, raw))
        except ValidationErrors as exc:
            errors.update(_prefixed(exc.errors, f"cost_entries[{index}]."))
    asset_change = None
    if body.get("asset_status") is not None:
        if not isinstance(body["asset_status"], dict):
            errors["asset_status"] = "Must be an object."
        elif wo.primary_asset is None:
            errors["asset_status"] = "This work order has no primary asset."
        else:
            try:
                asset_change = validate(body["asset_status"], ASSET_STATUS_SPEC)
            except ValidationErrors as exc:
                errors.update(_prefixed(exc.errors, "asset_status."))
    follow_up_data = None
    if body.get("follow_up") is not None:
        if not isinstance(body["follow_up"], dict):
            errors["follow_up"] = "Must be an object."
        else:
            try:
                follow_up_data = validate(body["follow_up"], FOLLOW_UP_SPEC)
            except ValidationErrors as exc:
                errors.update(_prefixed(exc.errors, "follow_up."))
    if errors:
        raise ValidationErrors(errors)

    pending: list = []
    for entry in cleaned_time:
        _add_time_entry_row(ctx, wo, entry)
    for entry in cleaned_cost:
        _add_cost_entry_row(ctx, wo, entry)

    if asset_change is not None:
        from asme.ops.services import assets as assets_service

        asset = wo.primary_asset
        previous_asset_status = asset.status
        try:
            assets_service.change_status(
                ctx,
                asset,
                asset_change["status"],
                downtime_type=asset_change.get("downtime_type"),
                downtime_reason=asset_change.get("downtime_reason"),
                note=asset_change.get("note"),
                work_order=wo,
                commit=False,
            )
        except ValidationErrors as exc:
            raise ValidationErrors(_prefixed(exc.errors, "asset_status."))
        pending.append(
            (
                events.ASSET_STATUS_CHANGED,
                {"asset_id": str(asset.id), "organization_id": str(ctx.org.id), "status": asset.status, "previous": previous_asset_status},
            )
        )

    follow_up_row = None
    if follow_up_data is not None:
        description = f"Follow-up to #{wo.number}"
        if follow_up_data.get("description"):
            description = f"{description}\n\n{follow_up_data['description']}"
        payload = {
            "title": follow_up_data["title"],
            "description": description,
            "priority": follow_up_data.get("priority") or wo.priority,
            "work_type": follow_up_data.get("work_type") or wo.work_type,
            "due_at": follow_up_data.get("due_at").isoformat() if follow_up_data.get("due_at") else None,
            "project_id": str(wo.project_id) if wo.project_id else None,
            "location_id": str(wo.location_id) if wo.location_id else None,
            "primary_asset_id": str(wo.primary_asset_id) if wo.primary_asset_id else None,
            "team_id": str(wo.team_id) if wo.team_id else None,
        }
        try:
            follow_up_row = _create_row(ctx, payload, pending=pending, audit_metadata={"follow_up_of": str(wo.id)})
        except ValidationErrors as exc:
            raise ValidationErrors(_prefixed(exc.errors, "follow_up."))

    metadata = {"follow_up_id": str(follow_up_row.id)} if follow_up_row is not None else None
    _change_status(ctx, wo, "complete", note=(body.get("note") or "").strip() or None, pending=pending, audit_metadata=metadata)
    db.session.commit()
    _emit_all(pending)
    return {"work_order": wo, "follow_up": follow_up_row}


# --------------------------------------------------------------------------- assignment / watchers


def set_assignees(ctx, wo: WorkOrder, user_ids, team_ids) -> WorkOrder:
    policy.authorize(ctx, "work_order.assign", wo)
    data = validate({"user_ids": user_ids if user_ids is not None else [], "team_ids": team_ids if team_ids is not None else []}, ASSIGNEES_SPEC)
    resolved = _resolve_references(ctx, {"assignee_user_ids": data["user_ids"], "assignee_team_ids": data["team_ids"]})
    before = {"user_ids": sorted(wo.assignee_user_ids), "team_ids": sorted(str(t) for t in wo.assignee_team_ids)}
    new_users, new_teams = _replace_assignees(wo, resolved["assignee_user_ids"], resolved["assignee_teams"])
    wo.updated_by_user_id = ctx.user.id
    db.session.flush()
    after = {"user_ids": sorted(wo.assignee_user_ids), "team_ids": sorted(str(t) for t in wo.assignee_team_ids)}
    if before != after:
        audit_events.record(ctx, "work_order.assignees_changed", wo, before=before, after=after, summary=f"Changed assignees on #{wo.number}")
    teams_by_id = {t.id: t for t in resolved["assignee_teams"]}
    _notify_assigned(ctx, wo, set(new_users) | _team_member_ids(teams_by_id[t] for t in new_teams))
    db.session.commit()
    return wo


def set_watchers(ctx, wo: WorkOrder, user_ids) -> WorkOrder:
    policy.authorize(ctx, "work_order.assign", wo)
    data = validate({"user_ids": user_ids if user_ids is not None else []}, WATCHERS_SPEC)
    resolved = _resolve_references(ctx, {"watcher_user_ids": data["user_ids"]})
    before = {"user_ids": sorted(wo.watcher_user_ids)}
    _replace_watchers(wo, resolved["watcher_user_ids"])
    wo.updated_by_user_id = ctx.user.id
    db.session.flush()
    after = {"user_ids": sorted(wo.watcher_user_ids)}
    if before != after:
        audit_events.record(ctx, "work_order.watchers_changed", wo, before=before, after=after, summary=f"Changed watchers on #{wo.number}")
    db.session.commit()
    return wo


def watch(ctx, wo: WorkOrder) -> WorkOrder:
    if not can_read_work_order(ctx, wo):
        raise NotFound()
    if ctx.user.id in wo.watcher_user_ids:
        return wo
    before = {"user_ids": sorted(wo.watcher_user_ids)}
    wo.watchers.append(WorkOrderWatcher(user_id=ctx.user.id))
    db.session.flush()
    audit_events.record(
        ctx, "work_order.watchers_changed", wo, before=before, after={"user_ids": sorted(wo.watcher_user_ids)}, summary=f"Started watching #{wo.number}"
    )
    db.session.commit()
    return wo


def unwatch(ctx, wo: WorkOrder) -> WorkOrder:
    if not can_read_work_order(ctx, wo):
        raise NotFound()
    if ctx.user.id not in wo.watcher_user_ids:
        return wo
    before = {"user_ids": sorted(wo.watcher_user_ids)}
    for row in list(wo.watchers):
        if row.user_id == ctx.user.id:
            wo.watchers.remove(row)
    db.session.flush()
    audit_events.record(
        ctx, "work_order.watchers_changed", wo, before=before, after={"user_ids": sorted(wo.watcher_user_ids)}, summary=f"Stopped watching #{wo.number}"
    )
    db.session.commit()
    return wo


# --------------------------------------------------------------------------- time & cost


def add_time_entry(ctx, wo: WorkOrder, data: dict) -> TimeEntry:
    policy.authorize(ctx, "work_order.log_time", wo)
    entry = _validate_time_entry(ctx, wo, data if isinstance(data, dict) else {})
    row = _add_time_entry_row(ctx, wo, entry)
    db.session.commit()
    return row


def delete_time_entry(ctx, wo: WorkOrder, entry_id) -> WorkOrder:
    tid = parse_uuid(entry_id)
    row = db.session.get(TimeEntry, tid) if tid else None
    if row is None or row.work_order_id != wo.id or row.organization_id != ctx.org.id:
        raise NotFound("Time entry not found.")
    if row.user_id != ctx.user.id and row.created_by_user_id != ctx.user.id:
        policy.authorize(ctx, "work_order.assign", wo)
    snapshot = {"time_entry_id": str(row.id), "user_id": row.user_id, "minutes": row.minutes, "note": row.note}
    wo.time_entries.remove(row)
    db.session.flush()
    wo.actual_minutes = sum(int(e.minutes) for e in wo.time_entries)
    wo.updated_by_user_id = ctx.user.id
    audit_events.record(ctx, "work_order.time_removed", wo, before=snapshot, summary=f"Removed {snapshot['minutes']} min from #{wo.number}")
    db.session.commit()
    return wo


def add_cost_entry(ctx, wo: WorkOrder, data: dict) -> CostEntry:
    policy.authorize(ctx, "work_order.log_time", wo)
    entry = _validate_cost_entry(ctx, data if isinstance(data, dict) else {})
    row = _add_cost_entry_row(ctx, wo, entry)
    db.session.commit()
    return row


def delete_cost_entry(ctx, wo: WorkOrder, entry_id) -> WorkOrder:
    cid = parse_uuid(entry_id)
    row = db.session.get(CostEntry, cid) if cid else None
    if row is None or row.work_order_id != wo.id or row.organization_id != ctx.org.id:
        raise NotFound("Cost entry not found.")
    if row.created_by_user_id != ctx.user.id:
        policy.authorize(ctx, "work_order.assign", wo)
    snapshot = {"cost_entry_id": str(row.id), "type": row.type, "amount": row.amount, "description": row.description}
    wo.cost_entries.remove(row)
    db.session.flush()
    wo.updated_by_user_id = ctx.user.id
    audit_events.record(ctx, "work_order.cost_removed", wo, before=snapshot, summary=f"Removed {snapshot['type']} cost from #{wo.number}")
    db.session.commit()
    return wo


# --------------------------------------------------------------------------- dependencies


def recompute_blocked(wo: WorkOrder) -> list[WorkOrder]:
    """Set ``wo.is_blocked`` from its open blockers and return them (no commit)."""
    blockers = [dep.blocking_work_order for dep in wo.blocked_by if dep.blocking_work_order is not None and dep.blocking_work_order.status not in CLOSED_STATUSES]
    wo.is_blocked = bool(blockers)
    return blockers


def _reaches(start: WorkOrder, target_id) -> bool:
    """True when following "blocks" edges from ``start`` reaches ``target_id``."""
    seen = set()
    stack = [start]
    while stack:
        current = stack.pop()
        if current.id in seen:
            continue
        seen.add(current.id)
        for dep in current.blocking:
            if dep.blocked_work_order_id == target_id:
                return True
            if dep.blocked is not None:
                stack.append(dep.blocked)
    return False


def add_dependency(ctx, wo: WorkOrder, blocking_id) -> WorkOrderDependency:
    policy.authorize(ctx, "work_order.edit", wo)
    data = validate({"blocking_work_order_id": blocking_id}, DEPENDENCY_SPEC)
    blocking = db.session.get(WorkOrder, data["blocking_work_order_id"])
    if blocking is None or not can_read_work_order(ctx, blocking):
        raise ValidationErrors({"blocking_work_order_id": "Unknown work order."})
    if blocking.id == wo.id:
        raise ValidationErrors({"blocking_work_order_id": "A work order cannot block itself."})
    if any(dep.blocking_work_order_id == blocking.id for dep in wo.blocked_by):
        raise ValidationErrors({"blocking_work_order_id": f"#{blocking.number} already blocks this work order."})
    if _reaches(wo, blocking.id):
        raise ValidationErrors({"blocking_work_order_id": f"Adding #{blocking.number} would create a dependency cycle."})
    dep = WorkOrderDependency(blocking_work_order=blocking, blocked=wo, dependency_type="finish_to_start")
    db.session.add(dep)
    db.session.flush()
    recompute_blocked(wo)
    wo.updated_by_user_id = ctx.user.id
    audit_events.record(
        ctx,
        "work_order.dependency_added",
        wo,
        after={"dependency_id": str(dep.id), "blocking_work_order_id": str(blocking.id), "blocking_number": blocking.number, "is_blocked": wo.is_blocked},
        summary=f"#{wo.number} is now blocked by #{blocking.number}",
    )
    db.session.commit()
    return dep


def remove_dependency(ctx, wo: WorkOrder, dependency_id) -> WorkOrder:
    policy.authorize(ctx, "work_order.edit", wo)
    did = parse_uuid(dependency_id)
    dep = db.session.get(WorkOrderDependency, did) if did else None
    if dep is None or dep.blocked_work_order_id != wo.id:
        raise NotFound("Dependency not found.")
    blocking = dep.blocking_work_order
    snapshot = {"dependency_id": str(dep.id), "blocking_work_order_id": str(dep.blocking_work_order_id), "blocking_number": blocking.number if blocking else None}
    wo.blocked_by.remove(dep)
    db.session.flush()
    recompute_blocked(wo)
    wo.updated_by_user_id = ctx.user.id
    audit_events.record(ctx, "work_order.dependency_removed", wo, before=snapshot, after={"is_blocked": wo.is_blocked}, summary=f"Removed dependency from #{wo.number}")
    db.session.commit()
    return wo


# --------------------------------------------------------------------------- duplicate


def duplicate(ctx, wo: WorkOrder) -> WorkOrder:
    policy.authorize(ctx, "work_order.create")
    if not can_read_work_order(ctx, wo):
        raise NotFound()
    payload = {
        "title": (wo.title + " (copy)")[:240],
        "description": wo.description,
        "priority": wo.priority,
        "work_type": wo.work_type,
        "project_id": str(wo.project_id) if wo.project_id else None,
        "location_id": str(wo.location_id) if wo.location_id else None,
        "primary_asset_id": str(wo.primary_asset_id) if wo.primary_asset_id else None,
        "team_id": str(wo.team_id) if wo.team_id else None,
        "vendor_id": str(wo.vendor_id) if wo.vendor_id else None,
        "estimated_minutes": wo.estimated_minutes,
        "budget_code": wo.budget_code,
        "parent_completion_policy": wo.parent_completion_policy,
        "category_ids": [str(c) for c in wo.category_ids],
        "asset_ids": [str(link.asset_id) for link in wo.asset_links if link.relationship_type == "related"],
        "assignee_user_ids": sorted(wo.assignee_user_ids),
        "assignee_team_ids": [str(t) for t in sorted(wo.assignee_team_ids, key=str)],
    }
    pending: list = []
    copy = _create_row(ctx, payload, pending=pending, audit_metadata={"duplicated_from": str(wo.id)})
    audit_events.record(
        ctx,
        "work_order.duplicated",
        copy,
        after={"source_work_order_id": str(wo.id), "source_number": wo.number},
        summary=f"Duplicated #{wo.number} as #{copy.number}",
        source_id=str(wo.id),
    )
    db.session.commit()
    _emit_all(pending)
    return copy


# --------------------------------------------------------------------------- listing


def _bad_filter(name: str, message: str | None = None):
    return Validation(message or f"Invalid value for filter '{name}'.", field=name, code="bad_filter")


def _uuids(name: str, values) -> list:
    parsed = [parse_uuid(v) for v in values]
    if any(p is None for p in parsed):
        raise _bad_filter(name)
    return parsed


def _user_ids(ctx, name: str, values) -> list[int]:
    ids: list[int] = []
    for value in values:
        if str(value).strip().lower() == "me":
            ids.append(ctx.user.id)
            continue
        try:
            ids.append(int(value))
        except (TypeError, ValueError):
            raise _bad_filter(name)
    return ids


def _org_tz(ctx):
    try:
        return ZoneInfo(ctx.org.timezone or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        # The profile validator rejects unknown zones on write; an org row
        # imported with a bad zone still needs a usable day boundary.
        return ZoneInfo("UTC")


def _due_criterion(ctx, value: str):
    if value not in DUE_CHOICES:
        raise _bad_filter("due", "Filter 'due' must be one of: " + ", ".join(DUE_CHOICES) + ".")
    now = utcnow()
    if value == "none":
        return WorkOrder.due_at.is_(None)
    if value == "overdue":
        return WorkOrder.due_at.isnot(None) & (WorkOrder.due_at < now) & WorkOrder.status.in_(OPEN_STATUSES)
    local_now = now.astimezone(_org_tz(ctx))
    start_local = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    days = {"today": 1, "week": 7, "month": 30}[value]
    start = start_local.astimezone(now.tzinfo)
    end = (start_local + timedelta(days=days)).astimezone(now.tzinfo)
    return WorkOrder.due_at.isnot(None) & (WorkOrder.due_at >= start) & (WorkOrder.due_at < end)


def _apply_filters(ctx, query, filters: dict, q: str):
    filters = filters or {}
    for name, choices in (("status", WORK_ORDER_STATUSES), ("priority", PRIORITIES), ("work_type", WORK_TYPES)):
        values = filters.get(name)
        if values:
            if any(v not in choices for v in values):
                raise _bad_filter(name, f"Filter '{name}' must be one of: " + ", ".join(choices) + ".")
            query = query.filter(getattr(WorkOrder, name).in_(values))
    if filters.get("project"):
        query = query.filter(WorkOrder.project_id.in_(_uuids("project", filters["project"])))
    if filters.get("location"):
        query = query.filter(WorkOrder.location_id.in_(_uuids("location", filters["location"])))
    if filters.get("vendor"):
        query = query.filter(WorkOrder.vendor_id.in_(_uuids("vendor", filters["vendor"])))
    if filters.get("asset"):
        ids = _uuids("asset", filters["asset"])
        linked = select(WorkOrderAsset.work_order_id).where(WorkOrderAsset.asset_id.in_(ids))
        query = query.filter(or_(WorkOrder.primary_asset_id.in_(ids), WorkOrder.id.in_(linked)))
    if filters.get("team"):
        ids = _uuids("team", filters["team"])
        assigned = select(WorkOrderAssignee.work_order_id).where(WorkOrderAssignee.team_id.in_(ids))
        query = query.filter(or_(WorkOrder.team_id.in_(ids), WorkOrder.id.in_(assigned)))
    if filters.get("assignee"):
        ids = _user_ids(ctx, "assignee", filters["assignee"])
        direct = select(WorkOrderAssignee.work_order_id).where(WorkOrderAssignee.user_id.in_(ids))
        their_teams = select(TeamMember.team_id).where(TeamMember.user_id.in_(ids))
        via_team = select(WorkOrderAssignee.work_order_id).where(WorkOrderAssignee.team_id.in_(their_teams))
        query = query.filter(or_(WorkOrder.id.in_(direct), WorkOrder.id.in_(via_team)))
    if filters.get("category"):
        ids = _uuids("category", filters["category"])
        query = query.filter(WorkOrder.id.in_(select(WorkOrderCategory.work_order_id).where(WorkOrderCategory.category_id.in_(ids))))
    if filters.get("due"):
        query = query.filter(_due_criterion(ctx, filters["due"][0]))
    if filters.get("created_by"):
        query = query.filter(WorkOrder.created_by_user_id.in_(_user_ids(ctx, "created_by", filters["created_by"])))
    if filters.get("parent"):
        value = filters["parent"][0]
        if value.lower() == "none":
            query = query.filter(WorkOrder.parent_work_order_id.is_(None))
        else:
            query = query.filter(WorkOrder.parent_work_order_id == _uuids("parent", [value])[0])
    q = (q or "").strip()
    if q:
        match = NUMBER_RE.match(q)
        if match:
            query = query.filter(WorkOrder.number == int(match.group(1)))
        else:
            like = f"%{q}%"
            query = query.filter(or_(WorkOrder.title.ilike(like), WorkOrder.description.ilike(like)))
    return query


def _order_by(sort: str):
    descending = sort.startswith("-")
    key = sort[1:] if descending else sort
    if key not in LIST_SORTS:
        raise Validation(f"Unknown sort '{sort}'.", field="sort", code="bad_sort")
    if key == "priority":
        rank = case(PRIORITY_RANK, value=WorkOrder.priority, else_=0)
        primary = [rank.desc() if descending else rank.asc()]
    elif key == "due_at":
        primary = [WorkOrder.due_at.is_(None), WorkOrder.due_at.desc() if descending else WorkOrder.due_at.asc()]
    elif key == "title":
        column = func.lower(WorkOrder.title)
        primary = [column.desc() if descending else column.asc()]
    else:
        column = getattr(WorkOrder, key)
        primary = [column.desc() if descending else column.asc()]
    return [*primary, WorkOrder.number.desc(), WorkOrder.id.asc()]


def list_query(ctx, filters: dict, sort: str, q: str, tab: str | None):
    tab = (tab or "todo").strip().lower()
    if tab not in TABS:
        raise Validation("tab must be one of: " + ", ".join(TABS) + ".", field="tab", code="bad_filter")
    query = _apply_filters(ctx, visible_work_orders_query(ctx), filters, q)
    if tab == "todo":
        query = query.filter(WorkOrder.status.in_(OPEN_STATUSES))
    elif tab == "done":
        query = query.filter(WorkOrder.status.in_(CLOSED_STATUSES))
    return query.order_by(*_order_by(sort or DEFAULT_SORT))


def tab_counts(ctx, filters: dict, q: str) -> dict:
    query = _apply_filters(ctx, visible_work_orders_query(ctx), filters, q)
    rows = query.order_by(None).with_entities(WorkOrder.status, func.count(WorkOrder.id)).group_by(WorkOrder.status).all()
    counts = {"todo": 0, "done": 0}
    for status, count in rows:
        if status in OPEN_STATUSES:
            counts["todo"] += int(count)
        elif status in CLOSED_STATUSES:
            counts["done"] += int(count)
    return counts
