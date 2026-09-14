"""Scheduled scans: overdue / due-soon work orders and missed milestones.

``run_work_order_scan`` is the body of the hourly ``ops.work_order.scan`` outbox
job. It runs without a user, so for each organization it builds a
``SystemContext`` – the slice of ``PolicyContext`` that ``notifications.notify``
and ``audit_events.record`` rely on (``org``, ``user=None``, ``user_id=None``).
Every notification carries a dedupe key of ``<kind>:<work order id>:<due date>``
so the people involved are told once per due date however often the scan runs.
Each organization is committed on its own.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from asme.extensions import db
from asme.ops.models import Milestone, Organization, WorkOrder
from asme.ops.serializers import iso
from asme.ops.services import audit_events, notifications
from asme.ops.types import as_utc, utcnow

log = logging.getLogger("asme.ops.scans")

SCAN_STATUSES = ("open", "in_progress", "on_hold")  # drafts are not committed work yet
DUE_SOON_WINDOW = timedelta(hours=24)
MILESTONE_FINAL_STATUSES = ("done", "missed")


@dataclass(frozen=True)
class SystemContext:
    """Actor-less context for background jobs."""

    org: Organization
    user: object = None
    user_id: int | None = None

    @property
    def org_id(self):
        return self.org.id


def system_context(org: Organization) -> SystemContext:
    return SystemContext(org=org)


def run_work_order_scan(now: datetime | None = None) -> dict[str, int]:
    """Scan every organization once. Returns how many notifications were created
    for overdue and due-soon work orders, how many milestones were marked
    missed, and how many organizations were scanned."""
    now = as_utc(now) if now is not None else utcnow()
    totals = {"overdue_notified": 0, "due_soon_notified": 0, "milestones_missed": 0, "organizations": 0}
    for org in Organization.query.order_by(Organization.created_at.asc(), Organization.slug.asc()).all():
        ctx = system_context(org)
        totals["overdue_notified"] += _notify_overdue(ctx, now)
        totals["due_soon_notified"] += _notify_due_soon(ctx, now)
        totals["milestones_missed"] += _mark_missed_milestones(ctx, now)
        db.session.commit()
        totals["organizations"] += 1
    log.info("work-order scan at %s: %s", iso(now), totals)
    return totals


# --------------------------------------------------------------------------- work orders


def _open_work_orders(org_id, *criteria) -> list[WorkOrder]:
    return (
        WorkOrder.query.filter(
            WorkOrder.organization_id == org_id,
            WorkOrder.status.in_(SCAN_STATUSES),
            WorkOrder.due_at.isnot(None),
            *criteria,
        )
        .order_by(WorkOrder.due_at.asc(), WorkOrder.number.asc())
        .all()
    )


def _recipients(wo: WorkOrder) -> set[int]:
    """Assignees, members of assigned teams, watchers and the creator."""
    ids: set[int] = set(wo.assignee_user_ids)
    for assignee in wo.assignees:
        if assignee.team is not None:
            ids |= assignee.team.member_user_ids
    ids |= wo.watcher_user_ids
    if wo.created_by_user_id:
        ids.add(wo.created_by_user_id)
    return ids


def _notify_overdue(ctx: SystemContext, now: datetime) -> int:
    created = 0
    for wo in _open_work_orders(ctx.org_id, WorkOrder.due_at < now):
        due_at = as_utc(wo.due_at)
        rows = notifications.notify(
            ctx,
            _recipients(wo),
            "work_order.overdue",
            f"#{wo.number} {wo.title} is overdue",
            f"Due {iso(due_at)}.",
            entity=wo,
            dedupe_key=f"overdue:{wo.id}:{due_at.date()}",
        )
        created += len(rows)
    return created


def _notify_due_soon(ctx: SystemContext, now: datetime) -> int:
    created = 0
    for wo in _open_work_orders(ctx.org_id, WorkOrder.due_at >= now, WorkOrder.due_at <= now + DUE_SOON_WINDOW):
        due_at = as_utc(wo.due_at)
        rows = notifications.notify(
            ctx,
            _recipients(wo),
            "work_order.due_soon",
            f"#{wo.number} {wo.title} is due soon",
            f"Due {iso(due_at)}.",
            entity=wo,
            dedupe_key=f"due_soon:{wo.id}:{due_at.date()}",
        )
        created += len(rows)
    return created


# --------------------------------------------------------------------------- milestones


def _mark_missed_milestones(ctx: SystemContext, now: datetime) -> int:
    today = now.date()
    rows = (
        Milestone.query.filter(
            Milestone.organization_id == ctx.org_id,
            Milestone.due_date.isnot(None),
            Milestone.due_date < today,
            Milestone.status.notin_(MILESTONE_FINAL_STATUSES),
        )
        .order_by(Milestone.due_date.asc(), Milestone.order_index.asc())
        .all()
    )
    for milestone in rows:
        previous = milestone.status
        milestone.status = "missed"
        audit_events.record(
            ctx,
            "milestone.missed",
            milestone,
            before={"status": previous},
            after={"status": "missed"},
            summary=f"{milestone.name} missed its due date ({milestone.due_date.isoformat()})",
            project_id=str(milestone.project_id),
            due_date=milestone.due_date.isoformat(),
        )
    return len(rows)
