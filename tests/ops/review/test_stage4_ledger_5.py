"""A work order cannot be credited for parts it never took out of stock.

``POST /parts/:id/transactions`` with ``{"type": "return", "work_order_id": ...}``
goes through ``inventory.record_transaction``, which posts the ledger row and
then calls ``_parts_cost_entry(credit=True)`` without checking that the work
order ever issued this part and without referencing an issue. Anyone who may log
time on the work order can therefore hand it an arbitrary negative ``parts`` cost
entry, pushing the work order's parts cost - and the project's
``budget.used`` - below zero.
"""

from __future__ import annotations

from decimal import Decimal

from asme.extensions import db as _db
from asme.ops.models import CostEntry, Location, Part, WorkOrder
from asme.ops.services import inventory
from asme.services.errors import ServiceError

D = Decimal


def _parts_cost(work_order) -> Decimal:
    rows = CostEntry.query.filter_by(work_order_id=work_order.id, type="parts").all()
    return sum((Decimal(str(row.amount)) for row in rows), D("0"))


def test_returning_to_a_work_order_that_issued_nothing_credits_nothing(app, org, users, ctx_admin):
    shelf = Location(organization_id=org.id, name="Shelf A")
    _db.session.add(shelf)
    part = Part(organization_id=org.id, name="M5 bolt", unit="each", unit_cost=D("12.5000"))
    _db.session.add(part)
    work_order = WorkOrder(
        organization_id=org.id,
        number=902,
        title="Nothing was ever issued here",
        status="open",
        created_by_user_id=users["admin"].id,
    )
    _db.session.add(work_order)
    _db.session.commit()

    try:
        inventory.record_transaction(
            ctx_admin,
            part,
            {"type": "return", "location_id": str(shelf.id), "quantity": 40, "work_order_id": str(work_order.id)},
        )
    except ServiceError:
        pass  # refusing the return is a correct outcome too
    _db.session.expire_all()

    assert _parts_cost(work_order) >= D("0.00"), "a work order was credited for parts it never issued"
