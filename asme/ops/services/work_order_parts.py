"""Work-order parts: planning, reservation, kitting, issue and return.

A line in ``ops_work_order_parts`` says which part a work order needs, where it
is drawn from and how far along it is. Quantities never move on their own: every
change goes through ``inventory_ledger.post`` and this module keeps the line's
cached ``quantity_*`` columns, its readiness and the system ``parts`` cost
entries in step with the ledger inside one transaction.

Readiness runs ``assigned -> reserved -> kitted -> staged -> issued``; ``kit``
and ``stage`` are readiness-only (audited, no ledger row). Issuing consumes the
line's reservation first - a ``release`` row for what the reservation covers and
an ``issue`` row for the whole quantity, both inside the same transaction - and
writes a system ``parts`` cost entry linked to the issue transaction. Returning
walks the line's issues newest first and writes one ``return`` row per issue it
reverses, each priced at that issue's own unit cost, so the credits add up to
exactly what was charged even when a receipt moved the part's average cost in
between - the operations report and project budgets follow the stock and can
never go negative through a return.

Every mutating function takes ``ctx`` first, authorizes before writing, audits in
the same transaction, commits, and only then emits the ledger's queued events.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select

from asme.extensions import db
from asme.ops import policy
from asme.ops.models import CostEntry, InventoryTransaction, Location, Part, WorkOrder, WorkOrderPart
from asme.ops.models.inventory import WORK_ORDER_PART_READINESS
from asme.ops.services import audit_events
from asme.ops.services import inventory_ledger as ledger
from asme.ops.types import parse_uuid
from asme.ops.validation import Field, ValidationErrors, validate
from asme.services.errors import Conflict, Forbidden, NotFound

ZERO = Decimal("0")
MONEY_PLACES = Decimal("0.01")
MIN_QUANTITY = Decimal("0.001")  # one step of Numeric(14, 3)

INVENTORY_MANAGE = "inventory.manage"
PARTS_COST_TYPE = "parts"
DESCRIPTION_MAX = 400

# assigned < reserved < kitted < staged < issued
READINESS_RANK = {name: index for index, name in enumerate(WORK_ORDER_PART_READINESS)}
READINESS_NONE = "none"

RESERVE_MESSAGE = "Only inventory managers and work-order editors can reserve parts."
ISSUE_MESSAGE = "Only inventory managers and people working this work order can issue parts."
KIT_MESSAGE = "Only inventory managers can kit or stage parts."
LOCATION_REQUIRED = "Choose a location for this part first."
RESERVATION_CONSUMED_NOTE = "Consumed by issue"

_QUANTITY_FIELD = Field(
    "decimal",
    required=True,
    nullable=False,
    minimum=MIN_QUANTITY,
    maximum=ledger.QUANTITY_MAX,
    check=ledger.quantity_check,
)

ADD_SPEC = {
    "part_id": Field("uuid", required=True, nullable=False),
    "location_id": Field("uuid"),
    "quantity_planned": _QUANTITY_FIELD,
    "note": Field("text", max_len=2000),
}
UPDATE_SPEC = {
    "quantity_planned": Field(
        "decimal", nullable=False, minimum=MIN_QUANTITY, maximum=ledger.QUANTITY_MAX, check=ledger.quantity_check
    ),
    "note": Field("text", max_len=2000),
}
QUANTITY_SPEC = {"quantity": _QUANTITY_FIELD, "note": Field("text", max_len=2000)}
NOTE_SPEC = {"note": Field("text", max_len=2000)}

LINE_FIELDS = (
    "part_id",
    "location_id",
    "quantity_planned",
    "quantity_reserved",
    "quantity_issued",
    "quantity_returned",
    "readiness",
    "note",
)


# --------------------------------------------------------------------------- numbers


def _quantity(value) -> Decimal:
    """A stored quantity as an exact ``Decimal`` (SQLite may hand back a float)."""
    if value is None:
        return ZERO
    if isinstance(value, float):
        value = Decimal(repr(value))
    return Decimal(value).quantize(ledger.QUANTITY_PLACES, rounding=ROUND_HALF_UP)


def _unit_cost(value) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, float):
        value = Decimal(repr(value))
    return Decimal(value).quantize(ledger.UNIT_COST_PLACES, rounding=ROUND_HALF_UP)


def _quantity_text(value: Decimal) -> str:
    """``3.000`` -> ``3``, ``0.500`` -> ``0.5`` - for cost-entry descriptions."""
    return format(_quantity(value).normalize(), "f")


def _money(quantity: Decimal, unit_cost: Decimal) -> Decimal:
    return (quantity * unit_cost).quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)


# --------------------------------------------------------------------------- authorization


def _authorize_plan(ctx, wo: WorkOrder) -> None:
    policy.authorize(ctx, "work_order.edit", wo)


def _authorize_reserve(ctx, wo: WorkOrder) -> None:
    """Reserving and releasing: inventory managers, or whoever may edit the work order."""
    if ctx.has(INVENTORY_MANAGE) or policy.can(ctx, "work_order.edit", wo):
        return
    raise Forbidden(RESERVE_MESSAGE, permission=INVENTORY_MANAGE)


def _authorize_issue(ctx, wo: WorkOrder) -> None:
    """Issuing and returning: inventory managers, or the people doing the work."""
    if ctx.has(INVENTORY_MANAGE) or policy.can(ctx, "work_order.log_time", wo):
        return
    raise Forbidden(ISSUE_MESSAGE, permission=INVENTORY_MANAGE)


def _authorize_kit(ctx, wo: WorkOrder) -> None:
    if not ctx.has(INVENTORY_MANAGE):
        raise Forbidden(KIT_MESSAGE, permission=INVENTORY_MANAGE)


# --------------------------------------------------------------------------- reads


def list_for_work_order(ctx, wo: WorkOrder) -> list[WorkOrderPart]:
    """Every part line of ``wo``, oldest first. The caller has already proved it
    may read the work order."""
    stmt = (
        select(WorkOrderPart)
        .where(WorkOrderPart.organization_id == ctx.org.id, WorkOrderPart.work_order_id == wo.id)
        .order_by(WorkOrderPart.created_at.asc(), WorkOrderPart.id.asc())
    )
    return list(db.session.scalars(stmt))


def readiness_summary(rows) -> str:
    """``"none"`` when the work order has no parts, otherwise the least advanced
    readiness across its lines."""
    rows = list(rows)
    if not rows:
        return READINESS_NONE
    return min((row.readiness for row in rows), key=lambda value: READINESS_RANK.get(value, 0))


def outstanding_count(wo: WorkOrder) -> int:
    """How many lines still hold a reservation that was never issued. Reported as
    ``parts_outstanding`` when a work order is completed; completing never
    releases anything by itself."""
    rows = db.session.scalars(
        select(WorkOrderPart).where(WorkOrderPart.work_order_id == wo.id, WorkOrderPart.quantity_reserved > 0)
    ).all()
    return sum(1 for row in rows if _quantity(row.quantity_reserved) > 0)


def get_line(ctx, wo: WorkOrder, line_id) -> WorkOrderPart:
    """Load one line of ``wo``; anything else (foreign organization, other work
    order, malformed id) is a 404."""
    parsed = parse_uuid(line_id)
    if parsed is None:
        raise NotFound("Part line not found.")
    line = policy.get_or_404(ctx, WorkOrderPart, parsed, "Part line not found.")
    if line.work_order_id != wo.id:
        raise NotFound("Part line not found.")
    return line


# --------------------------------------------------------------------------- internals


def _snapshot(line: WorkOrderPart) -> dict:
    return audit_events.snapshot(line, LINE_FIELDS)


def _label(line: WorkOrderPart, quantity: Decimal | None = None) -> str:
    part = line.part
    name = part.name if part is not None else "part"
    unit = (part.unit if part is not None else None) or "each"
    amount = _quantity_text(quantity if quantity is not None else line.quantity_planned)
    return f"{amount} {unit} {name}"


def _record(ctx, wo: WorkOrder, line: WorkOrderPart, event: str, *, before: dict | None, summary: str, **metadata) -> None:
    """Part-line history belongs to the work order: it is audited against the work
    order so it reaches the work-order timeline and the change feed without a new
    visibility rule."""
    audit_events.record(
        ctx,
        event,
        wo,
        before=before,
        after=_snapshot(line),
        summary=summary,
        work_order_part_id=str(line.id),
        part_id=str(line.part_id),
        **metadata,
    )


def _resolve_location(ctx, line: WorkOrderPart) -> Location:
    if line.location_id is None:
        raise ValidationErrors({"location_id": LOCATION_REQUIRED})
    location = policy.get_or_404(ctx, Location, line.location_id)
    return location


def _remaining_need(line: WorkOrderPart) -> Decimal:
    """Planned quantity still to be issued (returns put quantity back in play)."""
    outstanding = _quantity(line.quantity_issued) - _quantity(line.quantity_returned)
    remaining = _quantity(line.quantity_planned) - outstanding
    return remaining if remaining > 0 else ZERO


def _advance(line: WorkOrderPart, readiness: str) -> None:
    if READINESS_RANK.get(readiness, 0) > READINESS_RANK.get(line.readiness, 0):
        line.readiness = readiness


def _recompute_readiness(line: WorkOrderPart) -> None:
    """Called after a release or a return: a line with nothing reserved and
    nothing outstanding falls back to ``assigned``, and a line that is no longer
    fully issued falls back to ``reserved``."""
    reserved = _quantity(line.quantity_reserved)
    outstanding = _quantity(line.quantity_issued) - _quantity(line.quantity_returned)
    if outstanding >= _quantity(line.quantity_planned) and outstanding > 0:
        line.readiness = "issued"
        return
    if line.readiness == "issued":
        line.readiness = "reserved" if reserved > 0 else "assigned"
        return
    if reserved <= 0 and outstanding <= 0 and line.readiness == "reserved":
        line.readiness = "assigned"


def issues_newest_first(*, work_order_id=None, work_order_part_id=None, part_id=None) -> list[InventoryTransaction]:
    """Every ``issue`` row of one work-order part line (or of one work order and
    part), newest first."""
    stmt = select(InventoryTransaction).where(InventoryTransaction.transaction_type == "issue")
    if work_order_part_id is not None:
        stmt = stmt.where(InventoryTransaction.work_order_part_id == work_order_part_id)
    else:
        stmt = stmt.where(InventoryTransaction.work_order_id == work_order_id, InventoryTransaction.part_id == part_id)
    return list(db.session.scalars(stmt.order_by(InventoryTransaction.created_at.desc(), InventoryTransaction.id.desc())))


def _returned_against(issue_ids: list) -> dict:
    """``{issue_id: quantity already returned against it}``, in one query."""
    if not issue_ids:
        return {}
    rows = db.session.execute(
        select(InventoryTransaction.reference_transaction_id, func.sum(InventoryTransaction.quantity))
        .where(
            InventoryTransaction.transaction_type == "return",
            InventoryTransaction.reference_transaction_id.in_(issue_ids),
        )
        .group_by(InventoryTransaction.reference_transaction_id)
    )
    return {issue_id: _quantity(total) for issue_id, total in rows}


def plan_return(quantity: Decimal, issues: list[InventoryTransaction]) -> tuple[list[tuple[InventoryTransaction, Decimal]], Decimal]:
    """Split ``quantity`` across ``issues`` newest first, skipping what has
    already been returned.

    Returns ``([(issue, quantity from that issue)], quantity left over)``. The
    leftover is what no issue accounts for; crediting it would hand the work
    order money it was never charged, so callers either refuse it or put it back
    on the shelf without a cost entry. Pricing each piece at the unit cost of the
    issue it reverses is the only way the credits can add up to exactly what the
    issues charged when the part's average cost moved in between.
    """
    returned = _returned_against([issue.id for issue in issues])
    remaining = _quantity(quantity)
    plan: list[tuple[InventoryTransaction, Decimal]] = []
    for issue in issues:
        if remaining <= 0:
            break
        available = _quantity(issue.quantity) - returned.get(issue.id, ZERO)
        if available <= 0:
            continue
        take = available if available < remaining else remaining
        # Neighbouring issues at the same price need no separate rows: the credit
        # is identical either way and one movement stays one ledger row.
        if plan and _unit_cost(plan[-1][0].unit_cost) == _unit_cost(issue.unit_cost):
            plan[-1] = (plan[-1][0], plan[-1][1] + take)
        else:
            plan.append((issue, take))
        remaining -= take
    return plan, remaining


def _cost_entry(ctx, wo: WorkOrder, line: WorkOrderPart, *, amount: Decimal, description: str, transaction) -> CostEntry:
    row = CostEntry(
        organization_id=ctx.org.id,
        work_order_id=wo.id,
        type=PARTS_COST_TYPE,
        amount=amount,
        description=description[:DESCRIPTION_MAX],
        inventory_transaction_id=getattr(transaction, "id", None),
        created_by_user_id=ctx.user.id,
        updated_by_user_id=ctx.user.id,
    )
    wo.cost_entries.append(row)
    db.session.flush()
    return row


def _commit(ctx) -> None:
    db.session.commit()
    ledger.emit_pending_events()


# --------------------------------------------------------------------------- plan the line


def add(ctx, wo: WorkOrder, payload: dict) -> WorkOrderPart:
    """Put a part on a work order. Needs ``work_order.edit``."""
    _authorize_plan(ctx, wo)
    data = validate(payload, ADD_SPEC)
    errors: dict[str, str] = {}

    part = db.session.get(Part, data["part_id"])
    if part is None or part.organization_id != ctx.org.id or not part.is_active:
        errors["part_id"] = "Unknown part."
        part = None

    location = None
    if data.get("location_id") is not None:
        location = db.session.get(Location, data["location_id"])
        if location is None or location.organization_id != ctx.org.id:
            errors["location_id"] = "Unknown location."
            location = None
    elif part is not None and part.default_location_id is not None:
        location = db.session.get(Location, part.default_location_id)
    if errors:
        raise ValidationErrors(errors)

    location_id = location.id if location is not None else None
    existing = WorkOrderPart.query.filter_by(work_order_id=wo.id, part_id=part.id, location_id=location_id).first()
    if existing is not None:
        raise Conflict(
            f"{part.name} is already on this work order at that location.",
            code="part_already_added",
            work_order_part_id=str(existing.id),
        )

    line = WorkOrderPart(
        organization_id=ctx.org.id,
        work_order_id=wo.id,
        part_id=part.id,
        location_id=location_id,
        quantity_planned=data["quantity_planned"],
        quantity_reserved=ZERO,
        quantity_issued=ZERO,
        quantity_returned=ZERO,
        readiness="assigned",
        note=data.get("note"),
        created_by_user_id=ctx.user.id,
        updated_by_user_id=ctx.user.id,
    )
    db.session.add(line)
    db.session.flush()
    _record(ctx, wo, line, "work_order.part_added", before=None, summary=f"Added {_label(line)} to #{wo.number}")
    wo.updated_by_user_id = ctx.user.id
    _commit(ctx)
    return line


def update(ctx, wo: WorkOrder, line: WorkOrderPart, payload: dict) -> WorkOrderPart:
    """Change the planned quantity or the note. Needs ``work_order.edit``."""
    _authorize_plan(ctx, wo)
    data = validate(payload, UPDATE_SPEC, partial=True)
    before = _snapshot(line)
    if "quantity_planned" in data:
        outstanding = _quantity(line.quantity_issued) - _quantity(line.quantity_returned)
        if data["quantity_planned"] < outstanding:
            raise ValidationErrors(
                {"quantity_planned": f"At least {_quantity_text(outstanding)} has already been issued."}
            )
        line.quantity_planned = data["quantity_planned"]
    if "note" in data:
        line.note = data["note"]
    _recompute_readiness(line)
    line.updated_by_user_id = ctx.user.id
    db.session.flush()
    after = _snapshot(line)
    if before != after:
        _record(ctx, wo, line, "work_order.part_updated", before=before, summary=f"Updated {_label(line)} on #{wo.number}")
        wo.updated_by_user_id = ctx.user.id
    _commit(ctx)
    return line


def remove(ctx, wo: WorkOrder, line: WorkOrderPart) -> WorkOrder:
    """Take a part off a work order. Only while nothing is reserved or issued."""
    _authorize_plan(ctx, wo)
    if _quantity(line.quantity_reserved) > 0 or _quantity(line.quantity_issued) > 0:
        raise Conflict(
            "Release the reservation and return what was issued before removing this part.",
            code="work_order_part_in_use",
            work_order_part_id=str(line.id),
        )
    before = _snapshot(line)
    summary = f"Removed {_label(line)} from #{wo.number}"
    audit_events.record(
        ctx,
        "work_order.part_removed",
        wo,
        before=before,
        summary=summary,
        work_order_part_id=str(line.id),
        part_id=str(line.part_id),
    )
    db.session.delete(line)
    wo.updated_by_user_id = ctx.user.id
    _commit(ctx)
    return wo


# --------------------------------------------------------------------------- reserve / release


def reserve(ctx, wo: WorkOrder, line: WorkOrderPart, payload: dict) -> WorkOrderPart:
    """Hold stock at the line's location. ``inventory.manage`` or ``work_order.edit``."""
    _authorize_reserve(ctx, wo)
    data = validate(payload, QUANTITY_SPEC)
    quantity = data["quantity"]
    location = _resolve_location(ctx, line)
    allowed = _remaining_need(line) - _quantity(line.quantity_reserved)
    if quantity > allowed:
        raise ValidationErrors(
            {"quantity": f"At most {_quantity_text(allowed if allowed > 0 else ZERO)} can still be reserved."}
        )

    before = _snapshot(line)
    ledger.post(
        ctx,
        part=line.part,
        location=location,
        transaction_type="reservation",
        on_hand_delta=ZERO,
        reserved_delta=quantity,
        quantity=quantity,
        work_order=wo,
        work_order_part=line,
        note=data.get("note"),
    )
    line.quantity_reserved = _quantity(line.quantity_reserved) + quantity
    _advance(line, "reserved")
    line.updated_by_user_id = ctx.user.id
    db.session.flush()
    _record(
        ctx,
        wo,
        line,
        "work_order.part_reserved",
        before=before,
        summary=f"Reserved {_label(line, quantity)} for #{wo.number}",
        quantity=str(quantity),
    )
    wo.updated_by_user_id = ctx.user.id
    _commit(ctx)
    return line


def _release_line(ctx, wo: WorkOrder, line: WorkOrderPart, quantity: Decimal, note: str | None) -> None:
    """One release inside the caller's transaction (no commit)."""
    location = _resolve_location(ctx, line)
    before = _snapshot(line)
    ledger.post(
        ctx,
        part=line.part,
        location=location,
        transaction_type="release",
        on_hand_delta=ZERO,
        reserved_delta=-quantity,
        quantity=quantity,
        work_order=wo,
        work_order_part=line,
        note=note,
    )
    line.quantity_reserved = _quantity(line.quantity_reserved) - quantity
    _recompute_readiness(line)
    line.updated_by_user_id = ctx.user.id
    db.session.flush()
    _record(
        ctx,
        wo,
        line,
        "work_order.part_released",
        before=before,
        summary=f"Released {_label(line, quantity)} on #{wo.number}",
        quantity=str(quantity),
    )


def release(ctx, wo: WorkOrder, line: WorkOrderPart, payload: dict) -> WorkOrderPart:
    """Give a held quantity back. ``inventory.manage`` or ``work_order.edit``."""
    _authorize_reserve(ctx, wo)
    data = validate(payload, QUANTITY_SPEC)
    quantity = data["quantity"]
    reserved = _quantity(line.quantity_reserved)
    if quantity > reserved:
        raise ValidationErrors({"quantity": f"Only {_quantity_text(reserved)} is reserved."})
    _release_line(ctx, wo, line, quantity, data.get("note"))
    wo.updated_by_user_id = ctx.user.id
    _commit(ctx)
    return line


def release_all(ctx, wo: WorkOrder) -> list[WorkOrderPart]:
    """Release every reservation on the work order (used after completion)."""
    _authorize_reserve(ctx, wo)
    lines = list_for_work_order(ctx, wo)
    touched = [line for line in lines if _quantity(line.quantity_reserved) > 0]
    for line in touched:
        _release_line(ctx, wo, line, _quantity(line.quantity_reserved), None)
    if touched:
        wo.updated_by_user_id = ctx.user.id
    _commit(ctx)
    return lines


# --------------------------------------------------------------------------- kit / stage


def set_readiness(ctx, wo: WorkOrder, line: WorkOrderPart, readiness: str, payload: dict | None = None) -> WorkOrderPart:
    """``kit`` and ``stage``: readiness only, audited, no ledger row. ``inventory.manage``."""
    if readiness not in ("kitted", "staged"):
        raise ValueError(f"unsupported readiness {readiness!r}")
    _authorize_kit(ctx, wo)
    data = validate(payload or {}, NOTE_SPEC, partial=True)
    if line.readiness == "issued":
        raise Conflict(
            "This part has already been issued.",
            code="invalid_transition",
            **{"from": line.readiness, "action": "kit" if readiness == "kitted" else "stage"},
        )
    before = _snapshot(line)
    line.readiness = readiness
    if data.get("note"):
        line.note = data["note"]
    line.updated_by_user_id = ctx.user.id
    db.session.flush()
    after = _snapshot(line)
    if before != after:
        verb = "Kitted" if readiness == "kitted" else "Staged"
        _record(
            ctx,
            wo,
            line,
            f"work_order.part_{readiness}",
            before=before,
            summary=f"{verb} {_label(line)} for #{wo.number}",
        )
        wo.updated_by_user_id = ctx.user.id
    _commit(ctx)
    return line


# --------------------------------------------------------------------------- issue / return


def issue(ctx, wo: WorkOrder, line: WorkOrderPart, payload: dict) -> WorkOrderPart:
    """Take the parts out of stock and charge them to the work order.

    The line's reservation is consumed first (a ``release`` row for as much as it
    covers), then one ``issue`` row for the whole quantity; both live in the same
    transaction. When the part has a unit cost a system ``parts`` cost entry is
    written against the issue transaction.
    """
    _authorize_issue(ctx, wo)
    data = validate(payload, QUANTITY_SPEC)
    quantity = data["quantity"]
    location = _resolve_location(ctx, line)
    part = line.part
    unit_cost = _unit_cost(part.unit_cost if part is not None else None)

    before = _snapshot(line)
    consumed = min(quantity, _quantity(line.quantity_reserved))
    # The release and the issue are one movement: a savepoint keeps the release
    # from surviving an issue that runs out of stock.
    with db.session.begin_nested():
        if consumed > 0:
            ledger.post(
                ctx,
                part=part,
                location=location,
                transaction_type="release",
                on_hand_delta=ZERO,
                reserved_delta=-consumed,
                quantity=consumed,
                work_order=wo,
                work_order_part=line,
                note=RESERVATION_CONSUMED_NOTE,
            )
        transaction = ledger.post(
            ctx,
            part=part,
            location=location,
            transaction_type="issue",
            on_hand_delta=-quantity,
            quantity=quantity,
            unit_cost=unit_cost,
            work_order=wo,
            work_order_part=line,
            note=data.get("note"),
        )

    line.quantity_reserved = _quantity(line.quantity_reserved) - consumed
    line.quantity_issued = _quantity(line.quantity_issued) + quantity
    outstanding = _quantity(line.quantity_issued) - _quantity(line.quantity_returned)
    if outstanding >= _quantity(line.quantity_planned):
        line.readiness = "issued"
    line.updated_by_user_id = ctx.user.id
    db.session.flush()

    cost = None
    if unit_cost is not None:
        cost = _cost_entry(
            ctx,
            wo,
            line,
            amount=_money(quantity, unit_cost),
            description=_label(line, quantity),
            transaction=transaction,
        )
    _record(
        ctx,
        wo,
        line,
        "work_order.part_issued",
        before=before,
        summary=f"Issued {_label(line, quantity)} on #{wo.number}",
        quantity=str(quantity),
        inventory_transaction_id=str(transaction.id),
        cost_entry_id=str(cost.id) if cost is not None else None,
        amount=str(cost.amount) if cost is not None else None,
    )
    wo.updated_by_user_id = ctx.user.id
    _commit(ctx)
    return line


def return_parts(ctx, wo: WorkOrder, line: WorkOrderPart, payload: dict) -> WorkOrderPart:
    """Put unused parts back on the shelf and reverse exactly what they cost.

    The return is split across the line's issues newest first and each piece is
    written as its own ``return`` row referencing the issue it reverses, priced
    at that issue's unit cost. Pricing the whole return at one issue's cost would
    credit more than was charged whenever a receipt re-weighted the part's
    average cost between two issues, leaving the work order - and the project
    budget - with a negative parts cost.
    """
    _authorize_issue(ctx, wo)
    data = validate(payload, QUANTITY_SPEC)
    quantity = data["quantity"]
    location = _resolve_location(ctx, line)
    outstanding = _quantity(line.quantity_issued) - _quantity(line.quantity_returned)
    if quantity > outstanding:
        raise ValidationErrors({"quantity": f"Only {_quantity_text(outstanding if outstanding > 0 else ZERO)} can be returned."})

    plan, leftover = plan_return(quantity, issues_newest_first(work_order_part_id=line.id))
    # Quantity no issue accounts for goes back on the shelf uncosted rather than
    # being credited at someone else's price.
    pieces: list[tuple[InventoryTransaction | None, Decimal]] = list(plan)
    if leftover > 0:
        pieces.append((None, leftover))

    before = _snapshot(line)
    note = data.get("note")
    transactions: list[InventoryTransaction] = []
    costs: list[CostEntry] = []
    for reference, piece in pieces:
        unit_cost = _unit_cost(reference.unit_cost) if reference is not None else None
        transaction = ledger.post(
            ctx,
            part=line.part,
            location=location,
            transaction_type="return",
            on_hand_delta=piece,
            quantity=piece,
            unit_cost=unit_cost,
            work_order=wo,
            work_order_part=line,
            reference=reference,
            note=note,
        )
        transactions.append(transaction)
        if unit_cost is not None:
            costs.append(
                _cost_entry(
                    ctx,
                    wo,
                    line,
                    amount=-_money(piece, unit_cost),
                    description=f"Returned {_label(line, piece)}",
                    transaction=transaction,
                )
            )

    line.quantity_returned = _quantity(line.quantity_returned) + quantity
    _recompute_readiness(line)
    line.updated_by_user_id = ctx.user.id
    db.session.flush()

    credited = sum((Decimal(str(row.amount)) for row in costs), ZERO)
    _record(
        ctx,
        wo,
        line,
        "work_order.part_returned",
        before=before,
        summary=f"Returned {_label(line, quantity)} on #{wo.number}",
        quantity=str(quantity),
        inventory_transaction_id=str(transactions[0].id) if transactions else None,
        inventory_transaction_ids=[str(row.id) for row in transactions],
        cost_entry_id=str(costs[0].id) if costs else None,
        amount=str(credited) if costs else None,
    )
    wo.updated_by_user_id = ctx.user.id
    _commit(ctx)
    return line
