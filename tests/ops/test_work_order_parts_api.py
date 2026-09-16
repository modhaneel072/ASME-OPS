"""Work-order parts: planning, reservation, kitting, issue and return.

The ledger primitive itself is covered by ``test_inventory_ledger``; this file
covers the work-order vertical on top of it - who may do what, the readiness
transitions, the cost entries that issue and return write, and the fact that the
operations report and project budgets follow the stock.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from asme.extensions import db as _db
from asme.ops import policy
from asme.ops.models import (
    AuditEvent,
    CostEntry,
    InventoryBalance,
    InventoryTransaction,
    Location,
    OpsProject,
    Organization,
    Part,
    WorkOrder,
    WorkOrderAssignee,
    WorkOrderPart,
)
from asme.ops.services import inventory_ledger as ledger
from asme.ops.services import work_order_parts, work_orders as work_orders_service
from asme.services.errors import Conflict, Forbidden, NotFound
from tests.ops.conftest import make_user

D = Decimal
_counter = {"n": 0}

LINE_KEYS = {
    "id",
    "part",
    "location",
    "quantity_planned",
    "quantity_reserved",
    "quantity_issued",
    "quantity_returned",
    "readiness",
    "note",
    "created_at",
}


def _next_number() -> int:
    _counter["n"] += 1
    return _counter["n"]


def _location(org, name="Shelf A", **kw):
    row = Location(organization_id=org.id, name=name, **kw)
    _db.session.add(row)
    _db.session.commit()
    return row


def _part(org, name="Bearing 608", **kw):
    row = Part(organization_id=org.id, name=name, **kw)
    _db.session.add(row)
    _db.session.commit()
    return row


def _wo(org, creator, **kw):
    kw.setdefault("title", "Replace wheel hub")
    kw.setdefault("status", "open")
    row = WorkOrder(organization_id=org.id, number=_next_number(), created_by_user_id=creator.id, **kw)
    _db.session.add(row)
    _db.session.commit()
    return row


def _receive(ctx, part, location, quantity, unit_cost=None):
    row = ledger.post(
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
    return row


def _url(wo) -> str:
    return f"/api/v1/work-orders/{wo.id}/parts"


def _balance(part, location):
    return InventoryBalance.query.filter_by(part_id=part.id, location_id=location.id).first()


def _types(line_id) -> list[str]:
    rows = InventoryTransaction.query.filter_by(work_order_part_id=UUID(str(line_id))).all()
    return sorted(row.transaction_type for row in rows)


def _costs(wo) -> list[CostEntry]:
    return CostEntry.query.filter_by(work_order_id=wo.id).order_by(CostEntry.created_at.asc()).all()


def _amounts(wo) -> list[Decimal]:
    return [Decimal(str(row.amount)) for row in _costs(wo)]


# --------------------------------------------------------------------------- happy path


def test_plan_reserve_kit_stage_issue_and_return(client, org, users, ctx_admin, api_login):
    shelf = _location(org, "Shelf A")
    part = _part(org, "Bearing 608", sku="BRG-608", unit="each", unit_cost=D("2.5000"))
    _receive(ctx_admin, part, shelf, D("10"))
    wo = _wo(org, users["admin"])
    api_login(users["admin"])
    url = _url(wo)

    empty = client.get(url)
    assert empty.status_code == 200, empty.get_json()
    assert empty.get_json()["payload"] == {
        "items": [],
        "work_order_parts": [],
        "readiness_summary": "none",
        "parts_outstanding": 0,
    }

    created = client.post(url, json={"part_id": str(part.id), "location_id": str(shelf.id), "quantity_planned": 4, "note": "Front hub"})
    assert created.status_code == 201, created.get_json()
    payload = created.get_json()["payload"]
    line = payload["work_order_part"]
    assert set(line) == LINE_KEYS
    assert line["part"] == {
        "id": str(part.id),
        "name": "Bearing 608",
        "sku": "BRG-608",
        "unit": "each",
        "stock_state": "ok",
        "totals": {"on_hand": 10.0, "reserved": 0.0, "available": 10.0, "ordered": 0.0},
    }
    assert line["location"] == {"id": str(shelf.id), "name": "Shelf A"}
    assert line["quantity_planned"] == 4 and line["note"] == "Front hub"
    assert (line["quantity_reserved"], line["quantity_issued"], line["quantity_returned"]) == (0, 0, 0)
    assert line["readiness"] == "assigned" and payload["readiness_summary"] == "assigned"
    assert payload["items"] == payload["work_order_parts"] == [line]
    assert AuditEvent.query.filter_by(event_type="work_order.part_added", entity_id=str(wo.id)).count() == 1

    line_url = f"{url}/{line['id']}"
    reserved = client.post(f"{line_url}/reserve", json={"quantity": 4})
    assert reserved.status_code == 200, reserved.get_json()
    body = reserved.get_json()["payload"]
    assert body["work_order_part"]["quantity_reserved"] == 4 and body["work_order_part"]["readiness"] == "reserved"
    assert body["work_order_part"]["part"]["totals"] == {"on_hand": 10.0, "reserved": 4.0, "available": 6.0, "ordered": 0.0}
    assert body["readiness_summary"] == "reserved" and body["parts_outstanding"] == 1

    kitted = client.post(f"{line_url}/kit", json={})
    assert kitted.status_code == 200 and kitted.get_json()["payload"]["work_order_part"]["readiness"] == "kitted"
    staged = client.post(f"{line_url}/stage", json={})
    assert staged.status_code == 200 and staged.get_json()["payload"]["work_order_part"]["readiness"] == "staged"
    assert _types(line["id"]) == ["reservation"]  # kit and stage move readiness only

    issued = client.post(f"{line_url}/issue", json={"quantity": 3})
    assert issued.status_code == 200, issued.get_json()
    after_issue = issued.get_json()["payload"]["work_order_part"]
    assert after_issue["quantity_issued"] == 3 and after_issue["quantity_reserved"] == 1
    assert after_issue["readiness"] == "staged"  # 3 of 4: not fully issued yet
    assert _types(line["id"]) == ["issue", "release", "reservation"]  # the reservation is consumed first
    assert ledger._stored(_balance(part, shelf).on_hand) == D("7")
    assert ledger._stored(_balance(part, shelf).reserved) == D("1")
    assert _amounts(wo) == [D("7.50")]
    entry = _costs(wo)[0]
    assert entry.type == "parts" and entry.description == "3 each Bearing 608"
    assert entry.inventory_transaction_id is not None
    assert AuditEvent.query.filter_by(event_type="work_order.part_issued", entity_id=str(wo.id)).count() == 1

    rest = client.post(f"{line_url}/issue", json={"quantity": 1})
    assert rest.status_code == 200
    full = rest.get_json()["payload"]["work_order_part"]
    assert full["quantity_issued"] == 4 and full["quantity_reserved"] == 0 and full["readiness"] == "issued"
    assert rest.get_json()["payload"]["parts_outstanding"] == 0
    assert _amounts(wo) == [D("7.50"), D("2.50")]

    returned = client.post(f"{line_url}/return", json={"quantity": 2})
    assert returned.status_code == 200, returned.get_json()
    after_return = returned.get_json()["payload"]["work_order_part"]
    assert after_return["quantity_returned"] == 2 and after_return["readiness"] == "assigned"
    assert ledger._stored(_balance(part, shelf).on_hand) == D("8")  # 10 received, 4 issued, 2 back
    assert _amounts(wo) == [D("7.50"), D("2.50"), D("-5.00")]
    reversal = _costs(wo)[-1]
    assert reversal.description == "Returned 2 each Bearing 608"
    return_row = InventoryTransaction.query.filter_by(work_order_part_id=UUID(line["id"]), transaction_type="return").one()
    assert return_row.reference is not None and return_row.reference.transaction_type == "issue"
    assert ledger._stored(return_row.reference.quantity) == D("1")  # the latest issue
    assert reversal.inventory_transaction_id == return_row.id


def test_readiness_summary_is_the_least_advanced_line(client, org, users, ctx_admin, api_login):
    shelf = _location(org)
    bearing = _part(org, "Bearing 608")
    bolt = _part(org, "Hex Bolt")
    _receive(ctx_admin, bearing, shelf, D("5"))
    _receive(ctx_admin, bolt, shelf, D("5"))
    wo = _wo(org, users["admin"])
    api_login(users["admin"])
    url = _url(wo)

    first = client.post(url, json={"part_id": str(bearing.id), "location_id": str(shelf.id), "quantity_planned": 1}).get_json()["payload"]
    client.post(f"{url}/{first['work_order_part']['id']}/reserve", json={"quantity": 1})
    second = client.post(url, json={"part_id": str(bolt.id), "location_id": str(shelf.id), "quantity_planned": 2}).get_json()["payload"]
    assert second["readiness_summary"] == "assigned"

    client.post(f"{url}/{second['work_order_part']['id']}/reserve", json={"quantity": 2})
    listed = client.get(url).get_json()["payload"]
    assert listed["readiness_summary"] == "reserved" and len(listed["items"]) == 2
    assert [item["part"]["name"] for item in listed["items"]] == ["Bearing 608", "Hex Bolt"]


# --------------------------------------------------------------------------- reporting


def test_issued_parts_reach_the_operations_report_and_the_project_budget(client, org, users, ctx_admin, api_login):
    project = OpsProject(organization_id=org.id, name="Rover", code="CCR", budget_amount=D("100.00"))
    _db.session.add(project)
    _db.session.commit()
    shelf = _location(org)
    part = _part(org, "Bearing 608", unit_cost=D("2.0000"))
    _receive(ctx_admin, part, shelf, D("10"))
    wo = _wo(org, users["admin"], project_id=project.id)
    api_login(users["admin"])
    url = _url(wo)

    line = client.post(url, json={"part_id": str(part.id), "location_id": str(shelf.id), "quantity_planned": 5}).get_json()["payload"][
        "work_order_part"
    ]
    assert client.post(f"{url}/{line['id']}/issue", json={"quantity": 3}).status_code == 200

    report = client.get("/api/v1/reports/operations").get_json()["payload"]
    assert report["parts_cost"] == 6.0 and report["other_cost"] == 0.0
    health = client.get(f"/api/v1/projects/{project.id}/health").get_json()["payload"]
    assert health["budget"]["amount"] == 100.0 and health["budget"]["used"] == 6.0 and health["budget"]["remaining"] == 94.0

    assert client.post(f"{url}/{line['id']}/return", json={"quantity": 1}).status_code == 200
    report = client.get("/api/v1/reports/operations").get_json()["payload"]
    assert report["parts_cost"] == 4.0
    health = client.get(f"/api/v1/projects/{project.id}/health").get_json()["payload"]
    assert health["budget"]["used"] == 4.0 and health["budget"]["remaining"] == 96.0


def test_parts_cost_entries_cannot_be_deleted_by_hand(client, org, users, ctx_admin, api_login):
    shelf = _location(org)
    part = _part(org, "Bearing 608", unit_cost=D("2.0000"))
    _receive(ctx_admin, part, shelf, D("4"))
    wo = _wo(org, users["admin"])
    api_login(users["admin"])
    url = _url(wo)
    line = client.post(url, json={"part_id": str(part.id), "location_id": str(shelf.id), "quantity_planned": 2}).get_json()["payload"][
        "work_order_part"
    ]
    client.post(f"{url}/{line['id']}/issue", json={"quantity": 2})
    entry = _costs(wo)[0]

    blocked = client.delete(f"/api/v1/work-orders/{wo.id}/cost-entries/{entry.id}")
    assert blocked.status_code == 409
    body = blocked.get_json()
    assert body["code"] == "inventory_linked" and body["cost_entry_id"] == str(entry.id)
    assert _db.session.get(CostEntry, entry.id) is not None

    with pytest.raises(Conflict) as caught:
        work_orders_service.delete_cost_entry(ctx_admin, wo, entry.id)
    assert caught.value.code == "inventory_linked"

    # a hand-written cost entry on the same work order is still removable
    manual = client.post(f"/api/v1/work-orders/{wo.id}/cost-entries", json={"type": "other", "amount": 5, "description": "Shipping"})
    assert manual.status_code == 201
    manual_id = manual.get_json()["payload"]["cost_entry"]["id"]
    assert client.delete(f"/api/v1/work-orders/{wo.id}/cost-entries/{manual_id}").status_code == 200


# --------------------------------------------------------------------------- stock rules


def test_issue_beyond_available_is_a_conflict_and_writes_nothing(client, org, users, ctx_admin, api_login):
    shelf = _location(org)
    part = _part(org, "Bearing 608", unit_cost=D("2.0000"))
    _receive(ctx_admin, part, shelf, D("2"))
    wo = _wo(org, users["admin"])
    api_login(users["admin"])
    url = _url(wo)
    line = client.post(url, json={"part_id": str(part.id), "location_id": str(shelf.id), "quantity_planned": 5}).get_json()["payload"][
        "work_order_part"
    ]
    client.post(f"{url}/{line['id']}/reserve", json={"quantity": 2})

    denied = client.post(f"{url}/{line['id']}/issue", json={"quantity": 3})
    assert denied.status_code == 409
    body = denied.get_json()
    assert body["code"] == "insufficient_stock" and body["part_id"] == str(part.id) and body["requested"] == 3.0

    # the reservation the issue would have consumed is untouched
    assert _types(line["id"]) == ["reservation"]
    assert ledger._stored(_balance(part, shelf).on_hand) == D("2")
    assert ledger._stored(_balance(part, shelf).reserved) == D("2")
    assert _costs(wo) == []
    current = client.get(url).get_json()["payload"]["items"][0]
    assert current["quantity_reserved"] == 2 and current["quantity_issued"] == 0


def test_quantity_rules_on_reserve_release_issue_and_return(client, org, users, ctx_admin, api_login):
    shelf = _location(org)
    part = _part(org, "Bearing 608", unit_cost=D("1.0000"))
    _receive(ctx_admin, part, shelf, D("20"))
    wo = _wo(org, users["admin"])
    api_login(users["admin"])
    url = _url(wo)
    line = client.post(url, json={"part_id": str(part.id), "location_id": str(shelf.id), "quantity_planned": 3}).get_json()["payload"][
        "work_order_part"
    ]
    line_url = f"{url}/{line['id']}"

    too_much = client.post(f"{line_url}/reserve", json={"quantity": 4})
    assert too_much.status_code == 400 and "quantity" in too_much.get_json()["errors"]
    assert client.post(f"{line_url}/reserve", json={"quantity": 3}).status_code == 200
    assert client.post(f"{line_url}/release", json={"quantity": 4}).status_code == 400

    released = client.post(f"{line_url}/release", json={"quantity": 1})
    assert released.status_code == 200
    assert released.get_json()["payload"]["work_order_part"]["quantity_reserved"] == 2
    assert ledger._stored(_balance(part, shelf).reserved) == D("2")

    assert client.post(f"{line_url}/return", json={"quantity": 1}).status_code == 400  # nothing issued yet
    client.post(f"{line_url}/issue", json={"quantity": 2})
    over_return = client.post(f"{line_url}/return", json={"quantity": 3})
    assert over_return.status_code == 400 and "quantity" in over_return.get_json()["errors"]

    # a line without a location cannot move stock
    other = _part(org, "Hex Bolt")
    bare = client.post(url, json={"part_id": str(other.id), "quantity_planned": 1}).get_json()["payload"]["work_order_part"]
    assert bare["location"] is None
    no_location = client.post(f"{url}/{bare['id']}/reserve", json={"quantity": 1})
    assert no_location.status_code == 400 and "location_id" in no_location.get_json()["errors"]


def test_release_all_clears_reservations_and_completion_reports_them(client, org, users, ctx_admin, api_login):
    shelf = _location(org)
    part = _part(org, "Bearing 608")
    _receive(ctx_admin, part, shelf, D("10"))
    wo = _wo(org, users["admin"])
    api_login(users["admin"])
    url = _url(wo)
    line = client.post(url, json={"part_id": str(part.id), "location_id": str(shelf.id), "quantity_planned": 4}).get_json()["payload"][
        "work_order_part"
    ]
    client.post(f"{url}/{line['id']}/reserve", json={"quantity": 4})

    # completing leaves the reservation in place and says how many lines hold one;
    # the count reaches the HTTP response, not only the service result
    completed = client.post(f"/api/v1/work-orders/{wo.id}/complete", json={})
    assert completed.status_code == 200, completed.get_json()
    body = completed.get_json()["payload"]
    assert body["parts_outstanding"] == 1
    assert body["work_order"]["status"] == "done"
    assert work_order_parts.outstanding_count(_db.session.get(WorkOrder, wo.id)) == 1
    assert ledger._stored(_balance(part, shelf).reserved) == D("4")

    cleared = client.post(f"{url}/release-all", json={})
    assert cleared.status_code == 200
    payload = cleared.get_json()["payload"]
    assert payload["parts_outstanding"] == 0 and payload["items"][0]["quantity_reserved"] == 0
    assert payload["items"][0]["readiness"] == "assigned"
    assert ledger._stored(_balance(part, shelf).reserved) == D("0")
    assert work_order_parts.outstanding_count(_db.session.get(WorkOrder, wo.id)) == 0
    # releasing again is a no-op, not an error
    assert client.post(f"{url}/release-all", json={}).status_code == 200


def test_update_and_delete_rules(client, org, users, ctx_admin, api_login):
    shelf = _location(org)
    part = _part(org, "Bearing 608", unit_cost=D("1.0000"))
    _receive(ctx_admin, part, shelf, D("10"))
    wo = _wo(org, users["admin"])
    api_login(users["admin"])
    url = _url(wo)
    line = client.post(url, json={"part_id": str(part.id), "location_id": str(shelf.id), "quantity_planned": 5}).get_json()["payload"][
        "work_order_part"
    ]
    line_url = f"{url}/{line['id']}"

    duplicate = client.post(url, json={"part_id": str(part.id), "location_id": str(shelf.id), "quantity_planned": 1})
    assert duplicate.status_code == 409 and duplicate.get_json()["code"] == "part_already_added"

    updated = client.patch(line_url, json={"quantity_planned": 6, "note": "Two per corner"})
    assert updated.status_code == 200
    assert updated.get_json()["payload"]["work_order_part"]["quantity_planned"] == 6
    assert updated.get_json()["payload"]["work_order_part"]["note"] == "Two per corner"

    client.post(f"{line_url}/reserve", json={"quantity": 2})
    blocked = client.delete(line_url)
    assert blocked.status_code == 409 and blocked.get_json()["code"] == "work_order_part_in_use"

    client.post(f"{line_url}/issue", json={"quantity": 2})
    below = client.patch(line_url, json={"quantity_planned": 1})
    assert below.status_code == 400 and "quantity_planned" in below.get_json()["errors"]

    client.post(f"{line_url}/return", json={"quantity": 2})
    removed = client.delete(line_url)  # nothing reserved, but two were issued and returned
    assert removed.status_code == 409 and removed.get_json()["code"] == "work_order_part_in_use"

    fresh = _part(org, "Hex Bolt")
    spare = client.post(url, json={"part_id": str(fresh.id), "location_id": str(shelf.id), "quantity_planned": 1}).get_json()["payload"][
        "work_order_part"
    ]
    gone = client.delete(f"{url}/{spare['id']}")
    assert gone.status_code == 200 and [item["id"] for item in gone.get_json()["payload"]["items"]] == [line["id"]]
    assert _db.session.get(WorkOrderPart, UUID(spare["id"])) is None
    assert AuditEvent.query.filter_by(event_type="work_order.part_removed", entity_id=str(wo.id)).count() == 1


def test_kitting_an_issued_line_is_an_invalid_transition(client, org, users, ctx_admin, api_login):
    shelf = _location(org)
    part = _part(org, "Bearing 608")
    _receive(ctx_admin, part, shelf, D("4"))
    wo = _wo(org, users["admin"])
    api_login(users["admin"])
    url = _url(wo)
    line = client.post(url, json={"part_id": str(part.id), "location_id": str(shelf.id), "quantity_planned": 2}).get_json()["payload"][
        "work_order_part"
    ]
    client.post(f"{url}/{line['id']}/issue", json={"quantity": 2})

    denied = client.post(f"{url}/{line['id']}/kit", json={})
    assert denied.status_code == 409
    body = denied.get_json()
    assert body["code"] == "invalid_transition" and body["from"] == "issued" and body["action"] == "kit"


# --------------------------------------------------------------------------- validation


def test_validation_lists_every_bad_field(client, org, users, api_login):
    wo = _wo(org, users["admin"])
    api_login(users["admin"])
    url = _url(wo)

    malformed = client.post(url, json={"part_id": "not-a-uuid", "location_id": "not-a-uuid", "quantity_planned": 0, "note": "x" * 2100})
    assert malformed.status_code == 400
    payload = malformed.get_json()
    assert payload["code"] == "validation"
    assert set(payload["errors"]) == {"part_id", "location_id", "quantity_planned", "note"}

    missing = client.post(url, json={})
    assert missing.status_code == 400 and set(missing.get_json()["errors"]) == {"part_id", "quantity_planned"}

    inactive = _part(org, "Retired Bolt", is_active=False)
    unknown = client.post(url, json={"part_id": str(inactive.id), "quantity_planned": 1})
    assert unknown.status_code == 400 and set(unknown.get_json()["errors"]) == {"part_id"}

    shelf = _location(org)
    part = _part(org, "Bearing 608")
    line = client.post(url, json={"part_id": str(part.id), "location_id": str(shelf.id), "quantity_planned": 1}).get_json()["payload"][
        "work_order_part"
    ]
    for action in ("reserve", "release", "issue", "return"):
        response = client.post(f"{url}/{line['id']}/{action}", json={"quantity": -1})
        assert response.status_code == 400, action
        assert set(response.get_json()["errors"]) == {"quantity"}, action
    fractional = client.post(f"{url}/{line['id']}/reserve", json={"quantity": 0.00051})
    assert fractional.status_code == 400 and "quantity" in fractional.get_json()["errors"]


# --------------------------------------------------------------------------- permissions


def test_permissions_for_planning_kitting_and_issuing(client, org, users, ctx_admin, api_login):
    shelf = _location(org)
    part = _part(org, "Bearing 608", unit_cost=D("1.0000"))
    _receive(ctx_admin, part, shelf, D("10"))
    wo = _wo(org, users["admin"])
    api_login(users["admin"])
    url = _url(wo)
    line = client.post(url, json={"part_id": str(part.id), "location_id": str(shelf.id), "quantity_planned": 4}).get_json()["payload"][
        "work_order_part"
    ]
    line_url = f"{url}/{line['id']}"

    # full member: reads the work order, but may not plan, reserve, kit or issue
    api_login(users["member"])
    assert client.get(url).status_code == 200
    assert client.post(url, json={"part_id": str(part.id), "quantity_planned": 1}).status_code == 403
    assert client.post(f"{line_url}/reserve", json={"quantity": 1}).status_code == 403
    assert client.post(f"{line_url}/kit", json={}).status_code == 403
    assert client.post(f"{line_url}/issue", json={"quantity": 1}).status_code == 403

    # the requester role has no work-order read key at all
    requester = make_user("Rae Requester", "rae-parts@uiowa.edu", ops_role="requester", org=org)
    api_login(requester)
    assert client.get(url).status_code == 403

    # an assignee may issue and return without inventory.manage
    wo_row = _db.session.get(WorkOrder, wo.id)
    wo_row.assignees.append(WorkOrderAssignee(user_id=users["member"].id))
    _db.session.commit()
    api_login(users["member"])
    assert client.post(f"{line_url}/kit", json={}).status_code == 403  # still inventory.manage only
    issued = client.post(f"{line_url}/issue", json={"quantity": 1})
    assert issued.status_code == 200, issued.get_json()
    assert client.post(f"{line_url}/return", json={"quantity": 1}).status_code == 200

    # an inventory manager may do all of it without being on the work order
    manager = make_user("Ines Inventory", "ines@uiowa.edu", ops_role="inventory_manager", org=org)
    api_login(manager)
    assert client.post(f"{line_url}/reserve", json={"quantity": 2}).status_code == 200
    assert client.post(f"{line_url}/kit", json={}).status_code == 200
    assert client.post(f"{line_url}/issue", json={"quantity": 1}).status_code == 200


def test_service_functions_authorize_and_take_context_first(org, users, ctx_admin, ctx_member):
    shelf = _location(org)
    part = _part(org, "Bearing 608")
    _receive(ctx_admin, part, shelf, D("5"))
    wo = _wo(org, users["admin"])
    line = work_order_parts.add(
        ctx_admin, wo, {"part_id": str(part.id), "location_id": str(shelf.id), "quantity_planned": 2}
    )
    assert line.readiness == "assigned" and line.organization_id == org.id

    for call in (
        lambda: work_order_parts.add(ctx_member, wo, {"part_id": str(part.id), "quantity_planned": 1}),
        lambda: work_order_parts.reserve(ctx_member, wo, line, {"quantity": 1}),
        lambda: work_order_parts.set_readiness(ctx_member, wo, line, "kitted"),
        lambda: work_order_parts.issue(ctx_member, wo, line, {"quantity": 1}),
    ):
        with pytest.raises(Forbidden):
            call()


# --------------------------------------------------------------------------- tenancy


def test_cross_organization_ids_are_404(client, org, users, ctx_admin, api_login):
    other = Organization(name="Other Chapter", slug=f"other-{uuid4().hex[:6]}")
    _db.session.add(other)
    _db.session.flush()
    foreign_wo = WorkOrder(organization_id=other.id, number=1, title="Foreign", created_by_user_id=users["admin"].id)
    foreign_part = Part(organization_id=other.id, name="Foreign Bolt")
    foreign_location = Location(organization_id=other.id, name="Foreign Shelf")
    _db.session.add_all([foreign_wo, foreign_part, foreign_location])
    _db.session.flush()
    foreign_line = WorkOrderPart(
        organization_id=other.id,
        work_order_id=foreign_wo.id,
        part_id=foreign_part.id,
        quantity_planned=D("1"),
        quantity_reserved=D("0"),
        quantity_issued=D("0"),
        quantity_returned=D("0"),
        readiness="assigned",
    )
    _db.session.add(foreign_line)
    _db.session.commit()

    shelf = _location(org)
    part = _part(org, "Bearing 608")
    wo = _wo(org, users["admin"])
    other_wo = _wo(org, users["admin"], title="Another work order")
    api_login(users["admin"])
    url = _url(wo)
    line = client.post(url, json={"part_id": str(part.id), "location_id": str(shelf.id), "quantity_planned": 1}).get_json()["payload"][
        "work_order_part"
    ]

    assert client.get(f"/api/v1/work-orders/{foreign_wo.id}/parts").status_code == 404
    assert client.post(f"/api/v1/work-orders/{foreign_wo.id}/parts", json={"part_id": str(part.id), "quantity_planned": 1}).status_code == 404
    assert client.get("/api/v1/work-orders/not-a-uuid/parts").status_code == 404
    assert client.post(f"{url}/{foreign_line.id}/reserve", json={"quantity": 1}).status_code == 404
    assert client.patch(f"{url}/{foreign_line.id}", json={"quantity_planned": 2}).status_code == 404
    assert client.delete(f"{url}/{uuid4()}").status_code == 404
    assert client.post(f"{url}/not-a-uuid/issue", json={"quantity": 1}).status_code == 404
    # a line of another work order in the same chapter is not addressable here either
    assert client.post(f"/api/v1/work-orders/{other_wo.id}/parts/{line['id']}/reserve", json={"quantity": 1}).status_code == 404

    rejected = client.post(url, json={"part_id": str(foreign_part.id), "location_id": str(foreign_location.id), "quantity_planned": 1})
    assert rejected.status_code == 400 and set(rejected.get_json()["errors"]) == {"part_id", "location_id"}

    with pytest.raises(NotFound):
        work_order_parts.get_line(ctx_admin, _db.session.get(WorkOrder, wo.id), foreign_line.id)


def test_login_is_required(client, org, users):
    wo = _wo(org, users["admin"])
    assert client.get(_url(wo)).status_code == 401
    assert client.post(_url(wo), json={"part_id": str(uuid4()), "quantity_planned": 1}).status_code == 401


def test_part_defaults_to_its_own_location(client, org, users, ctx_admin, api_login):
    shelf = _location(org, "Shelf A")
    part = _part(org, "Bearing 608", default_location_id=shelf.id)
    _receive(ctx_admin, part, shelf, D("3"))
    wo = _wo(org, users["admin"])
    api_login(users["admin"])
    created = client.post(_url(wo), json={"part_id": str(part.id), "quantity_planned": 2})
    assert created.status_code == 201
    assert created.get_json()["payload"]["work_order_part"]["location"] == {"id": str(shelf.id), "name": "Shelf A"}
