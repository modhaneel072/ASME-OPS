"""Change feed: audit events since a timestamp, limited to what the caller may read.

Polling clients call ``GET /changes?since=`` and advance ``since`` to the
``next_since`` they get back.

Visibility is **deny by default**: an entity type with no rule below is not
delivered, so a new audited entity cannot leak simply by existing.

* ``work_order`` – the id must come from ``work_orders.visible_work_orders_query``;
* ``project`` – the project must pass ``policy.visible_project_filter``;
* ``milestone`` – the milestone's project must pass the same filter;
* ``asset`` – the asset must be readable (private-project assets are hidden);
* ``comment`` / ``attachment`` – resolved through the entity they hang off;
* ``saved_filter`` – the caller's own, or one shared with them;
* ``part`` / ``part_type`` – any member holding ``inventory.read`` (inventory
  transactions are not audited at all: the ledger is its own history);
* ``purchase_request`` – the plan's read rule, reached through
  ``entities.visible_purchase_requests_query``;
* ``membership`` – only with ``user.manage``/``audit.read``, plus the caller's own;
* chapter-wide reference data (locations, categories, asset types, vendors,
  teams, the chapter itself) – any member holding the matching read permission.

The feed is a poll trigger, not an audit viewer: ``before``/``after``/
``metadata`` are only serialized for callers holding ``audit.read``
(``asme.ops.serializers.notifications.change_event``).

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
# Reference data the whole chapter works from: knowing it changed is safe for
# anyone holding the matching read permission (``None`` = every member).
CHAPTER_WIDE_ENTITY_TYPES: dict[str, str | None] = {
    "organization": None,
    "location": "location.read",
    "category": "category.read",
    "asset_type": "asset.read",
    "vendor": "vendor.read",
    "team": "team.read",
}

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
        wanted[row.entity_type].add(row.entity_id)
    readable = {entity_type: _readable_ids(ctx, entity_type, ids) for entity_type, ids in wanted.items()}
    return [row for row in rows if row.entity_id in readable.get(row.entity_type, ())]


def _readable_ids(ctx, entity_type: str, ids: set[str]) -> set[str]:
    """Which of ``ids`` of ``entity_type`` this caller may know about.

    Anything without an explicit rule returns nothing: a type nobody has
    reasoned about must not reach the feed.
    """
    if entity_type in CHAPTER_WIDE_ENTITY_TYPES:
        permission = CHAPTER_WIDE_ENTITY_TYPES[entity_type]
        return set(ids) if permission is None or ctx.has(permission) else set()
    resolver = _RESOLVERS.get(entity_type)
    return resolver(ctx, ids) if resolver else set()


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


def _readable_asset_ids(ctx, raw_ids) -> set[str]:
    """Assets are hidden when they belong to a project the caller cannot read."""
    from asme.ops.models import Asset
    from asme.ops.services.assets import visible_assets_query

    ids = _uuids(raw_ids)
    if not ids or not ctx.has("asset.read"):
        return set()
    query = visible_assets_query(ctx).filter(Asset.id.in_(ids)).with_entities(Asset.id)
    return {str(row[0]) for row in query.all()}


def _readable_inventory_ids(model):
    """Parts and part types are chapter reference data behind ``inventory.read``."""

    def resolve(ctx, raw_ids) -> set[str]:
        ids = _uuids(raw_ids)
        if not ids or not ctx.has("inventory.read"):
            return set()
        stmt = select(model.id).where(model.organization_id == ctx.org.id, model.id.in_(ids))
        return {str(value) for value in db.session.scalars(stmt)}

    return resolve


def _readable_purchase_request_ids(ctx, raw_ids) -> set[str]:
    """The plan's purchase-request read rule, reached through ``entities``."""
    from asme.ops.models import PurchaseRequest
    from asme.ops.services.entities import visible_purchase_requests_query

    ids = _uuids(raw_ids)
    if not ids:
        return set()
    query = visible_purchase_requests_query(ctx).filter(PurchaseRequest.id.in_(ids)).with_entities(PurchaseRequest.id)
    return {str(row[0]) for row in query.all()}


def _readable_saved_filter_ids(ctx, raw_ids) -> set[str]:
    """Own filters, plus ones shared with the whole chapter or with a team the
    caller belongs to."""
    from asme.ops.models import SavedFilter

    ids = _uuids(raw_ids)
    if not ids:
        return set()
    shared = [SavedFilter.visibility == "chapter"]
    if ctx.team_ids:
        shared.append(and_(SavedFilter.visibility == "team", SavedFilter.team_id.in_(list(ctx.team_ids))))
    stmt = select(SavedFilter.id).where(
        SavedFilter.organization_id == ctx.org.id,
        SavedFilter.id.in_(ids),
        or_(SavedFilter.owner_user_id == ctx.user.id, *shared),
    )
    return {str(value) for value in db.session.scalars(stmt)}


def _readable_membership_ids(ctx, raw_ids) -> set[str]:
    """Who joined, changed role or was suspended is directory administration;
    without ``user.manage``/``audit.read`` a member only sees their own."""
    from asme.ops.models import Membership

    ids = _uuids(raw_ids)
    if not ids:
        return set()
    if ctx.has("user.manage") or ctx.has("audit.read"):
        stmt = select(Membership.id).where(Membership.organization_id == ctx.org.id, Membership.id.in_(ids))
    else:
        stmt = select(Membership.id).where(
            Membership.organization_id == ctx.org.id, Membership.id.in_(ids), Membership.user_id == ctx.user.id
        )
    return {str(value) for value in db.session.scalars(stmt)}


def _readable_child_ids(model):
    """Comments and attachments inherit the visibility of what they hang off."""

    def resolve(ctx, raw_ids) -> set[str]:
        ids = _uuids(raw_ids)
        if not ids:
            return set()
        rows = db.session.scalars(select(model).where(model.organization_id == ctx.org.id, model.id.in_(ids))).all()
        by_parent_type: dict[str, set[str]] = defaultdict(set)
        for row in rows:
            by_parent_type[row.entity_type].add(str(row.entity_id))
        readable_parents = {
            parent_type: _readable_ids(ctx, parent_type, parent_ids) for parent_type, parent_ids in by_parent_type.items()
        }
        return {str(row.id) for row in rows if str(row.entity_id) in readable_parents.get(row.entity_type, ())}

    return resolve


def _build_resolvers() -> dict:
    from asme.ops.models import Attachment, Comment, Part, PartType

    return {
        "work_order": _readable_work_order_ids,
        "project": _readable_project_ids,
        "milestone": _readable_milestone_ids,
        "asset": _readable_asset_ids,
        "part": _readable_inventory_ids(Part),
        "part_type": _readable_inventory_ids(PartType),
        "purchase_request": _readable_purchase_request_ids,
        "saved_filter": _readable_saved_filter_ids,
        "membership": _readable_membership_ids,
        "comment": _readable_child_ids(Comment),
        "attachment": _readable_child_ids(Attachment),
    }


class _Resolvers(dict):
    """Built on first use so importing this module stays cycle-free."""

    def get(self, key, default=None):
        if not self:
            self.update(_build_resolvers())
        return super().get(key, default)


_RESOLVERS = _Resolvers()
