"""Purchase requests API: drafts, validation, the read rule, listing tabs and
search, ``from-low-stock`` grouping and the chapter's purchasing settings."""

from __future__ import annotations

from decimal import Decimal

import pytest

from asme.extensions import db as _db
from asme.ops.models import (
    AuditEvent,
    Location,
    OpsProject,
    Organization,
    Part,
    PartVendor,
    ProjectMember,
    PurchaseRequest,
    Team,
    Vendor,
)
from asme.ops.services import purchase_requests as service
from asme.services.errors import Forbidden, NotFound
from tests.ops.conftest import make_user

API = "/api/v1/purchase-requests"
SETTINGS = "/api/v1/purchasing/settings"
D = Decimal


# --------------------------------------------------------------------------- fixtures / helpers


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


def _prefer(part, vendor, **fields):
    link = PartVendor(part_id=part.id, vendor_id=vendor.id, preferred=True, **fields)
    _db.session.add(link)
    _db.session.commit()
    return link


def _project(org, name, code, *, lead=None, visibility="chapter"):
    project = OpsProject(organization_id=org.id, name=name, code=code, visibility=visibility, lead_user_id=lead.id if lead else None)
    _db.session.add(project)
    _db.session.flush()
    if lead is not None:
        _db.session.add(ProjectMember(project_id=project.id, user_id=lead.id, project_role="lead"))
    _db.session.commit()
    return project


def _team(org, name):
    row = Team(organization_id=org.id, name=name)
    _db.session.add(row)
    _db.session.commit()
    return row


def _body(**overrides):
    payload = {
        "title": "Drivetrain fasteners",
        "purpose": "Rebuild the drive shaft.",
        "items": [{"description": "M6 bolts", "quantity": 20, "unit_price": "0.4500"}],
    }
    payload.update(overrides)
    return payload


def _create(client, **overrides):
    response = client.post(API, json=_body(**overrides))
    assert response.status_code == 201, response.get_json()
    return response.get_json()["payload"]["purchase_request"]


def _foreign_request(users):
    other = Organization(name="Other Chapter", slug="other-chapter")
    _db.session.add(other)
    _db.session.flush()
    foreign = PurchaseRequest(
        organization_id=other.id,
        number=1,
        title="Foreign order",
        requester_user_id=users["admin"].id,
        status="draft",
        shipping_amount=0,
        tax_amount=0,
        estimated_total=0,
    )
    _db.session.add(foreign)
    _db.session.commit()
    return foreign


# --------------------------------------------------------------------------- create / read / update


def test_create_draft_computes_totals_and_audits(client, org, users, api_login):
    api_login(users["member"])
    body = _create(
        client,
        shipping_amount="12.50",
        tax_amount="3.25",
        items=[
            {"description": "M6 bolts", "quantity": 20, "unit_price": "0.4500"},
            {"description": "Nylock nuts", "quantity": "10.5", "unit_price": "1.20"},
        ],
    )
    assert body["number"] == 1 and body["display_number"] == "PR-1"
    assert body["status"] == "draft" and body["requester"]["id"] == users["member"].id
    assert body["item_count"] == 2
    # 20 * 0.45 = 9.00, 10.5 * 1.20 = 12.60, + 12.50 shipping + 3.25 tax
    assert body["estimated_total"] == 37.35
    assert [item["line_total"] for item in body["items"]] == [9.0, 12.6]
    assert body["approved_total"] is None and body["decline_reason"] is None
    assert body["events"] == [] and body["attachment_count"] == 0
    assert set(body["available_actions"]) == {"submit", "cancel"}

    event = AuditEvent.query.filter_by(event_type="purchase_request.created", entity_id=body["id"]).one()
    assert event.entity_type == "purchase_request" and event.after_json["title"] == "Drivetrain fasteners"


def test_create_line_takes_its_description_from_the_part(client, org, users, api_login):
    part = _part(org, "Bearing 608ZZ", sku="BR-608", unit="each")
    api_login(users["member"])
    body = _create(client, items=[{"part_id": str(part.id), "quantity": 4, "unit_price": "2.00"}])
    assert body["items"][0]["part"] == {"id": str(part.id), "name": "Bearing 608ZZ", "sku": "BR-608", "unit": "each"}
    assert body["items"][0]["description"] == "Bearing 608ZZ"


def test_create_validation_lists_every_bad_field(client, org, users, api_login):
    api_login(users["member"])
    missing = client.post(API, json={})
    assert missing.status_code == 400 and set(missing.get_json()["errors"]) == {"title", "items"}

    empty_items = client.post(API, json=_body(items=[]))
    assert empty_items.status_code == 400 and set(empty_items.get_json()["errors"]) == {"items"}

    header = client.post(API, json=_body(title="", shipping_amount=-1, needed_by="not-a-date", budget_code="b" * 80))
    assert header.status_code == 400
    assert header.get_json()["code"] == "validation"
    assert set(header.get_json()["errors"]) == {"title", "shipping_amount", "needed_by", "budget_code"}

    references = client.post(
        API,
        json=_body(
            project_id="11111111-1111-1111-1111-111111111111",
            vendor_id="22222222-2222-2222-2222-222222222222",
            items=[{"quantity": 0}, {"description": "Shim", "quantity": 1, "part_id": "33333333-3333-3333-3333-333333333333"}],
        ),
    )
    assert references.status_code == 400
    assert set(references.get_json()["errors"]) == {
        "project_id",
        "vendor_id",
        "items[0].quantity",
        "items[0].description",
        "items[1].part_id",
    }

    lines = client.post(API, json=_body(items=["not-an-object", {"description": "x" * 400, "quantity": "abc", "unit_price": -2}]))
    assert lines.status_code == 400
    assert set(lines.get_json()["errors"]) == {"items[0]", "items[1].description", "items[1].quantity", "items[1].unit_price"}


def test_patch_replaces_items_only_while_draft(client, org, users, api_login):
    vendor = _vendor(org, "McMaster-Carr")
    api_login(users["member"])
    body = _create(client)
    patched = client.patch(
        f"{API}/{body['id']}",
        json={"title": "Renamed", "vendor_id": str(vendor.id), "items": [{"description": "Washers", "quantity": 100, "unit_price": "0.05"}]},
    )
    assert patched.status_code == 200
    after = patched.get_json()["payload"]["purchase_request"]
    assert after["title"] == "Renamed" and after["vendor"]["name"] == "McMaster-Carr"
    assert [item["description"] for item in after["items"]] == ["Washers"]
    assert after["estimated_total"] == 5.0

    assert client.post(f"{API}/{body['id']}/submit", json={}).status_code == 200
    late = client.patch(f"{API}/{body['id']}", json={"title": "Too late"})
    assert late.status_code == 409 and late.get_json()["code"] == "invalid_transition"


def test_only_the_requester_or_a_reviewer_may_edit_a_draft(client, org, users, api_login):
    api_login(users["member"])
    body = _create(client)

    other = make_user("Nia Member", "nia@uiowa.edu", ops_role="full_member", org=org)
    api_login(other)
    assert client.patch(f"{API}/{body['id']}", json={"title": "Hijack"}).status_code == 404

    treasurer = make_user("Tess Treasurer", "tess@uiowa.edu", ops_role="treasurer", org=org)
    api_login(treasurer)
    assert client.patch(f"{API}/{body['id']}", json={"title": "Trimmed"}).status_code == 200


# --------------------------------------------------------------------------- read rule


def test_read_rule_hides_other_members_requests(client, org, users, api_login):
    api_login(users["member"])
    mine = _create(client)

    other = make_user("Nia Member", "nia@uiowa.edu", ops_role="full_member", org=org)
    api_login(other)
    assert client.get(f"{API}/{mine['id']}").status_code == 404
    assert client.get(API).get_json()["payload"]["total"] == 0

    treasurer = make_user("Tess Treasurer", "tess@uiowa.edu", ops_role="treasurer", org=org)
    api_login(treasurer)
    assert client.get(f"{API}/{mine['id']}").status_code == 200
    assert client.get(API).get_json()["payload"]["total"] == 1

    manager = make_user("Ines Inventory", "ines@uiowa.edu", ops_role="inventory_manager", org=org)
    api_login(manager)
    assert client.get(f"{API}/{mine['id']}").status_code == 200


def test_project_lead_reads_requests_on_their_project(client, org, users, api_login):
    lead = make_user("Pat Lead", "pat@uiowa.edu", ops_role="project_lead", org=org)
    project = _project(org, "Baja", "BAJA", lead=lead)
    other_project = _project(org, "Rover", "ROVR")

    api_login(users["member"])
    on_project = _create(client, project_id=str(project.id))
    elsewhere = _create(client, title="Elsewhere", project_id=str(other_project.id))

    api_login(lead)
    assert client.get(f"{API}/{on_project['id']}").status_code == 200
    assert client.get(f"{API}/{elsewhere['id']}").status_code == 404
    listed = client.get(API).get_json()["payload"]
    assert [row["id"] for row in listed["items"]] == [on_project["id"]]


def test_cross_organization_ids_are_404(client, org, users, api_login):
    foreign = _foreign_request(users)
    api_login(users["admin"])
    assert client.get(f"{API}/{foreign.id}").status_code == 404
    assert client.patch(f"{API}/{foreign.id}", json={"title": "Hijack"}).status_code == 404
    assert client.post(f"{API}/{foreign.id}/submit", json={}).status_code == 404
    assert client.post(f"{API}/{foreign.id}/approve", json={}).status_code == 404
    assert client.get(f"{API}/not-a-uuid").status_code == 404
    assert client.get(API).get_json()["payload"]["total"] == 0
    assert PurchaseRequest.query.get(foreign.id).title == "Foreign order"


def test_submitting_requires_the_purchase_submit_permission(client, org, users, requester, api_login):
    api_login(requester)
    denied = client.post(API, json=_body())
    assert denied.status_code == 403 and denied.get_json()["permission"] == ["purchase.submit"]
    assert client.get(API).get_json()["payload"]["total"] == 0


# --------------------------------------------------------------------------- listing


def test_list_tabs_filters_sorting_and_search(client, org, users, api_login):
    vendor = _vendor(org, "DigiKey")
    api_login(users["member"])
    first = _create(client, title="Alpha order", vendor_id=str(vendor.id))
    second = _create(client, title="Beta order", items=[{"description": "Aluminium sheet", "quantity": 2, "unit_price": "40.00"}])
    assert client.post(f"{API}/{second['id']}/submit", json={}).status_code == 200

    payload = client.get(API).get_json()["payload"]
    assert payload["total"] == 2
    assert payload["tabs"] == {"mine": 2, "review": 0, "open": 2, "closed": 0, "all": 2}

    mine = client.get(f"{API}?tab=mine").get_json()["payload"]
    assert mine["total"] == 2
    closed = client.get(f"{API}?tab=closed").get_json()["payload"]
    assert closed["total"] == 0

    by_vendor = client.get(f"{API}?filter[vendor]={vendor.id}").get_json()["payload"]
    assert [row["id"] for row in by_vendor["items"]] == [first["id"]]
    by_status = client.get(f"{API}?filter[status]=treasurer_review").get_json()["payload"]
    assert [row["id"] for row in by_status["items"]] == [second["id"]]
    by_requester = client.get(f"{API}?filter[requester]=me").get_json()["payload"]
    assert by_requester["total"] == 2

    assert [row["number"] for row in client.get(f"{API}?sort=number").get_json()["payload"]["items"]] == [1, 2]
    assert [row["number"] for row in client.get(f"{API}?sort=-estimated_total").get_json()["payload"]["items"]] == [2, 1]

    assert [row["id"] for row in client.get(f"{API}?q=PR-1").get_json()["payload"]["items"]] == [first["id"]]
    assert [row["id"] for row in client.get(f"{API}?q=Beta").get_json()["payload"]["items"]] == [second["id"]]
    assert [row["id"] for row in client.get(f"{API}?q=aluminium").get_json()["payload"]["items"]] == [second["id"]]

    bad_status = client.get(f"{API}?filter[status]=nope")
    assert bad_status.status_code == 400 and bad_status.get_json()["code"] == "bad_filter"
    bad_tab = client.get(f"{API}?tab=everything")
    assert bad_tab.status_code == 400 and bad_tab.get_json()["code"] == "bad_filter"
    bad_sort = client.get(f"{API}?sort=title")
    assert bad_sort.status_code == 400 and bad_sort.get_json()["code"] == "bad_sort"


def test_review_tab_holds_what_the_caller_can_act_on(client, org, users, api_login):
    api_login(users["member"])
    mine = _create(client)
    assert client.post(f"{API}/{mine['id']}/submit", json={}).status_code == 200

    treasurer = make_user("Tess Treasurer", "tess@uiowa.edu", ops_role="treasurer", org=org)
    api_login(treasurer)
    payload = client.get(f"{API}?tab=review").get_json()["payload"]
    assert [row["id"] for row in payload["items"]] == [mine["id"]]
    assert payload["tabs"]["review"] == 1

    # A treasurer never reviews their own request.
    own = _create(client, title="Treasurer's own")
    assert client.post(f"{API}/{own['id']}/submit", json={}).status_code == 200
    payload = client.get(f"{API}?tab=review").get_json()["payload"]
    assert [row["id"] for row in payload["items"]] == [mine["id"]]

    api_login(users["member"])
    assert client.get(f"{API}?tab=review").get_json()["payload"]["total"] == 0


# --------------------------------------------------------------------------- from low stock


def test_from_low_stock_groups_by_preferred_vendor(client, org, users, api_login):
    shelf = _location(org, "Shelf A")
    mcmaster = _vendor(org, "McMaster-Carr")
    digikey = _vendor(org, "DigiKey")
    bolts = _part(org, "M6 bolt", reorder_quantity=D("10"), minimum_stock=D("5"), default_location_id=shelf.id)
    nuts = _part(org, "M6 nut", maximum_stock=D("20"), minimum_stock=D("4"), unit_cost=D("0.3000"))
    resistors = _part(org, "10k resistor", minimum_stock=D("5"))
    tape = _part(org, "Masking tape")
    _prefer(bolts, mcmaster, vendor_part_number="91290A115", url="https://www.mcmaster.com/91290A115", last_price=D("0.2500"))
    _prefer(nuts, mcmaster)
    _prefer(resistors, digikey, last_price=D("0.0500"))

    api_login(users["member"])
    response = client.post(f"{API}/from-low-stock", json={"part_ids": [str(bolts.id), str(nuts.id), str(resistors.id), str(tape.id)]})
    assert response.status_code == 201, response.get_json()
    drafts = response.get_json()["payload"]["purchase_requests"]
    assert len(drafts) == 3

    by_vendor = {(draft["vendor"] or {}).get("name"): draft for draft in drafts}
    assert set(by_vendor) == {"McMaster-Carr", "DigiKey", None}

    mcmaster_items = by_vendor["McMaster-Carr"]["items"]
    assert [item["description"] for item in mcmaster_items] == ["M6 bolt", "M6 nut"]
    # reorder_quantity wins; then maximum_stock - available
    assert [item["quantity"] for item in mcmaster_items] == [10.0, 20.0]
    assert [item["unit_price"] for item in mcmaster_items] == [0.25, 0.3]
    assert mcmaster_items[0]["vendor_part_number"] == "91290A115"
    assert mcmaster_items[0]["receive_location"]["name"] == "Shelf A"
    assert by_vendor["McMaster-Carr"]["title"] == "Restock: McMaster-Carr"

    # minimum_stock - available, and the min-1 floor for a part with no levels
    assert [item["quantity"] for item in by_vendor["DigiKey"]["items"]] == [5.0]
    assert [item["quantity"] for item in by_vendor[None]["items"]] == [1.0]
    assert by_vendor[None]["title"] == "Restock"
    assert all(draft["status"] == "draft" for draft in drafts)


def test_from_low_stock_rejects_unknown_parts_and_other_roles(client, org, users, requester, api_login):
    api_login(users["member"])
    bad = client.post(f"{API}/from-low-stock", json={"part_ids": ["44444444-4444-4444-4444-444444444444"]})
    assert bad.status_code == 400 and set(bad.get_json()["errors"]) == {"part_ids"}
    empty = client.post(f"{API}/from-low-stock", json={})
    assert empty.status_code == 400 and set(empty.get_json()["errors"]) == {"part_ids"}

    api_login(requester)
    denied = client.post(f"{API}/from-low-stock", json={"part_ids": []})
    assert denied.status_code == 403


# --------------------------------------------------------------------------- purchasing settings


def test_purchasing_settings_round_trip_and_validation(client, org, users, api_login):
    team = _team(org, "Critical Parts")
    api_login(users["admin"])

    defaults = client.get(SETTINGS)
    assert defaults.status_code == 200
    assert defaults.get_json()["payload"]["purchasing"] == {
        "advisor_review_threshold": None,
        "require_project_lead_approval": False,
        "critical_parts_team_id": None,
    }

    saved = client.put(
        SETTINGS,
        json={"advisor_review_threshold": "250", "require_project_lead_approval": True, "critical_parts_team_id": str(team.id)},
    )
    assert saved.status_code == 200
    assert saved.get_json()["payload"]["purchasing"] == {
        "advisor_review_threshold": 250.0,
        "require_project_lead_approval": True,
        "critical_parts_team_id": str(team.id),
    }
    assert client.get(SETTINGS).get_json()["payload"]["purchasing"]["advisor_review_threshold"] == 250.0

    # PUT replaces the block, so omitted keys fall back to their default.
    reset = client.put(SETTINGS, json={})
    assert reset.get_json()["payload"]["purchasing"] == {
        "advisor_review_threshold": None,
        "require_project_lead_approval": False,
        "critical_parts_team_id": None,
    }

    negative = client.put(SETTINGS, json={"advisor_review_threshold": -1})
    assert negative.status_code == 400 and set(negative.get_json()["errors"]) == {"advisor_review_threshold"}
    unknown_team = client.put(SETTINGS, json={"critical_parts_team_id": "55555555-5555-5555-5555-555555555555"})
    assert unknown_team.status_code == 400 and set(unknown_team.get_json()["errors"]) == {"critical_parts_team_id"}

    audit = AuditEvent.query.filter_by(event_type="organization.purchasing_settings_updated").first()
    assert audit is not None and audit.after_json["require_project_lead_approval"] is True


def test_purchasing_settings_need_the_chapter_settings_permission(client, org, users, api_login):
    foreign_team = None
    other = Organization(name="Other Chapter", slug="other-chapter")
    _db.session.add(other)
    _db.session.flush()
    foreign_team = Team(organization_id=other.id, name="Theirs")
    _db.session.add(foreign_team)
    _db.session.commit()

    api_login(users["admin"])
    denied = client.put(SETTINGS, json={"critical_parts_team_id": str(foreign_team.id)})
    assert denied.status_code == 400 and set(denied.get_json()["errors"]) == {"critical_parts_team_id"}

    api_login(users["member"])
    assert client.get(SETTINGS).status_code == 403
    assert client.put(SETTINGS, json={}).status_code == 403


# --------------------------------------------------------------------------- service


def test_service_rejects_unknown_actions_and_foreign_rows(ctx_admin, ctx_member, org, users):
    request = service.create(ctx_member, _body())
    with pytest.raises(Exception) as exc:
        service.perform(ctx_member, request, "teleport", {})
    assert getattr(exc.value, "code", None) == "bad_action"

    foreign = _foreign_request({"admin": users["admin"]})
    with pytest.raises(NotFound):
        service.get_readable(ctx_admin, foreign.id)
    with pytest.raises(NotFound):
        service.perform(ctx_admin, foreign, "submit", {})


def test_service_settings_require_permission(ctx_member, ctx_admin):
    with pytest.raises(Forbidden):
        service.get_settings(ctx_member)
    with pytest.raises(Forbidden):
        service.update_settings(ctx_member, {})
    assert service.update_settings(ctx_admin, {"advisor_review_threshold": "100"})["advisor_review_threshold"] == D("100.00")
