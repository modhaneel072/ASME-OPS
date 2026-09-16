"""``/api/v1/parts`` and ``/api/v1/part-types``: the catalogue, its vendor and
asset links, the stock filters and who may touch any of it."""

from __future__ import annotations

from decimal import Decimal

import pytest

from asme.extensions import db as _db
from asme.ops.models import (
    Asset,
    AuditEvent,
    InventoryBalance,
    Location,
    OpsProject,
    Organization,
    Part,
    PartAsset,
    PartType,
    PartVendor,
    PurchaseRequest,
    PurchaseRequestItem,
    Vendor,
)
from asme.ops.services import parts as parts_service
from asme.ops.validation import ValidationErrors
from asme.services.errors import Forbidden, NotFound
from tests.ops.conftest import make_user

D = Decimal

PLAN_PART_KEYS = {
    "id",
    "name",
    "sku",
    "unit",
    "description",
    "part_type",
    "manufacturer",
    "manufacturer_part_number",
    "unit_cost",
    "is_critical",
    "minimum_stock",
    "maximum_stock",
    "reorder_quantity",
    "default_location",
    "qr_code",
    "is_active",
    "totals",
    "stock_state",
    "preferred_vendor",
    "created_at",
    "updated_at",
}
PLAN_DETAIL_KEYS = PLAN_PART_KEYS | {"balances", "vendors", "assets", "open_purchase_requests", "recent_transactions"}


# --------------------------------------------------------------------------- inline helpers


def _location(org, name, **kw):
    row = Location(organization_id=org.id, name=name, **kw)
    _db.session.add(row)
    _db.session.commit()
    return row


def _vendor(org, name):
    row = Vendor(organization_id=org.id, name=name)
    _db.session.add(row)
    _db.session.commit()
    return row


def _asset(org, name, **kw):
    row = Asset(organization_id=org.id, name=name, **kw)
    _db.session.add(row)
    _db.session.commit()
    return row


def _part(org, name, **kw):
    row = Part(organization_id=org.id, name=name, **kw)
    _db.session.add(row)
    _db.session.commit()
    return row


def _balance(org, part, location, on_hand, reserved=0):
    row = InventoryBalance(
        organization_id=org.id, part_id=part.id, location_id=location.id, on_hand=D(str(on_hand)), reserved=D(str(reserved))
    )
    _db.session.add(row)
    _db.session.commit()
    return row


def _foreign_org():
    other = Organization(name="Other Chapter", slug="other-chapter")
    _db.session.add(other)
    _db.session.flush()
    return other


def _names(payload):
    return [item["name"] for item in payload["items"]]


# --------------------------------------------------------------------------- create / read / update


def test_part_crud_roundtrip_with_audit(client, org, users, api_login):
    api_login(users["admin"])
    location = _location(org, "Bin A")
    type_response = client.post("/api/v1/part-types", json={"name": "Fastener", "color": "#0878d1", "icon": "bolt"})
    assert type_response.status_code == 201, type_response.get_json()
    fastener = type_response.get_json()["payload"]["part_type"]
    assert fastener == {"id": fastener["id"], "name": "Fastener", "color": "#0878d1", "icon": "bolt", "part_count": 0}

    created = client.post(
        "/api/v1/parts",
        json={
            "name": "M4x12 Socket Head Cap Screw",
            "sku": "FAS-M4-12",
            "description": "Stainless, box of 100",
            "part_type_id": fastener["id"],
            "manufacturer": "McMaster-Carr",
            "manufacturer_part_number": "91292A110",
            "unit": "each",
            "unit_cost": 0.1875,
            "is_critical": True,
            "minimum_stock": 50,
            "maximum_stock": 500,
            "reorder_quantity": 250,
            "default_location_id": str(location.id),
            "qr_code": "QR-FAS-M4-12",
        },
    )
    assert created.status_code == 201, created.get_json()
    body = created.get_json()["payload"]["part"]
    assert set(body) == PLAN_DETAIL_KEYS
    assert body["name"] == "M4x12 Socket Head Cap Screw" and body["sku"] == "FAS-M4-12" and body["unit"] == "each"
    assert body["part_type"] == {"id": fastener["id"], "name": "Fastener", "color": "#0878d1", "icon": "bolt"}
    assert body["unit_cost"] == 0.1875 and body["is_critical"] is True
    assert body["minimum_stock"] == 50.0 and body["maximum_stock"] == 500.0 and body["reorder_quantity"] == 250.0
    assert body["default_location"] == {"id": str(location.id), "name": "Bin A"}
    assert body["totals"] == {"on_hand": 0.0, "reserved": 0.0, "available": 0.0, "ordered": 0.0}
    assert body["stock_state"] == "out"  # a minimum is set and nothing is on hand
    assert body["preferred_vendor"] is None and body["is_active"] is True
    assert body["balances"] == [] and body["vendors"] == [] and body["assets"] == []
    assert body["open_purchase_requests"] == [] and body["recent_transactions"] == []

    fetched = client.get(f"/api/v1/parts/{body['id']}")
    assert fetched.status_code == 200 and fetched.get_json()["payload"]["part"] == body

    patched = client.patch(f"/api/v1/parts/{body['id']}", json={"minimum_stock": 75, "description": None, "is_critical": False})
    assert patched.status_code == 200, patched.get_json()
    after = patched.get_json()["payload"]["part"]
    assert after["minimum_stock"] == 75.0 and after["description"] is None and after["is_critical"] is False

    create_event = AuditEvent.query.filter_by(event_type="part.created", entity_id=body["id"]).one()
    assert create_event.entity_type == "part" and create_event.actor_user_id == users["admin"].id
    assert create_event.after_json["sku"] == "FAS-M4-12"
    update_event = AuditEvent.query.filter_by(event_type="part.updated", entity_id=body["id"]).one()
    assert update_event.before_json["minimum_stock"] == 50.0 and update_event.after_json["minimum_stock"] == 75.0
    assert sorted(update_event.metadata_json["changed_fields"]) == ["description", "is_critical", "minimum_stock"]

    types = client.get("/api/v1/part-types").get_json()["payload"]
    assert types["items"] == [{**fastener, "part_count": 1}]


def test_part_validation_lists_every_bad_field(client, org, users, api_login):
    api_login(users["admin"])
    bad = client.post(
        "/api/v1/parts",
        json={
            "name": "",
            "sku": "S" * 61,
            "unit": "furlong",
            "unit_cost": -1,
            "minimum_stock": "not-a-number",
            "reorder_quantity": 1.23456,
            "part_type_id": "11111111-1111-1111-1111-111111111111",
            "default_location_id": "22222222-2222-2222-2222-222222222222",
        },
    )
    assert bad.status_code == 400
    payload = bad.get_json()
    assert payload["code"] == "validation"
    assert set(payload["errors"]) == {"name", "sku", "unit", "unit_cost", "minimum_stock", "reorder_quantity"}

    missing = client.post("/api/v1/parts", json={})
    assert missing.status_code == 400 and set(missing.get_json()["errors"]) == {"name"}

    unknown_refs = client.post(
        "/api/v1/parts",
        json={
            "name": "Ghost",
            "part_type_id": "11111111-1111-1111-1111-111111111111",
            "default_location_id": "22222222-2222-2222-2222-222222222222",
        },
    )
    assert unknown_refs.status_code == 400
    assert set(unknown_refs.get_json()["errors"]) == {"part_type_id", "default_location_id"}

    bad_band = client.post("/api/v1/parts", json={"name": "Wire", "minimum_stock": 100, "maximum_stock": 10})
    assert bad_band.status_code == 400 and set(bad_band.get_json()["errors"]) == {"maximum_stock"}

    # a case-sensitive unit survives the round trip
    litres = client.post("/api/v1/parts", json={"name": "Resin", "unit": "mL"})
    assert litres.status_code == 201 and litres.get_json()["payload"]["part"]["unit"] == "mL"


def test_part_sku_and_qr_code_are_unique_per_organization(client, org, users, api_login):
    api_login(users["admin"])
    first = client.post("/api/v1/parts", json={"name": "Bearing 608", "sku": "BRG-608", "qr_code": "QR-608"})
    assert first.status_code == 201
    dupe_sku = client.post("/api/v1/parts", json={"name": "Other", "sku": "brg-608"})
    assert dupe_sku.status_code == 400 and set(dupe_sku.get_json()["errors"]) == {"sku"}
    dupe_qr = client.post("/api/v1/parts", json={"name": "Other", "qr_code": "qr-608"})
    assert dupe_qr.status_code == 400 and set(dupe_qr.get_json()["errors"]) == {"qr_code"}

    second = client.post("/api/v1/parts", json={"name": "Bearing 625", "sku": "BRG-625"}).get_json()["payload"]["part"]
    clash = client.patch(f"/api/v1/parts/{second['id']}", json={"sku": "BRG-608"})
    assert clash.status_code == 400 and set(clash.get_json()["errors"]) == {"sku"}
    same = client.patch(f"/api/v1/parts/{second['id']}", json={"sku": "BRG-625"})
    assert same.status_code == 200


def test_unit_cost_is_locked_once_the_part_has_inventory_history(client, org, users, api_login):
    api_login(users["admin"])
    location = _location(org, "Bin A")
    part = client.post("/api/v1/parts", json={"name": "Filament", "unit_cost": 20}).get_json()["payload"]["part"]
    editable = client.patch(f"/api/v1/parts/{part['id']}", json={"unit_cost": 22})
    assert editable.status_code == 200 and editable.get_json()["payload"]["part"]["unit_cost"] == 22.0

    receipt = client.post(
        f"/api/v1/parts/{part['id']}/transactions",
        json={"type": "receipt", "location_id": str(location.id), "quantity": 1, "unit_cost": 24},
    )
    assert receipt.status_code == 201, receipt.get_json()

    locked = client.patch(f"/api/v1/parts/{part['id']}", json={"unit_cost": 5})
    assert locked.status_code == 400 and set(locked.get_json()["errors"]) == {"unit_cost"}
    # other fields stay editable
    assert client.patch(f"/api/v1/parts/{part['id']}", json={"minimum_stock": 3}).status_code == 200


def test_parts_are_never_deleted_only_deactivated(client, org, users, api_login):
    api_login(users["admin"])
    part = client.post("/api/v1/parts", json={"name": "Old Sensor"}).get_json()["payload"]["part"]
    assert client.delete(f"/api/v1/parts/{part['id']}").status_code == 405
    retired = client.patch(f"/api/v1/parts/{part['id']}", json={"is_active": False})
    assert retired.status_code == 200 and retired.get_json()["payload"]["part"]["is_active"] is False
    assert client.get("/api/v1/parts").get_json()["payload"]["total"] == 0
    assert _names(client.get("/api/v1/parts?filter[active]=false").get_json()["payload"]) == ["Old Sensor"]
    assert client.get("/api/v1/parts?filter[active]=all").get_json()["payload"]["total"] == 1


# --------------------------------------------------------------------------- list, filters and stock state


def test_part_list_search_filters_sorting_and_stock_counts(client, org, users, api_login):
    api_login(users["admin"])
    shelf = _location(org, "Shelf 1")
    drawer = _location(org, "Drawer 2")
    vendor = _vendor(org, "DigiKey")
    asset = _asset(org, "Rover Drive")
    part_type = PartType(organization_id=org.id, name="Electronics")
    _db.session.add(part_type)
    _db.session.commit()

    # ok: plenty on the shelf
    healthy = _part(org, "ESP32 Board", sku="ELC-ESP32", part_type_id=part_type.id, minimum_stock=D("2"))
    _balance(org, healthy, shelf, 10)
    # low: below the minimum but still available
    low = _part(org, "Servo MG996R", sku="ELC-SERVO", minimum_stock=D("10"), is_critical=True)
    _balance(org, low, shelf, 4)
    # out: everything reserved
    out = _part(org, "Battery 18650", sku="ELC-CELL", minimum_stock=D("5"))
    _balance(org, out, drawer, 6, reserved=6)
    # untracked: no minimum, nothing on hand, no history
    untracked = _part(org, "Zip Ties", sku="MSC-ZIP")

    _db.session.add_all(
        [
            PartVendor(part_id=low.id, vendor_id=vendor.id, preferred=True),
            PartAsset(part_id=healthy.id, asset_id=asset.id),
        ]
    )
    _db.session.commit()

    everything = client.get("/api/v1/parts").get_json()["payload"]
    assert _names(everything) == ["Battery 18650", "ESP32 Board", "Servo MG996R", "Zip Ties"]
    assert everything["stock_counts"] == {"low": 1, "out": 1}
    by_id = {item["name"]: item for item in everything["items"]}
    assert by_id["ESP32 Board"]["stock_state"] == "ok"
    assert by_id["Servo MG996R"]["stock_state"] == "low"
    assert by_id["Battery 18650"]["stock_state"] == "out"
    assert by_id["Zip Ties"]["stock_state"] == "untracked"
    assert by_id["Battery 18650"]["totals"] == {"on_hand": 6.0, "reserved": 6.0, "available": 0.0, "ordered": 0.0}
    assert by_id["Servo MG996R"]["preferred_vendor"] == {"id": str(vendor.id), "name": "DigiKey"}

    assert _names(client.get("/api/v1/parts?filter[stock]=low").get_json()["payload"]) == ["Servo MG996R"]
    assert _names(client.get("/api/v1/parts?filter[stock]=out").get_json()["payload"]) == ["Battery 18650"]
    assert _names(client.get("/api/v1/parts?filter[stock]=untracked").get_json()["payload"]) == ["Zip Ties"]
    assert _names(client.get("/api/v1/parts?filter[stock]=low,out").get_json()["payload"]) == ["Battery 18650", "Servo MG996R"]
    # the tab counts ignore the stock filter so the other tabs still show a number
    assert client.get("/api/v1/parts?filter[stock]=out").get_json()["payload"]["stock_counts"] == {"low": 1, "out": 1}

    assert _names(client.get(f"/api/v1/parts?filter[type]={part_type.id}").get_json()["payload"]) == ["ESP32 Board"]
    assert _names(client.get(f"/api/v1/parts?filter[location]={drawer.id}").get_json()["payload"]) == ["Battery 18650"]
    assert _names(client.get(f"/api/v1/parts?filter[vendor]={vendor.id}").get_json()["payload"]) == ["Servo MG996R"]
    assert _names(client.get(f"/api/v1/parts?filter[asset]={asset.id}").get_json()["payload"]) == ["ESP32 Board"]
    assert _names(client.get("/api/v1/parts?filter[critical]=true").get_json()["payload"]) == ["Servo MG996R"]

    assert _names(client.get("/api/v1/parts?q=esp32").get_json()["payload"]) == ["ESP32 Board"]
    assert _names(client.get("/api/v1/parts?q=ELC-").get_json()["payload"]) == ["Battery 18650", "ESP32 Board", "Servo MG996R"]

    ascending = _names(client.get("/api/v1/parts?sort=available").get_json()["payload"])
    assert ascending == ["Battery 18650", "Zip Ties", "Servo MG996R", "ESP32 Board"]
    # ties at zero available stay in name order, so the descending page is not simply reversed
    assert _names(client.get("/api/v1/parts?sort=-available").get_json()["payload"]) == [
        "ESP32 Board",
        "Servo MG996R",
        "Battery 18650",
        "Zip Ties",
    ]
    assert _names(client.get("/api/v1/parts?sort=-name").get_json()["payload"]) == ["Zip Ties", "Servo MG996R", "ESP32 Board", "Battery 18650"]

    bad_sort = client.get("/api/v1/parts?sort=colour")
    assert bad_sort.status_code == 400 and bad_sort.get_json()["code"] == "bad_sort"
    bad_stock = client.get("/api/v1/parts?filter[stock]=plenty")
    assert bad_stock.status_code == 400 and bad_stock.get_json()["code"] == "bad_filter"
    bad_filter = client.get("/api/v1/parts?filter[colour]=red")
    assert bad_filter.status_code == 400 and bad_filter.get_json()["code"] == "bad_filter"

    first = client.get("/api/v1/parts?limit=2").get_json()["payload"]
    assert len(first["items"]) == 2 and first["next_cursor"] and first["total"] == 4
    second = client.get(f"/api/v1/parts?limit=2&cursor={first['next_cursor']}").get_json()["payload"]
    assert _names(second) == ["Servo MG996R", "Zip Ties"] and second["next_cursor"] is None


def test_part_lookup_by_sku_or_qr_code(client, org, users, api_login):
    api_login(users["admin"])
    created = client.post("/api/v1/parts", json={"name": "Limit Switch", "sku": "ELC-LSW", "qr_code": "QR-LSW"})
    part = created.get_json()["payload"]["part"]

    by_sku = client.get("/api/v1/parts/by-code/ELC-LSW")
    assert by_sku.status_code == 200 and by_sku.get_json()["payload"]["part"]["id"] == part["id"]
    by_qr = client.get("/api/v1/parts/by-code/qr-lsw")
    assert by_qr.status_code == 200 and by_qr.get_json()["payload"]["part"]["id"] == part["id"]
    assert client.get("/api/v1/parts/by-code/NOPE").status_code == 404


def test_part_type_names_are_unique_and_types_need_manage(client, org, users, api_login):
    api_login(users["admin"])
    assert client.post("/api/v1/part-types", json={"name": "Hardware"}).status_code == 201
    dupe = client.post("/api/v1/part-types", json={"name": "hardware"})
    assert dupe.status_code == 400 and set(dupe.get_json()["errors"]) == {"name"}
    bad = client.post("/api/v1/part-types", json={"name": "", "color": "blue"})
    assert bad.status_code == 400 and set(bad.get_json()["errors"]) == {"name", "color"}

    api_login(users["member"])
    assert client.get("/api/v1/part-types").status_code == 200
    denied = client.post("/api/v1/part-types", json={"name": "Nope"})
    assert denied.status_code == 403 and denied.get_json()["permission"] == ["inventory.manage"]


# --------------------------------------------------------------------------- vendor and asset links


def test_put_vendors_replaces_the_list_and_allows_one_preferred(client, org, users, api_login):
    api_login(users["admin"])
    digikey = _vendor(org, "DigiKey")
    mouser = _vendor(org, "Mouser")
    part = client.post("/api/v1/parts", json={"name": "Op-Amp"}).get_json()["payload"]["part"]

    saved = client.put(
        f"/api/v1/parts/{part['id']}/vendors",
        json={
            "vendors": [
                {"vendor_id": str(mouser.id), "vendor_part_number": "MOU-1", "url": "https://mouser.com/1", "last_price": 1.25},
                {"vendor_id": str(digikey.id), "vendor_part_number": "DK-1", "preferred": True},
            ]
        },
    )
    assert saved.status_code == 200, saved.get_json()
    body = saved.get_json()["payload"]["part"]
    assert [link["vendor"]["name"] for link in body["vendors"]] == ["DigiKey", "Mouser"]  # preferred first
    assert body["vendors"][0]["preferred"] is True and body["vendors"][1]["last_price"] == 1.25
    assert body["preferred_vendor"] == {"id": str(digikey.id), "name": "DigiKey"}

    replaced = client.put(f"/api/v1/parts/{part['id']}/vendors", json={"vendors": [{"vendor_id": str(mouser.id)}]})
    assert replaced.status_code == 200
    after = replaced.get_json()["payload"]["part"]
    assert [link["vendor"]["name"] for link in after["vendors"]] == ["Mouser"]
    assert after["vendors"][0]["last_price"] == 1.25  # kept: the payload did not name it
    assert after["preferred_vendor"] is None

    cleared = client.put(f"/api/v1/parts/{part['id']}/vendors", json={"vendors": []})
    assert cleared.status_code == 200 and cleared.get_json()["payload"]["part"]["vendors"] == []

    event = AuditEvent.query.filter_by(event_type="part.vendors_changed", entity_id=part["id"]).all()
    assert len(event) == 3 and event[-1].after_json["vendors"] == []


def test_put_vendors_validation(client, org, users, api_login):
    api_login(users["admin"])
    digikey = _vendor(org, "DigiKey")
    mouser = _vendor(org, "Mouser")
    part = client.post("/api/v1/parts", json={"name": "Relay"}).get_json()["payload"]["part"]

    two_preferred = client.put(
        f"/api/v1/parts/{part['id']}/vendors",
        json={"vendors": [{"vendor_id": str(digikey.id), "preferred": True}, {"vendor_id": str(mouser.id), "preferred": True}]},
    )
    assert two_preferred.status_code == 400 and set(two_preferred.get_json()["errors"]) == {"vendors[1].preferred"}

    duplicate = client.put(
        f"/api/v1/parts/{part['id']}/vendors",
        json={"vendors": [{"vendor_id": str(digikey.id)}, {"vendor_id": str(digikey.id)}]},
    )
    assert duplicate.status_code == 400 and set(duplicate.get_json()["errors"]) == {"vendors[1].vendor_id"}

    bad = client.put(
        f"/api/v1/parts/{part['id']}/vendors",
        json={"vendors": [{"url": "mouser.com"}, {"vendor_id": "11111111-1111-1111-1111-111111111111"}, "nope"]},
    )
    assert bad.status_code == 400
    assert set(bad.get_json()["errors"]) == {"vendors[0].vendor_id", "vendors[0].url", "vendors[1].vendor_id", "vendors[2]"}

    not_a_list = client.put(f"/api/v1/parts/{part['id']}/vendors", json={"vendors": "digikey"})
    assert not_a_list.status_code == 400 and set(not_a_list.get_json()["errors"]) == {"vendors"}


def test_put_assets_replaces_the_list_and_hides_private_projects(client, org, users, api_login):
    api_login(users["admin"])
    pump = _asset(org, "Coolant Pump")
    press = _asset(org, "Arbor Press")
    part = client.post("/api/v1/parts", json={"name": "Pump Seal"}).get_json()["payload"]["part"]

    saved = client.put(f"/api/v1/parts/{part['id']}/assets", json={"asset_ids": [str(pump.id), str(press.id), str(pump.id)]})
    assert saved.status_code == 200, saved.get_json()
    assert sorted(a["name"] for a in saved.get_json()["payload"]["part"]["assets"]) == ["Arbor Press", "Coolant Pump"]

    replaced = client.put(f"/api/v1/parts/{part['id']}/assets", json={"asset_ids": [str(press.id)]})
    assert [a["name"] for a in replaced.get_json()["payload"]["part"]["assets"]] == ["Arbor Press"]
    assert client.put(f"/api/v1/parts/{part['id']}/assets", json={"asset_ids": []}).get_json()["payload"]["part"]["assets"] == []

    unknown = client.put(f"/api/v1/parts/{part['id']}/assets", json={"asset_ids": ["11111111-1111-1111-1111-111111111111"]})
    assert unknown.status_code == 400 and set(unknown.get_json()["errors"]) == {"asset_ids"}

    # an asset inside a private project the inventory manager is not a member of
    secret = OpsProject(organization_id=org.id, name="Secret Rover", code="SEC", visibility="private")
    _db.session.add(secret)
    _db.session.commit()
    hidden = _asset(org, "Secret Jig", project_id=secret.id)
    manager = make_user("Ines Inventory", "ines@uiowa.edu", ops_role="inventory_manager", org=org)
    api_login(manager)
    denied = client.put(f"/api/v1/parts/{part['id']}/assets", json={"asset_ids": [str(hidden.id)]})
    assert denied.status_code == 400 and set(denied.get_json()["errors"]) == {"asset_ids"}


# --------------------------------------------------------------------------- detail extras


def test_part_detail_reports_balances_and_open_purchase_requests(client, org, users, api_login):
    api_login(users["admin"])
    shelf = _location(org, "Shelf 1")
    drawer = _location(org, "Drawer 2")
    part = _part(org, "Stepper Motor", minimum_stock=D("2"))
    _balance(org, part, shelf, 5, reserved=2)
    _balance(org, part, drawer, 1)
    request_row = PurchaseRequest(
        organization_id=org.id, number=7, title="Motors", requester_user_id=users["admin"].id, status="ordered"
    )
    _db.session.add(request_row)
    _db.session.flush()
    _db.session.add(
        PurchaseRequestItem(
            purchase_request_id=request_row.id, part_id=part.id, description="Stepper Motor", quantity=D("10"), received_quantity=D("4")
        )
    )
    _db.session.commit()

    body = client.get(f"/api/v1/parts/{part.id}").get_json()["payload"]["part"]
    assert body["totals"] == {"on_hand": 6.0, "reserved": 2.0, "available": 4.0, "ordered": 6.0}
    assert body["stock_state"] == "ok"
    assert body["balances"] == [
        {"location": {"id": str(drawer.id), "name": "Drawer 2"}, "on_hand": 1.0, "reserved": 0.0, "available": 1.0},
        {"location": {"id": str(shelf.id), "name": "Shelf 1"}, "on_hand": 5.0, "reserved": 2.0, "available": 3.0},
    ]
    assert body["open_purchase_requests"] == [
        {"id": str(request_row.id), "number": 7, "display_number": "PR-7", "title": "Motors", "status": "ordered", "outstanding_quantity": 6.0}
    ]

    inventory = client.get(f"/api/v1/parts/{part.id}/inventory")
    assert inventory.status_code == 200
    payload = inventory.get_json()["payload"]
    assert payload["totals"] == body["totals"] and payload["balances"] == body["balances"]


# --------------------------------------------------------------------------- permissions and tenancy


def test_part_permissions(client, org, users, requester, api_login):
    api_login(users["admin"])
    part = client.post("/api/v1/parts", json={"name": "Grease"}).get_json()["payload"]["part"]

    # full_member holds inventory.read but not inventory.manage
    api_login(users["member"])
    assert client.get("/api/v1/parts").status_code == 200
    assert client.get(f"/api/v1/parts/{part['id']}").status_code == 200
    assert client.get("/api/v1/parts/by-code/nothing").status_code == 404
    denied = client.post("/api/v1/parts", json={"name": "Nope"})
    assert denied.status_code == 403 and denied.get_json()["permission"] == ["inventory.manage"]
    assert client.patch(f"/api/v1/parts/{part['id']}", json={"name": "Nope"}).status_code == 403
    assert client.put(f"/api/v1/parts/{part['id']}/vendors", json={"vendors": []}).status_code == 403
    assert client.put(f"/api/v1/parts/{part['id']}/assets", json={"asset_ids": []}).status_code == 403

    # requester holds neither key
    api_login(requester)
    assert client.get("/api/v1/parts").status_code == 403
    assert client.get(f"/api/v1/parts/{part['id']}").status_code == 403
    assert client.get("/api/v1/part-types").status_code == 403

    manager = make_user("Ines Inventory", "ines@uiowa.edu", ops_role="inventory_manager", org=org)
    api_login(manager)
    assert client.post("/api/v1/parts", json={"name": "Loctite"}).status_code == 201


def test_part_cross_organization_ids_are_404(client, org, users, api_login):
    other = _foreign_org()
    foreign = Part(organization_id=other.id, name="Foreign Widget", sku="FGN-1")
    _db.session.add(foreign)
    foreign_type = PartType(organization_id=other.id, name="Foreign Type")
    _db.session.add(foreign_type)
    _db.session.commit()

    api_login(users["admin"])
    assert client.get(f"/api/v1/parts/{foreign.id}").status_code == 404
    assert client.patch(f"/api/v1/parts/{foreign.id}", json={"name": "Hijack"}).status_code == 404
    assert client.put(f"/api/v1/parts/{foreign.id}/vendors", json={"vendors": []}).status_code == 404
    assert client.put(f"/api/v1/parts/{foreign.id}/assets", json={"asset_ids": []}).status_code == 404
    assert client.get(f"/api/v1/parts/{foreign.id}/inventory").status_code == 404
    assert client.get(f"/api/v1/parts/{foreign.id}/transactions").status_code == 404
    assert client.get("/api/v1/parts/not-a-uuid").status_code == 404
    assert client.get("/api/v1/parts/by-code/FGN-1").status_code == 404
    assert client.get("/api/v1/parts").get_json()["payload"]["total"] == 0
    assert client.get("/api/v1/part-types").get_json()["payload"]["total"] == 0

    borrowed = client.post("/api/v1/parts", json={"name": "Mine", "part_type_id": str(foreign_type.id)})
    assert borrowed.status_code == 400 and set(borrowed.get_json()["errors"]) == {"part_type_id"}
    assert Part.query.get(foreign.id).name == "Foreign Widget"


# --------------------------------------------------------------------------- service level


def test_part_service_authorization_and_lookup(ctx_admin, ctx_member, ctx_requester, org):
    part = parts_service.create(ctx_admin, {"name": "Service Part", "sku": "SVC-1"})
    assert part.organization_id == org.id and part.created_by_user_id == ctx_admin.user.id
    with pytest.raises(Forbidden):
        parts_service.create(ctx_member, {"name": "Denied"})
    with pytest.raises(Forbidden):
        parts_service.update(ctx_member, part, {"name": "Denied"})
    with pytest.raises(Forbidden):
        parts_service.get(ctx_requester, part.id)
    with pytest.raises(ValidationErrors) as exc:
        parts_service.create(ctx_admin, {"name": "Clash", "sku": "svc-1"})
    assert set(exc.value.errors) == {"sku"}

    other = _foreign_org()
    foreign = Part(organization_id=other.id, name="Foreign")
    _db.session.add(foreign)
    _db.session.commit()
    with pytest.raises(NotFound):
        parts_service.get(ctx_admin, foreign.id)
    with pytest.raises(NotFound):
        parts_service.update(ctx_admin, foreign, {"name": "Hijack"})
