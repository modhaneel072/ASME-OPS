from datetime import timedelta
from uuid import UUID, uuid4

import pytest

from asme.extensions import db as _db
from asme.ops import policy
from asme.ops.models import (
    Asset,
    AssetStatusHistory,
    AssetType,
    AssetTypeLink,
    AuditEvent,
    Location,
    OpsProject,
    Organization,
    ProjectMember,
    Team,
    TeamMember,
    WorkOrder,
    WorkOrderAsset,
)
from asme.ops.services import assets as asset_service
from asme.ops.types import utcnow
from asme.ops.validation import ValidationErrors
from asme.services.errors import Forbidden, NotFound, Validation
from tests.ops.conftest import make_user

PLAN_ASSET_KEYS = {
    "id",
    "name",
    "code",
    "description",
    "parent_id",
    "project",
    "location",
    "team",
    "owner",
    "manufacturer",
    "model",
    "serial_number",
    "purchase_date",
    "purchase_cost",
    "warranty_end",
    "criticality",
    "status",
    "types",
    "child_count",
    "open_work_order_count",
    "created_at",
    "updated_at",
}


# --------------------------------------------------------------------------- helpers (inline, no fixtures)


def _project(org, name, code, visibility="chapter", **kw):
    row = OpsProject(organization_id=org.id, name=name, code=code, visibility=visibility, **kw)
    _db.session.add(row)
    _db.session.commit()
    return row


def _team(org, name, lead=None, members=()):
    team = Team(organization_id=org.id, name=name)
    _db.session.add(team)
    _db.session.flush()
    if lead is not None:
        team.members.append(TeamMember(user_id=lead.id, is_lead=True))
    for user in members:
        team.members.append(TeamMember(user_id=user.id, is_lead=False))
    _db.session.commit()
    return team


def _location(org, name, **kw):
    row = Location(organization_id=org.id, name=name, **kw)
    _db.session.add(row)
    _db.session.commit()
    return row


def _asset(org, name, **kw):
    row = Asset(organization_id=org.id, name=name, **kw)
    _db.session.add(row)
    _db.session.commit()
    return row


def _asset_type(org, name, **kw):
    row = AssetType(organization_id=org.id, name=name, **kw)
    _db.session.add(row)
    _db.session.commit()
    return row


def _wo(org, number, status="open", **kw):
    row = WorkOrder(organization_id=org.id, number=number, title=f"WO {number}", status=status, **kw)
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


# --------------------------------------------------------------------------- create / read


def test_create_asset_happy_path_with_audit(client, org, users, api_login):
    api_login(users["admin"])
    project = _project(org, "Crater Cruncher Rover", "CCR")
    team = _team(org, "Robotic Arm", lead=users["lead"])
    location = _location(org, "Robotics Lab")
    type_response = client.post("/api/v1/asset-types", json={"name": "Printer", "color": "#0878d1", "icon": "printer"})
    assert type_response.status_code == 201, type_response.get_json()
    printer_type = type_response.get_json()["payload"]["asset_type"]
    assert printer_type == {"id": printer_type["id"], "name": "Printer", "color": "#0878d1", "icon": "printer", "asset_count": 0}

    created = client.post(
        "/api/v1/assets",
        json={
            "name": "3D Printer 01",
            "code": "PRN-01",
            "description": "Prusa MK4 on the back bench",
            "project_id": str(project.id),
            "location_id": str(location.id),
            "responsible_team_id": str(team.id),
            "owner_user_id": users["member"].id,
            "manufacturer": "Prusa",
            "model": "MK4",
            "serial_number": "SN-123",
            "purchase_date": "2025-08-15",
            "purchase_cost": 1099.5,
            "warranty_end": "2027-08-15",
            "criticality": "high",
            "qr_code": "QR-PRN-01",
            "custom_fields": {"nozzle_mm": 0.4},
            "type_ids": [printer_type["id"], printer_type["id"]],
        },
    )
    assert created.status_code == 201, created.get_json()
    body = created.get_json()["payload"]["asset"]
    assert PLAN_ASSET_KEYS <= set(body)
    assert body["name"] == "3D Printer 01" and body["code"] == "PRN-01" and body["parent_id"] is None
    assert body["project"] == {"id": str(project.id), "name": "Crater Cruncher Rover", "code": "CCR", "visibility": "chapter"}
    assert body["location"] == {"id": str(location.id), "name": "Robotics Lab"}
    assert body["team"] == {"id": str(team.id), "name": "Robotic Arm"}
    assert body["owner"]["id"] == users["member"].id and body["owner"]["email"] == users["member"].email
    assert body["purchase_date"] == "2025-08-15" and body["purchase_cost"] == 1099.5 and body["warranty_end"] == "2027-08-15"
    assert body["criticality"] == "high" and body["status"] == "online"
    assert body["types"] == [{"id": printer_type["id"], "name": "Printer", "color": "#0878d1"}]  # duplicates collapsed
    assert body["custom_fields"] == {"nozzle_mm": 0.4} and body["qr_code"] == "QR-PRN-01"
    assert body["child_count"] == 0 and body["open_work_order_count"] == 0
    assert body["created_at"].endswith("Z")

    fetched = client.get(f"/api/v1/assets/{body['id']}")
    assert fetched.status_code == 200 and fetched.get_json()["payload"]["asset"] == body

    event = AuditEvent.query.filter_by(event_type="asset.created", entity_id=body["id"]).one()
    assert event.entity_type == "asset" and event.actor_user_id == users["admin"].id
    assert event.after_json["name"] == "3D Printer 01" and event.after_json["type_ids"] == [printer_type["id"]]
    assert AssetStatusHistory.query.filter_by(asset_id=UUID(body["id"])).count() == 0  # online needs no initial row

    types = client.get("/api/v1/asset-types").get_json()["payload"]
    assert types["items"] == [{**printer_type, "asset_count": 1}]


def test_create_defaults_location_criticality_and_initial_status_history(client, org, users, api_login):
    api_login(users["admin"])
    default = Location.query.filter_by(organization_id=org.id, is_default=True).one()
    created = client.post("/api/v1/assets", json={"name": "Soldering Station 01", "status": "offline_planned"})
    assert created.status_code == 201
    body = created.get_json()["payload"]["asset"]
    assert body["location"] == {"id": str(default.id), "name": default.name}
    assert body["criticality"] == "none" and body["status"] == "offline_planned"
    history = AssetStatusHistory.query.filter_by(asset_id=UUID(body["id"])).one()
    assert history.from_status is None and history.to_status == "offline_planned"
    assert history.downtime_type == "planned" and history.ended_at is None
    assert history.changed_by_user_id == users["admin"].id

    retired = client.post("/api/v1/assets", json={"name": "Old Drill", "status": "retired"}).get_json()["payload"]["asset"]
    row = AssetStatusHistory.query.filter_by(asset_id=UUID(retired["id"])).one()
    assert row.to_status == "retired" and row.downtime_type is None


def test_create_validation_lists_every_bad_field(client, org, users, api_login):
    api_login(users["admin"])
    malformed = client.post(
        "/api/v1/assets",
        json={
            "code": "x" * 61,
            "purchase_cost": -1,
            "purchase_date": "2026-01-01",
            "warranty_end": "not-a-date",
            "criticality": "extreme",
            "status": "broken",
            "custom_fields": [1, 2],
            "responsible_team_id": "not-a-uuid",
            "owner_user_id": "abc",
            "type_ids": "printer",
        },
    )
    assert malformed.status_code == 400
    payload = malformed.get_json()
    assert payload["code"] == "validation"
    assert set(payload["errors"]) == {
        "name",
        "code",
        "purchase_cost",
        "warranty_end",
        "criticality",
        "status",
        "custom_fields",
        "responsible_team_id",
        "owner_user_id",
        "type_ids",
    }

    outsider = make_user("No Membership", "nobody@uiowa.edu")  # legacy user without an ops membership
    existing = _asset(org, "Bench Grinder", code="BG-1")
    unknown = client.post(
        "/api/v1/assets",
        json={
            "name": "Ghost",
            "code": "bg-1",
            "parent_id": str(uuid4()),
            "project_id": str(uuid4()),
            "location_id": str(uuid4()),
            "responsible_team_id": str(uuid4()),
            "owner_user_id": outsider.id,
            "type_ids": [str(uuid4())],
            "purchase_date": "2026-01-01",
            "warranty_end": "2025-12-31",
        },
    )
    assert unknown.status_code == 400
    assert set(unknown.get_json()["errors"]) == {
        "code",
        "parent_id",
        "project_id",
        "location_id",
        "responsible_team_id",
        "owner_user_id",
        "type_ids",
        "warranty_end",
    }
    assert Asset.query.filter_by(organization_id=org.id).count() == 1
    assert existing.code == "BG-1"


def test_parent_cycle_is_rejected(client, org, users, api_login):
    api_login(users["admin"])
    rover = _asset(org, "Rover")
    chassis = _asset(org, "Chassis", parent_asset_id=rover.id)
    wheel = _asset(org, "Wheel", parent_asset_id=chassis.id)

    looped = client.patch(f"/api/v1/assets/{rover.id}", json={"parent_id": str(wheel.id)})
    assert looped.status_code == 400
    assert looped.get_json()["code"] == "asset_cycle" and looped.get_json()["field"] == "parent_id"
    selfie = client.patch(f"/api/v1/assets/{rover.id}", json={"parent_id": str(rover.id)})
    assert selfie.status_code == 400 and selfie.get_json()["code"] == "asset_cycle"
    _db.session.refresh(rover)
    assert rover.parent_asset_id is None

    # re-parenting a leaf under a sibling branch is fine
    arm = _asset(org, "Arm", parent_asset_id=rover.id)
    moved = client.patch(f"/api/v1/assets/{wheel.id}", json={"parent_id": str(arm.id)})
    assert moved.status_code == 200 and moved.get_json()["payload"]["asset"]["parent_id"] == str(arm.id)


def test_patch_updates_fields_and_refuses_status(client, org, users, api_login):
    api_login(users["admin"])
    printer = _asset_type(org, "Printer")
    tool = _asset_type(org, "Tool")
    asset = _asset(org, "Bandsaw", code="BS-1", criticality="low")
    asset.type_links.append(AssetTypeLink(asset_type_id=printer.id))
    _db.session.commit()

    refused = client.patch(f"/api/v1/assets/{asset.id}", json={"status": "retired"})
    assert refused.status_code == 400 and refused.get_json()["errors"] == {"status": "Use the status endpoint."}
    combined = client.patch(f"/api/v1/assets/{asset.id}", json={"status": "retired", "name": "", "purchase_cost": "free"})
    assert combined.status_code == 400 and set(combined.get_json()["errors"]) == {"status", "name", "purchase_cost"}

    patched = client.patch(
        f"/api/v1/assets/{asset.id}",
        json={"name": "Bandsaw 14in", "criticality": "medium", "type_ids": [str(tool.id)], "manufacturer": "Grizzly", "custom_fields": {"blade": "14"}},
    )
    assert patched.status_code == 200, patched.get_json()
    body = patched.get_json()["payload"]["asset"]
    assert body["name"] == "Bandsaw 14in" and body["criticality"] == "medium" and body["status"] == "online"
    assert body["types"] == [{"id": str(tool.id), "name": "Tool", "color": tool.color}]
    assert body["manufacturer"] == "Grizzly" and body["custom_fields"] == {"blade": "14"}

    event = AuditEvent.query.filter_by(event_type="asset.updated", entity_id=str(asset.id)).one()
    assert event.before_json["name"] == "Bandsaw" and event.after_json["name"] == "Bandsaw 14in"
    assert event.before_json["type_ids"] == [str(printer.id)] and event.after_json["type_ids"] == [str(tool.id)]
    assert event.metadata_json["changed_fields"] == ["criticality", "custom_fields_json", "manufacturer", "name", "type_ids"]

    cleared = client.patch(f"/api/v1/assets/{asset.id}", json={"type_ids": [], "manufacturer": None})
    assert cleared.status_code == 200
    assert cleared.get_json()["payload"]["asset"]["types"] == [] and cleared.get_json()["payload"]["asset"]["manufacturer"] is None

    other = _asset(org, "Other", code="OT-1")
    dupe = client.patch(f"/api/v1/assets/{other.id}", json={"code": "bs-1"})
    assert dupe.status_code == 400 and set(dupe.get_json()["errors"]) == {"code"}
    same = client.patch(f"/api/v1/assets/{other.id}", json={"code": "OT-1"})
    assert same.status_code == 200


def test_code_unique_per_org(client, org, users, api_login):
    api_login(users["admin"])
    assert client.post("/api/v1/assets", json={"name": "A", "code": "PRN-01"}).status_code == 201
    dupe = client.post("/api/v1/assets", json={"name": "B", "code": "prn-01"})
    assert dupe.status_code == 400 and dupe.get_json()["errors"] == {"code": "This code is already used by another asset."}
    # blank codes are stored as null and never collide
    assert client.post("/api/v1/assets", json={"name": "C", "code": ""}).status_code == 201
    assert client.post("/api/v1/assets", json={"name": "D", "code": None}).status_code == 201


# --------------------------------------------------------------------------- visibility


def test_private_project_assets_are_hidden_from_non_members(client, org, users, api_login):
    secret = _project(org, "Sponsor Bid", "BID", visibility="private")
    hidden = _asset(org, "Secret Rig", project_id=secret.id)
    _asset(org, "Bench Grinder")

    api_login(users["member"])  # full_member: project.read only
    assert _names(client.get("/api/v1/assets").get_json()["payload"]) == ["Bench Grinder"]
    assert _names(client.get("/api/v1/assets?view=hierarchy").get_json()["payload"]) == ["Bench Grinder"]
    assert client.get(f"/api/v1/assets/{hidden.id}").status_code == 404
    assert client.get(f"/api/v1/assets/{hidden.id}/history").status_code == 404

    secret.members.append(ProjectMember(user_id=users["member"].id))
    _db.session.commit()
    assert _names(client.get("/api/v1/assets").get_json()["payload"]) == ["Bench Grinder", "Secret Rig"]
    assert client.get(f"/api/v1/assets/{hidden.id}").status_code == 200

    api_login(users["admin"])  # project.read_private
    assert _names(client.get("/api/v1/assets").get_json()["payload"]) == ["Bench Grinder", "Secret Rig"]

    # asset.manage at chapter scope does not grant a peek into private projects
    manager = make_user("Ines Inventory", "ines@uiowa.edu", ops_role="inventory_manager", org=org)
    api_login(manager)
    blocked = client.post("/api/v1/assets", json={"name": "Sneaky", "project_id": str(secret.id)})
    assert blocked.status_code == 400 and blocked.get_json()["errors"] == {"project_id": "Unknown project."}
    blocked_parent = client.post("/api/v1/assets", json={"name": "Sneaky", "parent_id": str(hidden.id)})
    assert blocked_parent.status_code == 400 and set(blocked_parent.get_json()["errors"]) == {"parent_id"}


def test_permissions_by_role(client, org, users, requester, api_login):
    asset = _asset(org, "Drill Press")

    api_login(users["member"])  # asset.read only
    assert client.get("/api/v1/assets").status_code == 200
    assert client.get(f"/api/v1/assets/{asset.id}").status_code == 200
    assert client.get("/api/v1/asset-types").status_code == 200
    denied = client.post("/api/v1/assets", json={"name": "Nope"})
    assert denied.status_code == 403 and denied.get_json()["permission"] == ["asset.manage"]
    assert client.patch(f"/api/v1/assets/{asset.id}", json={"name": "Nope"}).status_code == 403
    assert client.post("/api/v1/asset-types", json={"name": "Nope"}).status_code == 403

    api_login(requester)  # no asset keys at all
    assert client.get("/api/v1/assets").status_code == 403
    assert client.get(f"/api/v1/assets/{asset.id}").status_code == 403
    assert client.get(f"/api/v1/assets/{asset.id}/history").status_code == 403
    assert client.get("/api/v1/asset-types").status_code == 403


def test_project_lead_manages_only_own_project_assets(client, org, users, api_login):
    lead = make_user("Pat Lead", "pat@uiowa.edu", ops_role="project_lead", org=org)
    mine = _project(org, "Rover", "CCR", lead_user_id=lead.id)
    mine.members.append(ProjectMember(user_id=lead.id, project_role="lead"))
    theirs = _project(org, "Showcase", "FES")
    _db.session.commit()
    foreign_asset = _asset(org, "Booth", project_id=theirs.id)
    unowned = _asset(org, "Shared Vise")

    api_login(lead)
    ok = client.post("/api/v1/assets", json={"name": "Rover Chassis", "project_id": str(mine.id)})
    assert ok.status_code == 201, ok.get_json()
    chassis_id = ok.get_json()["payload"]["asset"]["id"]
    assert client.post("/api/v1/assets", json={"name": "Booth Light", "project_id": str(theirs.id)}).status_code == 403
    assert client.post("/api/v1/assets", json={"name": "No Project"}).status_code == 403
    assert client.patch(f"/api/v1/assets/{foreign_asset.id}", json={"name": "Hijack"}).status_code == 403
    assert client.patch(f"/api/v1/assets/{unowned.id}", json={"name": "Hijack"}).status_code == 403
    assert client.patch(f"/api/v1/assets/{chassis_id}", json={"name": "Chassis v2"}).status_code == 200
    # moving an asset out of a managed project into one you do not manage is refused
    moved = client.patch(f"/api/v1/assets/{chassis_id}", json={"project_id": str(theirs.id)})
    assert moved.status_code == 403
    _db.session.expire_all()
    assert _db.session.get(Asset, UUID(chassis_id)).project_id == mine.id


def test_cross_organization_ids_are_404_or_rejected(client, org, users, api_login):
    other = _foreign_org()
    foreign_asset = Asset(organization_id=other.id, name="Foreign Lathe", code="FL-1")
    foreign_type = AssetType(organization_id=other.id, name="Foreign Type")
    foreign_location = Location(organization_id=other.id, name="Foreign Room")
    foreign_team = Team(organization_id=other.id, name="Foreign Team")
    foreign_project = OpsProject(organization_id=other.id, name="Foreign Project", code="FP")
    _db.session.add_all([foreign_asset, foreign_type, foreign_location, foreign_team, foreign_project])
    _db.session.commit()

    api_login(users["admin"])
    assert client.get(f"/api/v1/assets/{foreign_asset.id}").status_code == 404
    assert client.patch(f"/api/v1/assets/{foreign_asset.id}", json={"name": "Hijack"}).status_code == 404
    assert client.post(f"/api/v1/assets/{foreign_asset.id}/status", json={"status": "retired"}).status_code == 404
    assert client.get(f"/api/v1/assets/{foreign_asset.id}/history").status_code == 404
    assert client.get("/api/v1/assets/not-a-uuid").status_code == 404
    assert client.get("/api/v1/assets").get_json()["payload"]["total"] == 0
    assert client.get("/api/v1/asset-types").get_json()["payload"]["items"] == []

    # the same code is free in this organization
    assert client.post("/api/v1/assets", json={"name": "Our Lathe", "code": "FL-1"}).status_code == 201

    rejected = client.post(
        "/api/v1/assets",
        json={
            "name": "Smuggled",
            "parent_id": str(foreign_asset.id),
            "type_ids": [str(foreign_type.id)],
            "location_id": str(foreign_location.id),
            "responsible_team_id": str(foreign_team.id),
            "project_id": str(foreign_project.id),
        },
    )
    assert rejected.status_code == 400
    assert set(rejected.get_json()["errors"]) == {"parent_id", "type_ids", "location_id", "responsible_team_id", "project_id"}
    _db.session.refresh(foreign_asset)
    assert foreign_asset.name == "Foreign Lathe"


# --------------------------------------------------------------------------- list


def test_list_search_filters_and_sorts(client, org, users, api_login):
    api_login(users["admin"])
    lab = _location(org, "Robotics Lab")
    shop = _location(org, "Machine Shop")
    arm_team = _team(org, "Robotic Arm", lead=users["lead"])
    rover_project = _project(org, "Rover", "CCR")
    printer_type = _asset_type(org, "Printer")
    tool_type = _asset_type(org, "Tool")

    rover = _asset(org, "Crater Cruncher Rover", code="CCR-1", criticality="high", location_id=lab.id, project_id=rover_project.id, responsible_team_id=arm_team.id)
    arm = _asset(org, "Robotic Arm", parent_asset_id=rover.id, criticality="medium", location_id=lab.id, project_id=rover_project.id, responsible_team_id=arm_team.id)
    printer = _asset(org, "3D Printer 01", code="PRN-01", serial_number="MK4-777", manufacturer="Prusa", model="MK4", status="offline_unplanned", criticality="low", location_id=shop.id)
    printer.type_links.append(AssetTypeLink(asset_type_id=printer_type.id))
    calipers = _asset(org, "Digital Calipers", status="do_not_track", location_id=shop.id)
    calipers.type_links.append(AssetTypeLink(asset_type_id=tool_type.id))
    retired = _asset(org, "Old Mill", status="retired", is_active=False, location_id=shop.id)
    _db.session.commit()

    def names(query=""):
        response = client.get(f"/api/v1/assets{query}")
        assert response.status_code == 200, response.get_json()
        return _names(response.get_json()["payload"])

    assert names() == ["3D Printer 01", "Crater Cruncher Rover", "Digital Calipers", "Robotic Arm"]  # inactive hidden by default
    assert names("?filter[active]=false") == ["Old Mill"]
    assert names("?filter[active]=all") == ["3D Printer 01", "Crater Cruncher Rover", "Digital Calipers", "Old Mill", "Robotic Arm"]
    assert names("?q=mk4") == ["3D Printer 01"]  # serial number
    assert names("?q=prusa") == ["3D Printer 01"]  # manufacturer
    assert names("?q=ccr") == ["Crater Cruncher Rover"]  # code
    assert names("?q=arm") == ["Robotic Arm"]
    assert names("?filter[status]=offline_unplanned,do_not_track") == ["3D Printer 01", "Digital Calipers"]
    assert names("?filter[criticality]=high&filter[criticality]=medium") == ["Crater Cruncher Rover", "Robotic Arm"]
    assert names(f"?filter[type]={printer_type.id}") == ["3D Printer 01"]
    assert names(f"?filter[type]={printer_type.id},{tool_type.id}") == ["3D Printer 01", "Digital Calipers"]
    assert names(f"?filter[project]={rover_project.id}") == ["Crater Cruncher Rover", "Robotic Arm"]
    assert names(f"?filter[location]={shop.id}") == ["3D Printer 01", "Digital Calipers"]
    assert names(f"?filter[team]={arm_team.id}") == ["Crater Cruncher Rover", "Robotic Arm"]
    assert names("?filter[parent]=root") == ["3D Printer 01", "Crater Cruncher Rover", "Digital Calipers"]
    assert names(f"?filter[parent]={rover.id}") == ["Robotic Arm"]

    assert names("?sort=-name") == ["Robotic Arm", "Digital Calipers", "Crater Cruncher Rover", "3D Printer 01"]
    assert names("?sort=status") == ["Crater Cruncher Rover", "Robotic Arm", "3D Printer 01", "Digital Calipers"]
    assert names("?sort=criticality") == ["Digital Calipers", "3D Printer 01", "Robotic Arm", "Crater Cruncher Rover"]
    assert names("?sort=-criticality") == ["Crater Cruncher Rover", "Robotic Arm", "3D Printer 01", "Digital Calipers"]
    assert names("?sort=-created_at") == ["Digital Calipers", "3D Printer 01", "Robotic Arm", "Crater Cruncher Rover"]
    arm.description = "touched"
    _db.session.commit()
    assert names("?sort=-updated_at")[0] == "Robotic Arm"

    page = client.get("/api/v1/assets?limit=3").get_json()["payload"]
    assert len(page["items"]) == 3 and page["total"] == 4 and page["next_cursor"]
    rest = client.get(f"/api/v1/assets?limit=3&cursor={page['next_cursor']}").get_json()["payload"]
    assert _names(rest) == ["Robotic Arm"] and rest["next_cursor"] is None

    for bad in ("?filter[colour]=red", "?filter[status]=broken", "?filter[type]=nope", "?filter[parent]=nope", "?filter[active]=maybe"):
        response = client.get(f"/api/v1/assets{bad}")
        assert response.status_code == 400 and response.get_json()["code"] == "bad_filter", bad
    bad_sort = client.get("/api/v1/assets?sort=serial_number")
    assert bad_sort.status_code == 400 and bad_sort.get_json()["code"] == "bad_sort"


def test_child_and_open_work_order_counts(client, org, users, api_login):
    api_login(users["admin"])
    rover = _asset(org, "Rover")
    _asset(org, "Chassis", parent_asset_id=rover.id)
    _asset(org, "Arm", parent_asset_id=rover.id)
    _asset(org, "Scrapped Wheel", parent_asset_id=rover.id, is_active=False)
    printer = _asset(org, "Printer")

    _wo(org, 1, status="open", primary_asset_id=rover.id)
    linked = _wo(org, 2, status="in_progress")
    linked.asset_links.append(WorkOrderAsset(asset_id=rover.id, relationship_type="related"))
    both = _wo(org, 3, status="on_hold", primary_asset_id=rover.id)  # primary AND linked: counted once
    both.asset_links.append(WorkOrderAsset(asset_id=rover.id, relationship_type="primary"))
    _wo(org, 4, status="done", primary_asset_id=rover.id)  # closed: not counted
    _wo(org, 5, status="canceled", primary_asset_id=printer.id)
    secret = _project(org, "Bid", "BID", visibility="private")
    _wo(org, 6, status="open", primary_asset_id=printer.id, project_id=secret.id)  # hidden from non-members
    _db.session.commit()

    listing = {item["name"]: item for item in client.get("/api/v1/assets").get_json()["payload"]["items"]}
    assert listing["Rover"]["child_count"] == 2 and listing["Rover"]["open_work_order_count"] == 3
    assert listing["Chassis"]["child_count"] == 0 and listing["Chassis"]["open_work_order_count"] == 0
    assert listing["Printer"]["open_work_order_count"] == 1
    single = client.get(f"/api/v1/assets/{rover.id}").get_json()["payload"]["asset"]
    assert single["child_count"] == 2 and single["open_work_order_count"] == 3

    api_login(users["member"])
    listing = {item["name"]: item for item in client.get("/api/v1/assets").get_json()["payload"]["items"]}
    assert listing["Printer"]["open_work_order_count"] == 0


def test_hierarchy_view_nests_children(client, org, users, api_login):
    api_login(users["admin"])
    lab = _location(org, "Robotics Lab")
    shop = _location(org, "Machine Shop")
    rover = _asset(org, "Rover", location_id=lab.id, status="offline_planned")
    chassis = _asset(org, "Chassis", parent_asset_id=rover.id, location_id=lab.id)
    _asset(org, "Wheel Module 1", parent_asset_id=chassis.id, location_id=lab.id)
    _asset(org, "Arm", parent_asset_id=rover.id, location_id=lab.id)
    _asset(org, "Broken Wheel", parent_asset_id=chassis.id, location_id=lab.id, is_active=False)
    _asset(org, "3D Printer", location_id=shop.id)
    orphan = _asset(org, "Spare Motor", parent_asset_id=rover.id, location_id=shop.id)

    tree = client.get("/api/v1/assets?view=hierarchy&filter[status]=online&limit=1")  # status/limit ignored
    assert tree.status_code == 200, tree.get_json()
    payload = tree.get_json()["payload"]
    assert payload["next_cursor"] is None and payload["total"] == 6
    roots = {node["name"]: node for node in payload["items"]}
    assert set(roots) == {"3D Printer", "Rover"}
    rover_node = roots["Rover"]
    assert PLAN_ASSET_KEYS <= set(rover_node) and rover_node["child_count"] == 3
    assert [child["name"] for child in rover_node["children"]] == ["Arm", "Chassis", "Spare Motor"]
    chassis_node = rover_node["children"][1]
    assert [child["name"] for child in chassis_node["children"]] == ["Wheel Module 1"]  # inactive child excluded
    assert chassis_node["child_count"] == 1
    assert roots["3D Printer"]["children"] == []

    shop_only = client.get(f"/api/v1/assets?view=hierarchy&filter[location]={shop.id}").get_json()["payload"]
    assert sorted(node["name"] for node in shop_only["items"]) == ["3D Printer", "Spare Motor"]
    assert next(node for node in shop_only["items"] if node["name"] == "Spare Motor")["parent_id"] == str(rover.id)
    assert orphan.parent_asset_id == rover.id

    unknown = client.get("/api/v1/assets?view=hierarchy&filter[nope]=1")
    assert unknown.status_code == 400 and unknown.get_json()["code"] == "bad_filter"


# --------------------------------------------------------------------------- history


def test_history_merges_status_audit_and_work_orders(client, org, users, api_login):
    api_login(users["admin"])
    created = client.post("/api/v1/assets", json={"name": "Oscilloscope", "code": "OSC-1"})
    asset_id = created.get_json()["payload"]["asset"]["id"]
    assert client.patch(f"/api/v1/assets/{asset_id}", json={"description": "Rigol 4-channel"}).status_code == 200
    offline = client.post(f"/api/v1/assets/{asset_id}/status", json={"status": "offline_unplanned", "downtime_reason": "Blown fuse"})
    assert offline.status_code == 200, offline.get_json()
    primary = _wo(org, 1, status="open", primary_asset_id=UUID(asset_id), created_by_user_id=users["admin"].id)
    linked = _wo(org, 2, status="done", created_by_user_id=users["admin"].id)
    linked.asset_links.append(WorkOrderAsset(asset_id=UUID(asset_id)))
    unrelated = _wo(org, 3, status="open")
    _db.session.commit()

    response = client.get(f"/api/v1/assets/{asset_id}/history")
    assert response.status_code == 200
    items = response.get_json()["payload"]["items"]
    kinds = [(item["kind"], item.get("event_type") or item.get("to_status") or item.get("number")) for item in items]
    assert ("status", "offline_unplanned") in kinds
    assert ("audit", "asset.created") in kinds and ("audit", "asset.updated") in kinds and ("audit", "asset.status_changed") in kinds
    assert ("work_order", 1) in kinds and ("work_order", 2) in kinds and ("work_order", 3) not in kinds
    assert len(items) == 6
    stamps = [item["at"] for item in items]
    assert stamps == sorted(stamps, reverse=True)
    status_item = next(item for item in items if item["kind"] == "status")
    assert status_item["downtime_reason"] == "Blown fuse" and status_item["changed_by"]["id"] == users["admin"].id
    assert status_item["from_status"] == "online" and status_item["ended_at"] is None
    order_item = next(item for item in items if item["kind"] == "work_order" and item["number"] == 1)
    assert order_item == {"kind": "work_order", "id": str(primary.id), "number": 1, "title": "WO 1", "status": "open", "at": order_item["at"]}
    audit_item = next(item for item in items if item["kind"] == "audit" and item["event_type"] == "asset.updated")
    assert audit_item["actor"]["id"] == users["admin"].id and audit_item["after"]["description"] == "Rigol 4-channel"

    limited = client.get(f"/api/v1/assets/{asset_id}/history?limit=2").get_json()["payload"]["items"]
    assert len(limited) == 2 and [item["at"] for item in limited] == stamps[:2]

    # a member who can only see assigned work orders does not see the unassigned ones in the timeline
    operator = make_user("Ollie Operator", "ollie@uiowa.edu", ops_role="shop_operator", org=org)
    api_login(operator)
    items = client.get(f"/api/v1/assets/{asset_id}/history").get_json()["payload"]["items"]
    assert [item["kind"] for item in items if item["kind"] == "work_order"] == []
    assert unrelated.number == 3


# --------------------------------------------------------------------------- asset types


def test_asset_types_list_and_create(client, org, users, api_login):
    api_login(users["admin"])
    assert client.get("/api/v1/asset-types").get_json()["payload"] == {"items": [], "next_cursor": None, "total": 0, "asset_types": []}
    created = client.post("/api/v1/asset-types", json={"name": "Vehicle"})
    assert created.status_code == 201
    vehicle = created.get_json()["payload"]["asset_type"]
    assert vehicle["color"] == "#475569" and vehicle["icon"] == "box" and vehicle["asset_count"] == 0
    dupe = client.post("/api/v1/asset-types", json={"name": "vehicle"})
    assert dupe.status_code == 400 and set(dupe.get_json()["errors"]) == {"name"}
    bad = client.post("/api/v1/asset-types", json={"name": "", "color": "blue", "icon": "x" * 61})
    assert bad.status_code == 400 and set(bad.get_json()["errors"]) == {"name", "color", "icon"}
    event = AuditEvent.query.filter_by(event_type="asset_type.created", entity_id=vehicle["id"]).one()
    assert event.entity_type == "asset_type"

    rover = _asset(org, "Rover")
    rover.type_links.append(AssetTypeLink(asset_type_id=UUID(vehicle["id"])))
    scrapped = _asset(org, "Scrapped Cart", is_active=False)
    scrapped.type_links.append(AssetTypeLink(asset_type_id=UUID(vehicle["id"])))
    secret = _project(org, "Bid", "BID", visibility="private")
    hidden = _asset(org, "Secret Van", project_id=secret.id)
    hidden.type_links.append(AssetTypeLink(asset_type_id=UUID(vehicle["id"])))
    _db.session.commit()
    assert client.get("/api/v1/asset-types").get_json()["payload"]["items"][0]["asset_count"] == 2
    api_login(users["member"])
    assert client.get("/api/v1/asset-types").get_json()["payload"]["items"][0]["asset_count"] == 1


# --------------------------------------------------------------------------- service-level


def test_service_authorization_and_lookups(ctx_admin, ctx_member, ctx_requester, org):
    asset = asset_service.create(ctx_admin, {"name": "Lathe"})
    assert asset.organization_id == org.id and asset.created_by_user_id == ctx_admin.user.id
    assert asset_service.get(ctx_member, asset.id) is asset
    with pytest.raises(Forbidden):
        asset_service.create(ctx_member, {"name": "Denied"})
    with pytest.raises(Forbidden):
        asset_service.update(ctx_member, asset, {"name": "Denied"})
    with pytest.raises(Forbidden):
        asset_service.get(ctx_requester, asset.id)
    with pytest.raises(Forbidden):
        asset_service.list_query(ctx_requester)
    with pytest.raises(Forbidden):
        asset_service.list_types(ctx_requester)
    with pytest.raises(NotFound):
        asset_service.get(ctx_admin, uuid4())
    with pytest.raises(NotFound):
        asset_service.get(ctx_admin, "garbage")
    with pytest.raises(ValidationErrors) as exc:
        asset_service.update(ctx_admin, asset, {"status": "retired"})
    assert exc.value.errors == {"status": "Use the status endpoint."}
    with pytest.raises(Validation) as cycle:
        asset_service.update(ctx_admin, asset, {"parent_id": str(asset.id)})
    assert cycle.value.code == "asset_cycle"

    other = _foreign_org()
    foreign = Asset(organization_id=other.id, name="Foreign")
    _db.session.add(foreign)
    _db.session.commit()
    with pytest.raises(NotFound):
        asset_service.get(ctx_admin, foreign.id)
    with pytest.raises(NotFound):
        asset_service.update(ctx_admin, foreign, {"name": "Hijack"})
    with pytest.raises(NotFound):
        asset_service.history(ctx_admin, foreign)
    assert policy.can_read_project is not None  # visibility helpers are the ones from policy
    assert asset_service.list_query(ctx_admin).count() == 1


def test_history_limit_bounds_and_ordering(ctx_admin, org, users):
    asset = asset_service.create(ctx_admin, {"name": "Charger"})
    first = asset_service.change_status(ctx_admin, asset, "offline_planned", note="calibration")
    second = asset_service.change_status(ctx_admin, asset, "online")
    entries = asset_service.history(ctx_admin, asset, limit=1000)
    assert [kind for kind, _at, _row in entries][:2] == ["audit", "status"]
    status_rows = [row for kind, _at, row in entries if kind == "status"]
    assert status_rows == [second, first]
    assert first.ended_at is not None and first.ended_at >= first.started_at
    assert second.ended_at is None
    assert second.started_at <= utcnow() + timedelta(seconds=1)
    assert len(asset_service.history(ctx_admin, asset, limit=0)) == 1
