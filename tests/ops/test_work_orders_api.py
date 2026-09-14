"""Work orders API: create / list / detail / update / sub-work orders /
assignment / watchers / time & cost / dependencies / duplicate.

Row helpers (``_project``, ``_team`` ...) are imported by the transition and
authz test modules so every work-order test builds its fixtures the same way.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from asme.extensions import db as _db
from asme.ops import policy
from asme.ops.models import (
    Asset,
    AuditEvent,
    Category,
    Location,
    Notification,
    OpsProject,
    Organization,
    ProjectMember,
    Team,
    TeamMember,
    Vendor,
    WorkOrder,
)
from asme.ops.services import work_orders
from asme.ops.types import utcnow
from tests.ops.conftest import make_user

# --------------------------------------------------------------------------- row helpers


def _project(org, name, code, visibility="chapter", members=(), **kw):
    row = OpsProject(organization_id=org.id, name=name, code=code, visibility=visibility, **kw)
    _db.session.add(row)
    _db.session.flush()
    for user in members:
        row.members.append(ProjectMember(user_id=user.id, project_role="member"))
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


def _category(org, name, **kw):
    """Get-or-create: the bootstrap already seeds Safety, Electrical, Mechanical ..."""
    row = Category.query.filter_by(organization_id=org.id, name=name).first()
    if row is None:
        row = Category(organization_id=org.id, name=name, **kw)
        _db.session.add(row)
        _db.session.commit()
    return row


def _location(org, name):
    row = Location(organization_id=org.id, name=name)
    _db.session.add(row)
    _db.session.commit()
    return row


def _asset(org, name, project=None, **kw):
    row = Asset(organization_id=org.id, name=name, project_id=project.id if project else None, **kw)
    _db.session.add(row)
    _db.session.commit()
    return row


def _vendor(org, name):
    row = Vendor(organization_id=org.id, name=name)
    _db.session.add(row)
    _db.session.commit()
    return row


def _other_org_work_order():
    """A second organization with one work order; ids from it must 404 everywhere."""
    other = Organization(name="Other Chapter", slug=f"other-{uuid.uuid4().hex[:6]}")
    _db.session.add(other)
    _db.session.flush()
    foreign = WorkOrder(organization_id=other.id, number=1, title="Foreign", status="open")
    _db.session.add(foreign)
    _db.session.commit()
    return other, foreign


def _create(ctx, **data):
    data.setdefault("title", "Test work order")
    return work_orders.create(ctx, data)


def _audit(event_type, entity_id=None):
    query = AuditEvent.query.filter_by(event_type=event_type)
    if entity_id is not None:
        query = query.filter_by(entity_id=str(entity_id))
    return query.order_by(AuditEvent.occurred_at).all()


def _iso(dt):
    return dt.isoformat().replace("+00:00", "Z")


# --------------------------------------------------------------------------- create


def test_create_work_order_happy_path(client, org, users, api_login, captured_events):
    project = _project(org, "Crater Cruncher Rover", "CCR")
    team = _team(org, "Robotic Arm", members=[users["member"]])
    category = _category(org, "Mechanical Repair")
    location = _location(org, "Robotics Lab")
    asset = _asset(org, "Rover Chassis", project=project)
    related = _asset(org, "Wheel Module 1")
    vendor = _vendor(org, "McMaster-Carr")
    start = utcnow().replace(microsecond=0)
    due = start + timedelta(days=3)

    api_login(users["admin"])
    response = client.post(
        "/api/v1/work-orders",
        json={
            "title": "Replace stripped shoulder gear",
            "description": "The shoulder joint slips under load.",
            "priority": "high",
            "work_type": "reactive",
            "project_id": str(project.id),
            "location_id": str(location.id),
            "primary_asset_id": str(asset.id),
            "team_id": str(team.id),
            "vendor_id": str(vendor.id),
            "start_at": _iso(start),
            "due_at": _iso(due),
            "estimated_minutes": 90,
            "budget_code": "ARM-2026",
            "parent_completion_policy": "auto",
            "assignee_user_ids": [users["member"].id],
            "assignee_team_ids": [str(team.id)],
            "watcher_user_ids": [users["lead"].id],
            "category_ids": [str(category.id)],
            "asset_ids": [str(related.id)],
        },
    )
    assert response.status_code == 201, response.get_json()
    body = response.get_json()["payload"]["work_order"]
    assert body["number"] == 1 and body["status"] == "open" and body["priority"] == "high"
    assert body["project"]["code"] == "CCR" and body["location"]["name"] == "Robotics Lab"
    assert body["asset"]["name"] == "Rover Chassis" and body["team"]["name"] == "Robotic Arm"
    assert body["vendor"]["name"] == "McMaster-Carr" and body["budget_code"] == "ARM-2026"
    assert [a["id"] for a in body["assignees"]] == [users["member"].id]
    assert [t["name"] for t in body["assignee_teams"]] == ["Robotic Arm"]
    assert [w["id"] for w in body["watchers"]] == [users["lead"].id]
    assert [c["name"] for c in body["categories"]] == ["Mechanical Repair"]
    assert [a["name"] for a in body["related_assets"]] == ["Wheel Module 1"]
    assert body["start_at"] == _iso(start) and body["due_at"] == _iso(due)
    assert body["estimated_minutes"] == 90 and body["actual_minutes"] == 0
    assert body["is_overdue"] is False and body["is_blocked"] is False
    assert body["parent_id"] is None and body["parent_number"] is None
    assert body["sub_work_orders"] == {"total": 0, "done": 0}
    assert body["created_by"]["id"] == users["admin"].id
    assert body["parent_completion_policy"] == "auto"
    assert [(h["from_status"], h["to_status"]) for h in body["status_history"]] == [(None, "open")]
    assert body["status_history"][0]["changed_by"]["id"] == users["admin"].id
    assert body["time_entries"] == [] and body["cost_entries"] == []
    assert body["dependencies"] == {"blocked_by": [], "blocking": []} and body["children"] == []

    created = _audit("work_order.created", body["id"])
    assert len(created) == 1 and created[0].actor_user_id == users["admin"].id
    assert created[0].after_json["title"] == "Replace stripped shoulder gear"
    assert created[0].after_json["assignee_user_ids"] == [users["member"].id]

    assigned = Notification.query.filter_by(type="work_order.assigned").all()
    assert {n.user_id for n in assigned} == {users["member"].id}
    assert assigned[0].title == "#1 Replace stripped shoulder gear assigned to you"
    watching = Notification.query.filter_by(user_id=users["lead"].id).all()
    assert len(watching) == 1 and watching[0].type == "work_order.status_changed"

    names = [name for name, _ in captured_events]
    assert "ops.work_order.created" in names
    payload = [p for name, p in captured_events if name == "ops.work_order.created"][0]
    assert payload == {"work_order_id": body["id"], "organization_id": str(org.id)}


def test_create_reports_every_format_error(client, org, users, api_login):
    api_login(users["admin"])
    response = client.post(
        "/api/v1/work-orders",
        json={
            "title": "",
            "priority": "urgent",
            "work_type": "magic",
            "estimated_minutes": -5,
            "budget_code": "x" * 61,
            "due_at": "not-a-date",
            "assignee_user_ids": "me",
            "parent_completion_policy": "sometimes",
        },
    )
    assert response.status_code == 400
    body = response.get_json()
    assert body["code"] == "validation"
    assert set(body["errors"]) == {
        "title",
        "priority",
        "work_type",
        "estimated_minutes",
        "budget_code",
        "due_at",
        "assignee_user_ids",
        "parent_completion_policy",
    }


def test_create_reports_every_reference_and_rule_error(client, org, users, api_login):
    other, _foreign = _other_org_work_order()
    foreign_location = Location(organization_id=other.id, name="Elsewhere")
    _db.session.add(foreign_location)
    _db.session.commit()
    start = utcnow()
    api_login(users["admin"])
    response = client.post(
        "/api/v1/work-orders",
        json={
            "title": "Broken references",
            "project_id": str(uuid.uuid4()),
            "location_id": str(foreign_location.id),
            "primary_asset_id": str(uuid.uuid4()),
            "team_id": str(uuid.uuid4()),
            "vendor_id": str(uuid.uuid4()),
            "parent_id": str(uuid.uuid4()),
            "assignee_user_ids": [999999],
            "assignee_team_ids": [str(uuid.uuid4())],
            "watcher_user_ids": [999998],
            "category_ids": [str(uuid.uuid4())],
            "asset_ids": [str(uuid.uuid4())],
            "start_at": _iso(start),
            "due_at": _iso(start - timedelta(hours=1)),
        },
    )
    assert response.status_code == 400
    errors = response.get_json()["errors"]
    assert errors["project_id"] == "Unknown project."
    assert set(errors) == {
        "project_id",
        "location_id",
        "primary_asset_id",
        "team_id",
        "vendor_id",
        "parent_id",
        "assignee_user_ids",
        "assignee_team_ids",
        "watcher_user_ids",
        "category_ids",
        "asset_ids",
        "due_at",
    }


def test_private_project_is_unknown_to_non_members(client, org, users, api_login):
    secret = _project(org, "Sponsor Bid", "BID", visibility="private")
    api_login(users["member"])
    response = client.post("/api/v1/work-orders", json={"title": "Peek", "project_id": str(secret.id)})
    assert response.status_code == 400 and response.get_json()["errors"] == {"project_id": "Unknown project."}


def test_critical_priority_requires_cancel_permission_or_safety_category(client, org, users, api_login):
    safety = _category(org, "Safety")
    api_login(users["member"])  # full_member: no work_order.cancel
    denied = client.post("/api/v1/work-orders", json={"title": "Exposed wiring", "priority": "critical"})
    assert denied.status_code == 400
    assert denied.get_json()["errors"] == {"priority": "Critical priority requires a safety officer or lead."}

    allowed = client.post("/api/v1/work-orders", json={"title": "Exposed wiring", "priority": "critical", "category_ids": [str(safety.id)]})
    assert allowed.status_code == 201 and allowed.get_json()["payload"]["work_order"]["priority"] == "critical"

    api_login(users["admin"])
    admin = client.post("/api/v1/work-orders", json={"title": "Gas leak", "priority": "critical"})
    assert admin.status_code == 201


def test_asset_project_is_inherited_and_inactive_assignees_rejected(client, org, users, api_login):
    project = _project(org, "Rover", "CCR")
    asset = _asset(org, "Chassis", project=project)
    suspended = make_user("Sue Spended", "sue@uiowa.edu", org=org)
    from asme.ops import bootstrap

    bootstrap.membership_for(suspended, org).member_status = "suspended"
    _db.session.commit()

    api_login(users["admin"])
    inherited = client.post("/api/v1/work-orders", json={"title": "Inspect chassis", "primary_asset_id": str(asset.id)})
    assert inherited.status_code == 201
    assert inherited.get_json()["payload"]["work_order"]["project"]["id"] == str(project.id)

    rejected = client.post("/api/v1/work-orders", json={"title": "Nope", "assignee_user_ids": [suspended.id]})
    assert rejected.status_code == 400 and "assignee_user_ids" in rejected.get_json()["errors"]


def test_numbers_are_sequential_per_organization(ctx_admin, org):
    first = _create(ctx_admin, title="One")
    second = _create(ctx_admin, title="Two")
    assert (first.number, second.number) == (1, 2)
    other, foreign = _other_org_work_order()
    assert foreign.number == 1 and foreign.organization_id != org.id


# --------------------------------------------------------------------------- draft / update


def test_draft_publishes_via_patch_and_other_status_changes_are_rejected(client, org, users, api_login, captured_events):
    api_login(users["admin"])
    draft = client.post("/api/v1/work-orders", json={"title": "Plan showcase", "draft": True}).get_json()["payload"]["work_order"]
    assert draft["status"] == "draft"
    assert [(h["from_status"], h["to_status"]) for h in draft["status_history"]] == [(None, "draft")]

    rejected = client.patch(f"/api/v1/work-orders/{draft['id']}", json={"status": "done"})
    assert rejected.status_code == 400
    assert rejected.get_json()["errors"] == {"status": "Use the action endpoints to change status."}

    published = client.patch(f"/api/v1/work-orders/{draft['id']}", json={"status": "open", "title": "Plan the showcase"})
    assert published.status_code == 200
    body = published.get_json()["payload"]["work_order"]
    assert body["status"] == "open" and body["title"] == "Plan the showcase"
    assert [(h["from_status"], h["to_status"]) for h in body["status_history"]] == [(None, "draft"), ("draft", "open")]
    assert [p["status"] for name, p in captured_events if name == "ops.work_order.status_changed"] == ["open"]

    noop = client.patch(f"/api/v1/work-orders/{draft['id']}", json={"status": "open"})
    assert noop.status_code == 200

    back_to_draft = client.patch(f"/api/v1/work-orders/{draft['id']}", json={"status": "draft"})
    assert back_to_draft.status_code == 400


def test_update_audits_only_changed_fields(client, org, users, api_login):
    category = _category(org, "Electrical")
    api_login(users["admin"])
    wo = client.post("/api/v1/work-orders", json={"title": "Old title", "priority": "low", "estimated_minutes": 30}).get_json()["payload"]["work_order"]

    response = client.patch(
        f"/api/v1/work-orders/{wo['id']}",
        json={"title": "New title", "priority": "medium", "estimated_minutes": 30, "category_ids": [str(category.id)]},
    )
    assert response.status_code == 200
    body = response.get_json()["payload"]["work_order"]
    assert body["title"] == "New title" and body["priority"] == "medium"
    assert [c["name"] for c in body["categories"]] == ["Electrical"]

    events = _audit("work_order.updated", wo["id"])
    assert len(events) == 1
    assert events[0].before_json == {"title": "Old title", "priority": "low", "category_ids": []}
    assert events[0].after_json == {"title": "New title", "priority": "medium", "category_ids": [str(category.id)]}
    assert events[0].metadata_json["fields"] == ["category_ids", "priority", "title"]

    bad = client.patch(f"/api/v1/work-orders/{wo['id']}", json={"title": "", "priority": "urgent"})
    assert bad.status_code == 400 and set(bad.get_json()["errors"]) == {"title", "priority"}


def test_update_can_clear_and_swap_references(client, org, users, api_login):
    project = _project(org, "Rover", "CCR")
    asset_a = _asset(org, "A")
    asset_b = _asset(org, "B")
    api_login(users["admin"])
    wo = client.post(
        "/api/v1/work-orders",
        json={"title": "Refs", "project_id": str(project.id), "primary_asset_id": str(asset_a.id), "asset_ids": [str(asset_b.id)]},
    ).get_json()["payload"]["work_order"]
    assert wo["asset"]["name"] == "A" and [a["name"] for a in wo["related_assets"]] == ["B"]

    swapped = client.patch(
        f"/api/v1/work-orders/{wo['id']}", json={"project_id": None, "primary_asset_id": str(asset_b.id), "asset_ids": [str(asset_a.id)]}
    ).get_json()["payload"]["work_order"]
    assert swapped["project"] is None and swapped["asset"]["name"] == "B"
    assert [a["name"] for a in swapped["related_assets"]] == ["A"]


# --------------------------------------------------------------------------- cross-organization


def test_foreign_organization_ids_are_not_found(client, org, users, api_login):
    _other, foreign = _other_org_work_order()
    api_login(users["admin"])
    assert client.get(f"/api/v1/work-orders/{foreign.id}").status_code == 404
    assert client.patch(f"/api/v1/work-orders/{foreign.id}", json={"title": "x"}).status_code == 404
    assert client.post(f"/api/v1/work-orders/{foreign.id}/start", json={}).status_code == 404
    assert client.get("/api/v1/work-orders/not-a-uuid").status_code == 404
    listing = client.get("/api/v1/work-orders?tab=all").get_json()["payload"]
    assert listing["total"] == 0 and listing["items"] == []


# --------------------------------------------------------------------------- list


def test_list_tabs_filters_sort_and_search(client, org, users, api_login, ctx_admin):
    project = _project(org, "Rover", "CCR")
    team = _team(org, "Wheels", lead=users["lead"], members=[users["member"]])
    category = _category(org, "Fabrication")
    location = _location(org, "Machine Shop")
    asset = _asset(org, "Lathe")
    vendor = _vendor(org, "DigiKey")
    now = utcnow()

    late = _create(ctx_admin, title="Late wheel hub", priority="high", due_at=_iso(now - timedelta(days=2)), project_id=str(project.id))
    soon = _create(ctx_admin, title="Bearing swap", priority="critical", due_at=_iso(now + timedelta(hours=2)), assignee_user_ids=[users["member"].id])
    via_team = _create(ctx_admin, title="Team weld", priority="low", assignee_team_ids=[str(team.id)], category_ids=[str(category.id)])
    parked = _create(ctx_admin, title="Lathe cleanup", location_id=str(location.id), asset_ids=[str(asset.id)], vendor_id=str(vendor.id))
    finished = _create(ctx_admin, title="Finished thing", work_type="event")
    work_orders.transition(ctx_admin, finished, "complete")
    child = _create(ctx_admin, title="Child of late", parent_id=str(late.id))
    _db.session.commit()

    api_login(users["admin"])
    default = client.get("/api/v1/work-orders").get_json()["payload"]
    assert default["tabs"] == {"todo": 5, "done": 1}
    assert default["total"] == 5 and finished.title not in [i["title"] for i in default["items"]]
    assert {i["title"] for i in default["items"]} == {"Late wheel hub", "Bearing swap", "Team weld", "Lathe cleanup", "Child of late"}
    assert "work_orders" in default and default["next_cursor"] is None
    late_item = next(i for i in default["items"] if i["title"] == "Late wheel hub")
    assert late_item["is_overdue"] is True and late_item["sub_work_orders"] == {"total": 1, "done": 0}
    child_item = next(i for i in default["items"] if i["title"] == "Child of late")
    assert child_item["parent_number"] == late.number and child_item["project"]["id"] == str(project.id)

    done = client.get("/api/v1/work-orders?tab=done").get_json()["payload"]
    assert [i["title"] for i in done["items"]] == ["Finished thing"]
    assert client.get("/api/v1/work-orders?tab=all").get_json()["payload"]["total"] == 6
    assert client.get("/api/v1/work-orders?tab=bogus").status_code == 400

    def titles(query):
        response = client.get(f"/api/v1/work-orders?{query}")
        assert response.status_code == 200, response.get_json()
        return [i["title"] for i in response.get_json()["payload"]["items"]]

    assert titles("status=done&tab=all") == ["Finished thing"]
    assert set(titles("priority=high,critical")) == {"Late wheel hub", "Bearing swap"}
    assert titles("work_type=event&tab=all") == ["Finished thing"]
    assert set(titles(f"project={project.id}")) == {"Late wheel hub", "Child of late"}
    assert titles(f"location={location.id}") == ["Lathe cleanup"]
    assert titles(f"asset={asset.id}") == ["Lathe cleanup"]
    assert titles(f"vendor={vendor.id}") == ["Lathe cleanup"]
    assert titles(f"team={team.id}") == ["Team weld"]
    assert set(titles(f"assignee={users['member'].id}")) == {"Bearing swap", "Team weld"}
    assert titles(f"category={category.id}") == ["Team weld"]
    assert titles("due=overdue") == ["Late wheel hub"]
    assert titles("due=today") == ["Bearing swap"]
    assert set(titles("due=week")) == {"Bearing swap"}
    assert set(titles("due=none")) == {"Team weld", "Lathe cleanup", "Child of late"}
    assert titles(f"created_by={users['member'].id}") == []
    assert len(titles("created_by=me")) == 5
    assert titles("parent=none&tab=all") and "Child of late" not in titles("parent=none")
    assert titles(f"parent={late.id}") == ["Child of late"]
    assert titles(f"q=%23{soon.number}") == ["Bearing swap"]
    assert titles(f"q={soon.number}") == ["Bearing swap"]
    assert titles("q=lathe") == ["Lathe cleanup"]
    assert titles("sort=-priority")[:2] == ["Bearing swap", "Late wheel hub"]
    assert titles("sort=priority")[-2:] == ["Late wheel hub", "Bearing swap"]
    assert titles("sort=due_at")[:2] == ["Late wheel hub", "Bearing swap"]
    assert titles("sort=-due_at")[:2] == ["Bearing swap", "Late wheel hub"]
    assert titles("sort=number")[0] == "Late wheel hub" and titles("sort=-number")[0] == "Child of late"
    assert titles("sort=title")[0] == "Bearing swap"
    assert titles("sort=created_at")[0] == "Late wheel hub"

    api_login(users["member"])
    assert set(titles("assignee=me")) == {"Bearing swap", "Team weld"}
    tabs = client.get("/api/v1/work-orders?assignee=me").get_json()["payload"]["tabs"]
    assert tabs == {"todo": 2, "done": 0}

    # parse_filters rejects unknown names in the explicit filter[...] form (bare unknown keys are ignored)
    unknown = client.get("/api/v1/work-orders?filter[colour]=red")
    assert unknown.status_code == 400 and unknown.get_json()["code"] == "bad_filter"
    assert titles("filter[status]=done&tab=all") == ["Finished thing"]
    assert client.get("/api/v1/work-orders?sort=colour").status_code == 400
    assert client.get("/api/v1/work-orders?status=bogus").status_code == 400
    assert client.get("/api/v1/work-orders?due=someday").status_code == 400
    assert client.get("/api/v1/work-orders?project=not-a-uuid").status_code == 400

    paged = client.get("/api/v1/work-orders?limit=2&sort=number").get_json()["payload"]
    assert len(paged["items"]) == 2 and paged["next_cursor"] and paged["total"] == 5
    rest = client.get(f"/api/v1/work-orders?limit=2&sort=number&cursor={paged['next_cursor']}").get_json()["payload"]
    assert [i["number"] for i in rest["items"]] == [via_team.number, parked.number]


# --------------------------------------------------------------------------- sub-work orders


def test_sub_work_orders_inherit_project_and_respect_nesting_limit(client, org, users, api_login):
    project = _project(org, "Rover", "CCR")
    api_login(users["admin"])
    root = client.post("/api/v1/work-orders", json={"title": "Root", "project_id": str(project.id)}).get_json()["payload"]["work_order"]

    level1 = client.post(f"/api/v1/work-orders/{root['id']}/sub-work-orders", json={"title": "Level 1"})
    assert level1.status_code == 201
    l1 = level1.get_json()["payload"]["work_order"]
    assert l1["parent_id"] == root["id"] and l1["parent_number"] == root["number"]
    assert l1["project"]["id"] == str(project.id)

    l2 = client.post(f"/api/v1/work-orders/{l1['id']}/sub-work-orders", json={"title": "Level 2"}).get_json()["payload"]["work_order"]
    l3 = client.post(f"/api/v1/work-orders/{l2['id']}/sub-work-orders", json={"title": "Level 3"}).get_json()["payload"]["work_order"]
    too_deep = client.post(f"/api/v1/work-orders/{l3['id']}/sub-work-orders", json={"title": "Level 4"})
    assert too_deep.status_code == 400 and "parent_id" in too_deep.get_json()["errors"]

    detail = client.get(f"/api/v1/work-orders/{root['id']}").get_json()["payload"]["work_order"]
    assert [c["title"] for c in detail["children"]] == ["Level 1"]
    assert detail["sub_work_orders"] == {"total": 1, "done": 0}

    # re-parenting under a descendant or itself is rejected
    cycle = client.patch(f"/api/v1/work-orders/{root['id']}", json={"parent_id": l2["id"]})
    assert cycle.status_code == 400 and "parent_id" in cycle.get_json()["errors"]
    selfie = client.patch(f"/api/v1/work-orders/{root['id']}", json={"parent_id": root["id"]})
    assert selfie.status_code == 400 and "parent_id" in selfie.get_json()["errors"]

    missing_parent = client.post(f"/api/v1/work-orders/{uuid.uuid4()}/sub-work-orders", json={"title": "Orphan"})
    assert missing_parent.status_code == 404


# --------------------------------------------------------------------------- assignees / watchers


def test_assignees_and_watchers_replace_notify_and_audit(client, org, users, api_login):
    team = _team(org, "Electrical", lead=users["lead"], members=[users["member"]])
    extra = make_user("Eve Extra", "eve@uiowa.edu", org=org)
    api_login(users["admin"])
    wo = client.post("/api/v1/work-orders", json={"title": "Wire harness", "assignee_user_ids": [users["member"].id]}).get_json()["payload"]["work_order"]
    Notification.query.delete()
    _db.session.commit()

    replaced = client.put(
        f"/api/v1/work-orders/{wo['id']}/assignees", json={"user_ids": [extra.id], "team_ids": [str(team.id)]}
    )
    assert replaced.status_code == 200
    body = replaced.get_json()["payload"]["work_order"]
    assert [a["id"] for a in body["assignees"]] == [extra.id]
    assert [t["id"] for t in body["assignee_teams"]] == [str(team.id)]
    notified = {n.user_id for n in Notification.query.filter_by(type="work_order.assigned").all()}
    assert notified == {extra.id, users["lead"].id, users["member"].id}
    changed = _audit("work_order.assignees_changed", wo["id"])
    assert len(changed) == 1
    assert changed[0].before_json == {"user_ids": [users["member"].id], "team_ids": []}
    assert changed[0].after_json == {"user_ids": [extra.id], "team_ids": [str(team.id)]}

    unchanged = client.put(f"/api/v1/work-orders/{wo['id']}/assignees", json={"user_ids": [extra.id], "team_ids": [str(team.id)]})
    assert unchanged.status_code == 200 and len(_audit("work_order.assignees_changed", wo["id"])) == 1

    bad = client.put(f"/api/v1/work-orders/{wo['id']}/assignees", json={"user_ids": [424242], "team_ids": [str(uuid.uuid4())]})
    assert bad.status_code == 400 and set(bad.get_json()["errors"]) == {"assignee_user_ids", "assignee_team_ids"}

    watchers = client.put(f"/api/v1/work-orders/{wo['id']}/watchers", json={"user_ids": [users["lead"].id]})
    assert watchers.status_code == 200
    assert [w["id"] for w in watchers.get_json()["payload"]["work_order"]["watchers"]] == [users["lead"].id]
    assert len(_audit("work_order.watchers_changed", wo["id"])) == 1

    api_login(users["member"])
    watched = client.post(f"/api/v1/work-orders/{wo['id']}/watch", json={})
    assert watched.status_code == 200
    assert {w["id"] for w in watched.get_json()["payload"]["work_order"]["watchers"]} == {users["lead"].id, users["member"].id}
    again = client.post(f"/api/v1/work-orders/{wo['id']}/watch", json={})
    assert again.status_code == 200 and len(_audit("work_order.watchers_changed", wo["id"])) == 2
    unwatched = client.delete(f"/api/v1/work-orders/{wo['id']}/watch")
    assert unwatched.status_code == 200
    assert [w["id"] for w in unwatched.get_json()["payload"]["work_order"]["watchers"]] == [users["lead"].id]
    assert len(_audit("work_order.watchers_changed", wo["id"])) == 3


# --------------------------------------------------------------------------- time & cost


def test_time_entries_create_derive_validate_and_delete(client, org, users, api_login):
    api_login(users["admin"])
    wo = client.post("/api/v1/work-orders", json={"title": "Timed"}).get_json()["payload"]["work_order"]
    url = f"/api/v1/work-orders/{wo['id']}/time-entries"

    logged = client.post(url, json={"minutes": 45, "note": "Disassembly"})
    assert logged.status_code == 201
    payload = logged.get_json()["payload"]
    assert payload["time_entry"]["minutes"] == 45 and payload["time_entry"]["user"]["id"] == users["admin"].id
    assert payload["work_order"]["actual_minutes"] == 45

    start = utcnow().replace(microsecond=0)
    derived = client.post(url, json={"started_at": _iso(start), "ended_at": _iso(start + timedelta(minutes=90))})
    assert derived.status_code == 201
    assert derived.get_json()["payload"]["time_entry"]["minutes"] == 90
    assert derived.get_json()["payload"]["work_order"]["actual_minutes"] == 135

    for_other = client.post(url, json={"minutes": 10, "user_id": users["member"].id})
    assert for_other.status_code == 201 and for_other.get_json()["payload"]["time_entry"]["user"]["id"] == users["member"].id

    missing = client.post(url, json={"note": "no minutes"})
    assert missing.status_code == 400 and set(missing.get_json()["errors"]) == {"minutes"}
    zero = client.post(url, json={"minutes": 0})
    assert zero.status_code == 400 and set(zero.get_json()["errors"]) == {"minutes"}
    backwards = client.post(url, json={"started_at": _iso(start), "ended_at": _iso(start - timedelta(minutes=5))})
    assert backwards.status_code == 400 and set(backwards.get_json()["errors"]) == {"ended_at", "minutes"}
    unknown_user = client.post(url, json={"minutes": 5, "user_id": 987654})
    assert unknown_user.status_code == 400 and set(unknown_user.get_json()["errors"]) == {"user_id"}

    assert len(_audit("work_order.time_logged", wo["id"])) == 3
    entry_id = payload["time_entry"]["id"]
    removed = client.delete(f"{url}/{entry_id}")
    assert removed.status_code == 200 and removed.get_json()["payload"]["work_order"]["actual_minutes"] == 100
    assert len(_audit("work_order.time_removed", wo["id"])) == 1
    assert client.delete(f"{url}/{entry_id}").status_code == 404
    assert client.delete(f"{url}/{uuid.uuid4()}").status_code == 404


def test_cost_entries_create_validate_and_delete(client, org, users, api_login):
    vendor = _vendor(org, "Amazon Business")
    api_login(users["admin"])
    wo = client.post("/api/v1/work-orders", json={"title": "Costed"}).get_json()["payload"]["work_order"]
    url = f"/api/v1/work-orders/{wo['id']}/cost-entries"

    added = client.post(url, json={"type": "parts", "amount": "12.50", "vendor_id": str(vendor.id), "description": "Bearings"})
    assert added.status_code == 201
    payload = added.get_json()["payload"]
    assert payload["cost_entry"]["amount"] == 12.5 and payload["cost_entry"]["vendor"]["name"] == "Amazon Business"
    assert payload["cost_entry"]["type"] == "parts" and payload["work_order"]["cost_entries"][0]["description"] == "Bearings"

    bad = client.post(url, json={"type": "bribes", "amount": -1})
    assert bad.status_code == 400 and set(bad.get_json()["errors"]) == {"type", "amount"}
    missing = client.post(url, json={})
    assert missing.status_code == 400 and set(missing.get_json()["errors"]) == {"type", "amount"}
    unknown_vendor = client.post(url, json={"type": "vendor", "amount": 5, "vendor_id": str(uuid.uuid4())})
    assert unknown_vendor.status_code == 400 and set(unknown_vendor.get_json()["errors"]) == {"vendor_id"}

    assert len(_audit("work_order.cost_added", wo["id"])) == 1
    removed = client.delete(f"{url}/{payload['cost_entry']['id']}")
    assert removed.status_code == 200 and removed.get_json()["payload"]["work_order"]["cost_entries"] == []
    assert len(_audit("work_order.cost_removed", wo["id"])) == 1
    assert client.delete(f"{url}/{payload['cost_entry']['id']}").status_code == 404


# --------------------------------------------------------------------------- dependencies


def test_dependencies_block_start_reject_cycles_and_recompute(client, org, users, api_login):
    api_login(users["admin"])
    a = client.post("/api/v1/work-orders", json={"title": "A"}).get_json()["payload"]["work_order"]
    b = client.post("/api/v1/work-orders", json={"title": "B"}).get_json()["payload"]["work_order"]
    c = client.post("/api/v1/work-orders", json={"title": "C"}).get_json()["payload"]["work_order"]

    # A is blocked by B
    added = client.post(f"/api/v1/work-orders/{a['id']}/dependencies", json={"blocking_work_order_id": b["id"]})
    assert added.status_code == 201, added.get_json()
    payload = added.get_json()["payload"]
    assert payload["dependency"]["work_order"]["number"] == b["number"]
    assert payload["work_order"]["is_blocked"] is True
    assert [d["work_order"]["title"] for d in payload["work_order"]["dependencies"]["blocked_by"]] == ["B"]
    b_detail = client.get(f"/api/v1/work-orders/{b['id']}").get_json()["payload"]["work_order"]
    assert [d["work_order"]["title"] for d in b_detail["dependencies"]["blocking"]] == ["A"]
    assert len(_audit("work_order.dependency_added", a["id"])) == 1

    blocked = client.post(f"/api/v1/work-orders/{a['id']}/start", json={})
    assert blocked.status_code == 409
    assert blocked.get_json()["code"] == "blocked" and blocked.get_json()["blocking"] == [b["number"]]

    for bad_id, label in ((a["id"], "self"), (b["id"], "duplicate"), (str(uuid.uuid4()), "unknown")):
        response = client.post(f"/api/v1/work-orders/{a['id']}/dependencies", json={"blocking_work_order_id": bad_id})
        assert response.status_code == 400, label
        assert set(response.get_json()["errors"]) == {"blocking_work_order_id"}, label
    invalid = client.post(f"/api/v1/work-orders/{a['id']}/dependencies", json={"blocking_work_order_id": "nope"})
    assert invalid.status_code == 400 and set(invalid.get_json()["errors"]) == {"blocking_work_order_id"}
    absent = client.post(f"/api/v1/work-orders/{a['id']}/dependencies", json={})
    assert absent.status_code == 400 and set(absent.get_json()["errors"]) == {"blocking_work_order_id"}

    # B blocked by C, then C blocked by A would be a cycle (A <- B <- C <- A)
    assert client.post(f"/api/v1/work-orders/{b['id']}/dependencies", json={"blocking_work_order_id": c["id"]}).status_code == 201
    cycle = client.post(f"/api/v1/work-orders/{c['id']}/dependencies", json={"blocking_work_order_id": a["id"]})
    assert cycle.status_code == 400 and "cycle" in cycle.get_json()["errors"]["blocking_work_order_id"]

    # completing C unblocks B; B still blocks A until B is done
    assert client.post(f"/api/v1/work-orders/{c['id']}/complete", json={}).status_code == 200
    assert client.get(f"/api/v1/work-orders/{b['id']}").get_json()["payload"]["work_order"]["is_blocked"] is False
    assert client.get(f"/api/v1/work-orders/{a['id']}").get_json()["payload"]["work_order"]["is_blocked"] is True
    assert client.post(f"/api/v1/work-orders/{b['id']}/complete", json={}).status_code == 200
    a_detail = client.get(f"/api/v1/work-orders/{a['id']}").get_json()["payload"]["work_order"]
    assert a_detail["is_blocked"] is False
    assert client.post(f"/api/v1/work-orders/{a['id']}/start", json={}).status_code == 200

    # reopening B blocks A again; removing the dependency clears it
    assert client.post(f"/api/v1/work-orders/{b['id']}/reopen", json={}).status_code == 200
    assert client.get(f"/api/v1/work-orders/{a['id']}").get_json()["payload"]["work_order"]["is_blocked"] is True
    dep_id = a_detail["dependencies"]["blocked_by"][0]["id"]
    removed = client.delete(f"/api/v1/work-orders/{a['id']}/dependencies/{dep_id}")
    assert removed.status_code == 200 and removed.get_json()["payload"]["work_order"]["is_blocked"] is False
    assert len(_audit("work_order.dependency_removed", a["id"])) == 1
    assert client.delete(f"/api/v1/work-orders/{a['id']}/dependencies/{dep_id}").status_code == 404
    assert client.delete(f"/api/v1/work-orders/{b['id']}/dependencies/{uuid.uuid4()}").status_code == 404


# --------------------------------------------------------------------------- duplicate


def test_duplicate_copies_fields_links_and_assignees(client, org, users, api_login):
    project = _project(org, "Rover", "CCR")
    team = _team(org, "Wheels", lead=users["lead"])
    category = _category(org, "Mechanical")
    location = _location(org, "Shop")
    asset = _asset(org, "Chassis")
    related = _asset(org, "Wheel")
    vendor = _vendor(org, "McMaster")
    api_login(users["admin"])
    source = client.post(
        "/api/v1/work-orders",
        json={
            "title": "Original",
            "description": "desc",
            "priority": "medium",
            "work_type": "preventive",
            "project_id": str(project.id),
            "location_id": str(location.id),
            "primary_asset_id": str(asset.id),
            "team_id": str(team.id),
            "vendor_id": str(vendor.id),
            "estimated_minutes": 25,
            "category_ids": [str(category.id)],
            "asset_ids": [str(related.id)],
            "assignee_user_ids": [users["member"].id],
            "assignee_team_ids": [str(team.id)],
            "draft": True,
        },
    ).get_json()["payload"]["work_order"]

    response = client.post(f"/api/v1/work-orders/{source['id']}/duplicate", json={})
    assert response.status_code == 201, response.get_json()
    copy = response.get_json()["payload"]["work_order"]
    assert copy["id"] != source["id"] and copy["number"] == source["number"] + 1
    assert copy["title"] == "Original (copy)" and copy["status"] == "open"
    for key in ("description", "priority", "work_type", "estimated_minutes"):
        assert copy[key] == source[key], key
    for key in ("project", "location", "asset", "team", "vendor"):
        assert copy[key]["id"] == source[key]["id"], key
    assert [c["id"] for c in copy["categories"]] == [str(category.id)]
    assert [a["id"] for a in copy["related_assets"]] == [str(related.id)]
    assert [a["id"] for a in copy["assignees"]] == [users["member"].id]
    assert [t["id"] for t in copy["assignee_teams"]] == [str(team.id)]
    assert copy["time_entries"] == [] and copy["status_history"][0]["to_status"] == "open"

    duplicated = _audit("work_order.duplicated", copy["id"])
    assert len(duplicated) == 1 and duplicated[0].metadata_json["source_id"] == source["id"]
    assert duplicated[0].after_json["source_number"] == source["number"]
    assert client.post(f"/api/v1/work-orders/{uuid.uuid4()}/duplicate", json={}).status_code == 404


def test_detail_shape_for_service_created_work_order(ctx_admin, org, users):
    wo = _create(ctx_admin, title="Shape", watcher_user_ids=[users["lead"].id])
    from asme.ops.serializers.work_orders import work_order_detail

    body = work_order_detail(wo)
    assert set(body) >= {
        "id",
        "number",
        "title",
        "description",
        "status",
        "priority",
        "work_type",
        "project",
        "location",
        "asset",
        "team",
        "assignees",
        "assignee_teams",
        "watchers",
        "categories",
        "vendor",
        "parent_id",
        "parent_number",
        "sub_work_orders",
        "start_at",
        "due_at",
        "completed_at",
        "canceled_at",
        "estimated_minutes",
        "actual_minutes",
        "is_overdue",
        "is_blocked",
        "budget_code",
        "completion_note",
        "created_by",
        "created_at",
        "updated_at",
        "status_history",
        "time_entries",
        "cost_entries",
        "dependencies",
        "children",
        "related_assets",
    }
    assert body["watchers"][0]["email"] == users["lead"].email
    assert policy.can(ctx_admin, "work_order.edit", wo)
