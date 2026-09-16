"""Locations service (``ops_locations``).

Locations form a tree per organization. Exactly one location per organization is
the default (bootstrap creates ``General``); it can be swapped with
``make_default`` but never deleted or deactivated while it is the default.
Deleting is a hard delete and is refused while anything still points at the row:
assets, work orders, child locations, inventory balances, ledger rows, work-order
part lines, parts that default to it or purchase-request receive lines.
"""

from __future__ import annotations

from collections import defaultdict
from typing import NamedTuple
from uuid import UUID

from sqlalchemy import func, or_, select

from asme.extensions import db
from asme.ops import policy
from asme.ops.models import (
    Asset,
    InventoryBalance,
    InventoryTransaction,
    Location,
    Part,
    PurchaseRequest,
    PurchaseRequestItem,
    WorkOrder,
    WorkOrderPart,
)
from asme.ops.models.work import OPEN_STATUSES
from asme.ops.services import audit_events
from asme.ops.validation import Field, ValidationErrors, validate
from asme.services.errors import Conflict

AUDIT_FIELDS = ("name", "description", "parent_location_id", "building", "room", "address_json", "is_default", "is_active")
SORTS = ("name", "created_at")
ROOT = "root"
PARENT_NOT_FOUND = "Choose a location in this chapter."
PARENT_CYCLE = "A location cannot be nested inside itself or one of its descendants."


def _check_address(value) -> str | None:
    return None if isinstance(value, dict) else "Must be an object."


SPEC = {
    "name": Field("str", required=True, max_len=160, nullable=False),
    "description": Field("text"),
    "parent_id": Field("uuid"),
    "building": Field("str", max_len=160),
    "room": Field("str", max_len=80),
    "address": Field("json", check=_check_address),
}
UPDATE_SPEC = {**SPEC, "is_active": Field("bool", nullable=False)}
_ATTRIBUTES = (("name", "name"), ("description", "description"), ("building", "building"), ("room", "room"), ("address", "address_json"), ("is_active", "is_active"))


class TreeNode(NamedTuple):
    location: Location
    children: list["TreeNode"]


# --------------------------------------------------------------------------- reads


def base_query(ctx):
    return Location.query.filter(Location.organization_id == ctx.org.id)


def get(ctx, location_id) -> Location:
    return policy.get_or_404(ctx, Location, location_id)


def _like(term: str) -> str:
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _search(query, q: str):
    if not q:
        return query
    pattern = _like(q)
    return query.filter(
        or_(
            Location.name.ilike(pattern, escape="\\"),
            Location.building.ilike(pattern, escape="\\"),
            Location.room.ilike(pattern, escape="\\"),
        )
    )


def _filtered(ctx, *, active: bool | None):
    query = base_query(ctx)
    if active is not None:
        query = query.filter(Location.is_active == active)
    return query


def list_query(ctx, *, q: str = "", parent: UUID | str | None = None, active: bool | None = True, sort: str = "name"):
    """Flat, ordered query. ``parent`` is ``None`` (any), ``ROOT`` or a parent id;
    ``active`` is ``None`` (any) or a bool."""
    query = _filtered(ctx, active=active)
    if parent == ROOT:
        query = query.filter(Location.parent_location_id.is_(None))
    elif parent is not None:
        query = query.filter(Location.parent_location_id == parent)
    query = _search(query, q)
    descending = sort.startswith("-")
    key = sort[1:] if descending else sort
    if key not in SORTS:
        raise ValueError(f"unknown location sort {sort!r}")
    column = func.lower(Location.name) if key == "name" else Location.created_at
    return query.order_by(column.desc() if descending else column.asc(), Location.id.asc())


def tree(ctx, *, q: str = "", active: bool | None = True) -> list[TreeNode]:
    """Roots with nested children, siblings ordered by name. With ``q`` only the
    matching locations and their ancestors are kept; a node whose parent is
    filtered out is returned as a root."""
    query = _filtered(ctx, active=active)
    rows = query.order_by(func.lower(Location.name).asc(), Location.id.asc()).all()
    by_id = {row.id: row for row in rows}
    keep = set(by_id)
    if q:
        keep = set()
        for (matched_id,) in _search(query, q).with_entities(Location.id).all():
            current = matched_id
            while current is not None and current in by_id and current not in keep:
                keep.add(current)
                current = by_id[current].parent_location_id
    children: dict[UUID, list[Location]] = defaultdict(list)
    roots: list[Location] = []
    for row in rows:
        if row.id not in keep:
            continue
        if row.parent_location_id is not None and row.parent_location_id in keep:
            children[row.parent_location_id].append(row)
        else:
            roots.append(row)

    def build(row: Location) -> TreeNode:
        return TreeNode(row, [build(child) for child in children[row.id]])

    return [build(row) for row in roots]


def flatten(nodes: list[TreeNode]) -> list[Location]:
    out: list[Location] = []
    stack = list(nodes)
    while stack:
        node = stack.pop()
        out.append(node.location)
        stack.extend(node.children)
    return out


def _path(location_id, lookup: dict) -> list[str]:
    names: list[str] = []
    seen: set = set()
    current = location_id
    while current is not None and current in lookup and current not in seen:
        seen.add(current)
        name, parent_id = lookup[current]
        names.append(name)
        current = parent_id
    names.reverse()
    return names


def enrich(ctx, rows) -> dict[UUID, dict]:
    """Per-location ``path``, ``asset_count`` and ``open_work_order_count`` for
    ``rows`` (three queries in total)."""
    ids = [row.id for row in rows]
    if not ids:
        return {}
    lookup = {
        row.id: (row.name, row.parent_location_id)
        for row in db.session.execute(select(Location.id, Location.name, Location.parent_location_id).where(Location.organization_id == ctx.org.id))
    }
    asset_counts = dict(
        db.session.execute(
            select(Asset.location_id, func.count(Asset.id))
            .where(Asset.organization_id == ctx.org.id, Asset.location_id.in_(ids))
            .group_by(Asset.location_id)
        ).all()
    )
    work_order_counts = dict(
        db.session.execute(
            select(WorkOrder.location_id, func.count(WorkOrder.id))
            .where(WorkOrder.organization_id == ctx.org.id, WorkOrder.location_id.in_(ids), WorkOrder.status.in_(OPEN_STATUSES))
            .group_by(WorkOrder.location_id)
        ).all()
    )
    return {
        row.id: {
            "path": _path(row.id, lookup),
            "asset_count": int(asset_counts.get(row.id, 0)),
            "open_work_order_count": int(work_order_counts.get(row.id, 0)),
        }
        for row in rows
    }


def usage_of(ctx, location: Location) -> dict[str, int]:
    """Everything that still points at ``location``: assets, work orders (any
    status), child locations and the Stage 4 inventory rows.

    A balance or a ledger row whose location is deleted is orphaned - the stock
    still counts chapter-wide but no screen can reach it, and the ledger is
    append-only so the row can never be corrected. PostgreSQL enforces those
    foreign keys, so counting them here turns a 500 into a 409."""

    def count(model, column):
        return int(db.session.scalar(select(func.count(model.id)).where(model.organization_id == ctx.org.id, column == location.id)) or 0)

    # ``ops_purchase_request_items`` carries no organization_id of its own.
    receive_lines = int(
        db.session.scalar(
            select(func.count(PurchaseRequestItem.id))
            .join(PurchaseRequest, PurchaseRequest.id == PurchaseRequestItem.purchase_request_id)
            .where(PurchaseRequest.organization_id == ctx.org.id, PurchaseRequestItem.receive_location_id == location.id)
        )
        or 0
    )
    return {
        "assets": count(Asset, Asset.location_id),
        "work_orders": count(WorkOrder, WorkOrder.location_id),
        "children": count(Location, Location.parent_location_id),
        "inventory_balances": count(InventoryBalance, InventoryBalance.location_id),
        "inventory_transactions": count(InventoryTransaction, InventoryTransaction.location_id),
        "work_order_parts": count(WorkOrderPart, WorkOrderPart.location_id),
        "parts": count(Part, Part.default_location_id),
        "purchase_request_items": receive_lines,
    }


# --------------------------------------------------------------------------- writes


def _resolve_parent(ctx, parent_id, *, location: Location | None = None) -> Location | None:
    """Load the parent by id, rejecting ids from other organizations and, when
    re-parenting ``location``, any parent that is ``location`` or one of its descendants."""
    if parent_id is None:
        return None
    parent = db.session.get(Location, parent_id)
    if parent is None or parent.organization_id != ctx.org.id:
        raise ValidationErrors({"parent_id": PARENT_NOT_FOUND})
    if location is not None:
        current = parent
        seen: set = set()
        while current is not None and current.id not in seen:
            if current.id == location.id:
                raise ValidationErrors({"parent_id": PARENT_CYCLE})
            seen.add(current.id)
            current = current.parent
    return parent


def create(ctx, payload: dict) -> Location:
    policy.authorize(ctx, "location.manage")
    data = validate(payload, SPEC)
    parent = _resolve_parent(ctx, data.get("parent_id"))
    location = Location(
        organization_id=ctx.org.id,
        name=data["name"],
        description=data.get("description"),
        parent_location_id=parent.id if parent is not None else None,
        building=data.get("building"),
        room=data.get("room"),
        address_json=data.get("address"),
        is_default=False,
        is_active=True,
        created_by_user_id=ctx.user_id,
        updated_by_user_id=ctx.user_id,
    )
    db.session.add(location)
    db.session.flush()
    audit_events.record(
        ctx,
        "location.created",
        location,
        after=audit_events.snapshot(location, AUDIT_FIELDS),
        summary=f"Created location {location.name}",
    )
    db.session.commit()
    return location


def update(ctx, location: Location, payload: dict) -> Location:
    policy.authorize(ctx, "location.manage", location)
    errors: dict[str, str] = {}
    data: dict = {}
    try:
        data = validate(payload, UPDATE_SPEC, partial=True)
    except ValidationErrors as exc:
        errors.update(exc.errors)
    if isinstance(payload, dict) and "is_default" in payload:
        errors["is_default"] = "Use make-default to change the default location."
    if data.get("is_active") is False and location.is_default:
        errors["is_active"] = "The default location cannot be deactivated. Make another location the default first."
    parent = None
    if "parent_id" in data:
        try:
            parent = _resolve_parent(ctx, data["parent_id"], location=location)
        except ValidationErrors as exc:
            errors.update(exc.errors)
    if errors:
        raise ValidationErrors(errors)

    before = audit_events.snapshot(location, AUDIT_FIELDS)
    for key, attribute in _ATTRIBUTES:
        if key in data:
            setattr(location, attribute, data[key])
    if "parent_id" in data:
        location.parent_location_id = parent.id if parent is not None else None
    after = audit_events.snapshot(location, AUDIT_FIELDS)
    if after == before:
        return location
    location.updated_by_user_id = ctx.user_id
    audit_events.record(ctx, "location.updated", location, before=before, after=after, summary=f"Updated location {location.name}")
    db.session.commit()
    return location


def delete(ctx, location: Location) -> None:
    policy.authorize(ctx, "location.manage", location)
    if location.is_default:
        raise Conflict("The default location cannot be deleted. Make another location the default first.", code="default_location_protected")
    usage = usage_of(ctx, location)
    if any(usage.values()):
        raise Conflict(
            "This location is still used by assets, work orders, inventory or child locations.",
            code="location_in_use",
            usage=usage,
        )
    audit_events.record(
        ctx,
        "location.deleted",
        location,
        before=audit_events.snapshot(location, AUDIT_FIELDS),
        summary=f"Deleted location {location.name}",
    )
    db.session.delete(location)
    db.session.commit()


def make_default(ctx, location: Location) -> Location:
    policy.authorize(ctx, "location.manage", location)
    if location.is_default:
        return location
    if not location.is_active:
        raise Conflict("An inactive location cannot be the default. Reactivate it first.", code="location_inactive")
    previous = base_query(ctx).filter(Location.is_default.is_(True)).all()
    for row in previous:
        row.is_default = False
        row.updated_by_user_id = ctx.user_id
    location.is_default = True
    location.updated_by_user_id = ctx.user_id
    audit_events.record(
        ctx,
        "location.default_changed",
        location,
        before={"default_location_id": previous[0].id if previous else None},
        after={"default_location_id": location.id},
        summary=f"{location.name} is now the default location",
    )
    db.session.commit()
    return location
