"""The purchase-request approval workflow: the from-state table, each step's
permission, the self-approval rule, receiving through the inventory ledger, the
approval timeline, notifications, events and ``available_actions``."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from asme import events
from asme.extensions import db as _db
from asme.ops import bootstrap, policy
from asme.ops.models import (
    AuditEvent,
    InventoryTransaction,
    Location,
    Notification,
    OpsProject,
    Part,
    PartVendor,
    ProjectMember,
    PurchaseRequest,
    PurchaseRequestEvent,
    Vendor,
)
from asme.ops.services import inventory_ledger as ledger
from asme.ops.services import purchase_requests as service
from tests.ops.conftest import make_user

API = "/api/v1/purchase-requests"
SETTINGS = "/api/v1/purchasing/settings"
D = Decimal


# --------------------------------------------------------------------------- helpers


def _uuid(value):
    return value if isinstance(value, UUID) else UUID(str(value))


def _vendor(org, name):
    row = Vendor(organization_id=org.id, name=name)
    _db.session.add(row)
    _db.session.commit()
    return row


def _location(org, name, *, is_default=False):
    row = Location(organization_id=org.id, name=name, is_default=is_default)
    _db.session.add(row)
    _db.session.commit()
    return row


def _part(org, name, **fields):
    row = Part(organization_id=org.id, name=name, **fields)
    _db.session.add(row)
    _db.session.commit()
    return row


def _link(part, vendor, **fields):
    row = PartVendor(part_id=part.id, vendor_id=vendor.id, preferred=True, **fields)
    _db.session.add(row)
    _db.session.commit()
    return row


def _project(org, name, code, *, lead=None, budget=None):
    project = OpsProject(
        organization_id=org.id,
        name=name,
        code=code,
        visibility="chapter",
        lead_user_id=lead.id if lead else None,
        budget_amount=budget,
    )
    _db.session.add(project)
    _db.session.flush()
    if lead is not None:
        _db.session.add(ProjectMember(project_id=project.id, user_id=lead.id, project_role="lead"))
    _db.session.commit()
    return project


def _post(client, request_id, action, **body):
    return client.post(f"{API}/{request_id}/{action}", json=body)


def _act(client, request_id, action, **body):
    response = _post(client, request_id, action, **body)
    assert response.status_code == 200, response.get_json()
    return response.get_json()["payload"]["purchase_request"]


def _draft(client, **overrides):
    payload = {"title": "Drivetrain fasteners", "items": [{"description": "M6 bolts", "quantity": 20, "unit_price": "0.4500"}]}
    payload.update(overrides)
    response = client.post(API, json=payload)
    assert response.status_code == 201, response.get_json()
    return response.get_json()["payload"]["purchase_request"]


def _timeline(request_id):
    rows = (
        PurchaseRequestEvent.query.filter_by(purchase_request_id=_uuid(request_id))
        .order_by(PurchaseRequestEvent.created_at, PurchaseRequestEvent.id)
        .all()
    )
    return [(row.action, row.from_status, row.to_status, row.step) for row in rows]


def _roles(org):
    return {
        "treasurer": make_user("Tess Treasurer", "tess@uiowa.edu", ops_role="treasurer", org=org),
        "advisor": make_user("Avi Advisor", "avi@uiowa.edu", ops_role="faculty_advisor", org=org),
        "manager": make_user("Ines Inventory", "ines@uiowa.edu", ops_role="inventory_manager", org=org),
        "lead": make_user("Pat Lead", "pat@uiowa.edu", ops_role="project_lead", org=org),
    }


# --------------------------------------------------------------------------- the full path


def test_full_path_from_draft_to_received(client, org, users, api_login):
    people = _roles(org)
    shelf = _location(org, "Shelf A")
    vendor = _vendor(org, "McMaster-Carr")
    bolt = _part(org, "M6 bolt", unit="each", unit_cost=D("1.0000"), minimum_stock=D("5"))
    link = _link(bolt, vendor, vendor_part_number="91290A115")
    project = _project(org, "Baja", "BAJA", lead=people["lead"], budget=D("2000.00"))

    received: list[tuple] = []

    def handler(name, **payload):
        received.append((name, payload))

    events.subscribe(events.PURCHASE_REQUEST_STATUS_CHANGED, handler)
    try:
        api_login(users["admin"])
        assert client.put(SETTINGS, json={"advisor_review_threshold": "100", "require_project_lead_approval": True}).status_code == 200

        # Receive some stock first so the weighted unit cost has a starting point.
        api_login(people["manager"])
        ctx_manager = policy.load_context(people["manager"], org)
        ledger.post(ctx_manager, part=bolt, location=shelf, transaction_type="receipt", on_hand_delta=D("10"), quantity=D("10"), unit_cost=D("1.0000"))
        _db.session.commit()
        ledger.emit_pending_events()

        api_login(users["member"])
        draft = _draft(
            client,
            project_id=str(project.id),
            vendor_id=str(vendor.id),
            items=[{"part_id": str(bolt.id), "quantity": 100, "unit_price": "2.0000", "receive_location_id": str(shelf.id)}],
        )
        assert draft["estimated_total"] == 200.0
        assert set(draft["available_actions"]) == {"submit", "cancel"}

        submitted = _act(client, draft["id"], "submit")
        assert submitted["status"] == "submitted" and submitted["submitted_at"] is not None
        assert Notification.query.filter_by(user_id=people["lead"].id, type="purchase_request.needs_review").count() == 1

        api_login(people["lead"])
        detail = client.get(f"{API}/{draft['id']}").get_json()["payload"]["purchase_request"]
        assert set(detail["available_actions"]) == {"approve", "decline", "request_changes"}
        after_lead = _act(client, draft["id"], "approve", comment="Needed for the rebuild.")
        assert after_lead["status"] == "treasurer_review"

        api_login(people["treasurer"])
        after_treasurer = _act(client, draft["id"], "approve")
        assert after_treasurer["status"] == "advisor_review"  # 200.00 >= the 100 threshold
        advisor_notes = Notification.query.filter_by(user_id=people["advisor"].id, type="purchase_request.needs_review").all()
        assert any("needs advisor sign-off" in row.title for row in advisor_notes)

        api_login(people["advisor"])
        approved = _act(client, draft["id"], "approve", approved_total="195.00")
        assert approved["status"] == "approved" and approved["approved_total"] == 195.0 and approved["approved_at"] is not None

        api_login(people["manager"])
        ordered = _act(client, draft["id"], "order", order_reference="AMZ-4417")
        assert ordered["status"] == "ordered" and ordered["order_reference"] == "AMZ-4417"
        assert PartVendor.query.get(link.id).last_ordered_at is not None
        assert ledger.part_totals([bolt.id])[bolt.id]["ordered"] == D("100.000")

        item_id = ordered["items"][0]["id"]
        partial = _act(client, draft["id"], "receive", lines=[{"item_id": item_id, "quantity": 40}], note="First box")
        assert partial["status"] == "partially_received"
        assert partial["items"][0]["received_quantity"] == 40.0
        assert ledger.part_totals([bolt.id])[bolt.id]["ordered"] == D("60.000")

        rest = _act(client, draft["id"], "receive", lines=[{"item_id": item_id, "quantity": 60}])
        assert rest["status"] == "received" and rest["received_at"] is not None
        assert rest["items"][0]["received_quantity"] == 100.0

        totals = ledger.part_totals([bolt.id])[bolt.id]
        assert totals["on_hand"] == D("110.000") and totals["ordered"] == D("0.000")
        # Weighted: (10 * 1.00 + 100 * 2.00) / 110
        assert ledger.to_unit_cost(Part.query.get(bolt.id).unit_cost) == D("1.9091")
        assert ledger.to_unit_cost(PartVendor.query.get(link.id).last_price) == D("2.0000")

        receipts = InventoryTransaction.query.filter_by(purchase_request_id=_uuid(draft["id"])).all()
        assert sorted(ledger.to_quantity(row.quantity) for row in receipts) == [D("40.000"), D("60.000")]
        assert all(row.transaction_type == "receipt" and row.location_id == shelf.id for row in receipts)

        assert _timeline(draft["id"]) == [
            ("submit", "draft", "submitted", None),
            ("approve", "submitted", "treasurer_review", "project_lead"),
            ("approve", "treasurer_review", "advisor_review", "treasurer"),
            ("approve", "advisor_review", "approved", "advisor"),
            ("order", "approved", "ordered", None),
            ("receive", "ordered", "partially_received", None),
            ("receive", "partially_received", "received", None),
        ]
        assert [payload["status"] for _name, payload in received] == [
            "submitted",
            "treasurer_review",
            "advisor_review",
            "approved",
            "ordered",
            "partially_received",
            "received",
        ]
        assert all(name == events.PURCHASE_REQUEST_STATUS_CHANGED for name, _payload in received)
        assert {event.event_type for event in AuditEvent.query.filter_by(entity_id=draft["id"])} == {
            "purchase_request.created",
            "purchase_request.submit",
            "purchase_request.approve",
            "purchase_request.order",
            "purchase_request.receive",
        }

        api_login(people["lead"])
        health = client.get(f"/api/v1/projects/{project.id}/health").get_json()["payload"]
        assert health["budget"]["committed"] == 195.0
    finally:
        events.unsubscribe(events.PURCHASE_REQUEST_STATUS_CHANGED, handler)


def test_below_the_threshold_treasurer_approval_is_final(client, org, users, api_login):
    people = _roles(org)
    api_login(users["admin"])
    assert client.put(SETTINGS, json={"advisor_review_threshold": "500"}).status_code == 200

    api_login(users["member"])
    draft = _draft(client)  # 20 * 0.45 = 9.00
    submitted = _act(client, draft["id"], "submit")
    assert submitted["status"] == "treasurer_review"  # no project lead step configured

    api_login(people["treasurer"])
    approved = _act(client, draft["id"], "approve")
    assert approved["status"] == "approved"
    assert approved["approved_total"] == 9.0  # defaults to the estimate
    assert Notification.query.filter_by(user_id=users["member"].id, type="purchase_request.status_changed").count() == 1


def test_project_lead_step_is_skipped_without_a_project(client, org, users, api_login):
    api_login(users["admin"])
    assert client.put(SETTINGS, json={"require_project_lead_approval": True}).status_code == 200
    api_login(users["member"])
    draft = _draft(client)
    assert _act(client, draft["id"], "submit")["status"] == "treasurer_review"


# --------------------------------------------------------------------------- guards


def test_nobody_approves_their_own_request(client, org, users, api_login):
    treasurer = make_user("Tess Treasurer", "tess@uiowa.edu", ops_role="treasurer", org=org)
    api_login(treasurer)
    draft = _draft(client)
    _act(client, draft["id"], "submit")
    denied = _post(client, draft["id"], "approve")
    assert denied.status_code == 409
    assert denied.get_json()["code"] == "self_approval"

    detail = client.get(f"{API}/{draft['id']}").get_json()["payload"]["purchase_request"]
    assert "approve" not in detail["available_actions"]
    assert {"decline", "request_changes", "cancel"} <= set(detail["available_actions"])

    other = make_user("Ola Officer", "ola@uiowa.edu", ops_role="executive_officer", org=org)
    api_login(other)
    assert _act(client, draft["id"], "approve")["status"] == "approved"


def test_invalid_from_states_conflict(client, org, users, api_login):
    people = _roles(org)
    api_login(users["member"])
    draft = _draft(client)

    early = _post(client, draft["id"], "approve")
    assert early.status_code == 409
    body = early.get_json()
    assert body["code"] == "invalid_transition" and body["from"] == "draft" and body["action"] == "approve"

    api_login(people["manager"])
    assert _post(client, draft["id"], "receive", lines=[]).status_code == 409
    assert _post(client, draft["id"], "order").status_code == 409

    api_login(users["member"])
    _act(client, draft["id"], "submit")
    twice = _post(client, draft["id"], "submit")
    assert twice.status_code == 409 and twice.get_json()["from"] == "treasurer_review"


def test_submit_needs_the_requester_and_a_line(client, org, users, api_login):
    treasurer = make_user("Tess Treasurer", "tess@uiowa.edu", ops_role="treasurer", org=org)
    api_login(users["member"])
    draft = _draft(client)

    api_login(treasurer)
    denied = _post(client, draft["id"], "submit")
    assert denied.status_code == 403 and denied.get_json()["permission"] == "purchase.submit"

    # A request whose lines were all removed cannot be submitted.
    api_login(users["member"])
    request = PurchaseRequest.query.get(_uuid(draft["id"]))
    for item in list(request.items):
        request.items.remove(item)
    _db.session.commit()
    empty = _post(client, draft["id"], "submit")
    assert empty.status_code == 400 and set(empty.get_json()["errors"]) == {"items"}


def test_each_review_step_has_its_own_approver(client, org, users, api_login):
    people = _roles(org)
    project = _project(org, "Baja", "BAJA", lead=people["lead"])
    api_login(users["admin"])
    assert client.put(SETTINGS, json={"advisor_review_threshold": "1", "require_project_lead_approval": True}).status_code == 200

    api_login(users["member"])
    draft = _draft(client, project_id=str(project.id))
    _act(client, draft["id"], "submit")

    # The treasurer cannot stand in for the project lead.
    api_login(people["treasurer"])
    denied = _post(client, draft["id"], "approve")
    assert denied.status_code == 403 and denied.get_json()["permission"] == "project.manage"

    api_login(people["lead"])
    _act(client, draft["id"], "approve")
    # ... and the project lead cannot stand in for the treasurer.
    denied = _post(client, draft["id"], "approve")
    assert denied.status_code == 403 and denied.get_json()["permission"] == "purchase.review"

    api_login(people["treasurer"])
    assert _act(client, draft["id"], "approve")["status"] == "advisor_review"
    denied = _post(client, draft["id"], "approve")
    assert denied.status_code == 403 and denied.get_json()["permission"] == "purchase.advisor_review"

    api_login(people["advisor"])
    assert _act(client, draft["id"], "approve")["status"] == "approved"


def test_decline_and_request_changes_need_a_comment(client, org, users, api_login):
    treasurer = make_user("Tess Treasurer", "tess@uiowa.edu", ops_role="treasurer", org=org)
    api_login(users["member"])
    first = _draft(client)
    second = _draft(client, title="Second")
    _act(client, first["id"], "submit")
    _act(client, second["id"], "submit")

    api_login(treasurer)
    missing = _post(client, first["id"], "decline")
    assert missing.status_code == 400 and set(missing.get_json()["errors"]) == {"comment"}
    declined = _act(client, first["id"], "decline", comment="Out of budget this semester.")
    assert declined["status"] == "declined" and declined["decline_reason"] == "Out of budget this semester."
    assert Notification.query.filter_by(user_id=users["member"].id, type="purchase_request.status_changed").count() == 1

    missing = _post(client, second["id"], "request-changes")
    assert missing.status_code == 400 and set(missing.get_json()["errors"]) == {"comment"}
    changed = _act(client, second["id"], "request-changes", comment="Split the shipping out.")
    assert changed["status"] == "draft" and changed["submitted_at"] is None

    reopened = _act(client, first["id"], "reopen")
    assert reopened["status"] == "draft" and reopened["decline_reason"] is None
    assert _timeline(first["id"]) == [
        ("submit", "draft", "treasurer_review", None),
        ("decline", "treasurer_review", "declined", "treasurer"),
        ("reopen", "declined", "draft", None),
    ]

    api_login(users["member"])
    assert _post(client, first["id"], "reopen").status_code == 409  # already a draft


def test_cancel_rules(client, org, users, api_login):
    treasurer = make_user("Tess Treasurer", "tess@uiowa.edu", ops_role="treasurer", org=org)
    api_login(users["member"])
    mine = _draft(client)
    canceled = _act(client, mine["id"], "cancel", comment="Found spares in the shop.")
    assert canceled["status"] == "canceled" and canceled["available_actions"] == []

    later = _draft(client, title="Later")
    _act(client, later["id"], "submit")
    api_login(treasurer)
    approved = _act(client, later["id"], "approve")
    assert approved["status"] == "approved"

    # The requester may no longer cancel once the money is approved; a reviewer may.
    api_login(users["member"])
    denied = _post(client, later["id"], "cancel")
    assert denied.status_code == 403
    api_login(treasurer)
    assert _act(client, later["id"], "cancel")["status"] == "canceled"
    assert _act(client, later["id"], "reopen")["status"] == "draft"


# --------------------------------------------------------------------------- receiving


def test_receiving_requires_inventory_manage_and_respects_outstanding(client, org, users, api_login):
    people = _roles(org)
    chapter_default = bootstrap.ensure_default_location(org)
    _db.session.commit()
    bolt = _part(org, "M6 bolt")
    api_login(users["member"])
    draft = _draft(client, items=[{"part_id": str(bolt.id), "quantity": 10, "unit_price": "1.00"}])
    _act(client, draft["id"], "submit")

    api_login(people["treasurer"])
    approved = _act(client, draft["id"], "approve")
    ordered = _act(client, draft["id"], "order")  # purchase.review may order
    assert ordered["status"] == "ordered" and approved["status"] == "approved"

    # A treasurer has purchase.review but not inventory.manage.
    denied = _post(client, draft["id"], "receive", lines=[{"item_id": ordered["items"][0]["id"], "quantity": 1}])
    assert denied.status_code == 403 and denied.get_json()["permission"] == "inventory.manage"

    api_login(people["manager"])
    item_id = ordered["items"][0]["id"]
    too_many = _post(client, draft["id"], "receive", lines=[{"item_id": item_id, "quantity": 11}])
    assert too_many.status_code == 400 and set(too_many.get_json()["errors"]) == {"lines[0].quantity"}
    assert InventoryTransaction.query.count() == 0

    zero = _post(client, draft["id"], "receive", lines=[{"item_id": item_id, "quantity": 0}])
    assert zero.status_code == 400 and set(zero.get_json()["errors"]) == {"lines[0].quantity"}

    unknown = _post(client, draft["id"], "receive", lines=[{"item_id": str(bolt.id), "quantity": 1}])
    assert unknown.status_code == 400 and set(unknown.get_json()["errors"]) == {"lines[0].item_id"}

    duplicate = _post(client, draft["id"], "receive", lines=[{"item_id": item_id, "quantity": 1}, {"item_id": item_id, "quantity": 1}])
    assert duplicate.status_code == 400 and set(duplicate.get_json()["errors"]) == {"lines[1].item_id"}

    none = _post(client, draft["id"], "receive", lines=[])
    assert none.status_code == 400 and set(none.get_json()["errors"]) == {"lines"}

    done = _act(client, draft["id"], "receive", lines=[{"item_id": item_id, "quantity": 10}])
    assert done["status"] == "received"
    assert ledger.part_totals([bolt.id])[bolt.id]["on_hand"] == D("10.000")
    # The location fell back to the chapter's default location.
    assert InventoryTransaction.query.one().location_id == chapter_default.id

    over = _post(client, draft["id"], "receive", lines=[{"item_id": item_id, "quantity": 1}])
    assert over.status_code == 409 and over.get_json()["code"] == "invalid_transition"


def test_receiving_prefers_the_line_location_then_the_parts_default(client, org, users, api_login):
    people = _roles(org)
    chapter_default = bootstrap.ensure_default_location(org)
    _db.session.commit()
    part_default = _location(org, "Electronics drawer")
    explicit = _location(org, "Bench")
    fuse = _part(org, "Fuse 5A", default_location_id=part_default.id)
    free_text = _part(org, "Zip ties")

    api_login(users["member"])
    draft = _draft(
        client,
        items=[
            {"part_id": str(fuse.id), "quantity": 2, "unit_price": "1.00"},
            {"part_id": str(free_text.id), "quantity": 3, "unit_price": "1.00"},
            {"description": "Shop rag bundle", "quantity": 1, "unit_price": "5.00"},
        ],
    )
    _act(client, draft["id"], "submit")

    api_login(people["treasurer"])
    _act(client, draft["id"], "approve")
    ordered = _act(client, draft["id"], "order")

    api_login(people["manager"])
    items = ordered["items"]
    received = _act(
        client,
        draft["id"],
        "receive",
        lines=[
            {"item_id": items[0]["id"], "quantity": 2},
            {"item_id": items[1]["id"], "quantity": 3, "location_id": str(explicit.id)},
            {"item_id": items[2]["id"], "quantity": 1},
        ],
    )
    assert received["status"] == "received"
    by_part = {row.part_id: row.location_id for row in InventoryTransaction.query.all()}
    assert by_part[fuse.id] == part_default.id
    assert by_part[free_text.id] == explicit.id
    # A free-text line moves no stock at all.
    assert len(by_part) == 2
    assert chapter_default.id not in by_part.values()


def test_receiving_rolls_back_when_a_line_fails(client, org, users, api_login):
    people = _roles(org)
    bootstrap.ensure_default_location(org)
    _db.session.commit()
    good = _part(org, "Washer")
    api_login(users["member"])
    draft = _draft(
        client,
        items=[{"part_id": str(good.id), "quantity": 5, "unit_price": "1.00"}, {"description": "Special order", "quantity": 1, "unit_price": "1.00"}],
    )
    _act(client, draft["id"], "submit")
    api_login(people["treasurer"])
    _act(client, draft["id"], "approve")
    ordered = _act(client, draft["id"], "order")

    api_login(people["manager"])
    items = ordered["items"]
    bad = _post(
        client,
        draft["id"],
        "receive",
        lines=[{"item_id": items[0]["id"], "quantity": 5}, {"item_id": items[1]["id"], "quantity": 99}],
    )
    assert bad.status_code == 400 and set(bad.get_json()["errors"]) == {"lines[1].quantity"}
    assert InventoryTransaction.query.count() == 0
    assert PurchaseRequest.query.get(_uuid(draft["id"])).status == "ordered"
    assert ledger.part_totals([good.id])[good.id]["on_hand"] == D("0.000")


# --------------------------------------------------------------------------- available actions


def test_available_actions_follow_the_caller_and_the_state(client, org, users, api_login):
    people = _roles(org)
    api_login(users["member"])
    draft = _draft(client)
    assert set(draft["available_actions"]) == {"submit", "cancel"}
    submitted = _act(client, draft["id"], "submit")
    assert submitted["available_actions"] == ["cancel"]  # the requester can still withdraw

    api_login(people["treasurer"])
    detail = client.get(f"{API}/{draft['id']}").get_json()["payload"]["purchase_request"]
    assert set(detail["available_actions"]) == {"approve", "decline", "request_changes", "cancel"}

    api_login(people["manager"])
    detail = client.get(f"{API}/{draft['id']}").get_json()["payload"]["purchase_request"]
    assert detail["available_actions"] == []  # nothing to do until it is approved

    api_login(people["treasurer"])
    _act(client, draft["id"], "approve")
    api_login(people["manager"])
    detail = client.get(f"{API}/{draft['id']}").get_json()["payload"]["purchase_request"]
    assert detail["available_actions"] == ["order"]


def test_service_available_actions_match_can_perform(ctx_admin, ctx_member, org):
    request = service.create(ctx_member, {"title": "Wire", "items": [{"description": "22 AWG", "quantity": 1, "unit_price": "1.00"}]})
    assert service.available_actions(ctx_member, request) == ["submit", "cancel"]
    assert service.available_actions(ctx_admin, request) == ["cancel"]
    for action in service.ACTIONS:
        assert service.can_perform(ctx_member, request, action) == (action in ("submit", "cancel"))
