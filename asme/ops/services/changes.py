"""Change feed: audit events since a timestamp, limited to what the caller may read.

Polling clients call ``GET /changes?since=`` and advance ``since`` to the
``next_since`` they get back. Visibility is enforced per entity type:

* ``work_order`` – the id must come from ``work_orders.visible_work_orders_query``;
* ``project`` – the project must pass ``policy.visible_project_filter``;
* ``milestone`` – the milestone's project must pass the same filter;
* everything else is chapter-wide.

``ops_audit_events.entity_id`` is a hyphenated string while the entity tables
use ``Uuid`` columns (32-hex on SQLite, native on PostgreSQL), so the check is
done per batch in Python rather than with a dialect-specific cast: events are
read oldest first in keyset batches, each batch's guarded ids are checked with
one query per type, and scanning continues until the page is full, the events
run out, or ``MAX_SCAN_BATCHES`` is reached. In the last case ``has_more`` is
true and ``next_since`` is the last *scanned* timestamp, so a client that can
see very little still moves forward instead of re-reading the same window.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, or_, select

from asme.extensions import db
from asme.ops import policy
from asme.ops.models import AuditEvent, Milestone, OpsProject
from asme.ops.types import parse_uuid, utcnow
from asme.ops.validation import Field, validate

DEFAULT_LIMIT = 100
MAX_LIMIT = 200
SCAN_BATCH = 200
MAX_SCAN_BATCHES = 10
GUARDED_ENTITY_TYPES = ("work_order", "project", "milestone")

FEED_SPEC = {
    "since": Field("datetime", required=True, nullable=False),
    "limit": Field("int", minimum=1, default=DEFAULT_LIMIT, nullable=False),
}


def list_changes(ctx, params: dict) -> dict:
    """Return ``{"events": [AuditEvent], "has_more": bool, "now": datetime, "next_since": datetime}``.

    ``params`` are the raw query parameters (``since`` required ISO-8601,
    ``limit`` optional, capped at ``MAX_LIMIT``). Events are ordered by
    ``occurred_at`` ascending and are strictly after ``since``. ``next_since``
    is what the client should poll from next: ``now`` once the feed is
    exhausted, otherwise the timestamp of the last delivered (or scanned) event.
    """
    data = validate(params, FEED_SPEC)
    since: datetime = data["since"]
    limit = min(int(data["limit"]), MAX_LIMIT)
    now = utcnow()

    batch_size = max(SCAN_BATCH, limit + 1)
    collected: list[AuditEvent] = []
    last_scanned: AuditEvent | None = None
    exhausted = False
    for _ in range(MAX_SCAN_BATCHES):
        rows = _batch(ctx, since, last_scanned, batch_size)
        if not rows:
            exhausted = True
            break
        collected.extend(_visible(ctx, rows))
        last_scanned = rows[-1]
        if len(rows) < batch_size:
            exhausted = True
            break
        if len(collected) > limit:
            break

    if len(collected) > limit:
        events = collected[:limit]
        return {"events": events, "has_more": True, "now": now, "next_since": events[-1].occurred_at}
    if exhausted or last_scanned is None:
        return {"events": collected, "has_more": False, "now": now, "next_since": now}
    return {"events": collected, "has_more": True, "now": now, "next_since": last_scanned.occurred_at}


# --------------------------------------------------------------------------- internals


def _batch(ctx, since: datetime, after: AuditEvent | None, size: int) -> list[AuditEvent]:
    stmt = select(AuditEvent).where(AuditEvent.organization_id == ctx.org.id, AuditEvent.occurred_at > since)
    if after is not None:
        stmt = stmt.where(
            or_(
                AuditEvent.occurred_at > after.occurred_at,
                and_(AuditEvent.occurred_at == after.occurred_at, AuditEvent.id > after.id),
            )
        )
    stmt = stmt.order_by(AuditEvent.occurred_at.asc(), AuditEvent.id.asc()).limit(size)
    return list(db.session.scalars(stmt))


def _visible(ctx, rows: list[AuditEvent]) -> list[AuditEvent]:
    wanted: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        if row.entity_type in GUARDED_ENTITY_TYPES:
            wanted[row.entity_type].add(row.entity_id)
    readable: dict[str, set[str]] = {}
    if wanted.get("work_order"):
        readable["work_order"] = _readable_work_order_ids(ctx, wanted["work_order"])
    if wanted.get("project"):
        readable["project"] = _readable_project_ids(ctx, wanted["project"])
    if wanted.get("milestone"):
        readable["milestone"] = _readable_milestone_ids(ctx, wanted["milestone"])
    return [
        row
        for row in rows
        if row.entity_type not in GUARDED_ENTITY_TYPES or row.entity_id in readable.get(row.entity_type, ())
    ]


def _uuids(raw_ids) -> list[UUID]:
    parsed = (parse_uuid(value) for value in raw_ids)
    return [value for value in parsed if value is not None]


def _readable_work_order_ids(ctx, raw_ids) -> set[str]:
    from asme.ops.models import WorkOrder
    from asme.ops.services.work_orders import visible_work_orders_query

    ids = _uuids(raw_ids)
    if not ids:
        return set()
    query = visible_work_orders_query(ctx).filter(WorkOrder.id.in_(ids)).with_entities(WorkOrder.id)
    return {str(row[0]) for row in query.all()}


def _readable_project_ids(ctx, raw_ids) -> set[str]:
    ids = _uuids(raw_ids)
    if not ids:
        return set()
    stmt = select(OpsProject.id).where(
        OpsProject.organization_id == ctx.org.id,
        OpsProject.id.in_(ids),
        policy.visible_project_filter(ctx, OpsProject.id, include_null=False),
    )
    return {str(value) for value in db.session.scalars(stmt)}


def _readable_milestone_ids(ctx, raw_ids) -> set[str]:
    ids = _uuids(raw_ids)
    if not ids:
        return set()
    stmt = (
        select(Milestone.id)
        .join(OpsProject, OpsProject.id == Milestone.project_id)
        .where(
            Milestone.organization_id == ctx.org.id,
            Milestone.id.in_(ids),
            OpsProject.organization_id == ctx.org.id,
            policy.visible_project_filter(ctx, Milestone.project_id, include_null=False),
        )
    )
    return {str(value) for value in db.session.scalars(stmt)}
