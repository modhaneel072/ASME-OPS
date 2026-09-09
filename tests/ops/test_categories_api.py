"""API tests for ``/api/v1/categories``."""

from __future__ import annotations

from uuid import uuid4

import pytest

from asme.extensions import db as _db
from asme.ops import bootstrap
from asme.ops.models import AuditEvent, Category, Organization, WorkOrder, WorkOrderCategory
from asme.ops.services import categories as categories_service
from asme.services.errors import Forbidden

CATEGORY_KEYS = {"id", "name", "color", "icon", "description", "usage", "created_at", "updated_at", "created_by"}
DUPLICATE = "A category with this name already exists."


def _create(client, **payload):
    response = client.post("/api/v1/categories", json=payload)
    assert response.status_code == 201, response.get_json()
    return response.get_json()["payload"]["category"]


def _items(client, url="/api/v1/categories"):
    response = client.get(url)
    assert response.status_code == 200, response.get_json()
    return response.get_json()["payload"]


def _names(client, url="/api/v1/categories"):
    return [item["name"] for item in _items(client, url)["items"]]


def _by_name(org, name):
    return Category.query.filter_by(organization_id=org.id, name=name).one()


def _other_org():
    other = Organization(name="Other Chapter", slug="other")
    _db.session.add(other)
    _db.session.flush()
    return other


def _foreign_category(name="Elsewhere"):
    foreign = Category(organization_id=_other_org().id, name=name)
    _db.session.add(foreign)
    _db.session.commit()
    return foreign


def _work_order_with(org, user, number, category):
    row = WorkOrder(organization_id=org.id, number=number, title=f"WO {number}", created_by_user_id=user.id)
    row.category_links.append(WorkOrderCategory(category_id=category.id))
    _db.session.add(row)
    _db.session.commit()
    return row


# --------------------------------------------------------------------------- reads


def test_list_shows_seed_categories(client, org, users, api_login):
    api_login(users["admin"])
    payload = _items(client)
    assert payload["total"] == len(bootstrap.SEED_CATEGORIES) == 14
    assert payload["next_cursor"] is None
    names = [item["name"] for item in payload["items"]]
    assert names == sorted((name for name, _, _ in bootstrap.SEED_CATEGORIES), key=str.lower)
    mechanical = next(item for item in payload["items"] if item["name"] == "Mechanical")
    assert set(mechanical) == CATEGORY_KEYS
    assert mechanical["color"] == "#0878d1" and mechanical["icon"] == "wrench"
    assert mechanical["usage"] == {"work_orders": 0}
    assert mechanical["created_by"] is None and mechanical["description"] is None
    assert mechanical["created_at"].endswith("Z")


def test_list_search_sorts_and_pagination(client, org, users, api_login):
    api_login(users["admin"])
    assert _names(client, "/api/v1/categories?q=elec") == ["Electrical"]
    assert _names(client, "/api/v1/categories?q=PROC") == ["Procurement", "Standard Operating Procedure"]
    assert _names(client, "/api/v1/categories?q=%25") == []

    safety = _by_name(org, "Safety")
    damage = _by_name(org, "Damage")
    _work_order_with(org, users["admin"], 1, safety)
    _work_order_with(org, users["admin"], 2, safety)
    _work_order_with(org, users["admin"], 3, damage)
    most_used = _items(client, "/api/v1/categories?sort=-usage")["items"]
    assert [(item["name"], item["usage"]["work_orders"]) for item in most_used[:3]] == [("Safety", 2), ("Damage", 1), ("Documentation", 0)]
    assert _names(client, "/api/v1/categories?sort=usage")[-2:] == ["Damage", "Safety"]
    assert _names(client, "/api/v1/categories?sort=-name")[0] == "Standard Operating Procedure"
    assert _names(client, "/api/v1/categories?q=age&sort=-usage") == ["Damage"]

    _create(client, name="Zebra Striping")
    assert _names(client, "/api/v1/categories?sort=-created_at")[0] == "Zebra Striping"
    assert _names(client, "/api/v1/categories?sort=created_at")[-1] == "Zebra Striping"

    page = _items(client, "/api/v1/categories?limit=10")
    assert len(page["items"]) == 10 and page["total"] == 15 and page["next_cursor"]
    rest = _items(client, f"/api/v1/categories?limit=10&cursor={page['next_cursor']}")
    assert len(rest["items"]) == 5 and rest["next_cursor"] is None
    assert [item["name"] for item in page["items"] + rest["items"]] == _names(client, "/api/v1/categories?limit=200")

    for url in ("/api/v1/categories?sort=color", "/api/v1/categories?filter[active]=true"):
        response = client.get(url)
        assert response.status_code == 400, url
        assert response.get_json()["ok"] is False


# --------------------------------------------------------------------------- writes


def test_create_applies_defaults_and_audits(client, org, users, api_login):
    api_login(users["admin"])
    created = _create(client, name="  Testing ")
    assert created["name"] == "Testing"
    assert created["color"] == "#0878d1" and created["icon"] == "tag" and created["description"] is None
    assert created["usage"] == {"work_orders": 0}
    assert created["created_by"]["id"] == users["admin"].id
    assert created["created_by"]["email"] == users["admin"].email

    custom = _create(client, name="Calibration", color="#ABCDEF", icon="gauge", description="Instrument checks")
    assert custom["color"] == "#ABCDEF" and custom["icon"] == "gauge" and custom["description"] == "Instrument checks"
    fetched = client.get(f"/api/v1/categories/{custom['id']}")
    assert fetched.status_code == 200
    assert fetched.get_json()["payload"]["category"] == custom

    events = AuditEvent.query.filter_by(event_type="category.created").all()
    assert {event.entity_id for event in events} == {created["id"], custom["id"]}
    assert all(event.actor_user_id == users["admin"].id and event.entity_type == "category" for event in events)
    by_id = {event.entity_id: event for event in events}
    assert by_id[custom["id"]].after_json["color"] == "#ABCDEF" and by_id[custom["id"]].before_json is None
    assert Category.query.filter_by(organization_id=org.id).count() == 16


def test_create_validation_lists_every_bad_field(client, org, users, api_login):
    api_login(users["admin"])
    response = client.post("/api/v1/categories", json={"name": "c" * 121, "color": "blue", "icon": "i" * 61, "description": 5})
    assert response.status_code == 400
    body = response.get_json()
    assert body["code"] == "validation"
    assert set(body["errors"]) == {"name", "color", "icon", "description"}

    missing = client.post("/api/v1/categories", json={})
    assert missing.status_code == 400
    assert missing.get_json()["errors"] == {"name": "This field is required."}

    blank = client.post("/api/v1/categories", json={"name": "Blank", "color": "", "icon": None})
    assert blank.status_code == 400
    assert set(blank.get_json()["errors"]) == {"color", "icon"}
    assert Category.query.filter_by(organization_id=org.id).count() == 14


def test_names_are_unique_per_organization_case_insensitively(client, org, users, api_login):
    api_login(users["admin"])
    duplicate = client.post("/api/v1/categories", json={"name": "  mechanical "})
    assert duplicate.status_code == 400
    assert duplicate.get_json()["errors"] == {"name": DUPLICATE}

    electrical = _by_name(org, "Electrical")
    clash = client.patch(f"/api/v1/categories/{electrical.id}", json={"name": "SOFTWARE"})
    assert clash.status_code == 400 and clash.get_json()["errors"] == {"name": DUPLICATE}
    recased = client.patch(f"/api/v1/categories/{electrical.id}", json={"name": "ELECTRICAL"})
    assert recased.status_code == 200
    assert recased.get_json()["payload"]["category"]["name"] == "ELECTRICAL"

    _foreign_category("Welding")  # a name used by another chapter is still free here
    assert _create(client, name="Welding")["name"] == "Welding"
    assert Category.query.filter_by(name="Welding").count() == 2


def test_patch_updates_and_audits(client, org, users, api_login):
    api_login(users["admin"])
    safety = _by_name(org, "Safety")
    safety_id = str(safety.id)
    response = client.patch(
        f"/api/v1/categories/{safety_id}",
        json={"color": "#112233", "icon": "shield", "description": "Safety-critical work"},
    )
    assert response.status_code == 200
    body = response.get_json()["payload"]["category"]
    assert body["name"] == "Safety" and body["color"] == "#112233" and body["icon"] == "shield"
    assert body["description"] == "Safety-critical work"

    event = AuditEvent.query.filter_by(event_type="category.updated").one()
    assert event.entity_id == safety_id and event.actor_user_id == users["admin"].id
    assert event.before_json["color"] == "#d84a4a" and event.after_json["color"] == "#112233"
    assert event.before_json["description"] is None and event.after_json["description"] == "Safety-critical work"

    unchanged = client.patch(f"/api/v1/categories/{safety_id}", json={})
    assert unchanged.status_code == 200
    assert AuditEvent.query.filter_by(event_type="category.updated").count() == 1

    bad = client.patch(f"/api/v1/categories/{safety_id}", json={"name": "", "color": "#12", "icon": ""})
    assert bad.status_code == 400
    assert set(bad.get_json()["errors"]) == {"name", "color", "icon"}


def test_delete_is_hard_when_unused_and_blocked_when_in_use(client, org, users, api_login):
    api_login(users["admin"])
    safety_id = _by_name(org, "Safety").id
    _work_order_with(org, users["admin"], 1, _by_name(org, "Safety"))

    blocked = client.delete(f"/api/v1/categories/{safety_id}")
    assert blocked.status_code == 409
    assert blocked.get_json()["code"] == "category_in_use"
    assert blocked.get_json()["usage"] == {"work_orders": 1}
    assert _db.session.get(Category, safety_id) is not None
    assert AuditEvent.query.filter_by(event_type="category.deleted").count() == 0

    WorkOrderCategory.query.filter_by(category_id=safety_id).delete()
    _db.session.commit()
    removed = client.delete(f"/api/v1/categories/{safety_id}")
    assert removed.status_code == 200
    assert removed.get_json()["payload"] == {"id": str(safety_id), "deleted": True}
    assert _db.session.get(Category, safety_id) is None
    event = AuditEvent.query.filter_by(event_type="category.deleted").one()
    assert event.entity_id == str(safety_id) and event.before_json["name"] == "Safety" and event.after_json is None
    assert client.get(f"/api/v1/categories/{safety_id}").status_code == 404
    assert Category.query.filter_by(organization_id=org.id).count() == 13


# --------------------------------------------------------------------------- authz


def test_permissions_by_role(client, org, users, requester, api_login):
    safety_id = _by_name(org, "Safety").id

    api_login(users["member"])  # full_member: category.read only
    assert client.get("/api/v1/categories").status_code == 200
    assert client.get(f"/api/v1/categories/{safety_id}").status_code == 200
    denied = client.post("/api/v1/categories", json={"name": "Nope"})
    assert denied.status_code == 403 and denied.get_json()["permission"] == ["category.manage"]
    assert client.patch(f"/api/v1/categories/{safety_id}", json={"name": "Nope"}).status_code == 403
    assert client.delete(f"/api/v1/categories/{safety_id}").status_code == 403
    assert Category.query.filter_by(organization_id=org.id).count() == 14

    api_login(requester)  # requester: no category.read
    forbidden = client.get("/api/v1/categories")
    assert forbidden.status_code == 403 and forbidden.get_json()["permission"] == ["category.read"]
    assert client.get(f"/api/v1/categories/{safety_id}").status_code == 403


def test_services_enforce_permissions_without_routes(org, ctx_requester, ctx_member):
    safety = _by_name(org, "Safety")
    with pytest.raises(Forbidden):
        categories_service.create(ctx_requester, {"name": "Nope"})
    with pytest.raises(Forbidden):
        categories_service.update(ctx_member, safety, {"name": "Nope"})
    with pytest.raises(Forbidden):
        categories_service.delete(ctx_member, safety)
    assert Category.query.filter_by(organization_id=org.id).count() == 14


def test_foreign_and_malformed_ids_are_404(client, org, users, api_login):
    api_login(users["admin"])
    foreign = _foreign_category()
    for target in (str(foreign.id), str(uuid4()), "not-a-uuid"):
        assert client.get(f"/api/v1/categories/{target}").status_code == 404, target
        assert client.patch(f"/api/v1/categories/{target}", json={"name": "Hijack"}).status_code == 404, target
        assert client.delete(f"/api/v1/categories/{target}").status_code == 404, target
    _db.session.refresh(foreign)
    assert foreign.name == "Elsewhere"
    assert "Elsewhere" not in _names(client)
