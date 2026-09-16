"""Inventory movements: receipts, issues, returns, adjustments, scrap,
transfers and cycle counts, plus the low-stock list and the chapter-wide ledger.

Every quantity change here goes through ``inventory_ledger.post`` - this module
never touches ``ops_inventory_balances`` and never computes stock in Python.
Each public write commits once and then emits the ledger's queued events.

Issuing a part against a work order also writes the system
``CostEntry(type="parts", inventory_transaction_id=...)`` so the operations
report and the project budget see what the work consumed. Returning against a
work order reverses issues that work order actually made - newest first, each
piece priced at the unit cost of the issue it reverses - so a return can never
credit more than was charged.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy import func, or_, select

from asme.extensions import db
from asme.ops import policy
from asme.ops.models import CostEntry, InventoryBalance, InventoryTransaction, Location, Part, PurchaseRequest, WorkOrder
from asme.ops.models.inventory import INVENTORY_TRANSACTION_TYPES
from asme.ops.services import audit_events, entities, inventory_ledger as ledger, parts as parts_service
from asme.ops.services import work_order_parts as work_order_parts_service
from asme.ops.services import work_orders as work_orders_service
from asme.ops.types import parse_uuid
from asme.ops.validation import Field, ValidationErrors, validate
from asme.services.errors import Conflict, NotFound, Validation

READ = parts_service.READ
MANAGE = parts_service.MANAGE

DIRECT_TYPES = ("receipt", "issue", "return", "adjustment", "scrap")
INCREASING_TYPES = ("receipt", "return")
DECREASING_TYPES = ("issue", "scrap")
WORK_ORDER_TYPES = ("issue", "return")
NOTE_REQUIRED_TYPES = ("adjustment", "scrap")
DIRECTIONS = ("increase", "decrease")

MAX_COUNT_LINES = 200
MONEY_PLACES = Decimal("0.01")
ZERO = Decimal("0")

LEDGER_FILTERS = {"type": "multi", "location": "multi", "part": "multi", "work_order": "multi", "purchase_request": "multi"}
PART_LEDGER_FILTERS = {"type": "multi", "location": "multi"}


def _positive_quantity(value) -> str | None:
    problem = ledger.quantity_check(value)
    if problem:
        return problem
    if value <= 0:
        return "Must be greater than zero."
    return None


def _quantity_field(*, positive: bool = False, **extra) -> Field:
    check = _positive_quantity if positive else ledger.quantity_check
    return Field("decimal", minimum=0, maximum=ledger.QUANTITY_MAX, check=check, **extra)


TRANSACTION_SPEC = {
    "type": Field("choice", choices=DIRECT_TYPES, required=True, nullable=False),
    "location_id": Field("uuid"),
    "quantity": _quantity_field(positive=True, required=True, nullable=False),
    "direction": Field("choice", choices=DIRECTIONS),
    "unit_cost": Field("decimal", minimum=0, maximum=ledger.UNIT_COST_MAX, check=ledger.unit_cost_check),
    "work_order_id": Field("uuid"),
    "note": Field("text"),
}

TRANSFER_SPEC = {
    "part_id": Field("uuid", required=True, nullable=False),
    "from_location_id": Field("uuid", required=True, nullable=False),
    "to_location_id": Field("uuid", required=True, nullable=False),
    "quantity": _quantity_field(positive=True, required=True, nullable=False),
    "note": Field("text"),
}

CYCLE_COUNT_SPEC = {
    "location_id": Field("uuid", required=True, nullable=False),
    # Field("any") so one bad entry becomes a "lines[n]" field error instead of
    # collapsing the whole list into a single message.
    "lines": Field("list", item=Field("any"), max_len=MAX_COUNT_LINES, required=True, nullable=False),
    "note": Field("text"),
    "work_order_id": Field("uuid"),
}

CYCLE_COUNT_LINE_SPEC = {
    "part_id": Field("uuid", required=True, nullable=False),
    "counted_quantity": _quantity_field(required=True, nullable=False),
}

RANGE_SPEC = {"from": Field("date"), "to": Field("date")}


# --------------------------------------------------------------------------- helpers


def _plain(value: Decimal) -> str:
    return format(Decimal(value).normalize(), "f")


def _default_location(ctx, part: Part) -> Location | None:
    if part.default_location_id is not None:
        row = db.session.get(Location, part.default_location_id)
        if row is not None and row.organization_id == ctx.org.id:
            return row
    return Location.query.filter_by(organization_id=ctx.org.id, is_default=True).first()


def _resolve_location(ctx, location_id, *, field: str) -> Location:
    row = db.session.get(Location, location_id) if location_id is not None else None
    if row is None or row.organization_id != ctx.org.id:
        raise ValidationErrors({field: "Unknown location."})
    return row


def _resolve_work_order(ctx, work_order_id) -> WorkOrder:
    row = db.session.get(WorkOrder, work_order_id) if work_order_id is not None else None
    if row is None or not work_orders_service.can_read_work_order(ctx, row):
        raise ValidationErrors({"work_order_id": "Unknown work order."})
    return row


def _authorize_movement(ctx, transaction_type: str, work_order: WorkOrder | None) -> None:
    """``inventory.manage`` moves stock; assignees may also issue and return parts
    against a work order they may log time on."""
    if ctx.has(MANAGE):
        return
    if transaction_type in WORK_ORDER_TYPES and work_order is not None and policy.can(ctx, "work_order.log_time", work_order):
        return
    policy.authorize(ctx, MANAGE)


def _parts_cost_entry(
    ctx,
    work_order: WorkOrder,
    part: Part,
    quantity: Decimal,
    transaction: InventoryTransaction,
    *,
    credit: bool,
    unit_cost: Decimal | None = None,
):
    """The system parts cost for an issue (or the credit for a return).

    An issue is priced at the part's current unit cost; a return is priced at the
    unit cost of the issue it reverses, which the caller passes in. Returns
    ``None`` when no unit cost is known."""
    if unit_cost is None:
        if part.unit_cost is None:
            return None
        unit_cost = ledger.to_unit_cost(part.unit_cost)
    amount = (quantity * unit_cost).quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)
    if credit:
        amount = -amount
    description = f"{_plain(quantity)} {part.unit or 'each'} {part.name}"
    row = CostEntry(
        organization_id=ctx.org.id,
        type="parts",
        amount=amount,
        description=description[:400],
        inventory_transaction_id=transaction.id,
        created_by_user_id=getattr(ctx, "user_id", None),
        updated_by_user_id=getattr(ctx, "user_id", None),
    )
    work_order.cost_entries.append(row)
    db.session.flush()
    work_order.updated_by_user_id = getattr(ctx, "user_id", None)
    audit_events.record(
        ctx,
        "work_order.cost_added",
        work_order,
        after={"cost_entry_id": str(row.id), "type": row.type, "amount": audit_events.jsonable(row.amount), "description": row.description},
        summary=f"Parts cost on #{work_order.number}: {description}",
        inventory_transaction_id=str(transaction.id),
    )
    return row


# --------------------------------------------------------------------------- part transactions


def record_transaction(ctx, part: Part, payload: dict) -> InventoryTransaction:
    """``POST /parts/:id/transactions`` - one receipt, issue, return, adjustment
    or scrap at a single location."""
    if part.organization_id != ctx.org.id:
        raise NotFound()
    data = validate(payload, TRANSACTION_SPEC)
    transaction_type = data["type"]
    errors: dict[str, str] = {}

    direction = data.get("direction")
    if transaction_type == "adjustment":
        if direction not in DIRECTIONS:
            errors["direction"] = "Choose increase or decrease."
    elif direction is not None:
        errors["direction"] = "Only an adjustment takes a direction."
    if transaction_type != "receipt" and data.get("unit_cost") is not None:
        errors["unit_cost"] = "Only a receipt records a unit cost."
    note = (data.get("note") or "").strip() or None
    if transaction_type in NOTE_REQUIRED_TYPES and not note:
        errors["note"] = "This field is required."
    if data.get("work_order_id") is not None and transaction_type not in WORK_ORDER_TYPES:
        errors["work_order_id"] = "Only an issue or a return can reference a work order."
    if errors:
        raise ValidationErrors(errors)

    work_order = _resolve_work_order(ctx, data["work_order_id"]) if data.get("work_order_id") is not None else None
    _authorize_movement(ctx, transaction_type, work_order)

    if data.get("location_id") is not None:
        location = _resolve_location(ctx, data["location_id"], field="location_id")
    else:
        location = _default_location(ctx, part)
        if location is None:
            raise ValidationErrors({"location_id": "This field is required."})

    quantity = data["quantity"]
    if transaction_type in INCREASING_TYPES:
        on_hand_delta = quantity
    elif transaction_type in DECREASING_TYPES:
        on_hand_delta = -quantity
    else:
        on_hand_delta = quantity if direction == "increase" else -quantity

    if transaction_type == "return" and work_order is not None:
        transaction = _return_to_work_order(ctx, part, location, quantity, work_order, note)
        db.session.commit()
        ledger.emit_pending_events()
        return transaction

    unit_cost = data.get("unit_cost")
    if transaction_type in WORK_ORDER_TYPES and part.unit_cost is not None:
        # An issue or return records what the stock was worth, exactly like the
        # work-order parts endpoints do; the ledger only re-weights on receipts.
        unit_cost = ledger.to_unit_cost(part.unit_cost)

    transaction = ledger.post(
        ctx,
        part=part,
        location=location,
        transaction_type=transaction_type,
        on_hand_delta=on_hand_delta,
        quantity=quantity,
        unit_cost=unit_cost,
        work_order=work_order,
        note=note,
    )
    if work_order is not None:
        _parts_cost_entry(ctx, work_order, part, quantity, transaction, credit=False)
    db.session.commit()
    ledger.emit_pending_events()
    return transaction


def _return_to_work_order(ctx, part: Part, location: Location, quantity: Decimal, work_order: WorkOrder, note: str | None) -> InventoryTransaction:
    """A return that names a work order reverses issues that work order actually
    made, exactly like ``POST /work-orders/:id/parts/:pid/return``.

    Without this a single request hands the work order an arbitrary negative
    ``parts`` cost entry - unreferenced, uncapped and priced at today's average
    cost - which drives the work order's parts cost and the project's
    ``budget.used`` below zero. Anyone who may log time on the work order can
    call it, so the rule has to live here and not only on the work-order route.
    """
    issues = work_order_parts_service.issues_newest_first(work_order_id=work_order.id, part_id=part.id)
    plan, leftover = work_order_parts_service.plan_return(quantity, issues)
    if leftover > 0:
        issued = sum((piece for _, piece in plan), ledger.to_quantity(0))
        raise Conflict(
            f"#{work_order.number} has only {_plain(issued)} {part.unit or 'each'} of {part.name} still out.",
            code="return_exceeds_issued",
            work_order_id=str(work_order.id),
            part_id=str(part.id),
            requested=float(quantity),
            outstanding=float(issued),
        )

    first: InventoryTransaction | None = None
    for reference, piece in plan:
        unit_cost = ledger.to_unit_cost(reference.unit_cost) if reference.unit_cost is not None else None
        transaction = ledger.post(
            ctx,
            part=part,
            location=location,
            transaction_type="return",
            on_hand_delta=piece,
            quantity=piece,
            unit_cost=unit_cost,
            work_order=work_order,
            reference=reference,
            note=note,
        )
        first = first if first is not None else transaction
        _parts_cost_entry(ctx, work_order, part, piece, transaction, credit=True, unit_cost=unit_cost)
    return first


# --------------------------------------------------------------------------- transfers


def transfer(ctx, payload: dict) -> tuple[InventoryTransaction, InventoryTransaction]:
    """Move stock between two locations: one ``transfer`` out and one in, the
    second referencing the first."""
    policy.authorize(ctx, MANAGE)
    data = validate(payload, TRANSFER_SPEC)
    part = policy.get_or_404(ctx, Part, data["part_id"], "Unknown part.")
    if data["from_location_id"] == data["to_location_id"]:
        raise ValidationErrors({"to_location_id": "Choose a different location."})
    source = _resolve_location(ctx, data["from_location_id"], field="from_location_id")
    target = _resolve_location(ctx, data["to_location_id"], field="to_location_id")
    quantity = data["quantity"]
    note = (data.get("note") or "").strip() or None

    # A transfer is one movement: the outgoing leg alone can empty the chapter's
    # only shelf, and judging stock per ledger row would raise a false
    # "out of stock" alert whose per-day dedupe key then swallows the real one.
    before_state = ledger.stock_state(ledger.part_totals([part.id])[part.id], part)
    out_row = ledger.post(
        ctx,
        part=part,
        location=source,
        transaction_type="transfer",
        on_hand_delta=-quantity,
        quantity=quantity,
        note=note,
        notify=False,
    )
    in_row = ledger.post(
        ctx,
        part=part,
        location=target,
        transaction_type="transfer",
        on_hand_delta=quantity,
        quantity=quantity,
        reference=out_row,
        note=note,
        notify=False,
    )
    after_totals = ledger.part_totals([part.id])[part.id]
    ledger.stock_state_changed(ctx, part, before_state, ledger.stock_state(after_totals, part), totals=after_totals)
    db.session.commit()
    ledger.emit_pending_events()
    return out_row, in_row


# --------------------------------------------------------------------------- cycle counts


def _count_lines(ctx, raw_lines: list) -> list[tuple[Part, Decimal]]:
    errors: dict[str, str] = {}
    cleaned: list[tuple[Part, Decimal]] = []
    seen: set[UUID] = set()
    for index, entry in enumerate(raw_lines):
        if not isinstance(entry, dict):
            errors[f"lines[{index}]"] = "Must be an object."
            continue
        try:
            line = validate(entry, CYCLE_COUNT_LINE_SPEC)
        except ValidationErrors as exc:
            errors.update({f"lines[{index}].{field}": message for field, message in exc.errors.items()})
            continue
        part = db.session.get(Part, line["part_id"])
        if part is None or part.organization_id != ctx.org.id:
            errors[f"lines[{index}].part_id"] = "Unknown part."
            continue
        if part.id in seen:
            errors[f"lines[{index}].part_id"] = "This part is already counted on another line."
            continue
        seen.add(part.id)
        cleaned.append((part, line["counted_quantity"]))
    if errors:
        raise ValidationErrors(errors)
    return cleaned


def cycle_count(ctx, payload: dict) -> list[dict]:
    """Record a physical count at one location. Every line is written, even when
    it agrees with the system, so the count date is known."""
    policy.authorize(ctx, MANAGE)
    data = validate(payload, CYCLE_COUNT_SPEC)
    raw_lines = data.get("lines") or []
    if not raw_lines:
        raise ValidationErrors({"lines": "Count at least one part."})
    location = _resolve_location(ctx, data["location_id"], field="location_id")
    work_order = _resolve_work_order(ctx, data["work_order_id"]) if data.get("work_order_id") is not None else None
    note = (data.get("note") or "").strip() or None
    lines = _count_lines(ctx, raw_lines)

    results: list[dict] = []
    for part, counted in lines:
        balance = InventoryBalance.query.filter_by(part_id=part.id, location_id=location.id).first()
        expected = ledger.to_quantity(balance.on_hand if balance is not None else 0)
        delta = counted - expected
        ledger.post(
            ctx,
            part=part,
            location=location,
            transaction_type="cycle_count",
            on_hand_delta=delta,
            quantity=abs(delta),
            counted_quantity=counted,
            work_order=work_order,
            note=note,
        )
        results.append({"part": part, "expected": expected, "counted": counted, "delta": delta})
    db.session.commit()
    ledger.emit_pending_events()
    return results


def cycle_count_sheet(ctx, location_id) -> tuple[Location, list[tuple[Part, Decimal, Decimal]]]:
    """``(location, [(part, on_hand, reserved)])`` for every part with a balance
    row at ``location_id`` - the paper the counter walks around with."""
    policy.authorize(ctx, READ)
    parsed = parse_uuid(location_id)
    if parsed is None:
        raise ValidationErrors({"location_id": "This field is required."})
    location = _resolve_location(ctx, parsed, field="location_id")
    rows = db.session.execute(
        select(Part, InventoryBalance.on_hand, InventoryBalance.reserved)
        .join(InventoryBalance, InventoryBalance.part_id == Part.id)
        .where(
            InventoryBalance.location_id == location.id,
            InventoryBalance.organization_id == ctx.org.id,
            Part.organization_id == ctx.org.id,
        )
        .order_by(func.lower(Part.name).asc(), Part.id.asc())
    ).all()
    return location, [(part, ledger.to_quantity(on_hand or 0), ledger.to_quantity(reserved or 0)) for part, on_hand, reserved in rows]


# --------------------------------------------------------------------------- low stock


def suggested_quantity(part: Part, totals: dict) -> Decimal:
    """``reorder_quantity``, else the gap to ``maximum_stock``, else the gap to
    ``minimum_stock``; never less than one.

    Defined once in the purchase-requests vertical, which applies the same rule
    when it turns low stock into drafts, so this list and the drafts made from
    it can never suggest different quantities."""
    from asme.ops.services.purchase_requests import suggested_order_quantity

    return suggested_order_quantity(part, totals)


def low_stock(ctx) -> list[dict]:
    """Active parts in ``low`` or ``out``, each with its preferred vendor link and
    a suggested order quantity. Critical parts first, then the deepest shortfall."""
    policy.authorize(ctx, READ)
    query = Part.query.filter(Part.organization_id == ctx.org.id, Part.is_active.is_(True)).filter(
        or_(parts_service.stock_criterion("low"), parts_service.stock_criterion("out"))
    )
    rows = query.order_by(Part.is_critical.desc(), func.lower(Part.name).asc(), Part.id.asc()).all()
    totals, states = parts_service.enrich(rows)
    items: list[dict] = []
    for part in rows:
        part_totals = totals.get(part.id, {})
        items.append(
            {
                "part": part,
                "totals": part_totals,
                "stock_state": states.get(part.id, "untracked"),
                "link": part.preferred_vendor_link,
                "suggested_quantity": suggested_quantity(part, part_totals),
            }
        )
    return items


# --------------------------------------------------------------------------- ledger listing


def parse_date_range(raw_from, raw_to) -> tuple[datetime | None, datetime | None]:
    """``?from=YYYY-MM-DD&to=YYYY-MM-DD`` as an inclusive UTC day range."""
    payload = {}
    if raw_from:
        payload["from"] = raw_from
    if raw_to:
        payload["to"] = raw_to
    if not payload:
        return None, None
    data = validate(payload, RANGE_SPEC, partial=True)
    start = _start_of_day(data["from"]) if isinstance(data.get("from"), date) else None
    end = _start_of_day(data["to"] + timedelta(days=1)) if isinstance(data.get("to"), date) else None
    if start is not None and end is not None and end <= start:
        raise ValidationErrors({"to": "Must be on or after the start date."})
    return start, end


def _start_of_day(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=timezone.utc)


def _type_values(values: list[str]) -> list[str]:
    cleaned = [value.strip().lower() for value in values]
    bad = [value for value in cleaned if value not in INVENTORY_TRANSACTION_TYPES]
    if bad:
        raise Validation("filter[type] accepts: " + ", ".join(INVENTORY_TRANSACTION_TYPES) + ".", field="type", code="bad_filter")
    return cleaned


def transactions_query(ctx, *, part: Part | None = None, filters: dict[str, list[str]] | None = None, date_from=None, date_to=None):
    """Newest-first ledger query. The route paginates it."""
    policy.authorize(ctx, READ)
    filters = filters or {}
    query = InventoryTransaction.query.filter(InventoryTransaction.organization_id == ctx.org.id)
    if part is not None:
        query = query.filter(InventoryTransaction.part_id == part.id)
    if filters.get("type"):
        query = query.filter(InventoryTransaction.transaction_type.in_(_type_values(filters["type"])))
    if filters.get("location"):
        query = query.filter(InventoryTransaction.location_id.in_(parts_service.uuid_values(filters["location"], "location")))
    if filters.get("part"):
        query = query.filter(InventoryTransaction.part_id.in_(parts_service.uuid_values(filters["part"], "part")))
    if filters.get("work_order"):
        query = query.filter(InventoryTransaction.work_order_id.in_(parts_service.uuid_values(filters["work_order"], "work_order")))
    if filters.get("purchase_request"):
        ids = parts_service.uuid_values(filters["purchase_request"], "purchase_request")
        query = query.filter(InventoryTransaction.purchase_request_id.in_(ids))
    if date_from is not None:
        query = query.filter(InventoryTransaction.created_at >= date_from)
    if date_to is not None:
        query = query.filter(InventoryTransaction.created_at < date_to)
    return query.order_by(InventoryTransaction.created_at.desc(), InventoryTransaction.id.desc())


def readable_work_order_ids(ctx, transactions: list[InventoryTransaction]) -> set:
    """The subset of the page's work-order ids the caller may read, in one query,
    so a private project's work order is never named in the ledger."""
    ids = {row.work_order_id for row in transactions if row.work_order_id is not None}
    if not ids:
        return set()
    rows = work_orders_service.visible_work_orders_query(ctx).filter(WorkOrder.id.in_(list(ids))).with_entities(WorkOrder.id).all()
    return {row[0] for row in rows}


def readable_purchase_request_ids(ctx, transactions: list[InventoryTransaction]) -> set:
    """The subset of the page's purchase-request ids the caller may read, in one
    query. The ledger is gated on ``inventory.read`` alone, so without this a
    receipt would hand every member the number, title and status of a request
    ``GET /purchase-requests/:id`` answers 404 for."""
    ids = {row.purchase_request_id for row in transactions if row.purchase_request_id is not None}
    if not ids:
        return set()
    rows = (
        entities.visible_purchase_requests_query(ctx)
        .filter(PurchaseRequest.id.in_(list(ids)))
        .with_entities(PurchaseRequest.id)
        .all()
    )
    return {row[0] for row in rows}
