"""The inventory ledger primitive.

Every quantity change in ASME Ops goes through ``post``: it locks the part,
locks (or creates) the ``(part, location)`` balance, applies the deltas, refuses
a result that would leave negative stock or more reserved than on hand, and
appends an immutable ``InventoryTransaction`` carrying the balance after the
change. Nothing else writes ``ops_inventory_balances``.

``post`` never commits - the calling service commits once for the whole
operation and then calls ``emit_pending_events()`` so domain events leave only
after the commit, exactly like the other services' ``pending`` lists.

``stock_state`` is the only definition of low stock in ASME Ops.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Iterable

from sqlalchemy import case, event as sa_event, func, select
from sqlalchemy.orm import Session

from asme import events
from asme.extensions import db
from asme.ops.models import (
    InventoryBalance,
    InventoryTransaction,
    Membership,
    Part,
    Permission,
    PurchaseRequest,
    PurchaseRequestItem,
    Role,
    RolePermission,
    Team,
    TeamMember,
)
from asme.ops.models.inventory import INVENTORY_TRANSACTION_TYPES, PURCHASE_REQUEST_ORDERED_STATUSES
from asme.ops.services import notifications
from asme.ops.types import parse_uuid, utcnow
from asme.services.errors import Conflict, NotFound, Validation

ZERO = Decimal("0")
QUANTITY_PLACES = Decimal("0.001")
UNIT_COST_PLACES = Decimal("0.0001")
QUANTITY_MAX = Decimal("99999999999.999")  # Numeric(14, 3)
UNIT_COST_MAX = Decimal("99999999.9999")  # Numeric(12, 4)

LOW_STOCK_NOTIFICATION = "inventory.low_stock"
ALERT_STATES = ("low", "out")
INVENTORY_MANAGE = "inventory.manage"
INSUFFICIENT_STOCK = "insufficient_stock"

_PENDING_EVENTS_KEY = "ops_inventory_pending_events"


# --------------------------------------------------------------------------- numbers


def _decimal(value, *, what: str) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        # Floats are refused so stock is never computed with binary arithmetic.
        raise TypeError(f"{what} must be a Decimal, int or numeric string, not {type(value).__name__}")
    if isinstance(value, Decimal):
        number = value
    else:
        try:
            number = Decimal(str(value))
        except (InvalidOperation, ValueError):
            raise ValueError(f"{what} is not a number: {value!r}")
    if not number.is_finite():
        raise ValueError(f"{what} must be finite")
    return number


def to_quantity(value) -> Decimal:
    """Exact quantity rounded half-up to the column's 3 decimal places."""
    return _decimal(value, what="quantity").quantize(QUANTITY_PLACES, rounding=ROUND_HALF_UP)


def to_unit_cost(value) -> Decimal:
    """Exact unit cost rounded half-up to the column's 4 decimal places."""
    return _decimal(value, what="unit cost").quantize(UNIT_COST_PLACES, rounding=ROUND_HALF_UP)


def _stored(value) -> Decimal:
    """A value read back from the database (SQLite may hand back floats)."""
    if value is None:
        return ZERO
    if isinstance(value, float):
        value = Decimal(repr(value))
    return Decimal(value).quantize(QUANTITY_PLACES, rounding=ROUND_HALF_UP)


def quantity_check(value) -> str | None:
    """``Field("decimal", check=quantity_check)`` - at most 3 decimal places and
    within ``Numeric(14, 3)``."""
    if not isinstance(value, Decimal) or not value.is_finite():
        return "Must be a number."
    if value != value.quantize(QUANTITY_PLACES, rounding=ROUND_HALF_UP):
        return "Use at most 3 decimal places."
    if abs(value) > QUANTITY_MAX:
        return f"Must be at most {QUANTITY_MAX}."
    return None


def unit_cost_check(value) -> str | None:
    """``Field("decimal", check=unit_cost_check)`` - at most 4 decimal places and
    within ``Numeric(12, 4)``."""
    if not isinstance(value, Decimal) or not value.is_finite():
        return "Must be a number."
    if value != value.quantize(UNIT_COST_PLACES, rounding=ROUND_HALF_UP):
        return "Use at most 4 decimal places."
    if abs(value) > UNIT_COST_MAX:
        return f"Must be at most {UNIT_COST_MAX}."
    return None


def quantity_number(value) -> float | None:
    """Quantity as a JSON number (3 decimal places)."""
    if value is None:
        return None
    return float(_stored(value))


def unit_cost_number(value) -> float | None:
    """Unit cost as a JSON number rounded to 4 places."""
    if value is None:
        return None
    if isinstance(value, float):
        value = Decimal(repr(value))
    return float(Decimal(value).quantize(UNIT_COST_PLACES, rounding=ROUND_HALF_UP))


def _plain(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    return text


# --------------------------------------------------------------------------- post


def _same_org(ctx, obj) -> None:
    if obj is not None and getattr(obj, "organization_id", ctx.org.id) != ctx.org.id:
        raise NotFound()


def _select_balance(part_id, location_id) -> InventoryBalance | None:
    stmt = (
        select(InventoryBalance)
        .where(InventoryBalance.part_id == part_id, InventoryBalance.location_id == location_id)
        .with_for_update()
    )
    return db.session.execute(stmt).scalar_one_or_none()


def post(
    ctx,
    *,
    part: Part,
    location,
    transaction_type: str,
    on_hand_delta,
    reserved_delta=0,
    quantity,
    unit_cost=None,
    counted_quantity=None,
    work_order=None,
    work_order_part=None,
    purchase_request=None,
    purchase_request_item=None,
    reference: InventoryTransaction | None = None,
    note: str | None = None,
    notify: bool = True,
) -> InventoryTransaction:
    """Apply one ledger movement at ``location`` and return the new transaction.

    Raises ``Conflict(code="insufficient_stock")`` (nothing written) when the
    result would leave ``on_hand < 0``, ``reserved < 0`` or ``reserved > on_hand``.
    Does not commit. Receipts with ``unit_cost`` re-weight ``part.unit_cost``.

    ``notify=False`` skips the low-stock evaluation for this row: stock alerts
    are chapter-wide, so an operation written as several posts (a transfer's two
    legs) must be judged once, around the whole operation, not per row - the leg
    that leaves a shelf empty is not a stock-out.
    """
    if transaction_type not in INVENTORY_TRANSACTION_TYPES:
        raise ValueError(f"unknown inventory transaction type {transaction_type!r}")
    if part is None or location is None:
        raise NotFound()
    for obj in (part, location, work_order, work_order_part, purchase_request, reference):
        _same_org(ctx, obj)
    if purchase_request_item is not None:
        _same_org(ctx, purchase_request_item.purchase_request)

    on_hand_delta = to_quantity(on_hand_delta)
    reserved_delta = to_quantity(reserved_delta)
    quantity = to_quantity(quantity)
    if quantity < 0 or (quantity == 0 and transaction_type != "cycle_count"):
        raise ValueError("quantity must be greater than zero")
    if counted_quantity is not None:
        counted_quantity = to_quantity(counted_quantity)
        if counted_quantity < 0:
            raise ValueError("counted quantity cannot be negative")
    if unit_cost is not None:
        unit_cost = to_unit_cost(unit_cost)
        if unit_cost < 0:
            raise ValueError("unit cost cannot be negative")

    # Serialise ledger writes per part (no-op on SQLite, which serialises writers):
    # the chapter-wide totals, the state transition and the weighted cost all
    # read other locations' balances.
    db.session.execute(select(Part.id).where(Part.id == part.id).with_for_update())
    before_totals = part_totals([part.id])[part.id]
    before_state = stock_state(before_totals, part) if notify else None

    balance = _select_balance(part.id, location.id)
    current_on_hand = _stored(balance.on_hand) if balance is not None else ZERO
    current_reserved = _stored(balance.reserved) if balance is not None else ZERO
    new_on_hand = current_on_hand + on_hand_delta
    new_reserved = current_reserved + reserved_delta
    if new_on_hand < 0 or new_reserved < 0 or new_reserved > new_on_hand:
        raise Conflict(
            f"Not enough {part.name} at this location.",
            code=INSUFFICIENT_STOCK,
            part_id=str(part.id),
            location_id=str(location.id),
            on_hand=float(current_on_hand),
            reserved=float(current_reserved),
            requested=float(quantity),
        )
    if new_on_hand > QUANTITY_MAX or new_reserved > QUANTITY_MAX:
        raise Validation(f"Quantity must be at most {QUANTITY_MAX}.", field="quantity")

    if transaction_type == "receipt" and unit_cost is not None and on_hand_delta > 0:
        old_total = before_totals["on_hand"]
        new_total = old_total + on_hand_delta
        if part.unit_cost is None or old_total <= 0:
            part.unit_cost = unit_cost
        else:
            old_cost = Decimal(repr(part.unit_cost)) if isinstance(part.unit_cost, float) else Decimal(part.unit_cost)
            weighted = ((old_total * old_cost) + (on_hand_delta * unit_cost)) / new_total
            part.unit_cost = weighted.quantize(UNIT_COST_PLACES, rounding=ROUND_HALF_UP)

    if balance is None:
        balance = InventoryBalance(organization_id=ctx.org.id, part_id=part.id, location_id=location.id)
        db.session.add(balance)
    balance.on_hand = new_on_hand
    balance.reserved = new_reserved
    balance.updated_at = utcnow()

    transaction = InventoryTransaction(
        organization_id=ctx.org.id,
        part_id=part.id,
        location_id=location.id,
        transaction_type=transaction_type,
        on_hand_delta=on_hand_delta,
        reserved_delta=reserved_delta,
        quantity=quantity,
        counted_quantity=counted_quantity,
        on_hand_after=new_on_hand,
        reserved_after=new_reserved,
        unit_cost=unit_cost,
        work_order_id=getattr(work_order, "id", None),
        work_order_part_id=getattr(work_order_part, "id", None),
        purchase_request_id=getattr(purchase_request, "id", None),
        purchase_request_item_id=getattr(purchase_request_item, "id", None),
        reference_transaction_id=getattr(reference, "id", None),
        note=note,
        created_by_user_id=getattr(ctx, "user_id", None),
        created_at=utcnow(),
    )
    db.session.add(transaction)
    db.session.flush()

    if notify:
        after_totals = part_totals([part.id])[part.id]
        stock_state_changed(ctx, part, before_state, stock_state(after_totals, part), totals=after_totals)
    return transaction


# --------------------------------------------------------------------------- totals and state


def _empty_totals() -> dict:
    return {"on_hand": ZERO, "reserved": ZERO, "available": ZERO, "ordered": ZERO, "has_transactions": False}


def part_totals(part_ids: Iterable) -> dict:
    """``{part_id: {"on_hand", "reserved", "available", "ordered", "has_transactions"}}``
    for every id given (unknown ids get zeros). Quantities are ``Decimal``.
    ``ordered`` is what is still outstanding on purchase requests that are
    ``ordered`` or ``partially_received``. Three grouped queries regardless of
    how many parts are asked for."""
    ids = []
    for raw in part_ids or ():
        parsed = parse_uuid(raw)
        if parsed is not None and parsed not in ids:
            ids.append(parsed)
    result = {pid: _empty_totals() for pid in ids}
    if not ids:
        return result

    balance_rows = db.session.execute(
        select(InventoryBalance.part_id, func.sum(InventoryBalance.on_hand), func.sum(InventoryBalance.reserved))
        .where(InventoryBalance.part_id.in_(ids))
        .group_by(InventoryBalance.part_id)
    )
    for part_id, on_hand, reserved in balance_rows:
        totals = result[part_id]
        totals["on_hand"] = _stored(on_hand)
        totals["reserved"] = _stored(reserved)

    transaction_rows = db.session.execute(
        select(InventoryTransaction.part_id, func.count(InventoryTransaction.id))
        .where(InventoryTransaction.part_id.in_(ids))
        .group_by(InventoryTransaction.part_id)
    )
    for part_id, count in transaction_rows:
        result[part_id]["has_transactions"] = bool(count)

    outstanding = case(
        (PurchaseRequestItem.quantity > PurchaseRequestItem.received_quantity, PurchaseRequestItem.quantity - PurchaseRequestItem.received_quantity),
        else_=0,
    )
    ordered_rows = db.session.execute(
        select(PurchaseRequestItem.part_id, func.sum(outstanding))
        .join(PurchaseRequest, PurchaseRequest.id == PurchaseRequestItem.purchase_request_id)
        .where(PurchaseRequestItem.part_id.in_(ids), PurchaseRequest.status.in_(PURCHASE_REQUEST_ORDERED_STATUSES))
        .group_by(PurchaseRequestItem.part_id)
    )
    for part_id, ordered in ordered_rows:
        result[part_id]["ordered"] = _stored(ordered)

    for totals in result.values():
        totals["available"] = totals["on_hand"] - totals["reserved"]
    return result


def stock_state(totals: dict, part: Part) -> str:
    """``"ok" | "low" | "out" | "untracked"`` - the only low-stock rule.

    * ``untracked``: no ``minimum_stock``, nothing on hand and no transactions ever;
    * ``out``: available <= 0;
    * ``low``: ``minimum_stock`` set and available below it;
    * ``ok`` otherwise.

    ``totals`` is one entry of ``part_totals``.
    """
    on_hand = _stored(totals.get("on_hand"))
    available = _stored(totals.get("available", on_hand - _stored(totals.get("reserved"))))
    if part.minimum_stock is None and on_hand == 0 and not totals.get("has_transactions", True):
        return "untracked"
    if available <= 0:
        return "out"
    if part.minimum_stock is not None and available < _stored(part.minimum_stock):
        return "low"
    return "ok"


# --------------------------------------------------------------------------- notifications


def active_member_ids_with_permission(org_id, key: str) -> set[int]:
    """User ids of active members of ``org_id`` whose role grants ``key`` (any scope)."""
    stmt = (
        select(Membership.user_id)
        .join(Role, Role.id == Membership.role_id)
        .join(RolePermission, RolePermission.role_id == Role.id)
        .join(Permission, Permission.id == RolePermission.permission_id)
        .where(
            Membership.organization_id == org_id,
            Membership.member_status == "active",
            Role.organization_id == org_id,
            Permission.key == key,
        )
        .distinct()
    )
    return {row[0] for row in db.session.execute(stmt)}


def critical_parts_team_lead_ids(org) -> set[int]:
    """Active-member leads of ``settings_json.purchasing.critical_parts_team_id``."""
    settings = org.settings_json if isinstance(org.settings_json, dict) else {}
    purchasing = settings.get("purchasing") if isinstance(settings.get("purchasing"), dict) else {}
    team_id = parse_uuid(purchasing.get("critical_parts_team_id"))
    if team_id is None:
        return set()
    stmt = (
        select(TeamMember.user_id)
        .join(Team, Team.id == TeamMember.team_id)
        .join(Membership, (Membership.user_id == TeamMember.user_id) & (Membership.organization_id == org.id))
        .where(Team.id == team_id, Team.organization_id == org.id, TeamMember.is_lead.is_(True), Membership.member_status == "active")
    )
    return {row[0] for row in db.session.execute(stmt)}


def _is_alert_transition(before: str | None, after: str) -> bool:
    if after not in ALERT_STATES or before == after:
        return False
    # Restocking from out to low is an improvement, not a new alert.
    return not (before == "out" and after == "low")


def stock_state_changed(ctx, part: Part, before: str | None, after: str, *, totals: dict | None = None) -> list:
    """Notify when ``part`` moves into ``low`` or ``out`` (``ok``/``untracked`` ->
    ``low``/``out``, or ``low`` -> ``out``). Recipients: every active member whose
    role grants ``inventory.manage``, plus the critical-parts team leads when the
    part is critical. One notification per user, part and UTC day. Returns the
    notification rows created and queues ``ops.inventory.low_stock``."""
    if not _is_alert_transition(before, after):
        return []
    recipients = active_member_ids_with_permission(ctx.org.id, INVENTORY_MANAGE)
    if part.is_critical:
        recipients |= critical_parts_team_lead_ids(ctx.org)
    totals = totals if totals is not None else part_totals([part.id])[part.id]
    available = _stored(totals.get("available"))
    unit = part.unit or "each"
    if after == "out":
        title = f"{part.name} is out of stock"
    else:
        title = f"{part.name} is low on stock"
    body = f"Available: {_plain(available)} {unit}."
    if part.minimum_stock is not None:
        body += f" Minimum: {_plain(_stored(part.minimum_stock))} {unit}."
    rows = notifications.notify(
        ctx,
        sorted(recipients),
        LOW_STOCK_NOTIFICATION,
        title,
        body,
        entity=part,
        dedupe_key=f"low_stock:{part.id}:{utcnow().date().isoformat()}",
        exclude_actor=False,
    )
    _queue_event(
        events.INVENTORY_LOW_STOCK,
        organization_id=str(ctx.org.id),
        part_id=str(part.id),
        state=after,
        previous=before,
        available=float(available),
    )
    return rows


# --------------------------------------------------------------------------- events after commit


def _queue_event(name: str, **payload) -> None:
    db.session.info.setdefault(_PENDING_EVENTS_KEY, []).append((name, payload))


def pending_events() -> list[tuple[str, dict]]:
    """Events queued by ledger posts in the current session (not yet emitted)."""
    return list(db.session.info.get(_PENDING_EVENTS_KEY, ()))


def emit_pending_events() -> int:
    """Emit and clear queued ledger events. Call right after ``db.session.commit()``."""
    queued = db.session.info.pop(_PENDING_EVENTS_KEY, None) or []
    for name, payload in queued:
        events.emit(name, **payload)
    return len(queued)


@sa_event.listens_for(Session, "after_soft_rollback")
def _discard_events_on_rollback(session, previous_transaction):
    # A rolled-back root transaction never happened, so neither did its events.
    if previous_transaction.parent is None and not previous_transaction.nested:
        session.info.pop(_PENDING_EVENTS_KEY, None)


# --------------------------------------------------------------------------- reconcile


def reconcile(org_id) -> list[dict]:
    """Recompute every balance of ``org_id`` from its transactions and return
    the rows that disagree. Reports only; never corrects anything."""
    org_id = parse_uuid(org_id)
    if org_id is None:
        return []
    ledger: dict[tuple, tuple[Decimal, Decimal]] = {}
    rows = db.session.execute(
        select(
            InventoryTransaction.part_id,
            InventoryTransaction.location_id,
            func.sum(InventoryTransaction.on_hand_delta),
            func.sum(InventoryTransaction.reserved_delta),
        )
        .where(InventoryTransaction.organization_id == org_id)
        .group_by(InventoryTransaction.part_id, InventoryTransaction.location_id)
    )
    for part_id, location_id, on_hand, reserved in rows:
        ledger[(part_id, location_id)] = (_stored(on_hand), _stored(reserved))

    balances: dict[tuple, tuple[Decimal, Decimal]] = {}
    for balance in db.session.execute(select(InventoryBalance).where(InventoryBalance.organization_id == org_id)).scalars():
        balances[(balance.part_id, balance.location_id)] = (_stored(balance.on_hand), _stored(balance.reserved))

    mismatches: list[dict] = []
    for key in sorted(set(ledger) | set(balances), key=lambda pair: (str(pair[0]), str(pair[1]))):
        ledger_values = ledger.get(key, (ZERO, ZERO))
        balance_values = balances.get(key)
        if balance_values is not None and balance_values == ledger_values:
            continue
        mismatches.append(
            {
                "organization_id": str(org_id),
                "part_id": str(key[0]),
                "location_id": str(key[1]),
                "balance_on_hand": str(balance_values[0]) if balance_values is not None else None,
                "ledger_on_hand": str(ledger_values[0]),
                "balance_reserved": str(balance_values[1]) if balance_values is not None else None,
                "ledger_reserved": str(ledger_values[1]),
            }
        )
    return mismatches
