"""Authorization for work orders: role keys at the route, object scope in the
service, project visibility, foreign organizations and read_assigned roles."""

from __future__ import annotations

import uuid

import pytest

from asme.extensions import db as _db
from asme.ops import policy
from asme.ops.models import WorkOrder
from asme.ops.services import work_orders
from asme.services.errors import Forbidden, NotFound
from tests.ops.conftest import make_user
from tests.ops.test_work_orders_api import _create, _other_org_work_order, _project, _team


def _wo_id(client, **body):
    body.setdefault("title", "Authz")
    response = client.post("/api/v1/work-orders", json=body)
    assert response.status_code == 201, response.get_json()
    return response.get_json()["payload"]["work_order"]["id"]


# --------------------------------------------------------------------------- requester


def test_requester_is_forbidden_at_the_route(client, org, users, requester, api_login):
    api_login(users["admin"])
    wo_id = _wo_id(client, title="Visible to members")

    api_login(requester)
    created = client.post("/api/v1/work-orders", json={"title": "Nope"})
    assert created.status_code == 403 and created.get_json()["code"] == "forbidden"
    assert created.get_json()["permission"] == ["work_order.create"]
    listed = client.get("/api/v1/work-orders")
    assert listed.status_code == 403
    assert listed.get_json()["permission"] == ["work_order.read_all", "work_order.read_assigned"]
    assert client.get(f"/api/v1/work-orders/{wo_id}").status_code == 403
    assert client.post(f"/api/v1/work-orders/{wo_id}/start", json={}).status_code == 403
    assert client.post(f"/api/v1/work-orders/{wo_id}/watch", json={}).status_code == 403


# --------------------------------------------------------------------------- full member: own vs others


def test_member_edits_own_work_order_but_not_another_members(client, org, users, api_login):
    other_member = make_user("Ola Other", "ola@uiowa.edu", org=org)
    api_login(other_member)
    theirs = _wo_id(client, title="Theirs")

    api_login(users["member"])
    mine = _wo_id(client, title="Mine")
    ok = client.patch(f"/api/v1/work-orders/{mine}", json={"title": "Mine, renamed"})
    assert ok.status_code == 200 and ok.get_json()["payload"]["work_order"]["title"] == "Mine, renamed"

    denied = client.patch(f"/api/v1/work-orders/{theirs}", json={"title": "Hijacked"})
    assert denied.status_code == 403 and denied.get_json()["code"] == "forbidden"
    assert denied.get_json()["permission"] == "work_order.edit"
    assert client.get(f"/api/v1/work-orders/{theirs}").get_json()["payload"]["work_order"]["title"] == "Theirs"

    # dependencies and reopen ride on work_order.edit too
    assert client.post(f"/api/v1/work-orders/{theirs}/dependencies", json={"blocking_work_order_id": mine}).status_code == 403
    assert client.post(f"/api/v1/work-orders/{mine}/dependencies", json={"blocking_work_order_id": theirs}).status_code == 201
    assert client.post(f"/api/v1/work-orders/{theirs}/reopen", json={}).status_code in (403, 409)
    # a member never holds assign / cancel
    assert client.put(f"/api/v1/work-orders/{mine}/assignees", json={"user_ids": []}).status_code == 403
    assert client.post(f"/api/v1/work-orders/{mine}/cancel", json={"note": "x"}).status_code == 403


def test_member_can_start_and_complete_only_when_assigned(client, org, users, api_login):
    team = _team(org, "Wheels", lead=users["lead"], members=[users["member"]])
    api_login(users["admin"])
    unassigned = _wo_id(client, title="Unassigned")
    direct = _wo_id(client, title="Direct", assignee_user_ids=[users["member"].id])
    via_team = _wo_id(client, title="Via team", assignee_team_ids=[str(team.id)])

    api_login(users["member"])
    assert client.post(f"/api/v1/work-orders/{unassigned}/start", json={}).status_code == 403
    assert client.post(f"/api/v1/work-orders/{unassigned}/complete", json={}).status_code == 403
    assert client.post(f"/api/v1/work-orders/{unassigned}/time-entries", json={"minutes": 5}).status_code == 403

    started = client.post(f"/api/v1/work-orders/{direct}/start", json={})
    assert started.status_code == 200 and started.get_json()["payload"]["work_order"]["status"] == "in_progress"
    assert client.post(f"/api/v1/work-orders/{direct}/hold", json={}).status_code == 200
    assert client.post(f"/api/v1/work-orders/{direct}/resume", json={}).status_code == 200
    logged = client.post(f"/api/v1/work-orders/{direct}/time-entries", json={"minutes": 5})
    assert logged.status_code == 201
    completed = client.post(f"/api/v1/work-orders/{direct}/complete", json={"note": "done"})
    assert completed.status_code == 200 and completed.get_json()["payload"]["work_order"]["status"] == "done"

    team_done = client.post(f"/api/v1/work-orders/{via_team}/complete", json={})
    assert team_done.status_code == 200 and team_done.get_json()["payload"]["work_order"]["status"] == "done"


def test_member_cannot_log_time_for_others_or_delete_their_entries(client, org, users, api_login):
    api_login(users["admin"])
    wo = _wo_id(client, title="Shared", assignee_user_ids=[users["member"].id])
    admin_entry = client.post(f"/api/v1/work-orders/{wo}/time-entries", json={"minutes": 30}).get_json()["payload"]["time_entry"]["id"]

    api_login(users["member"])
    for_other = client.post(f"/api/v1/work-orders/{wo}/time-entries", json={"minutes": 5, "user_id": users["admin"].id})
    assert for_other.status_code == 403 and for_other.get_json()["permission"] == "work_order.assign"
    own_entry = client.post(f"/api/v1/work-orders/{wo}/time-entries", json={"minutes": 5}).get_json()["payload"]["time_entry"]["id"]
    assert client.delete(f"/api/v1/work-orders/{wo}/time-entries/{admin_entry}").status_code == 403
    assert client.delete(f"/api/v1/work-orders/{wo}/time-entries/{own_entry}").status_code == 200

    cost = client.post(f"/api/v1/work-orders/{wo}/cost-entries", json={"type": "other", "amount": 1}).get_json()["payload"]["cost_entry"]["id"]
    api_login(users["admin"])
    assert client.delete(f"/api/v1/work-orders/{wo}/cost-entries/{cost}").status_code == 200
    assert client.delete(f"/api/v1/work-orders/{wo}/time-entries/{admin_entry}").status_code == 200


# --------------------------------------------------------------------------- team lead


def test_team_lead_assigns_only_on_own_teams_work_orders(client, org, users, api_login):
    led = _team(org, "Arm", lead=users["lead"])
    other = _team(org, "Software")
    member_of = _team(org, "Wheels", members=[users["lead"]])
    api_login(users["admin"])
    on_led = _wo_id(client, title="Arm work", team_id=str(led.id))
    on_other = _wo_id(client, title="Software work", team_id=str(other.id))
    on_member_of = _wo_id(client, title="Wheels work", team_id=str(member_of.id))
    assigned_to_led = _wo_id(client, title="Assigned to Arm", assignee_team_ids=[str(led.id)])
    no_team = _wo_id(client, title="No team")

    api_login(users["lead"])
    allowed = client.put(f"/api/v1/work-orders/{on_led}/assignees", json={"user_ids": [users["member"].id], "team_ids": []})
    assert allowed.status_code == 200
    assert [a["id"] for a in allowed.get_json()["payload"]["work_order"]["assignees"]] == [users["member"].id]
    assert client.put(f"/api/v1/work-orders/{assigned_to_led}/assignees", json={"user_ids": [users["member"].id]}).status_code == 200
    assert client.put(f"/api/v1/work-orders/{on_led}/watchers", json={"user_ids": [users["member"].id]}).status_code == 200

    for wo_id in (on_other, on_member_of, no_team):
        denied = client.put(f"/api/v1/work-orders/{wo_id}/assignees", json={"user_ids": [users["member"].id]})
        assert denied.status_code == 403, wo_id
        assert denied.get_json()["permission"] == "work_order.assign"
    assert client.put(f"/api/v1/work-orders/{on_other}/watchers", json={"user_ids": []}).status_code == 403

    # team scope also drives edit / cancel for the lead
    assert client.patch(f"/api/v1/work-orders/{on_led}", json={"title": "Arm work, edited"}).status_code == 200
    assert client.patch(f"/api/v1/work-orders/{on_other}", json={"title": "Nope"}).status_code == 403
    assert client.post(f"/api/v1/work-orders/{on_led}/cancel", json={"note": "scope ok"}).status_code == 200
    assert client.post(f"/api/v1/work-orders/{on_other}/cancel", json={"note": "scope no"}).status_code == 403


def test_project_lead_scope_follows_project_membership(org, users):
    lead = make_user("Pat Lead", "pat@uiowa.edu", ops_role="project_lead", org=org)
    mine = _project(org, "Rover", "CCR", members=[lead])
    other = _project(org, "Showcase", "FES")
    ctx_admin = policy.load_context(users["admin"], org)
    in_mine = _create(ctx_admin, title="In my project", project_id=str(mine.id))
    in_other = _create(ctx_admin, title="In other project", project_id=str(other.id))
    ctx = policy.load_context(lead, org)
    work_orders.set_assignees(ctx, in_mine, [users["member"].id], [])
    assert in_mine.assignee_user_ids == {users["member"].id}
    with pytest.raises(Forbidden):
        work_orders.set_assignees(ctx, in_other, [users["member"].id], [])
    work_orders.transition(ctx, in_mine, "start")
    with pytest.raises(Forbidden):
        work_orders.transition(ctx, in_other, "start")


# --------------------------------------------------------------------------- private projects


def test_private_project_work_orders_are_hidden_from_non_members(client, org, users, api_login):
    secret = _project(org, "Sponsor Bid", "BID", visibility="private")
    joined = _project(org, "Showcase", "FES", visibility="private", members=[users["member"]])
    public = _project(org, "Rover", "CCR")
    api_login(users["admin"])
    hidden = _wo_id(client, title="Secret work", project_id=str(secret.id), assignee_user_ids=[users["member"].id])
    visible_private = _wo_id(client, title="Showcase work", project_id=str(joined.id))
    visible_public = _wo_id(client, title="Rover work", project_id=str(public.id))
    no_project = _wo_id(client, title="Chapter work")

    api_login(users["member"])
    listing = client.get("/api/v1/work-orders").get_json()["payload"]
    assert {i["title"] for i in listing["items"]} == {"Showcase work", "Rover work", "Chapter work"}
    assert listing["tabs"] == {"todo": 3, "done": 0}
    assert client.get(f"/api/v1/work-orders/{hidden}").status_code == 404
    assert client.get(f"/api/v1/work-orders/{visible_private}").status_code == 200
    assert client.get(f"/api/v1/work-orders/{visible_public}").status_code == 200
    assert client.get(f"/api/v1/work-orders/{no_project}").status_code == 200
    # even though the member is assigned, the private project hides the work order entirely
    assert client.post(f"/api/v1/work-orders/{hidden}/start", json={}).status_code == 404
    assert client.post(f"/api/v1/work-orders/{hidden}/watch", json={}).status_code == 404
    assert client.post(f"/api/v1/work-orders/{hidden}/duplicate", json={}).status_code == 404
    assert client.post(f"/api/v1/work-orders/{hidden}/sub-work-orders", json={"title": "child"}).status_code == 404
    blocked = client.post(f"/api/v1/work-orders/{no_project}/dependencies", json={"blocking_work_order_id": hidden})
    assert blocked.status_code == 403  # no_project belongs to the admin: member lacks edit; hidden id is never confirmed
    own = _wo_id(client, title="Member's own")
    unknown = client.post(f"/api/v1/work-orders/{own}/dependencies", json={"blocking_work_order_id": hidden})
    assert unknown.status_code == 400 and unknown.get_json()["errors"] == {"blocking_work_order_id": "Unknown work order."}
    parent_hidden = client.post("/api/v1/work-orders", json={"title": "child of hidden", "parent_id": hidden})
    assert parent_hidden.status_code == 400 and parent_hidden.get_json()["errors"] == {"parent_id": "Unknown parent work order."}

    advisor = make_user("Dr. Advisor", "advisor@uiowa.edu", ops_role="faculty_advisor", org=org)
    api_login(advisor)
    everything = client.get("/api/v1/work-orders").get_json()["payload"]
    # four created by the admin plus the member's own one; the advisor reads private projects
    assert everything["total"] == 5 and client.get(f"/api/v1/work-orders/{hidden}").status_code == 200


# --------------------------------------------------------------------------- foreign organization


def test_foreign_organization_ids_are_404_on_every_route(client, org, users, api_login):
    _other, foreign = _other_org_work_order()
    api_login(users["admin"])
    local = _wo_id(client, title="Local")
    fid = foreign.id
    checks = [
        ("get", f"/api/v1/work-orders/{fid}", None),
        ("patch", f"/api/v1/work-orders/{fid}", {"title": "x"}),
        ("post", f"/api/v1/work-orders/{fid}/start", {}),
        ("post", f"/api/v1/work-orders/{fid}/hold", {}),
        ("post", f"/api/v1/work-orders/{fid}/resume", {}),
        ("post", f"/api/v1/work-orders/{fid}/complete", {}),
        ("post", f"/api/v1/work-orders/{fid}/cancel", {"note": "x"}),
        ("post", f"/api/v1/work-orders/{fid}/reopen", {}),
        ("post", f"/api/v1/work-orders/{fid}/duplicate", {}),
        ("post", f"/api/v1/work-orders/{fid}/sub-work-orders", {"title": "x"}),
        ("put", f"/api/v1/work-orders/{fid}/assignees", {"user_ids": []}),
        ("put", f"/api/v1/work-orders/{fid}/watchers", {"user_ids": []}),
        ("post", f"/api/v1/work-orders/{fid}/watch", {}),
        ("delete", f"/api/v1/work-orders/{fid}/watch", None),
        ("post", f"/api/v1/work-orders/{fid}/time-entries", {"minutes": 1}),
        ("delete", f"/api/v1/work-orders/{fid}/time-entries/{uuid.uuid4()}", None),
        ("post", f"/api/v1/work-orders/{fid}/cost-entries", {"type": "other", "amount": 1}),
        ("delete", f"/api/v1/work-orders/{fid}/cost-entries/{uuid.uuid4()}", None),
        ("post", f"/api/v1/work-orders/{fid}/dependencies", {"blocking_work_order_id": local}),
        ("delete", f"/api/v1/work-orders/{fid}/dependencies/{uuid.uuid4()}", None),
    ]
    for method, url, body in checks:
        response = getattr(client, method)(url, json=body) if body is not None else getattr(client, method)(url)
        assert response.status_code == 404, (method, url, response.get_json())
        assert response.get_json()["code"] == "not_found"

    # foreign ids inside bodies are treated as unknown, never as a leak
    dep = client.post(f"/api/v1/work-orders/{local}/dependencies", json={"blocking_work_order_id": str(fid)})
    assert dep.status_code == 400 and dep.get_json()["errors"] == {"blocking_work_order_id": "Unknown work order."}
    child = client.post("/api/v1/work-orders", json={"title": "x", "parent_id": str(fid)})
    assert child.status_code == 400 and child.get_json()["errors"] == {"parent_id": "Unknown parent work order."}
    assert client.get("/api/v1/work-orders?tab=all").get_json()["payload"]["total"] == 1

    ctx_admin = policy.load_context(users["admin"], org)
    with pytest.raises(NotFound):
        work_orders.get_readable(ctx_admin, fid)
    with pytest.raises(NotFound):
        work_orders.duplicate(ctx_admin, foreign)
    with pytest.raises(NotFound):
        work_orders.transition(ctx_admin, foreign, "start")
    with pytest.raises(NotFound):
        work_orders.update(ctx_admin, foreign, {"title": "x"})
    with pytest.raises(NotFound):
        work_orders.set_assignees(ctx_admin, foreign, [], [])
    with pytest.raises(NotFound):
        work_orders.watch(ctx_admin, foreign)
    with pytest.raises(NotFound):
        work_orders.add_time_entry(ctx_admin, foreign, {"minutes": 5})
    with pytest.raises(NotFound):
        work_orders.add_dependency(ctx_admin, foreign, local)
    assert _db.session.get(WorkOrder, fid).status == "open"


# --------------------------------------------------------------------------- read_assigned only


def test_shop_operator_sees_only_assigned_watched_or_created(client, org, users, api_login):
    operator = make_user("Op Erator", "op@uiowa.edu", ops_role="shop_operator", org=org)
    crew = _team(org, "Crew", members=[operator])
    api_login(users["admin"])
    direct = _wo_id(client, title="Direct", assignee_user_ids=[operator.id])
    via_team = _wo_id(client, title="Via team", assignee_team_ids=[str(crew.id)])
    watched = _wo_id(client, title="Watched", watcher_user_ids=[operator.id])
    unrelated = _wo_id(client, title="Unrelated")

    api_login(operator)
    listing = client.get("/api/v1/work-orders").get_json()["payload"]
    assert {i["title"] for i in listing["items"]} == {"Direct", "Via team", "Watched"}
    assert listing["tabs"] == {"todo": 3, "done": 0}
    assert client.get(f"/api/v1/work-orders/{unrelated}").status_code == 404
    assert client.post(f"/api/v1/work-orders/{unrelated}/watch", json={}).status_code == 404
    assert client.get(f"/api/v1/work-orders/{direct}").status_code == 200
    assert client.get(f"/api/v1/work-orders/{via_team}").status_code == 200
    assert client.get(f"/api/v1/work-orders/{watched}").status_code == 200

    # can act on assigned work, can only look at watched work, cannot create
    assert client.post(f"/api/v1/work-orders/{direct}/start", json={}).status_code == 200
    assert client.post(f"/api/v1/work-orders/{via_team}/time-entries", json={"minutes": 10}).status_code == 201
    assert client.post(f"/api/v1/work-orders/{watched}/start", json={}).status_code == 403
    assert client.patch(f"/api/v1/work-orders/{direct}", json={"title": "x"}).status_code == 403
    assert client.post("/api/v1/work-orders", json={"title": "x"}).status_code == 403
    assert client.post(f"/api/v1/work-orders/{direct}/duplicate", json={}).status_code == 403
    assert client.delete(f"/api/v1/work-orders/{watched}/watch").status_code == 200
    assert client.get(f"/api/v1/work-orders/{watched}").status_code == 404

    ctx_op = policy.load_context(operator, org)
    ctx_admin = policy.load_context(users["admin"], org)
    created_by_admin_for_op = _create(ctx_admin, title="Created by admin")
    assert not work_orders.can_read_work_order(ctx_op, created_by_admin_for_op)
    numbers = sorted(n for (n,) in work_orders.visible_work_orders_query(ctx_op).with_entities(WorkOrder.number).all())
    assert len(numbers) == 2  # direct + via_team (watched was unwatched)
