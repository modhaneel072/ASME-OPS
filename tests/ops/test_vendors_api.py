import pytest

from asme.extensions import db as _db
from asme.ops.models import AuditEvent, Organization, Vendor
from asme.ops.services import vendors as vendor_service
from asme.ops.validation import ValidationErrors
from asme.services.errors import Forbidden, NotFound
from tests.ops.conftest import make_user

VENDOR = {
    "name": "McMaster-Carr",
    "contact_name": "Sales Desk",
    "email": "Sales@McMaster.com",
    "phone": "+1 630 555 0100",
    "website": "https://www.mcmaster.com",
    "address": {"line1": "600 N County Line Rd", "city": "Elmhurst", "state": "IL"},
    "notes": "Net 30.",
}


def _foreign_vendor():
    other = Organization(name="Other Chapter", slug="other-chapter")
    _db.session.add(other)
    _db.session.flush()
    foreign = Vendor(organization_id=other.id, name="Foreign Supply")
    _db.session.add(foreign)
    _db.session.commit()
    return foreign


# --------------------------------------------------------------------------- API


def test_vendor_crud_roundtrip_with_audit(client, org, users, api_login):
    api_login(users["admin"])

    created = client.post("/api/v1/vendors", json=VENDOR)
    assert created.status_code == 201, created.get_json()
    body = created.get_json()["payload"]["vendor"]
    assert body["name"] == "McMaster-Carr"
    assert body["email"] == "sales@mcmaster.com"  # normalised
    assert body["address"] == VENDOR["address"]
    assert body["is_active"] is True
    assert set(body) == {"id", "name", "contact_name", "email", "phone", "website", "address", "notes", "is_active", "created_at", "updated_at"}
    vendor_id = body["id"]

    fetched = client.get(f"/api/v1/vendors/{vendor_id}")
    assert fetched.status_code == 200
    assert fetched.get_json()["payload"]["vendor"] == body

    patched = client.patch(f"/api/v1/vendors/{vendor_id}", json={"phone": "555-0199", "notes": None, "address": {"city": "Chicago"}})
    assert patched.status_code == 200
    after = patched.get_json()["payload"]["vendor"]
    assert after["phone"] == "555-0199" and after["notes"] is None and after["address"] == {"city": "Chicago"}

    created_event = AuditEvent.query.filter_by(event_type="vendor.created", entity_id=vendor_id).one()
    assert created_event.entity_type == "vendor" and created_event.actor_user_id == users["admin"].id
    assert created_event.after_json["name"] == "McMaster-Carr"
    updated_event = AuditEvent.query.filter_by(event_type="vendor.updated", entity_id=vendor_id).one()
    assert updated_event.before_json["phone"] == "+1 630 555 0100" and updated_event.after_json["phone"] == "555-0199"
    assert sorted(updated_event.metadata_json["changed_fields"]) == ["address_json", "notes", "phone"]


def test_vendor_validation_lists_every_bad_field(client, org, users, api_login):
    api_login(users["admin"])
    bad = client.post(
        "/api/v1/vendors",
        json={"name": "", "email": "not-an-email", "website": "mcmaster.com", "phone": "x" * 41, "address": ["not", "an", "object"]},
    )
    assert bad.status_code == 400
    payload = bad.get_json()
    assert payload["code"] == "validation"
    assert set(payload["errors"]) == {"name", "email", "website", "phone", "address"}

    missing = client.post("/api/v1/vendors", json={})
    assert missing.status_code == 400 and set(missing.get_json()["errors"]) == {"name"}


def test_vendor_name_is_unique_per_org_case_insensitively(client, org, users, api_login):
    api_login(users["admin"])
    assert client.post("/api/v1/vendors", json={"name": "DigiKey"}).status_code == 201
    dupe = client.post("/api/v1/vendors", json={"name": "digikey"})
    assert dupe.status_code == 400 and set(dupe.get_json()["errors"]) == {"name"}

    second = client.post("/api/v1/vendors", json={"name": "Amazon Business"}).get_json()["payload"]["vendor"]
    rename = client.patch(f"/api/v1/vendors/{second['id']}", json={"name": "DIGIKEY"})
    assert rename.status_code == 400 and set(rename.get_json()["errors"]) == {"name"}
    # renaming to itself (case change only) is allowed
    same = client.patch(f"/api/v1/vendors/{second['id']}", json={"name": "Amazon Business"})
    assert same.status_code == 200


def test_vendor_deactivate_via_patch_and_no_delete(client, org, users, api_login):
    api_login(users["admin"])
    vendor = client.post("/api/v1/vendors", json={"name": "Old Supplier"}).get_json()["payload"]["vendor"]
    retired = client.patch(f"/api/v1/vendors/{vendor['id']}", json={"is_active": False})
    assert retired.status_code == 200 and retired.get_json()["payload"]["vendor"]["is_active"] is False
    assert client.delete(f"/api/v1/vendors/{vendor['id']}").status_code == 405

    active_only = client.get("/api/v1/vendors?filter[active]=true").get_json()["payload"]
    assert active_only["items"] == [] and active_only["total"] == 0
    inactive = client.get("/api/v1/vendors?filter[active]=false").get_json()["payload"]
    assert [v["name"] for v in inactive["items"]] == ["Old Supplier"]
    everything = client.get("/api/v1/vendors").get_json()["payload"]
    assert everything["total"] == 1

    bad_filter = client.get("/api/v1/vendors?filter[active]=maybe")
    assert bad_filter.status_code == 400 and bad_filter.get_json()["code"] == "bad_filter"
    unknown_filter = client.get("/api/v1/vendors?filter[colour]=red")
    assert unknown_filter.status_code == 400 and unknown_filter.get_json()["code"] == "bad_filter"


def test_vendor_list_search_sort_and_pagination(client, org, users, api_login):
    api_login(users["admin"])
    for name, contact in (("Zeta Tools", "Ann"), ("alpha Metals", "Bob"), ("Midwest Fasteners", "Cy Zeta")):
        assert client.post("/api/v1/vendors", json={"name": name, "contact_name": contact}).status_code == 201

    by_name = client.get("/api/v1/vendors").get_json()["payload"]
    assert [v["name"] for v in by_name["items"]] == ["alpha Metals", "Midwest Fasteners", "Zeta Tools"]
    assert by_name["total"] == 3 and by_name["next_cursor"] is None
    desc = client.get("/api/v1/vendors?sort=-name").get_json()["payload"]
    assert [v["name"] for v in desc["items"]] == ["Zeta Tools", "Midwest Fasteners", "alpha Metals"]
    by_created = client.get("/api/v1/vendors?sort=created_at").get_json()["payload"]
    assert [v["name"] for v in by_created["items"]] == ["Zeta Tools", "alpha Metals", "Midwest Fasteners"]
    bad_sort = client.get("/api/v1/vendors?sort=phone")
    assert bad_sort.status_code == 400 and bad_sort.get_json()["code"] == "bad_sort"

    searched = client.get("/api/v1/vendors?q=zeta").get_json()["payload"]
    assert sorted(v["name"] for v in searched["items"]) == ["Midwest Fasteners", "Zeta Tools"]

    first = client.get("/api/v1/vendors?limit=2").get_json()["payload"]
    assert len(first["items"]) == 2 and first["next_cursor"] and first["total"] == 3
    second = client.get(f"/api/v1/vendors?limit=2&cursor={first['next_cursor']}").get_json()["payload"]
    assert [v["name"] for v in second["items"]] == ["Zeta Tools"] and second["next_cursor"] is None


def test_vendor_permissions(client, org, users, requester, api_login):
    api_login(users["admin"])
    vendor = client.post("/api/v1/vendors", json={"name": "Grainger"}).get_json()["payload"]["vendor"]

    # full_member holds vendor.read but not vendor.manage
    api_login(users["member"])
    assert client.get("/api/v1/vendors").status_code == 200
    assert client.get(f"/api/v1/vendors/{vendor['id']}").status_code == 200
    denied = client.post("/api/v1/vendors", json={"name": "Nope"})
    assert denied.status_code == 403 and denied.get_json()["permission"] == ["vendor.manage"]
    assert client.patch(f"/api/v1/vendors/{vendor['id']}", json={"name": "Nope"}).status_code == 403

    # requester holds neither key
    api_login(requester)
    assert client.get("/api/v1/vendors").status_code == 403
    assert client.get(f"/api/v1/vendors/{vendor['id']}").status_code == 403

    # inventory_manager holds vendor.manage at chapter scope
    manager = make_user("Ines Inventory", "ines@uiowa.edu", ops_role="inventory_manager", org=org)
    api_login(manager)
    assert client.post("/api/v1/vendors", json={"name": "Fastenal"}).status_code == 201


def test_vendor_cross_organization_ids_are_404(client, org, users, api_login):
    foreign = _foreign_vendor()
    api_login(users["admin"])
    assert client.get(f"/api/v1/vendors/{foreign.id}").status_code == 404
    assert client.patch(f"/api/v1/vendors/{foreign.id}", json={"name": "Hijack"}).status_code == 404
    assert client.get("/api/v1/vendors/not-a-uuid").status_code == 404
    listed = client.get("/api/v1/vendors").get_json()["payload"]
    assert listed["total"] == 0
    assert Vendor.query.get(foreign.id).name == "Foreign Supply"


# --------------------------------------------------------------------------- service


def test_vendor_service_authorization_and_lookup(ctx_admin, ctx_member, ctx_requester, org):
    vendor = vendor_service.create(ctx_admin, {"name": "Service Co"})
    assert vendor.organization_id == org.id and vendor.created_by_user_id == ctx_admin.user.id
    with pytest.raises(Forbidden):
        vendor_service.create(ctx_member, {"name": "Denied"})
    with pytest.raises(Forbidden):
        vendor_service.update(ctx_member, vendor, {"name": "Denied"})
    with pytest.raises(Forbidden):
        vendor_service.get(ctx_requester, vendor.id)
    with pytest.raises(ValidationErrors) as exc:
        vendor_service.create(ctx_admin, {"name": "Service Co"})
    assert set(exc.value.errors) == {"name"}
    foreign = _foreign_vendor()
    with pytest.raises(NotFound):
        vendor_service.get(ctx_admin, foreign.id)
    with pytest.raises(NotFound):
        vendor_service.update(ctx_admin, foreign, {"name": "Hijack"})
