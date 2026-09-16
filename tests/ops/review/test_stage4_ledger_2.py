"""Moving stock between two locations must not raise a chapter-wide stock alarm.

``inventory_ledger.post`` evaluates ``stock_state`` per ledger row, so the
outgoing leg of a transfer is judged while the incoming leg has not been written
yet: a part whose whole stock moves from one shelf to another looks "out of
stock" for the duration of one ``post`` call. That queues a false
``inventory.low_stock`` notification, and because the dedupe key is
``low_stock:<part>:<utc date>`` the genuine stock-out later the same day is then
swallowed and nobody is told.
"""

from __future__ import annotations

from decimal import Decimal

from asme.extensions import db as _db
from asme.ops.models import Location, Notification, Part
from asme.ops.services import inventory
from asme.ops.services import inventory_ledger as ledger

D = Decimal
LOW_STOCK = "inventory.low_stock"


def _location(org, name):
    row = Location(organization_id=org.id, name=name)
    _db.session.add(row)
    _db.session.commit()
    return row


def _alerts() -> list[Notification]:
    return Notification.query.filter_by(type=LOW_STOCK).all()


def test_a_transfer_does_not_raise_a_false_stock_alert(app, org, users, ctx_admin):
    shelf_a = _location(org, "Shelf A")
    shelf_b = _location(org, "Shelf B")
    part = Part(organization_id=org.id, name="M5 bolt", unit="each", minimum_stock=D("2"))
    _db.session.add(part)
    _db.session.commit()

    ledger.post(ctx_admin, part=part, location=shelf_a, transaction_type="receipt", on_hand_delta=D("10"), quantity=D("10"))
    _db.session.commit()
    ledger.emit_pending_events()
    assert _alerts() == []

    inventory.transfer(
        ctx_admin,
        {"part_id": str(part.id), "from_location_id": str(shelf_a.id), "to_location_id": str(shelf_b.id), "quantity": 10},
    )

    totals = ledger.part_totals([part.id])[part.id]
    assert ledger.stock_state(totals, part) == "ok", "the transfer did not change what the chapter holds"
    assert _alerts() == [], "a transfer between locations must not notify anyone about low stock"

    # The first genuine stock-out of the day must still reach the managers.
    inventory.record_transaction(ctx_admin, part, {"type": "issue", "location_id": str(shelf_b.id), "quantity": 10})
    titles = [row.title for row in _alerts()]
    assert titles == [f"{part.name} is out of stock"]
