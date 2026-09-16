"""A location that still holds stock must not be deletable.

``locations.delete`` only refuses while assets, work orders or child locations
point at the row; Stage 4 added ``ops_inventory_balances.location_id`` and
``ops_inventory_transactions.location_id`` without extending that guard. Deleting
such a location leaves balance and ledger rows pointing at a location that no
longer exists - the part still counts as in stock, ``part_detail.balances``
serializes a null location, and on PostgreSQL the delete is a foreign-key error
rather than a 409.
"""

from __future__ import annotations

from decimal import Decimal

from asme.extensions import db as _db
from asme.ops.models import InventoryBalance, InventoryTransaction, Location, Part
from asme.ops.services import inventory_ledger as ledger, locations
from asme.services.errors import Conflict

D = Decimal


def test_a_location_holding_stock_cannot_be_deleted(app, org, users, ctx_admin):
    shelf = Location(organization_id=org.id, name="Shelf A")
    _db.session.add(shelf)
    part = Part(organization_id=org.id, name="M5 bolt", unit="each")
    _db.session.add(part)
    _db.session.commit()
    shelf_id = shelf.id

    ledger.post(ctx_admin, part=part, location=shelf, transaction_type="receipt", on_hand_delta=D("5"), quantity=D("5"))
    _db.session.commit()
    ledger.emit_pending_events()

    try:
        locations.delete(ctx_admin, shelf)
    except Conflict:
        pass
    _db.session.expire_all()

    assert Location.query.filter_by(id=shelf_id).first() is not None, "a location holding stock must not be deleted"
    balance = InventoryBalance.query.filter_by(part_id=part.id).one()
    assert balance.location is not None, "the balance is orphaned: it points at a location that no longer exists"
    transaction = InventoryTransaction.query.filter_by(part_id=part.id).one()
    assert transaction.location is not None, "the ledger row is orphaned"
