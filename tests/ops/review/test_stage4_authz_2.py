"""The ledger must not name purchase requests the caller may not read.

The plan's purchase-request read rule is: ``purchase.review``,
``purchase.advisor_review`` or ``inventory.manage`` read everything; everyone
else reads their own requests plus the ones on projects they manage - "anything
else is 404".

``GET /inventory/transactions`` and ``GET /parts/:id/transactions`` are gated on
``inventory.read`` alone, which every full member holds. The serializer hides a
linked work order the caller may not read (``work_order_readable``) but emits
``purchase_request`` unconditionally, so a receipt posted by receiving a
purchase request hands every member that request's number, title and status -
the same request the API answers 404 for.
"""

from __future__ import annotations

from asme.extensions import db as _db
from asme.ops.models import Location, Part
from tests.ops.conftest import make_user

API = "/api/v1/purchase-requests"
SECRET_TITLE = "Confidential telemetry radios"


def _received_purchase_request(client, api_login, org, users, part, location):
    """Walk one request draft -> submit -> approve -> order -> receive and return it."""
    manager = make_user("Ivy Manager", "ivy.manager@uiowa.edu", ops_role="inventory_manager", org=org)
    api_login(manager)
    created = client.post(
        API,
        json={"title": SECRET_TITLE, "items": [{"part_id": str(part.id), "quantity": 4, "unit_price": "12.50"}]},
    )
    assert created.status_code == 201, created.get_json()
    request = created.get_json()["payload"]["purchase_request"]
    assert client.post(f"{API}/{request['id']}/submit", json={}).status_code == 200

    api_login(users["admin"])
    assert client.post(f"{API}/{request['id']}/approve", json={}).status_code == 200

    api_login(manager)
    assert client.post(f"{API}/{request['id']}/order", json={"order_reference": "PO-9"}).status_code == 200
    item = client.get(f"{API}/{request['id']}").get_json()["payload"]["purchase_request"]["items"][0]
    received = client.post(
        f"{API}/{request['id']}/receive",
        json={"lines": [{"item_id": item["id"], "quantity": 4, "location_id": str(location.id)}]},
    )
    assert received.status_code == 200, received.get_json()
    return request


def test_ledger_hides_purchase_requests_the_member_cannot_read(client, org, users, api_login):
    location = Location(organization_id=org.id, name="Shelf A", is_default=True)
    _db.session.add(location)
    _db.session.flush()
    part = Part(organization_id=org.id, name="Radio module", default_location_id=location.id)
    _db.session.add(part)
    _db.session.commit()

    request = _received_purchase_request(client, api_login, org, users, part, location)

    api_login(users["member"])
    assert client.get(f"{API}/{request['id']}").status_code == 404, "the read rule must hide this request"

    for url in (
        "/api/v1/inventory/transactions",
        f"/api/v1/parts/{part.id}/transactions",
    ):
        response = client.get(url)
        assert response.status_code == 200, response.get_json()
        rows = response.get_json()["payload"]["transactions"]
        assert rows, f"{url} returned no ledger rows to check"
        leaked = [row["purchase_request"] for row in rows if row["purchase_request"] is not None]
        assert not leaked, (
            f"{url} named purchase requests the caller gets a 404 for: {leaked}"
        )

    detail = client.get(f"/api/v1/parts/{part.id}")
    assert detail.status_code == 200, detail.get_json()
    recent = detail.get_json()["payload"]["part"]["recent_transactions"]
    leaked = [row["purchase_request"] for row in recent if row["purchase_request"] is not None]
    assert not leaked, f"GET /parts/:id recent_transactions leaked {leaked}"
