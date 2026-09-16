"""``/api/v1/parts/:id/transactions`` and ``/api/v1/inventory/*``: every movement
of stock, the transfer pair, cycle counts, the low-stock list and the
chapter-wide ledger."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import pytest

from asme.extensions import db as _db
from asme.ops.models import (
    CostEntry,
    InventoryBalance,
    InventoryTransaction,
    Location,
    OpsProject,
    Organization,
    Part,
    PartVendor,
    Vendor,
    WorkOrder,
    WorkOrderAssignee,
)
from asme.ops.services import inventory as inventory_service
from asme.services.errors import Forbidden
from tests.ops.conftest import make_user

D = Decimal

PLAN_TRANSACTION_KEYS = {
    "id",
    "type",
    "part",
    "location",
    "quantity",
    "on_hand_delta",
    "reserved_delta",
    "on_hand_after",
    "reserved_after",
    "counted_quantity",
    "unit_cost",
    "work_order",
    "purchase_request",
    "reference_transaction_id",
    "note",
    "created_by",
    "created_at",
}


# --------------------------------------------------------------------------- inline helpers


def _location(org, name, **kw):
    row = Location(organization_id=org.id, name=name, **kw)
    _db.session.add(row)
    _db.session.commit()
    return row


def _part(org, name, **kw):
    row = Part(organization_id=org.id, name=name, **kw)
    _db.session.add(row)
    _db.session.commit()
    return row


def _work_order(org, number, **kw):
    row = WorkOrder(organization_id=org.id, number=number, title=f"WO {number}", status="in_progress", **kw)
    _db.session.add(row)
    _db.session.commit()
    return row


def _assign(work_order, user):
    _db.session.add(WorkOrderAssignee(work_order_id=work_order.id, user_id=user.id))
    _db.session.commit()


def _foreign_org():
    other = Organization(name="Other Chapter", slug="other-chapter")
    _db.session.add(other)
    _db.session.flush()
    return other


def _post(client, part, **body):
    return client.post(f"/api/v1/parts/{part.id}/transactions", json=body)


def _receive(client, part, location, quantity, unit_cost=None):
    body = {"type": "receipt", "location_id": str(location.id), "quantity": quantity}
    if unit_cost is not None:
        body["unit_cost"] = unit_cost
    response = client.post(f"/api/v1/parts/{part.id}/transactions", json=body)
    assert response.status_code == 201, response.get_json()
    return response.get_json()["payload"]


def _balance(part, location):
    return InventoryBalance.query.filter_by(part_id=part.id, location_id=location.id).first()


def _today():
    return datetime.now(timezone.utc).date()


# --------------------------------------------------------------------------- movements


def test_receipt_issue_return_adjustment_and_scrap_move_stock(client, org, users, api_login):
    api_login(users["admin"])
    shelf = _location(org, "Shelf 1")
    part = _part(org, "Bearing 608", unit="each", minimum_stock=D("5"))

    received = _receive(client, part, shelf, 20, unit_cost=2.5)
    transaction = received["transaction"]
    assert set(transaction) == PLAN_TRANSACTION_KEYS
    assert transaction["type"] == "receipt" and transaction["quantity"] == 20.0
    assert transaction["on_hand_delta"] == 20.0 and transaction["on_hand_after"] == 20.0 and transaction["reserved_after"] == 0.0
    assert transaction["unit_cost"] == 2.5 and transaction["counted_quantity"] is None
    assert transaction["part"] == {"id": str(part.id), "name": "Bearing 608", "sku": None, "unit": "each"}
    assert transaction["location"] == {"id": str(shelf.id), "name": "Shelf 1"}
    assert transaction["work_order"] is None and transaction["purchase_request"] is None
    assert transaction["created_by"]["id"] == users["admin"].id and transaction["created_at"].endswith("Z")
    assert received["part"]["totals"] == {"on_hand": 20.0, "reserved": 0.0, "available": 20.0, "ordered": 0.0}
    assert received["part"]["stock_state"] == "ok" and received["part"]["unit_cost"] == 2.5

    issued = _post(client, part, type="issue", location_id=str(shelf.id), quantity=3)
    assert issued.status_code == 201, issued.get_json()
    assert issued.get_json()["payload"]["transaction"]["on_hand_after"] == 17.0
    assert issued.get_json()["payload"]["part"]["totals"]["available"] == 17.0

    returned = _post(client, part, type="return", location_id=str(shelf.id), quantity=1)
    assert returned.status_code == 201 and returned.get_json()["payload"]["transaction"]["on_hand_after"] == 18.0

    adjusted = _post(client, part, type="adjustment", location_id=str(shelf.id), quantity=2, direction="decrease", note="Found broken")
    assert adjusted.status_code == 201
    assert adjusted.get_json()["payload"]["transaction"]["on_hand_after"] == 16.0
    assert adjusted.get_json()["payload"]["transaction"]["note"] == "Found broken"

    scrapped = _post(client, part, type="scrap", location_id=str(shelf.id), quantity=6, note="Corroded")
    assert scrapped.status_code == 201 and scrapped.get_json()["payload"]["transaction"]["on_hand_after"] == 10.0

    assert _balance(part, shelf).on_hand == D("10.000")
    listed = client.get(f"/api/v1/parts/{part.id}/transactions").get_json()["payload"]
    assert [row["type"] for row in listed["items"]] == ["scrap", "adjustment", "return", "issue", "receipt"]
    assert listed["total"] == 5

    filtered = client.get(f"/api/v1/parts/{part.id}/transactions?filter[type]=receipt,scrap").get_json()["payload"]
    assert [row["type"] for row in filtered["items"]] == ["scrap", "receipt"]


def test_receipt_reweights_unit_cost(client, org, users, api_login):
    api_login(users["admin"])
    shelf = _location(org, "Shelf 1")
    part = _part(org, "Filament")
    _receive(client, part, shelf, 10, unit_cost=20)
    body = _receive(client, part, shelf, 10, unit_cost=30)
    assert body["part"]["unit_cost"] == 25.0


def test_issue_beyond_available_is_409_and_writes_nothing(client, org, users, api_login):
    api_login(users["admin"])
    shelf = _location(org, "Shelf 1")
    part = _part(org, "Servo")
    _receive(client, part, shelf, 2)

    denied = _post(client, part, type="issue", location_id=str(shelf.id), quantity=5)
    assert denied.status_code == 409
    body = denied.get_json()
    assert body["code"] == "insufficient_stock"
    assert body["part_id"] == str(part.id) and body["location_id"] == str(shelf.id)
    assert body["on_hand"] == 2.0 and body["reserved"] == 0.0 and body["requested"] == 5.0

    assert _balance(part, shelf).on_hand == D("2.000")
    assert InventoryTransaction.query.filter_by(part_id=part.id).count() == 1


def test_transaction_validation_lists_every_bad_field(client, org, users, api_login):
    api_login(users["admin"])
    shelf = _location(org, "Shelf 1")
    part = _part(org, "Wire")

    missing = _post(client, part)
    assert missing.status_code == 400 and set(missing.get_json()["errors"]) == {"type", "quantity"}

    bad = _post(client, part, type="teleport", quantity=0, location_id="not-a-uuid")
    assert bad.status_code == 400 and set(bad.get_json()["errors"]) == {"type", "quantity", "location_id"}

    adjustment = _post(client, part, type="adjustment", location_id=str(shelf.id), quantity=1)
    assert adjustment.status_code == 400 and set(adjustment.get_json()["errors"]) == {"direction", "note"}

    scrap = _post(client, part, type="scrap", location_id=str(shelf.id), quantity=1)
    assert scrap.status_code == 400 and set(scrap.get_json()["errors"]) == {"note"}

    stray = _post(client, part, type="receipt", location_id=str(shelf.id), quantity=1, direction="increase")
    assert stray.status_code == 400 and set(stray.get_json()["errors"]) == {"direction"}

    priced = _post(client, part, type="issue", location_id=str(shelf.id), quantity=1, unit_cost=3)
    assert priced.status_code == 400 and set(priced.get_json()["errors"]) == {"unit_cost"}

    linked = _post(client, part, type="receipt", location_id=str(shelf.id), quantity=1, work_order_id=str(shelf.id))
    assert linked.status_code == 400 and set(linked.get_json()["errors"]) == {"work_order_id"}

    unknown_location = _post(client, part, type="receipt", location_id="11111111-1111-1111-1111-111111111111", quantity=1)
    assert unknown_location.status_code == 400 and set(unknown_location.get_json()["errors"]) == {"location_id"}

    too_precise = _post(client, part, type="receipt", location_id=str(shelf.id), quantity=1.23456)
    assert too_precise.status_code == 400 and set(too_precise.get_json()["errors"]) == {"quantity"}


def test_location_defaults_to_the_part_then_the_chapter_default(client, org, users, api_login):
    api_login(users["admin"])
    default = Location.query.filter_by(organization_id=org.id, is_default=True).one()
    bin_a = _location(org, "Bin A")

    anywhere = _part(org, "Zip Ties")
    body = _post(client, anywhere, type="receipt", quantity=4)
    assert body.status_code == 201
    assert body.get_json()["payload"]["transaction"]["location"]["id"] == str(default.id)

    homed = _part(org, "Solder", default_location_id=bin_a.id)
    body = _post(client, homed, type="receipt", quantity=4)
    assert body.get_json()["payload"]["transaction"]["location"]["id"] == str(bin_a.id)


# --------------------------------------------------------------------------- work-order costs


def test_issue_against_a_work_order_writes_a_parts_cost_entry_and_return_credits_it(client, org, users, api_login):
    api_login(users["admin"])
    shelf = _location(org, "Shelf 1")
    part = _part(org, "Bearing 608", unit="each")
    work_order = _work_order(org, 41)
    _receive(client, part, shelf, 10, unit_cost=2.5)

    issued = _post(client, part, type="issue", location_id=str(shelf.id), quantity=4, work_order_id=str(work_order.id))
    assert issued.status_code == 201, issued.get_json()
    transaction = issued.get_json()["payload"]["transaction"]
    assert transaction["work_order"] == {"id": str(work_order.id), "number": 41, "title": "WO 41"}
    assert transaction["unit_cost"] == 2.5

    charge = CostEntry.query.filter_by(work_order_id=work_order.id, inventory_transaction_id=UUID(transaction["id"])).one()
    assert charge.type == "parts" and charge.amount == D("10.00")
    assert charge.description == "4 each Bearing 608"

    returned = _post(client, part, type="return", location_id=str(shelf.id), quantity=1, work_order_id=str(work_order.id))
    assert returned.status_code == 201
    credit = CostEntry.query.filter_by(
        work_order_id=work_order.id, inventory_transaction_id=UUID(returned.get_json()["payload"]["transaction"]["id"])
    ).one()
    assert credit.amount == D("-2.50")

    total = sum(entry.amount for entry in CostEntry.query.filter_by(work_order_id=work_order.id).all())
    assert total == D("7.50")


def test_a_part_without_a_unit_cost_charges_nothing(client, org, users, api_login):
    api_login(users["admin"])
    shelf = _location(org, "Shelf 1")
    part = _part(org, "Scrap Aluminium")
    work_order = _work_order(org, 42)
    _receive(client, part, shelf, 5)
    issued = _post(client, part, type="issue", location_id=str(shelf.id), quantity=1, work_order_id=str(work_order.id))
    assert issued.status_code == 201
    assert CostEntry.query.filter_by(work_order_id=work_order.id).count() == 0


def test_assignees_may_issue_against_their_work_order_but_not_receive(client, org, users, api_login):
    api_login(users["admin"])
    shelf = _location(org, "Shelf 1")
    part = _part(org, "Fuse")
    mine = _work_order(org, 43)
    theirs = _work_order(org, 44)
    _assign(mine, users["member"])
    _receive(client, part, shelf, 10)

    api_login(users["member"])
    # full_member holds work_order.log_time on assigned work only
    ok_issue = _post(client, part, type="issue", location_id=str(shelf.id), quantity=1, work_order_id=str(mine.id))
    assert ok_issue.status_code == 201, ok_issue.get_json()

    other = _post(client, part, type="issue", location_id=str(shelf.id), quantity=1, work_order_id=str(theirs.id))
    assert other.status_code == 403 and other.get_json()["permission"] == "inventory.manage"

    loose = _post(client, part, type="issue", location_id=str(shelf.id), quantity=1)
    assert loose.status_code == 403

    receipt = _post(client, part, type="receipt", location_id=str(shelf.id), quantity=1)
    assert receipt.status_code == 403


def test_inventory_write_endpoints_need_a_permission(client, org, users, requester, api_login):
    api_login(users["admin"])
    shelf = _location(org, "Shelf 1")
    part = _part(org, "Grease")

    api_login(requester)  # neither inventory.read nor work_order.log_time
    denied = _post(client, part, type="receipt", location_id=str(shelf.id), quantity=1)
    assert denied.status_code == 403 and denied.get_json()["permission"] == ["inventory.manage", "work_order.log_time"]
    assert client.get("/api/v1/inventory/transactions").status_code == 403
    assert client.get("/api/v1/inventory/low-stock").status_code == 403

    api_login(users["member"])  # inventory.read only
    assert client.get("/api/v1/inventory/transactions").status_code == 200
    assert client.get("/api/v1/inventory/low-stock").status_code == 200
    assert client.post("/api/v1/inventory/transfers", json={}).status_code == 403
    assert client.post("/api/v1/inventory/cycle-counts", json={}).status_code == 403


# --------------------------------------------------------------------------- transfers


def test_transfer_writes_a_linked_pair(client, org, users, api_login):
    api_login(users["admin"])
    shelf = _location(org, "Shelf 1")
    drawer = _location(org, "Drawer 2")
    part = _part(org, "Hex Key")
    _receive(client, part, shelf, 10)

    moved = client.post(
        "/api/v1/inventory/transfers",
        json={"part_id": str(part.id), "from_location_id": str(shelf.id), "to_location_id": str(drawer.id), "quantity": 4, "note": "Restock"},
    )
    assert moved.status_code == 201, moved.get_json()
    out_row, in_row = moved.get_json()["payload"]["transactions"]
    assert out_row["type"] == "transfer" and out_row["on_hand_delta"] == -4.0 and out_row["on_hand_after"] == 6.0
    assert in_row["type"] == "transfer" and in_row["on_hand_delta"] == 4.0 and in_row["on_hand_after"] == 4.0
    assert in_row["reference_transaction_id"] == out_row["id"] and out_row["reference_transaction_id"] is None
    assert in_row["note"] == "Restock"
    assert moved.get_json()["payload"]["part"]["totals"]["on_hand"] == 10.0

    assert _balance(part, shelf).on_hand == D("6.000") and _balance(part, drawer).on_hand == D("4.000")


def test_transfer_validation_and_shortfall(client, org, users, api_login):
    api_login(users["admin"])
    shelf = _location(org, "Shelf 1")
    drawer = _location(org, "Drawer 2")
    part = _part(org, "Hex Key")
    _receive(client, part, shelf, 1)

    same = client.post(
        "/api/v1/inventory/transfers",
        json={"part_id": str(part.id), "from_location_id": str(shelf.id), "to_location_id": str(shelf.id), "quantity": 1},
    )
    assert same.status_code == 400 and set(same.get_json()["errors"]) == {"to_location_id"}

    missing = client.post("/api/v1/inventory/transfers", json={})
    assert missing.status_code == 400
    assert set(missing.get_json()["errors"]) == {"part_id", "from_location_id", "to_location_id", "quantity"}

    short = client.post(
        "/api/v1/inventory/transfers",
        json={"part_id": str(part.id), "from_location_id": str(shelf.id), "to_location_id": str(drawer.id), "quantity": 9},
    )
    assert short.status_code == 409 and short.get_json()["code"] == "insufficient_stock"
    assert _balance(part, drawer) is None and _balance(part, shelf).on_hand == D("1.000")


# --------------------------------------------------------------------------- cycle counts


def test_cycle_count_records_every_line_and_the_sheet_lists_expected_quantities(client, org, users, api_login):
    api_login(users["admin"])
    shelf = _location(org, "Shelf 1")
    nuts = _part(org, "M4 Nut")
    bolts = _part(org, "M4 Bolt")
    _receive(client, nuts, shelf, 100)
    _receive(client, bolts, shelf, 50)

    sheet = client.get(f"/api/v1/inventory/cycle-counts/sheet?location_id={shelf.id}")
    assert sheet.status_code == 200
    body = sheet.get_json()["payload"]
    assert body["location"] == {"id": str(shelf.id), "name": "Shelf 1"}
    assert body["lines"] == [
        {"part": {"id": str(bolts.id), "name": "M4 Bolt", "sku": None, "unit": "each"}, "expected": 50.0, "reserved": 0.0},
        {"part": {"id": str(nuts.id), "name": "M4 Nut", "sku": None, "unit": "each"}, "expected": 100.0, "reserved": 0.0},
    ]

    counted = client.post(
        "/api/v1/inventory/cycle-counts",
        json={
            "location_id": str(shelf.id),
            "note": "Monthly count",
            "lines": [{"part_id": str(nuts.id), "counted_quantity": 94}, {"part_id": str(bolts.id), "counted_quantity": 50}],
        },
    )
    assert counted.status_code == 201, counted.get_json()
    lines = counted.get_json()["payload"]["lines"]
    assert lines[0]["expected"] == 100.0 and lines[0]["counted"] == 94.0 and lines[0]["delta"] == -6.0
    assert lines[1]["expected"] == 50.0 and lines[1]["counted"] == 50.0 and lines[1]["delta"] == 0.0

    assert _balance(nuts, shelf).on_hand == D("94.000")
    # the agreeing line is still written so the count date is known
    agreeing = InventoryTransaction.query.filter_by(part_id=bolts.id, transaction_type="cycle_count").one()
    assert agreeing.quantity == D("0.000") and agreeing.counted_quantity == D("50.000") and agreeing.note == "Monthly count"


def test_cycle_count_validation(client, org, users, api_login):
    api_login(users["admin"])
    shelf = _location(org, "Shelf 1")
    part = _part(org, "M4 Nut")

    missing = client.post("/api/v1/inventory/cycle-counts", json={})
    assert missing.status_code == 400 and set(missing.get_json()["errors"]) == {"location_id", "lines"}

    empty = client.post("/api/v1/inventory/cycle-counts", json={"location_id": str(shelf.id), "lines": []})
    assert empty.status_code == 400 and set(empty.get_json()["errors"]) == {"lines"}

    bad = client.post(
        "/api/v1/inventory/cycle-counts",
        json={
            "location_id": str(shelf.id),
            "lines": [
                {"counted_quantity": -1},
                {"part_id": str(part.id), "counted_quantity": 1},
                {"part_id": str(part.id), "counted_quantity": 2},
                "nope",
            ],
        },
    )
    assert bad.status_code == 400
    assert set(bad.get_json()["errors"]) == {"lines[0].part_id", "lines[0].counted_quantity", "lines[2].part_id", "lines[3]"}

    no_sheet = client.get("/api/v1/inventory/cycle-counts/sheet")
    assert no_sheet.status_code == 400 and set(no_sheet.get_json()["errors"]) == {"location_id"}


# --------------------------------------------------------------------------- low stock


def test_low_stock_lists_suggested_quantities_and_the_preferred_vendor(client, org, users, api_login):
    api_login(users["admin"])
    shelf = _location(org, "Shelf 1")
    vendor = Vendor(organization_id=org.id, name="DigiKey")
    _db.session.add(vendor)
    _db.session.commit()

    reorder = _part(org, "Servo", minimum_stock=D("10"), reorder_quantity=D("25"))
    to_maximum = _part(org, "Bearing", minimum_stock=D("10"), maximum_stock=D("20"))
    to_minimum = _part(org, "Cell", minimum_stock=D("5"), is_critical=True)
    healthy = _part(org, "Zip Tie", minimum_stock=D("1"))
    _db.session.add(PartVendor(part_id=reorder.id, vendor_id=vendor.id, preferred=True, vendor_part_number="DK-9", last_price=D("4.5000")))
    _db.session.commit()

    _receive(client, reorder, shelf, 4)
    _receive(client, to_maximum, shelf, 3)
    _receive(client, healthy, shelf, 9)

    listed = client.get("/api/v1/inventory/low-stock")
    assert listed.status_code == 200
    items = listed.get_json()["payload"]["items"]
    assert [item["name"] for item in items] == ["Cell", "Bearing", "Servo"]  # critical first, then by name
    by_name = {item["name"]: item for item in items}
    assert by_name["Servo"]["suggested_quantity"] == 25.0  # reorder_quantity wins
    assert by_name["Bearing"]["suggested_quantity"] == 17.0  # maximum - available
    assert by_name["Cell"]["suggested_quantity"] == 5.0  # minimum - available
    assert by_name["Cell"]["stock_state"] == "out" and by_name["Servo"]["stock_state"] == "low"
    assert by_name["Servo"]["preferred_vendor"] == {"id": str(vendor.id), "name": "DigiKey"}
    assert by_name["Servo"]["vendor_part_number"] == "DK-9" and by_name["Servo"]["last_price"] == 4.5
    assert by_name["Bearing"]["preferred_vendor"] is None and by_name["Bearing"]["last_price"] is None


def test_suggested_quantity_is_never_below_one(org, ctx_admin):
    part = _part(org, "Washer", minimum_stock=D("5"), maximum_stock=D("5"))
    assert inventory_service.suggested_quantity(part, {"available": D("5")}) == D("1")
    assert inventory_service.suggested_quantity(part, {"available": D("0")}) == D("5")


# --------------------------------------------------------------------------- chapter ledger


def test_chapter_ledger_filters_and_date_range(client, org, users, api_login):
    api_login(users["admin"])
    shelf = _location(org, "Shelf 1")
    drawer = _location(org, "Drawer 2")
    nuts = _part(org, "M4 Nut")
    bolts = _part(org, "M4 Bolt")
    work_order = _work_order(org, 51)
    _receive(client, nuts, shelf, 10)
    _receive(client, bolts, drawer, 10)
    assert _post(client, nuts, type="issue", location_id=str(shelf.id), quantity=2, work_order_id=str(work_order.id)).status_code == 201

    everything = client.get("/api/v1/inventory/transactions").get_json()["payload"]
    assert [row["type"] for row in everything["items"]] == ["issue", "receipt", "receipt"]
    assert everything["total"] == 3

    by_part = client.get(f"/api/v1/inventory/transactions?filter[part]={bolts.id}").get_json()["payload"]
    assert [row["part"]["name"] for row in by_part["items"]] == ["M4 Bolt"]
    by_location = client.get(f"/api/v1/inventory/transactions?filter[location]={drawer.id}").get_json()["payload"]
    assert by_location["total"] == 1
    by_type = client.get("/api/v1/inventory/transactions?filter[type]=issue").get_json()["payload"]
    assert by_type["total"] == 1
    by_work_order = client.get(f"/api/v1/inventory/transactions?filter[work_order]={work_order.id}").get_json()["payload"]
    assert by_work_order["total"] == 1

    today = _today()
    inside = client.get(f"/api/v1/inventory/transactions?from={today.isoformat()}&to={today.isoformat()}").get_json()["payload"]
    assert inside["total"] == 3
    before = client.get(f"/api/v1/inventory/transactions?to={(today - timedelta(days=1)).isoformat()}").get_json()["payload"]
    assert before["total"] == 0
    after = client.get(f"/api/v1/inventory/transactions?from={(today + timedelta(days=1)).isoformat()}").get_json()["payload"]
    assert after["total"] == 0

    backwards = client.get(f"/api/v1/inventory/transactions?from={today.isoformat()}&to={(today - timedelta(days=2)).isoformat()}")
    assert backwards.status_code == 400 and set(backwards.get_json()["errors"]) == {"to"}
    bad_date = client.get("/api/v1/inventory/transactions?from=yesterday")
    assert bad_date.status_code == 400 and set(bad_date.get_json()["errors"]) == {"from"}
    bad_type = client.get("/api/v1/inventory/transactions?filter[type]=teleport")
    assert bad_type.status_code == 400 and bad_type.get_json()["code"] == "bad_filter"


def test_ledger_hides_work_orders_the_reader_may_not_see(client, org, users, api_login):
    api_login(users["admin"])
    shelf = _location(org, "Shelf 1")
    part = _part(org, "M4 Nut")
    secret = OpsProject(organization_id=org.id, name="Secret Rover", code="SEC", visibility="private")
    _db.session.add(secret)
    _db.session.commit()
    hidden_order = _work_order(org, 52, project_id=secret.id)
    _receive(client, part, shelf, 10)
    assert _post(client, part, type="issue", location_id=str(shelf.id), quantity=1, work_order_id=str(hidden_order.id)).status_code == 201

    mine = client.get("/api/v1/inventory/transactions?filter[type]=issue").get_json()["payload"]
    assert mine["items"][0]["work_order"] == {"id": str(hidden_order.id), "number": 52, "title": "WO 52"}

    manager = make_user("Ines Inventory", "ines@uiowa.edu", ops_role="inventory_manager", org=org)
    api_login(manager)
    theirs = client.get("/api/v1/inventory/transactions?filter[type]=issue").get_json()["payload"]
    assert theirs["total"] == 1 and theirs["items"][0]["work_order"] is None


def test_inventory_cross_organization_ids_are_404_or_rejected(client, org, users, api_login):
    other = _foreign_org()
    foreign_part = Part(organization_id=other.id, name="Foreign Widget")
    foreign_location = Location(organization_id=other.id, name="Foreign Shelf")
    _db.session.add_all([foreign_part, foreign_location])
    _db.session.commit()

    api_login(users["admin"])
    shelf = _location(org, "Shelf 1")
    mine = _part(org, "Mine")

    assert _post(client, foreign_part, type="receipt", location_id=str(shelf.id), quantity=1).status_code == 404
    borrowed = _post(client, mine, type="receipt", location_id=str(foreign_location.id), quantity=1)
    assert borrowed.status_code == 400 and set(borrowed.get_json()["errors"]) == {"location_id"}

    transfer = client.post(
        "/api/v1/inventory/transfers",
        json={"part_id": str(foreign_part.id), "from_location_id": str(shelf.id), "to_location_id": str(shelf.id), "quantity": 1},
    )
    assert transfer.status_code == 404

    counted = client.post(
        "/api/v1/inventory/cycle-counts",
        json={"location_id": str(shelf.id), "lines": [{"part_id": str(foreign_part.id), "counted_quantity": 1}]},
    )
    assert counted.status_code == 400 and set(counted.get_json()["errors"]) == {"lines[0].part_id"}

    sheet = client.get(f"/api/v1/inventory/cycle-counts/sheet?location_id={foreign_location.id}")
    assert sheet.status_code == 400 and set(sheet.get_json()["errors"]) == {"location_id"}

    assert client.get("/api/v1/inventory/transactions").get_json()["payload"]["total"] == 0
    assert InventoryTransaction.query.filter_by(part_id=foreign_part.id).count() == 0


# --------------------------------------------------------------------------- service level


def test_inventory_service_refuses_a_member_without_the_permission(org, ctx_member):
    shelf = _location(org, "Shelf 1")
    part = _part(org, "Grease")
    with pytest.raises(Forbidden):
        inventory_service.record_transaction(ctx_member, part, {"type": "receipt", "location_id": str(shelf.id), "quantity": 1})
    with pytest.raises(Forbidden):
        inventory_service.transfer(ctx_member, {})
    with pytest.raises(Forbidden):
        inventory_service.cycle_count(ctx_member, {})
