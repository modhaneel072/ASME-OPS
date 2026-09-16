"""Parts catalogue service (``ops_parts``, ``ops_part_types``,
``ops_part_vendors``, ``ops_part_assets``).

This module owns what a part *is*; every quantity lives in the ledger
(``asme.ops.services.inventory_ledger``) and is only ever read from here.
Stock filtering and the ``available`` sort are expressed in SQL so a page of
parts costs a fixed number of queries no matter how many rows it holds, and the
SQL mirrors ``inventory_ledger.stock_state`` exactly - there is one definition
of "low stock" in ASME Ops and this is not a second one.

Parts are never deleted: ``update(ctx, part, {"is_active": false})`` retires one
while the ledger that points at it stays readable.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, func, not_, or_, select

from asme.extensions import db
from asme.ops import policy
from asme.ops.models import (
    Asset,
    InventoryBalance,
    InventoryTransaction,
    Location,
    Part,
    PartAsset,
    PartType,
    PartVendor,
    PurchaseRequest,
    PurchaseRequestItem,
    Vendor,
)
from asme.ops.models.inventory import (
    PART_TYPE_DEFAULT_COLOR,
    PART_TYPE_DEFAULT_ICON,
    PART_UNITS,
    PURCHASE_REQUEST_ORDERED_STATUSES,
    STOCK_STATES,
)
from asme.ops.serializers.parts import PART_SNAPSHOT_FIELDS, PART_TYPE_SNAPSHOT_FIELDS
from asme.ops.services import audit_events, inventory_ledger as ledger
from asme.ops.types import parse_uuid
from asme.ops.validation import Field, ValidationErrors, validate
from asme.services.errors import NotFound, Validation

READ = "inventory.read"
MANAGE = "inventory.manage"

SORTS = ("name", "sku", "available", "updated_at")
DEFAULT_SORT = "name"
FILTERS = {
    "type": "multi",
    "location": "multi",
    "vendor": "multi",
    "asset": "multi",
    "stock": "multi",
    "critical": "single",
    "active": "single",
}

MAX_VENDOR_LINKS = 50
MAX_ASSET_LINKS = 100
RECENT_TRANSACTION_LIMIT = 10
UNIT_COST_LOCKED = "The unit cost is maintained by receipts once a part has inventory history."


def _unit_check(value) -> str | None:
    # PART_UNITS is case sensitive ("L", "mL"), so this cannot be Field("choice"),
    # which lower-cases the value before comparing it.
    return None if value in PART_UNITS else "Choose one of: " + ", ".join(PART_UNITS) + "."


def _quantity_field(**extra) -> Field:
    return Field("decimal", minimum=0, maximum=ledger.QUANTITY_MAX, check=ledger.quantity_check, **extra)


def _unit_cost_field(**extra) -> Field:
    return Field("decimal", minimum=0, maximum=ledger.UNIT_COST_MAX, check=ledger.unit_cost_check, **extra)


PART_SPEC = {
    "name": Field("str", required=True, nullable=False, max_len=200, min_len=1),
    "sku": Field("str", max_len=60),
    "description": Field("text"),
    "part_type_id": Field("uuid"),
    "manufacturer": Field("str", max_len=160),
    "manufacturer_part_number": Field("str", max_len=160),
    "unit": Field("str", nullable=False, max_len=20, default="each", check=_unit_check),
    "unit_cost": _unit_cost_field(),
    "is_critical": Field("bool", nullable=False, default=False),
    "minimum_stock": _quantity_field(),
    "maximum_stock": _quantity_field(),
    "reorder_quantity": _quantity_field(),
    "default_location_id": Field("uuid"),
    "qr_code": Field("str", max_len=160),
    "is_active": Field("bool", nullable=False, default=True),
}

PART_TYPE_SPEC = {
    "name": Field("str", required=True, nullable=False, max_len=120, min_len=1),
    "color": Field("color", nullable=False, default=PART_TYPE_DEFAULT_COLOR),
    "icon": Field("str", nullable=False, max_len=60, default=PART_TYPE_DEFAULT_ICON),
}

VENDOR_LINK_SPEC = {
    "vendor_id": Field("uuid", required=True, nullable=False),
    "vendor_part_number": Field("str", max_len=160),
    "url": Field("url", max_len=500),
    "preferred": Field("bool", nullable=False, default=False),
    "last_price": _unit_cost_field(),
}

ASSET_LINKS_SPEC = {"asset_ids": Field("list", item=Field("uuid"), max_len=MAX_ASSET_LINKS, default=list)}

ASSIGNABLE = tuple(name for name in PART_SPEC if name != "name")


# --------------------------------------------------------------------------- SQL stock expressions


def _balance_sum(expression):
    return (
        select(func.coalesce(func.sum(expression), 0))
        .where(InventoryBalance.part_id == Part.id)
        .correlate(Part)
        .scalar_subquery()
    )


ON_HAND_EXPR = _balance_sum(InventoryBalance.on_hand)
AVAILABLE_EXPR = _balance_sum(InventoryBalance.on_hand - InventoryBalance.reserved)
HAS_TRANSACTIONS_EXPR = select(InventoryTransaction.id).where(InventoryTransaction.part_id == Part.id).correlate(Part).exists()
UNTRACKED_EXPR = and_(Part.minimum_stock.is_(None), ON_HAND_EXPR == 0, not_(HAS_TRANSACTIONS_EXPR))


def stock_criterion(state: str):
    """SQL mirror of ``inventory_ledger.stock_state`` for one state."""
    tracked = not_(UNTRACKED_EXPR)
    if state == "untracked":
        return UNTRACKED_EXPR
    if state == "out":
        return and_(tracked, AVAILABLE_EXPR <= 0)
    if state == "low":
        return and_(tracked, AVAILABLE_EXPR > 0, Part.minimum_stock.isnot(None), AVAILABLE_EXPR < Part.minimum_stock)
    if state == "ok":
        return and_(tracked, AVAILABLE_EXPR > 0, or_(Part.minimum_stock.is_(None), AVAILABLE_EXPR >= Part.minimum_stock))
    raise Validation("filter[stock] accepts: " + ", ".join(STOCK_STATES) + ".", field="stock", code="bad_filter")


# --------------------------------------------------------------------------- filter helpers


def uuid_values(values: list[str], name: str) -> list[UUID]:
    parsed = []
    for raw in values:
        value = parse_uuid(raw)
        if value is None:
            raise Validation(f"filter[{name}] must contain identifiers.", field=name, code="bad_filter")
        parsed.append(value)
    return parsed


def _parse_bool(values: list[str] | None, name: str, *, default: bool | None) -> bool | None:
    if not values:
        return default
    raw = values[0].strip().lower()
    if raw in {"true", "1", "yes"}:
        return True
    if raw in {"false", "0", "no"}:
        return False
    if raw == "all":
        return None
    raise Validation(f"filter[{name}] must be true, false or all.", field=name, code="bad_filter")


def _stock_values(values: list[str]) -> list[str]:
    cleaned = [value.strip().lower() for value in values]
    bad = [value for value in cleaned if value not in STOCK_STATES]
    if bad:
        raise Validation("filter[stock] accepts: " + ", ".join(STOCK_STATES) + ".", field="stock", code="bad_filter")
    return cleaned


# --------------------------------------------------------------------------- reads


def get(ctx, part_id) -> Part:
    policy.authorize(ctx, READ)
    parsed = parse_uuid(part_id)
    if parsed is None:
        raise NotFound()
    return policy.get_or_404(ctx, Part, parsed)


def by_code(ctx, code: str) -> Part:
    """Exact (case-insensitive) SKU or QR code lookup for the scanner."""
    policy.authorize(ctx, READ)
    needle = (code or "").strip().lower()
    if not needle:
        raise NotFound()
    row = (
        Part.query.filter(
            Part.organization_id == ctx.org.id,
            or_(func.lower(Part.sku) == needle, func.lower(Part.qr_code) == needle),
        )
        .order_by(Part.is_active.desc(), func.lower(Part.name).asc(), Part.id.asc())
        .first()
    )
    if row is None:
        raise NotFound("No part with that code.")
    return row


def _base_query(ctx, *, q: str, filters: dict[str, list[str]], with_stock: bool):
    query = Part.query.filter(Part.organization_id == ctx.org.id)
    if q:
        needle = f"%{q.lower()}%"
        columns = (Part.name, Part.sku, Part.manufacturer_part_number, Part.qr_code)
        query = query.filter(or_(*(func.lower(func.coalesce(column, "")).like(needle) for column in columns)))
    if filters.get("type"):
        query = query.filter(Part.part_type_id.in_(uuid_values(filters["type"], "type")))
    if filters.get("location"):
        location_ids = uuid_values(filters["location"], "location")
        query = query.filter(Part.id.in_(select(InventoryBalance.part_id).where(InventoryBalance.location_id.in_(location_ids))))
    if filters.get("vendor"):
        vendor_ids = uuid_values(filters["vendor"], "vendor")
        query = query.filter(Part.id.in_(select(PartVendor.part_id).where(PartVendor.vendor_id.in_(vendor_ids))))
    if filters.get("asset"):
        asset_ids = uuid_values(filters["asset"], "asset")
        query = query.filter(Part.id.in_(select(PartAsset.part_id).where(PartAsset.asset_id.in_(asset_ids))))
    critical = _parse_bool(filters.get("critical"), "critical", default=None)
    if critical is not None:
        query = query.filter(Part.is_critical.is_(critical))
    active = _parse_bool(filters.get("active"), "active", default=True)
    if active is not None:
        query = query.filter(Part.is_active.is_(active))
    if with_stock and filters.get("stock"):
        states = _stock_values(filters["stock"])
        query = query.filter(or_(*(stock_criterion(state) for state in states)))
    return query


def list_query(ctx, *, q: str = "", filters: dict[str, list[str]] | None = None, sort: str = DEFAULT_SORT):
    """Filtered, ordered query of the organization's parts. The route paginates."""
    policy.authorize(ctx, READ)
    filters = filters or {}
    query = _base_query(ctx, q=q, filters=filters, with_stock=True)
    descending = sort.startswith("-")
    key = sort[1:] if descending else sort
    if key not in SORTS:
        raise Validation(f"Unknown sort '{sort}'.", field="sort", code="bad_sort")
    column = {
        "name": func.lower(Part.name),
        "sku": func.lower(func.coalesce(Part.sku, "")),
        "available": AVAILABLE_EXPR,
        "updated_at": Part.updated_at,
    }[key]
    primary = column.desc() if descending else column.asc()
    return query.order_by(primary, func.lower(Part.name).asc(), Part.id.asc())


def stock_counts(ctx, *, q: str = "", filters: dict[str, list[str]] | None = None) -> dict[str, int]:
    """``{"low": n, "out": n}`` over the same filters minus ``filter[stock]``, so
    the Low stock / Out of stock tabs can show a count while another tab is open."""
    policy.authorize(ctx, READ)
    filters = filters or {}
    base = _base_query(ctx, q=q, filters=filters, with_stock=False)
    return {state: int(base.filter(stock_criterion(state)).count()) for state in ("low", "out")}


def enrich(parts: list[Part]) -> tuple[dict, dict]:
    """``(totals_by_part_id, stock_state_by_part_id)`` for a page of parts using
    the ledger's grouped queries - never one query per row."""
    ids = [row.id for row in parts]
    totals = ledger.part_totals(ids)
    states = {row.id: ledger.stock_state(totals.get(row.id, {}), row) for row in parts}
    return totals, states


def balances(ctx, part: Part) -> list[InventoryBalance]:
    """Every ``(part, location)`` balance row, ordered by location name."""
    policy.authorize(ctx, READ, part)
    return (
        InventoryBalance.query.join(Location, Location.id == InventoryBalance.location_id)
        .filter(InventoryBalance.part_id == part.id, InventoryBalance.organization_id == ctx.org.id)
        .order_by(func.lower(Location.name).asc(), InventoryBalance.id.asc())
        .all()
    )


def open_purchase_requests(ctx, part: Part) -> list[tuple[PurchaseRequest, Decimal]]:
    """``[(purchase_request, outstanding_quantity)]`` for requests that have this
    part on order but not yet fully received.

    The part screen is gated on ``inventory.read``, which is a wider audience
    than the purchase-request read rule, so only the requests this caller may
    read are named here."""
    from asme.ops.services.entities import visible_purchase_requests_query

    outstanding = func.sum(PurchaseRequestItem.quantity - PurchaseRequestItem.received_quantity)
    readable = visible_purchase_requests_query(ctx).with_entities(PurchaseRequest.id).subquery()
    rows = db.session.execute(
        select(PurchaseRequest, outstanding)
        .join(PurchaseRequestItem, PurchaseRequestItem.purchase_request_id == PurchaseRequest.id)
        .where(
            PurchaseRequest.organization_id == ctx.org.id,
            PurchaseRequest.id.in_(select(readable.c.id)),
            PurchaseRequestItem.part_id == part.id,
            PurchaseRequest.status.in_(PURCHASE_REQUEST_ORDERED_STATUSES),
            PurchaseRequestItem.quantity > PurchaseRequestItem.received_quantity,
        )
        .group_by(PurchaseRequest.id)
        .order_by(PurchaseRequest.number.desc())
    ).all()
    return [(request, ledger.to_quantity(quantity or 0)) for request, quantity in rows]


def has_transactions(part: Part) -> bool:
    return bool(
        db.session.scalar(select(func.count(InventoryTransaction.id)).where(InventoryTransaction.part_id == part.id))
    )


# --------------------------------------------------------------------------- writes


def _taken(ctx, column, value: str, *, exclude_id=None) -> bool:
    query = Part.query.filter(Part.organization_id == ctx.org.id, func.lower(column) == value.lower())
    if exclude_id is not None:
        query = query.filter(Part.id != exclude_id)
    return bool(db.session.query(query.exists()).scalar())


def _check_references(ctx, data: dict, *, part: Part | None = None) -> None:
    errors: dict[str, str] = {}
    if data.get("sku") is not None and _taken(ctx, Part.sku, data["sku"], exclude_id=part.id if part else None):
        errors["sku"] = "This SKU is already used by another part."
    if data.get("qr_code") is not None and _taken(ctx, Part.qr_code, data["qr_code"], exclude_id=part.id if part else None):
        errors["qr_code"] = "This code is already used by another part."
    if data.get("part_type_id") is not None:
        row = db.session.get(PartType, data["part_type_id"])
        if row is None or row.organization_id != ctx.org.id:
            errors["part_type_id"] = "Unknown part type."
    if data.get("default_location_id") is not None:
        row = db.session.get(Location, data["default_location_id"])
        if row is None or row.organization_id != ctx.org.id:
            errors["default_location_id"] = "Unknown location."
    minimum = data["minimum_stock"] if "minimum_stock" in data else getattr(part, "minimum_stock", None)
    maximum = data["maximum_stock"] if "maximum_stock" in data else getattr(part, "maximum_stock", None)
    if minimum is not None and maximum is not None and Decimal(str(maximum)) < Decimal(str(minimum)):
        errors["maximum_stock"] = "Maximum stock must be at least the minimum stock."
    if errors:
        raise ValidationErrors(errors)


def _assign(part: Part, data: dict) -> None:
    if "name" in data:
        part.name = data["name"]
    for key in ASSIGNABLE:
        if key in data:
            setattr(part, key, data[key])


def create(ctx, payload: dict) -> Part:
    policy.authorize(ctx, MANAGE)
    data = validate(payload, PART_SPEC)
    _check_references(ctx, data)
    part = Part(organization_id=ctx.org.id, created_by_user_id=ctx.user.id, updated_by_user_id=ctx.user.id)
    _assign(part, data)
    db.session.add(part)
    db.session.flush()
    audit_events.record(
        ctx,
        "part.created",
        part,
        after=audit_events.snapshot(part, PART_SNAPSHOT_FIELDS),
        summary=f"Created part {part.name}",
    )
    db.session.commit()
    return part


def update(ctx, part: Part, payload: dict) -> Part:
    policy.authorize(ctx, MANAGE, part)
    data = validate(payload, PART_SPEC, partial=True)
    if "unit_cost" in data and has_transactions(part):
        raise ValidationErrors({"unit_cost": UNIT_COST_LOCKED})
    _check_references(ctx, data, part=part)
    before = audit_events.snapshot(part, PART_SNAPSHOT_FIELDS)
    _assign(part, data)
    part.updated_by_user_id = ctx.user.id
    db.session.flush()
    after = audit_events.snapshot(part, PART_SNAPSHOT_FIELDS)
    changed = sorted(key for key in after if after[key] != before[key])
    audit_events.record(
        ctx,
        "part.updated",
        part,
        before=before,
        after=after,
        summary=f"Updated part {part.name}",
        changed_fields=changed,
    )
    db.session.commit()
    return part


# --------------------------------------------------------------------------- part types


def list_types(ctx) -> list[tuple[PartType, int]]:
    """``[(part_type, active_part_count)]`` ordered by name."""
    policy.authorize(ctx, READ)
    rows = db.session.execute(
        select(Part.part_type_id, func.count(Part.id))
        .where(Part.organization_id == ctx.org.id, Part.is_active.is_(True), Part.part_type_id.isnot(None))
        .group_by(Part.part_type_id)
    ).all()
    counts = {type_id: int(count) for type_id, count in rows}
    types = PartType.query.filter_by(organization_id=ctx.org.id).order_by(func.lower(PartType.name).asc(), PartType.id.asc()).all()
    return [(row, counts.get(row.id, 0)) for row in types]


def create_type(ctx, payload: dict) -> PartType:
    policy.authorize(ctx, MANAGE)
    data = validate(payload, PART_TYPE_SPEC)
    exists = db.session.query(
        PartType.query.filter(PartType.organization_id == ctx.org.id, func.lower(PartType.name) == data["name"].lower()).exists()
    ).scalar()
    if exists:
        raise ValidationErrors({"name": "A part type with this name already exists."})
    row = PartType(
        organization_id=ctx.org.id,
        name=data["name"],
        color=data["color"],
        icon=data["icon"],
        created_by_user_id=ctx.user.id,
        updated_by_user_id=ctx.user.id,
    )
    db.session.add(row)
    db.session.flush()
    audit_events.record(
        ctx,
        "part_type.created",
        row,
        after=audit_events.snapshot(row, PART_TYPE_SNAPSHOT_FIELDS),
        summary=f"Created part type {row.name}",
    )
    db.session.commit()
    return row


# --------------------------------------------------------------------------- vendor links


def _vendor_snapshot(part: Part) -> list[dict]:
    return [
        {
            "vendor_id": str(link.vendor_id),
            "vendor_part_number": link.vendor_part_number,
            "url": link.url,
            "preferred": bool(link.preferred),
            "last_price": audit_events.jsonable(link.last_price),
        }
        for link in sorted(part.vendor_links, key=lambda link: str(link.vendor_id))
    ]


def set_vendors(ctx, part: Part, payload: dict) -> Part:
    """Replace the part's vendor list. ``last_ordered_at`` (written by ordering a
    purchase request) survives a replacement; ``last_price`` survives unless the
    payload names it."""
    policy.authorize(ctx, MANAGE, part)
    raw = (payload or {}).get("vendors", [])
    if raw is None:
        raw = []
    if not isinstance(raw, list):
        raise ValidationErrors({"vendors": "Must be a list."})
    if len(raw) > MAX_VENDOR_LINKS:
        raise ValidationErrors({"vendors": f"At most {MAX_VENDOR_LINKS} vendors."})

    errors: dict[str, str] = {}
    cleaned: list[tuple[Vendor, dict]] = []
    seen: set[UUID] = set()
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            errors[f"vendors[{index}]"] = "Must be an object."
            continue
        try:
            data = validate(entry, VENDOR_LINK_SPEC)
        except ValidationErrors as exc:
            errors.update({f"vendors[{index}].{field}": message for field, message in exc.errors.items()})
            continue
        vendor = db.session.get(Vendor, data["vendor_id"])
        if vendor is None or vendor.organization_id != ctx.org.id:
            errors[f"vendors[{index}].vendor_id"] = "Unknown vendor."
            continue
        if vendor.id in seen:
            errors[f"vendors[{index}].vendor_id"] = "This vendor is already listed."
            continue
        seen.add(vendor.id)
        cleaned.append((vendor, data))
    preferred_positions = [index for index, (_, data) in enumerate(cleaned) if data.get("preferred")]
    for index in preferred_positions[1:]:
        errors[f"vendors[{index}].preferred"] = "Only one vendor can be preferred."
    if errors:
        raise ValidationErrors(errors)

    before = _vendor_snapshot(part)
    existing = {link.vendor_id: link for link in part.vendor_links}
    kept: list[PartVendor] = []
    for vendor, data in cleaned:
        link = existing.get(vendor.id)
        if link is None:
            link = PartVendor(vendor_id=vendor.id)
        link.vendor_part_number = data.get("vendor_part_number")
        link.url = data.get("url")
        link.preferred = bool(data.get("preferred"))
        if "last_price" in data:
            link.last_price = data["last_price"]
        kept.append(link)
    # delete-orphan on Part.vendor_links removes the links that are gone
    part.vendor_links = kept
    db.session.flush()
    part.updated_by_user_id = ctx.user.id
    after = _vendor_snapshot(part)
    audit_events.record(
        ctx,
        "part.vendors_changed",
        part,
        before={"vendors": before},
        after={"vendors": after},
        summary=f"Updated vendors for {part.name}",
    )
    db.session.commit()
    return part


# --------------------------------------------------------------------------- asset links


def set_assets(ctx, part: Part, payload: dict) -> Part:
    """Replace the "spare part for" asset list. Assets the caller cannot read are
    rejected rather than silently dropped."""
    from asme.ops.services import assets as assets_service

    policy.authorize(ctx, MANAGE, part)
    data = validate(payload or {}, ASSET_LINKS_SPEC)
    wanted: list[UUID] = []
    for asset_id in data.get("asset_ids") or []:
        if asset_id not in wanted:
            wanted.append(asset_id)
    if wanted:
        rows = {row.id: row for row in Asset.query.filter(Asset.id.in_(wanted)).all()}
        for asset_id in wanted:
            asset = rows.get(asset_id)
            if asset is None or not assets_service.can_read_asset(ctx, asset):
                raise ValidationErrors({"asset_ids": "Unknown asset."})

    before = sorted(str(link.asset_id) for link in part.asset_links)
    existing = {link.asset_id: link for link in part.asset_links}
    part.asset_links = [existing.get(asset_id) or PartAsset(asset_id=asset_id) for asset_id in wanted]
    db.session.flush()
    part.updated_by_user_id = ctx.user.id
    after = sorted(str(link.asset_id) for link in part.asset_links)
    audit_events.record(
        ctx,
        "part.assets_changed",
        part,
        before={"asset_ids": before},
        after={"asset_ids": after},
        summary=f"Updated assets for {part.name}",
    )
    db.session.commit()
    return part
