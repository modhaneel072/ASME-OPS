"""Returning parts issued at two different unit costs must not credit the work
order more than it was charged.

``work_order_parts.return_parts`` prices the whole return at the unit cost of
the *latest* issue. When stock was issued at one cost, a receipt re-weighted the
part's unit cost, and the rest was issued at the new cost, returning everything
credits ``returned x latest cost`` instead of what was actually charged, leaving
the work order with a negative parts cost even though nothing was consumed.
"""

from __future__ import annotations

from decimal import Decimal

from asme.extensions import db as _db
from asme.ops.models import CostEntry, Location, Part, WorkOrder, WorkOrderPart
from asme.ops.services import inventory_ledger as ledger
from asme.ops.services import work_order_parts

D = Decimal


def _location(org, name="Shelf A"):
    row = Location(organization_id=org.id, name=name)
    _db.session.add(row)
    _db.session.commit()
    return row


def _part(org, **kw):
    kw.setdefault("name", "Bearing 608")
    kw.setdefault("unit", "each")
    row = Part(organization_id=org.id, **kw)
    _db.session.add(row)
    _db.session.commit()
    return row


def _work_order(org, creator):
    row = WorkOrder(organization_id=org.id, number=901, title="Rebuild gearbox", status="open", created_by_user_id=creator.id)
    _db.session.add(row)
    _db.session.commit()
    return row


def _receive(ctx, part, location, quantity, unit_cost):
    ledger.post(
        ctx,
        part=part,
        location=location,
        transaction_type="receipt",
        on_hand_delta=quantity,
        quantity=quantity,
        unit_cost=unit_cost,
    )
    _db.session.commit()
    ledger.emit_pending_events()


def _parts_cost(work_order) -> Decimal:
    rows = CostEntry.query.filter_by(work_order_id=work_order.id, type="parts").all()
    return sum((Decimal(str(row.amount)) for row in rows), D("0"))


def test_return_credit_never_exceeds_what_the_issues_charged(app, org, users, ctx_admin):
    shelf = _location(org)
    part = _part(org)
    work_order = _work_order(org, users["admin"])

    _receive(ctx_admin, part, shelf, D("10"), D("10.0000"))
    line = WorkOrderPart(
        organization_id=org.id,
        work_order_id=work_order.id,
        part_id=part.id,
        location_id=shelf.id,
        quantity_planned=D("8"),
        quantity_reserved=D("0"),
        quantity_issued=D("0"),
        quantity_returned=D("0"),
        readiness="assigned",
        created_by_user_id=users["admin"].id,
    )
    _db.session.add(line)
    _db.session.commit()

    work_order_parts.issue(ctx_admin, work_order, line, {"quantity": 5})
    charged_first = _parts_cost(work_order)
    assert charged_first == D("50.00")

    # A dearer receipt re-weights the part: (5 * 10 + 5 * 30) / 10 = 20.
    _receive(ctx_admin, part, shelf, D("5"), D("30.0000"))
    assert ledger.to_unit_cost(part.unit_cost) == D("20.0000")

    work_order_parts.issue(ctx_admin, work_order, line, {"quantity": 3})
    charged = _parts_cost(work_order)
    assert charged == D("110.00")

    work_order_parts.return_parts(ctx_admin, work_order, line, {"quantity": 8})

    # Everything that was issued came back, so the work order must be charged
    # nothing for parts - and can never be credited more than it was charged.
    assert _parts_cost(work_order) == D("0.00")
