"""API tests for ``/api/v1/locations`` (nested locations, default location, usage rules)."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from asme.extensions import db as _db
from asme.ops.models import Asset, AuditEvent, Location, Organization, WorkOrder
from asme.ops.services import locations as locations_service
from asme.services.errors import Forbidden

LOCATION_KEYS = {
    "id",
    "name",
    "description",
    "parent_id",
    "building",
    "room",
    "address",
    "is_default",
    "is_active",
    "path",
    "asset_count",
    "open_work_order_count",
    "created_at",
    "updated_at",
}


def _create(client, **payload):
    response = client.post("/api/v1/locations", json=payload)
    assert response.status_code == 201, response.get_json()
    return response.get_json()["payload"]["location"]


def _items(client, url="/api/v1/locations"):
    response = client.get(url)
    assert response.status_code == 200, response.get_json()
    return response.get_json()["payload"]


def _names(client, url="/api/v1/locations"):
    return [item["name"] for item in _items(client, url)["items"]]


def _default(org):
    return Location.query.filter_by(organization_id=org.id, is_default=True).one()


def _foreign_location():
    other = Organization(name="Other Chapter", slug="other")
    _db.session.add(other)
    _db.session.flush()
    foreign = Location(organization_id=other.id, name="Elsewhere")
    _db.session.add(foreign)
    _db.session.commit()
    return foreign


def _work_order(org, user, number, **kw):
    row = WorkOrder(organization_id=org.id, number=number, title=f"WO {number}", created_by_user_id=user.id, **kw)
    _db.session.add(row)
    _db.session.commit()
    return row


# --------------------------------------------------------------------------- reads


def test_list_shows_seeded_default_location(client, org, users, api_login):
    api_login(users["admin"])
    payload = _items(client)
    assert payload["total"] == 1 and payload["next_cursor"] is None
    (general,) = payload["items"]
    assert set(general) == LOCATION_KEYS
    assert general["name"] == "General"
    assert general["is_default"] is True and general["is_active"] is True
    assert general["path"] == ["General"] and general["parent_id"] is None
    assert general["asset_count"] == 0 and general["open_work_order_count"] == 0
    assert general["created_at"].endswith("Z")


def test_create_nested_location_computes_path_and_audits(client, org, users, api_login):
    api_login(users["admin"])
    lab = _create(client, name="Robotics Lab", building="Seamans Center", room="1245", address={"street": "103 S Capitol St"})
    assert lab["path"] == ["Robotics Lab"]
    assert lab["building"] == "Seamans Center" and lab["room"] == "1245"
    assert lab["address"] == {"street": "103 S Capitol St"}
    assert lab["is_default"] is False and lab["is_active"] is True

    bench = _create(client, name="Bench 2", parent_id=lab["id"], description="Soldering bench")
    assert bench["parent_id"] == lab["id"]
    assert bench["path"] == ["Robotics Lab", "Bench 2"]
    assert bench["description"] == "Soldering bench"

    fetched = client.get(f"/api/v1/locations/{bench['id']}")
    assert fetched.status_code == 200
    assert fetched.get_json()["payload"]["location"] == bench

    events = AuditEvent.query.filter_by(event_type="location.created").order_by(AuditEvent.occurred_at).all()
    assert [event.entity_id for event in events] == [lab["id"], bench["id"]]
    assert all(event.actor_user_id == users["admin"].id and event.entity_type == "location" for event in events)
    assert events[1].before_json is None
    assert events[1].after_json["parent_location_id"] == lab["id"]
    assert events[1].after_json["name"] == "Bench 2"


def test_counts_assets_and_open_work_orders(client, org, users, api_login):
    api_login(users["admin"])
    lab = _create(client, name="Robotics Lab")
    other = _create(client, name="Elsewhere")
    lab_id = UUID(lab["id"])
    _db.session.add_all(
        [
            Asset(organization_id=org.id, name="Printer", location_id=lab_id),
            Asset(organization_id=org.id, name="Scope", location_id=lab_id),
            Asset(organization_id=org.id, name="Charger", location_id=UUID(other["id"])),
        ]
    )
    _db.session.commit()
    for number, status in enumerate(("draft", "open", "in_progress", "on_hold", "done", "canceled", "skipped"), start=1):
        _work_order(org, users["admin"], number, location_id=lab_id, status=status)
    _work_order(org, users["admin"], 99, status="open")  # no location

    by_name = {item["name"]: item for item in _items(client)["items"]}
    assert by_name["Robotics Lab"]["asset_count"] == 2
    assert by_name["Robotics Lab"]["open_work_order_count"] == 4
    assert by_name["Elsewhere"]["asset_count"] == 1 and by_name["Elsewhere"]["open_work_order_count"] == 0
    assert by_name["General"]["asset_count"] == 0 and by_name["General"]["open_work_order_count"] == 0

    detail = client.get(f"/api/v1/locations/{lab['id']}").get_json()["payload"]["location"]
    assert detail["asset_count"] == 2 and detail["open_work_order_count"] == 4


def test_list_filters_search_sort_and_pagination(client, org, users, api_login):
    api_login(users["admin"])
    shop = _create(client, name="Machine Shop", building="Seamans Center", room="1140")
    lab = _create(client, name="Robotics Lab", building="Seamans Center")
    _create(client, name="Bench 2", parent_id=lab["id"], room="Corner")
    storage = _create(client, name="ASME Storage", building="Annex")
    deactivated = client.patch(f"/api/v1/locations/{storage['id']}", json={"is_active": False})
    assert deactivated.status_code == 200
    assert deactivated.get_json()["payload"]["location"]["is_active"] is False

    assert _names(client) == ["Bench 2", "General", "Machine Shop", "Robotics Lab"]
    assert _names(client, "/api/v1/locations?sort=-name") == ["Robotics Lab", "Machine Shop", "General", "Bench 2"]
    assert _names(client, "/api/v1/locations?sort=created_at") == ["General", "Machine Shop", "Robotics Lab", "Bench 2"]
    assert _names(client, "/api/v1/locations?sort=-created_at") == ["Bench 2", "Robotics Lab", "Machine Shop", "General"]
    assert _names(client, "/api/v1/locations?filter[active]=false") == ["ASME Storage"]
    assert _names(client, "/api/v1/locations?filter[active]=true") == ["Bench 2", "General", "Machine Shop", "Robotics Lab"]
    assert _names(client, "/api/v1/locations?q=seamans") == ["Machine Shop", "Robotics Lab"]
    assert _names(client, "/api/v1/locations?q=CORNER") == ["Bench 2"]
    assert _names(client, "/api/v1/locations?q=1140") == ["Machine Shop"]
    assert _names(client, "/api/v1/locations?q=%25") == []
    assert _names(client, "/api/v1/locations?filter[parent]=root") == ["General", "Machine Shop", "Robotics Lab"]
    assert _names(client, f"/api/v1/locations?filter[parent]={lab['id']}") == ["Bench 2"]
    assert _names(client, f"/api/v1/locations?filter[parent]={shop['id']}") == []

    page = _items(client, "/api/v1/locations?limit=2")
    assert [item["name"] for item in page["items"]] == ["Bench 2", "General"]
    assert page["total"] == 4 and page["next_cursor"]
    rest = _items(client, f"/api/v1/locations?limit=2&cursor={page['next_cursor']}")
    assert [item["name"] for item in rest["items"]] == ["Machine Shop", "Robotics Lab"]
    assert rest["next_cursor"] is None

    for url in (
        "/api/v1/locations?filter[colour]=red",
        "/api/v1/locations?sort=room",
        "/api/v1/locations?filter[parent]=nope",
        "/api/v1/locations?filter[active]=maybe",
        "/api/v1/locations?view=blob",
    ):
        response = client.get(url)
        assert response.status_code == 400, url
        assert response.get_json()["ok"] is False


def test_tree_view_nests_children(client, org, users, api_login):
    api_login(users["admin"])
    lab = _create(client, name="Robotics Lab")
    bench = _create(client, name="Bench 2", parent_id=lab["id"])
    _create(client, name="Drawer A", parent_id=bench["id"])
    _create(client, name="Test Field")
    closed = _create(client, name="Closed Wing")
    client.patch(f"/api/v1/locations/{closed['id']}", json={"is_active": False})

    payload = _items(client, "/api/v1/locations?view=tree")
    assert set(payload) == {"items"}
    roots = {item["name"]: item for item in payload["items"]}
    assert list(roots) == ["General", "Robotics Lab", "Test Field"]
    assert set(roots["General"]) == LOCATION_KEYS | {"children"}
    assert roots["General"]["children"] == []
    assert [child["name"] for child in roots["Robotics Lab"]["children"]] == ["Bench 2"]
    drawer = roots["Robotics Lab"]["children"][0]["children"][0]
    assert drawer["name"] == "Drawer A" and drawer["path"] == ["Robotics Lab", "Bench 2", "Drawer A"] and drawer["children"] == []

    with_inactive = _items(client, "/api/v1/locations?view=tree&filter[active]=false")
    assert [item["name"] for item in with_inactive["items"]] == ["Closed Wing"]

    searched = _items(client, "/api/v1/locations?view=tree&q=drawer")
    assert [item["name"] for item in searched["items"]] == ["Robotics Lab"]
    assert searched["items"][0]["children"][0]["children"][0]["name"] == "Drawer A"


# --------------------------------------------------------------------------- writes


def test_create_validation_lists_every_bad_field(client, org, users, api_login):
    api_login(users["admin"])
    response = client.post(
        "/api/v1/locations",
        json={"name": "", "building": "b" * 161, "room": "r" * 81, "parent_id": "not-a-uuid", "address": "Iowa City"},
    )
    assert response.status_code == 400
    body = response.get_json()
    assert body["code"] == "validation"
    assert set(body["errors"]) == {"name", "building", "room", "parent_id", "address"}

    missing = client.post("/api/v1/locations", json={})
    assert missing.status_code == 400
    assert missing.get_json()["errors"] == {"name": "This field is required."}
    assert Location.query.filter_by(organization_id=org.id).count() == 1


def test_create_rejects_unknown_or_foreign_parent(client, org, users, api_login):
    api_login(users["admin"])
    foreign = _foreign_location()
    for parent_id in (str(foreign.id), str(uuid4())):
        response = client.post("/api/v1/locations", json={"name": "Orphan", "parent_id": parent_id})
        assert response.status_code == 400, response.get_json()
        assert set(response.get_json()["errors"]) == {"parent_id"}
    assert Location.query.filter_by(name="Orphan").count() == 0


def test_patch_updates_fields_and_audits(client, org, users, api_login):
    api_login(users["admin"])
    lab = _create(client, name="Robotics Lab", building="Seamans")
    response = client.patch(
        f"/api/v1/locations/{lab['id']}",
        json={"name": "Robotics Laboratory", "room": "1245", "building": "", "address": {"campus": "East"}},
    )
    assert response.status_code == 200
    body = response.get_json()["payload"]["location"]
    assert body["name"] == "Robotics Laboratory" and body["room"] == "1245"
    assert body["building"] is None and body["address"] == {"campus": "East"}
    assert body["path"] == ["Robotics Laboratory"]

    event = AuditEvent.query.filter_by(event_type="location.updated").one()
    assert event.entity_id == lab["id"] and event.actor_user_id == users["admin"].id
    assert event.before_json["name"] == "Robotics Lab" and event.after_json["name"] == "Robotics Laboratory"
    assert event.before_json["building"] == "Seamans" and event.after_json["building"] is None

    unchanged = client.patch(f"/api/v1/locations/{lab['id']}", json={})
    assert unchanged.status_code == 200
    assert AuditEvent.query.filter_by(event_type="location.updated").count() == 1

    bad = client.patch(f"/api/v1/locations/{lab['id']}", json={"name": "x" * 161, "is_default": True, "is_active": "maybe"})
    assert bad.status_code == 400
    assert set(bad.get_json()["errors"]) == {"name", "is_default", "is_active"}


def test_patch_rejects_parent_cycles(client, org, users, api_login):
    api_login(users["admin"])
    a = _create(client, name="A")
    b = _create(client, name="B", parent_id=a["id"])
    c = _create(client, name="C", parent_id=b["id"])
    for parent_id in (a["id"], b["id"], c["id"]):
        response = client.patch(f"/api/v1/locations/{a['id']}", json={"parent_id": parent_id})
        assert response.status_code == 400, response.get_json()
        assert set(response.get_json()["errors"]) == {"parent_id"}
    assert _db.session.get(Location, UUID(a["id"])).parent_location_id is None

    foreign = _foreign_location()
    stolen = client.patch(f"/api/v1/locations/{a['id']}", json={"parent_id": str(foreign.id)})
    assert stolen.status_code == 400 and set(stolen.get_json()["errors"]) == {"parent_id"}

    d = _create(client, name="D")
    moved = client.patch(f"/api/v1/locations/{c['id']}", json={"parent_id": d["id"]})
    assert moved.status_code == 200
    assert moved.get_json()["payload"]["location"]["path"] == ["D", "C"]
    detached = client.patch(f"/api/v1/locations/{b['id']}", json={"parent_id": None})
    assert detached.status_code == 200
    assert detached.get_json()["payload"]["location"]["path"] == ["B"]


def test_default_location_cannot_be_deactivated_or_deleted(client, org, users, api_login):
    api_login(users["admin"])
    general_id = _default(org).id
    deactivate = client.patch(f"/api/v1/locations/{general_id}", json={"is_active": False})
    assert deactivate.status_code == 400
    assert set(deactivate.get_json()["errors"]) == {"is_active"}
    delete = client.delete(f"/api/v1/locations/{general_id}")
    assert delete.status_code == 409
    assert delete.get_json()["code"] == "default_location_protected"
    assert _default(org).id == general_id and _default(org).is_active is True


def test_delete_removes_unused_location_and_blocks_in_use(client, org, users, api_login):
    api_login(users["admin"])
    parent = _create(client, name="Parent")
    child = _create(client, name="Child", parent_id=parent["id"])
    with_asset = _create(client, name="Asset Home")
    with_work_order = _create(client, name="Work Site")
    _db.session.add(Asset(organization_id=org.id, name="3D Printer 01", location_id=UUID(with_asset["id"])))
    _db.session.commit()
    _work_order(org, users["admin"], 1, location_id=UUID(with_work_order["id"]), status="done")

    for item, expected in ((parent, {"children": 1}), (with_asset, {"assets": 1}), (with_work_order, {"work_orders": 1})):
        response = client.delete(f"/api/v1/locations/{item['id']}")
        assert response.status_code == 409, response.get_json()
        body = response.get_json()
        assert body["code"] == "location_in_use"
        assert {key: value for key, value in body["usage"].items() if value} == expected
    assert Location.query.filter_by(organization_id=org.id).count() == 5

    removed = client.delete(f"/api/v1/locations/{child['id']}")
    assert removed.status_code == 200
    assert removed.get_json()["payload"] == {"id": child["id"], "deleted": True}
    assert _db.session.get(Location, UUID(child["id"])) is None
    event = AuditEvent.query.filter_by(event_type="location.deleted").one()
    assert event.entity_id == child["id"] and event.before_json["name"] == "Child" and event.after_json is None
    assert client.get(f"/api/v1/locations/{child['id']}").status_code == 404

    # the parent is childless now and can go as well
    assert client.delete(f"/api/v1/locations/{parent['id']}").status_code == 200
    assert Location.query.filter_by(organization_id=org.id).count() == 3


def test_make_default_switches_default_and_audits(client, org, users, api_login):
    api_login(users["admin"])
    general_id = _default(org).id
    lab = _create(client, name="Robotics Lab")

    response = client.post(f"/api/v1/locations/{lab['id']}/make-default", json={})
    assert response.status_code == 200
    assert response.get_json()["payload"]["location"]["is_default"] is True
    assert _default(org).id == UUID(lab["id"])
    assert Location.query.filter_by(organization_id=org.id, is_default=True).count() == 1
    assert _db.session.get(Location, general_id).is_default is False
    event = AuditEvent.query.filter_by(event_type="location.default_changed").one()
    assert event.entity_id == lab["id"] and event.actor_user_id == users["admin"].id
    assert event.before_json == {"default_location_id": str(general_id)}
    assert event.after_json == {"default_location_id": lab["id"]}

    again = client.post(f"/api/v1/locations/{lab['id']}/make-default", json={})
    assert again.status_code == 200
    assert AuditEvent.query.filter_by(event_type="location.default_changed").count() == 1

    # the former default is an ordinary unused location now
    assert client.delete(f"/api/v1/locations/{general_id}").status_code == 200

    closed = _create(client, name="Closed Room")
    assert client.patch(f"/api/v1/locations/{closed['id']}", json={"is_active": False}).status_code == 200
    refused = client.post(f"/api/v1/locations/{closed['id']}/make-default", json={})
    assert refused.status_code == 409 and refused.get_json()["code"] == "location_inactive"
    assert _default(org).id == UUID(lab["id"])


# --------------------------------------------------------------------------- authz


def test_permissions_by_role(client, org, users, requester, api_login):
    general_id = _default(org).id

    api_login(users["member"])  # full_member: location.read at chapter, no location.manage
    assert client.get("/api/v1/locations").status_code == 200
    assert client.get(f"/api/v1/locations/{general_id}").status_code == 200
    denied = client.post("/api/v1/locations", json={"name": "Nope"})
    assert denied.status_code == 403 and denied.get_json()["permission"] == ["location.manage"]
    assert client.patch(f"/api/v1/locations/{general_id}", json={"name": "Nope"}).status_code == 403
    assert client.delete(f"/api/v1/locations/{general_id}").status_code == 403
    assert client.post(f"/api/v1/locations/{general_id}/make-default", json={}).status_code == 403
    assert Location.query.filter_by(organization_id=org.id).count() == 1
    assert _default(org).name == "General"

    api_login(requester)  # requester: no location.read at all
    forbidden = client.get("/api/v1/locations")
    assert forbidden.status_code == 403 and forbidden.get_json()["permission"] == ["location.read"]
    assert client.get(f"/api/v1/locations/{general_id}").status_code == 403
    assert client.get("/api/v1/locations?view=tree").status_code == 403


def test_services_enforce_permissions_without_routes(org, ctx_requester, ctx_member):
    general = _default(org)
    with pytest.raises(Forbidden):
        locations_service.create(ctx_requester, {"name": "Nope"})
    with pytest.raises(Forbidden):
        locations_service.update(ctx_member, general, {"name": "Nope"})
    with pytest.raises(Forbidden):
        locations_service.delete(ctx_member, general)
    with pytest.raises(Forbidden):
        locations_service.make_default(ctx_member, general)
    assert Location.query.filter_by(organization_id=org.id).count() == 1


def test_foreign_and_malformed_ids_are_404(client, org, users, api_login):
    api_login(users["admin"])
    foreign = _foreign_location()
    for target in (str(foreign.id), str(uuid4()), "not-a-uuid"):
        assert client.get(f"/api/v1/locations/{target}").status_code == 404, target
        assert client.patch(f"/api/v1/locations/{target}", json={"name": "Hijack"}).status_code == 404, target
        assert client.delete(f"/api/v1/locations/{target}").status_code == 404, target
        assert client.post(f"/api/v1/locations/{target}/make-default", json={}).status_code == 404, target
    _db.session.refresh(foreign)
    assert foreign.name == "Elsewhere" and foreign.is_default is False
    assert _names(client) == ["General"]
    assert _names(client, f"/api/v1/locations?filter[parent]={foreign.id}") == []
