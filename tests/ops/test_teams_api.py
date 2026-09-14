"""Teams API: list/create/read/update/delete and membership replacement."""

from __future__ import annotations

import uuid

from asme.extensions import db as _db
from asme.ops.models import AuditEvent, Notification, OpsProject, Organization, Team, TeamMember, WorkOrder, WorkOrderAssignee
from tests.ops.conftest import make_user


def _post_team(client, **body):
    return client.post("/api/v1/teams", json=body)


def _project(org, name, code, visibility="chapter"):
    row = OpsProject(organization_id=org.id, name=name, code=code, visibility=visibility)
    _db.session.add(row)
    _db.session.commit()
    return row


def _other_org_team():
    other = Organization(name="Other Chapter", slug="other")
    _db.session.add(other)
    _db.session.flush()
    foreign = Team(organization_id=other.id, name="Foreign Team")
    _db.session.add(foreign)
    _db.session.commit()
    return other, foreign


def _membership_of(org, user):
    from asme.ops import bootstrap

    return bootstrap.membership_for(user, org)


# --------------------------------------------------------------------------- create / read


def test_create_and_read_team_happy_path(client, org, users, api_login):
    api_login(users["admin"])
    created = _post_team(
        client,
        name="Robotic Arm",
        description="Arm subsystem",
        members=[{"user_id": users["lead"].id, "is_lead": True}, {"user_id": users["member"].id}],
    )
    assert created.status_code == 201, created.get_json()
    team = created.get_json()["payload"]["team"]
    assert set(team) >= {"id", "name", "description", "parent_team_id", "project", "leads", "member_count", "created_at", "members"}
    assert team["name"] == "Robotic Arm" and team["project"] is None and team["parent_team_id"] is None
    assert team["member_count"] == 2
    assert [lead["id"] for lead in team["leads"]] == [users["lead"].id]
    assert team["leads"][0] == {"id": users["lead"].id, "name": "Lee Lead", "email": "lee@uiowa.edu", "avatar_url": None}
    members = {m["user"]["id"]: m for m in team["members"]}
    assert members[users["lead"].id]["is_lead"] is True and members[users["member"].id]["is_lead"] is False
    assert all(m["joined_at"].endswith("Z") for m in team["members"])

    row = _db.session.get(Team, uuid.UUID(team["id"]))
    assert row.organization_id == org.id and row.created_by_user_id == users["admin"].id

    event = AuditEvent.query.filter_by(event_type="team.created").one()
    assert event.entity_type == "team" and event.entity_id == team["id"] and event.actor_user_id == users["admin"].id
    assert sorted(event.after_json["member_ids"]) == sorted([users["lead"].id, users["member"].id])

    notified = {n.user_id for n in Notification.query.filter_by(type="team.added").all()}
    assert notified == {users["lead"].id, users["member"].id}

    listed = client.get("/api/v1/teams")
    assert listed.status_code == 200
    body = listed.get_json()["payload"]
    assert body["total"] == 1 and body["next_cursor"] is None
    assert body["items"][0]["id"] == team["id"] and "members" not in body["items"][0]
    assert body["items"][0]["member_count"] == 2

    detail = client.get(f"/api/v1/teams/{team['id']}")
    assert detail.status_code == 200
    assert detail.get_json()["payload"]["team"]["members"][0]["is_lead"] is True  # leads listed first


def test_create_team_validation_errors(client, org, users, api_login):
    api_login(users["admin"])
    assert _post_team(client, name="Wheels").status_code == 201

    empty = _post_team(client)
    assert empty.status_code == 400 and set(empty.get_json()["errors"]) == {"name"}

    duplicate = _post_team(client, name="  wheels ")
    assert duplicate.status_code == 400
    assert set(duplicate.get_json()["errors"]) == {"name"}

    outsider = make_user("No Membership", "nobody@uiowa.edu")
    invited = make_user("Ivy Invited", "ivy@uiowa.edu", org=org)
    _membership_of(org, invited).member_status = "invited"
    _db.session.commit()

    bad = _post_team(
        client,
        name="Software",
        parent_team_id="not-a-uuid",
        project_id=str(uuid.uuid4()),
        members=[{"user_id": outsider.id}, {"user_id": invited.id}],
    )
    assert bad.status_code == 400
    assert set(bad.get_json()["errors"]) == {"parent_team_id", "project_id", "members"}

    malformed = _post_team(client, name="Software", members=[{"is_lead": True}, "nope", {"user_id": users["lead"].id, "is_lead": "maybe"}])
    assert malformed.status_code == 400 and set(malformed.get_json()["errors"]) == {"members"}

    duplicated = _post_team(client, name="Software", members=[{"user_id": users["lead"].id}, {"user_id": users["lead"].id, "is_lead": True}])
    assert duplicated.status_code == 400 and set(duplicated.get_json()["errors"]) == {"members"}

    assert Team.query.filter_by(organization_id=org.id).count() == 1


def test_create_team_requires_team_manage(client, org, users, requester, api_login):
    api_login(requester)
    denied = _post_team(client, name="Nope")
    assert denied.status_code == 403 and denied.get_json()["permission"] == ["team.manage"]

    api_login(users["member"])  # full_member has team.read but not team.manage
    denied = _post_team(client, name="Nope")
    assert denied.status_code == 403 and denied.get_json()["code"] == "forbidden"
    assert Team.query.count() == 0


def test_team_lead_creating_a_team_becomes_its_lead(client, org, users, api_login):
    api_login(users["lead"])
    created = _post_team(client, name="Wheels", members=[{"user_id": users["member"].id}])
    assert created.status_code == 201, created.get_json()
    team = created.get_json()["payload"]["team"]
    assert [lead["id"] for lead in team["leads"]] == [users["lead"].id]
    assert team["member_count"] == 2

    # the automatic lead can keep managing the team through team scope
    patched = client.patch(f"/api/v1/teams/{team['id']}", json={"description": "Drivetrain"})
    assert patched.status_code == 200 and patched.get_json()["payload"]["team"]["description"] == "Drivetrain"

    # requesting is_lead false for yourself is overridden: the creator stays lead
    again = _post_team(client, name="Arm", members=[{"user_id": users["lead"].id, "is_lead": False}])
    assert again.status_code == 201
    assert [lead["id"] for lead in again.get_json()["payload"]["team"]["leads"]] == [users["lead"].id]


def test_team_lead_can_only_manage_teams_they_lead(client, org, users, api_login):
    api_login(users["admin"])
    arm = _post_team(client, name="Arm", members=[{"user_id": users["lead"].id, "is_lead": False}]).get_json()["payload"]["team"]
    wheels = _post_team(client, name="Wheels", members=[{"user_id": users["lead"].id, "is_lead": True}]).get_json()["payload"]["team"]

    api_login(users["lead"])
    assert client.get(f"/api/v1/teams/{arm['id']}").status_code == 200
    denied = client.patch(f"/api/v1/teams/{arm['id']}", json={"name": "Arm 2"})
    assert denied.status_code == 403 and denied.get_json()["code"] == "forbidden"
    assert client.put(f"/api/v1/teams/{arm['id']}/members", json={"members": []}).status_code == 403
    assert client.delete(f"/api/v1/teams/{arm['id']}").status_code == 403

    allowed = client.patch(f"/api/v1/teams/{wheels['id']}", json={"name": "Wheels and Mobility"})
    assert allowed.status_code == 200 and allowed.get_json()["payload"]["team"]["name"] == "Wheels and Mobility"
    assert client.put(f"/api/v1/teams/{wheels['id']}/members", json={"members": [{"user_id": users["lead"].id, "is_lead": True}]}).status_code == 200


# --------------------------------------------------------------------------- list


def test_list_filters_sorting_and_search(client, org, users, api_login):
    rover = _project(org, "Rover", "CCR")
    api_login(users["admin"])
    ids = {}
    for name, extra in (("Wheels", {"project_id": str(rover.id)}), ("Arm", {"project_id": str(rover.id)}), ("Software", {}), ("Events", {})):
        response = _post_team(client, name=name, **extra)
        assert response.status_code == 201, response.get_json()
        ids[name] = response.get_json()["payload"]["team"]["id"]
    archived = client.patch(f"/api/v1/teams/{ids['Events']}", json={"is_active": False})
    assert archived.status_code == 200 and archived.get_json()["payload"]["team"]["is_active"] is False

    def names(query=""):
        response = client.get(f"/api/v1/teams{query}")
        assert response.status_code == 200, response.get_json()
        return [item["name"] for item in response.get_json()["payload"]["items"]]

    assert names() == ["Arm", "Software", "Wheels"]  # active only, sorted by name
    assert names("?sort=-name") == ["Wheels", "Software", "Arm"]
    assert names("?sort=created_at") == ["Wheels", "Arm", "Software"]
    assert names("?filter[active]=false") == ["Events"]
    assert names("?filter[active]=all") == ["Arm", "Events", "Software", "Wheels"]
    assert names(f"?filter[project]={rover.id}") == ["Arm", "Wheels"]
    assert names("?q=soft") == ["Software"]
    assert names("?q=SOFT&filter[active]=all") == ["Software"]

    with_project = client.get(f"/api/v1/teams?filter[project]={rover.id}").get_json()["payload"]["items"][0]
    assert with_project["project"] == {"id": str(rover.id), "name": "Rover", "code": "CCR", "visibility": "chapter"}

    page = client.get("/api/v1/teams?limit=2").get_json()["payload"]
    assert [i["name"] for i in page["items"]] == ["Arm", "Software"] and page["total"] == 3 and page["next_cursor"]
    rest = client.get(f"/api/v1/teams?limit=2&cursor={page['next_cursor']}").get_json()["payload"]
    assert [i["name"] for i in rest["items"]] == ["Wheels"] and rest["next_cursor"] is None

    assert client.get("/api/v1/teams?filter[bogus]=1").status_code == 400
    assert client.get("/api/v1/teams?sort=member_count").status_code == 400
    assert client.get("/api/v1/teams?filter[active]=maybe").status_code == 400
    assert client.get("/api/v1/teams?filter[project]=not-a-uuid").status_code == 400


def test_team_project_must_be_readable_and_hides_private_teams(client, org, users, api_login):
    secret = _project(org, "Sponsor Bid", "BID", visibility="private")
    public = _project(org, "Rover", "CCR")

    api_login(users["lead"])  # team_lead: project.read but not project.read_private
    denied = _post_team(client, name="Bid Team", project_id=str(secret.id))
    assert denied.status_code == 400 and set(denied.get_json()["errors"]) == {"project_id"}
    allowed = _post_team(client, name="Rover Team", project_id=str(public.id))
    assert allowed.status_code == 201

    api_login(users["admin"])
    bid = _post_team(client, name="Bid Team", project_id=str(secret.id))
    assert bid.status_code == 201
    bid_id = bid.get_json()["payload"]["team"]["id"]

    api_login(users["lead"])
    listed = [item["name"] for item in client.get("/api/v1/teams").get_json()["payload"]["items"]]
    assert listed == ["Rover Team"]
    assert client.get(f"/api/v1/teams/{bid_id}").status_code == 404

    api_login(users["admin"])
    assert client.get(f"/api/v1/teams/{bid_id}").status_code == 200


# --------------------------------------------------------------------------- update / delete


def test_patch_team_updates_audits_and_rejects_cycles(client, org, users, api_login):
    api_login(users["admin"])
    root = _post_team(client, name="Engineering").get_json()["payload"]["team"]
    child = _post_team(client, name="Arm", parent_team_id=root["id"]).get_json()["payload"]["team"]
    assert child["parent_team_id"] == root["id"]
    other = _post_team(client, name="Software").get_json()["payload"]["team"]

    updated = client.patch(f"/api/v1/teams/{child['id']}", json={"name": "Robotic Arm", "description": "6-DOF arm"})
    assert updated.status_code == 200
    body = updated.get_json()["payload"]["team"]
    assert body["name"] == "Robotic Arm" and body["description"] == "6-DOF arm"
    event = AuditEvent.query.filter_by(event_type="team.updated", entity_id=child["id"]).one()
    assert event.before_json["name"] == "Arm" and event.after_json["name"] == "Robotic Arm"

    self_parent = client.patch(f"/api/v1/teams/{child['id']}", json={"parent_team_id": child["id"]})
    assert self_parent.status_code == 400 and set(self_parent.get_json()["errors"]) == {"parent_team_id"}
    cycle = client.patch(f"/api/v1/teams/{root['id']}", json={"parent_team_id": child["id"]})
    assert cycle.status_code == 400 and set(cycle.get_json()["errors"]) == {"parent_team_id"}

    taken = client.patch(f"/api/v1/teams/{child['id']}", json={"name": "SOFTWARE"})
    assert taken.status_code == 400 and set(taken.get_json()["errors"]) == {"name"}
    same_name = client.patch(f"/api/v1/teams/{child['id']}", json={"name": "robotic arm"})
    assert same_name.status_code == 200 and same_name.get_json()["payload"]["team"]["name"] == "robotic arm"

    cleared = client.patch(f"/api/v1/teams/{child['id']}", json={"parent_team_id": None})
    assert cleared.status_code == 200 and cleared.get_json()["payload"]["team"]["parent_team_id"] is None
    moved = client.patch(f"/api/v1/teams/{child['id']}", json={"parent_team_id": other["id"]})
    assert moved.status_code == 200 and moved.get_json()["payload"]["team"]["parent_team_id"] == other["id"]

    empty = client.patch(f"/api/v1/teams/{child['id']}", json={})
    assert empty.status_code == 400 and empty.get_json()["code"] == "validation"
    bad = client.patch(f"/api/v1/teams/{child['id']}", json={"name": "", "is_active": "sometimes"})
    assert bad.status_code == 400 and set(bad.get_json()["errors"]) == {"name", "is_active"}


def test_delete_team_conflicts_when_referenced(client, org, users, api_login):
    api_login(users["admin"])
    parent = _post_team(client, name="Engineering").get_json()["payload"]["team"]
    child = _post_team(client, name="Arm", parent_team_id=parent["id"]).get_json()["payload"]["team"]
    owner = _post_team(client, name="Wheels").get_json()["payload"]["team"]
    assignee = _post_team(client, name="Software").get_json()["payload"]["team"]

    blocked = client.delete(f"/api/v1/teams/{parent['id']}")
    assert blocked.status_code == 409 and blocked.get_json()["code"] == "team_in_use"
    assert blocked.get_json()["references"] == {"child_teams": 1}

    wo = WorkOrder(organization_id=org.id, number=1, title="Fix wheel", created_by_user_id=users["admin"].id, team_id=uuid.UUID(owner["id"]))
    wo2 = WorkOrder(organization_id=org.id, number=2, title="Flash firmware", created_by_user_id=users["admin"].id)
    wo2.assignees.append(WorkOrderAssignee(team_id=uuid.UUID(assignee["id"])))
    _db.session.add_all([wo, wo2])
    _db.session.commit()

    blocked = client.delete(f"/api/v1/teams/{owner['id']}")
    assert blocked.status_code == 409 and blocked.get_json()["references"] == {"work_orders": 1}
    blocked = client.delete(f"/api/v1/teams/{assignee['id']}")
    assert blocked.status_code == 409 and blocked.get_json()["references"] == {"work_order_assignments": 1}

    deleted = client.delete(f"/api/v1/teams/{child['id']}")
    assert deleted.status_code == 200 and deleted.get_json()["payload"] == {"deleted": True, "id": child["id"]}
    assert _db.session.get(Team, uuid.UUID(child["id"])) is None
    assert TeamMember.query.filter_by(team_id=uuid.UUID(child["id"])).count() == 0
    event = AuditEvent.query.filter_by(event_type="team.deleted").one()
    assert event.entity_id == child["id"] and event.before_json["name"] == "Arm"
    assert client.get(f"/api/v1/teams/{child['id']}").status_code == 404

    # the parent is free once its only child is gone
    assert client.delete(f"/api/v1/teams/{parent['id']}").status_code == 200


# --------------------------------------------------------------------------- members


def test_put_members_replaces_membership_and_notifies_new_members(client, org, users, requester, api_login):
    api_login(users["admin"])
    team = _post_team(
        client, name="Arm", members=[{"user_id": users["lead"].id, "is_lead": True}, {"user_id": users["member"].id}]
    ).get_json()["payload"]["team"]
    Notification.query.delete()
    _db.session.commit()

    replaced = client.put(
        f"/api/v1/teams/{team['id']}/members",
        json={"members": [{"user_id": users["member"].id, "is_lead": True}, {"user_id": requester.id, "is_lead": False}]},
    )
    assert replaced.status_code == 200, replaced.get_json()
    body = replaced.get_json()["payload"]["team"]
    assert body["member_count"] == 2
    assert [lead["id"] for lead in body["leads"]] == [users["member"].id]
    assert {m["user"]["id"]: m["is_lead"] for m in body["members"]} == {users["member"].id: True, requester.id: False}

    assert {n.user_id for n in Notification.query.filter_by(type="team.added").all()} == {requester.id}
    notification = Notification.query.filter_by(type="team.added").one()
    assert notification.entity_type == "team" and notification.entity_id == team["id"] and "Arm" in notification.title

    event = AuditEvent.query.filter_by(event_type="team.members_changed").one()
    assert event.before_json == {"member_ids": sorted([users["lead"].id, users["member"].id]), "lead_ids": [users["lead"].id]}
    assert event.after_json == {"member_ids": sorted([users["member"].id, requester.id]), "lead_ids": [users["member"].id]}

    # the lead's policy context no longer contains the team
    from asme.ops import policy

    assert uuid.UUID(team["id"]) not in policy.load_context(users["lead"], org).team_ids

    cleared = client.put(f"/api/v1/teams/{team['id']}/members", json={"members": []})
    assert cleared.status_code == 200 and cleared.get_json()["payload"]["team"]["member_count"] == 0
    assert TeamMember.query.filter_by(team_id=uuid.UUID(team["id"])).count() == 0


def test_put_members_validation(client, org, users, api_login):
    api_login(users["admin"])
    team = _post_team(client, name="Arm").get_json()["payload"]["team"]
    suspended = make_user("Sue Suspended", "sue@uiowa.edu", org=org)
    _membership_of(org, suspended).member_status = "suspended"
    stranger = make_user("Stan Stranger", "stan@uiowa.edu")
    _db.session.commit()

    missing = client.put(f"/api/v1/teams/{team['id']}/members", json={})
    assert missing.status_code == 400 and set(missing.get_json()["errors"]) == {"members"}
    not_list = client.put(f"/api/v1/teams/{team['id']}/members", json={"members": {"user_id": 1}})
    assert not_list.status_code == 400 and set(not_list.get_json()["errors"]) == {"members"}
    for user in (suspended, stranger):
        rejected = client.put(f"/api/v1/teams/{team['id']}/members", json={"members": [{"user_id": user.id}]})
        assert rejected.status_code == 400 and set(rejected.get_json()["errors"]) == {"members"}
    unknown = client.put(f"/api/v1/teams/{team['id']}/members", json={"members": [{"user_id": 999999}]})
    assert unknown.status_code == 400 and set(unknown.get_json()["errors"]) == {"members"}
    bad_type = client.put(f"/api/v1/teams/{team['id']}/members", json={"members": [{"user_id": True}]})
    assert bad_type.status_code == 400 and set(bad_type.get_json()["errors"]) == {"members"}
    assert client.get(f"/api/v1/teams/{team['id']}").get_json()["payload"]["team"]["member_count"] == 0
    assert AuditEvent.query.filter_by(event_type="team.members_changed").count() == 0


# --------------------------------------------------------------------------- tenancy


def test_cross_organization_team_ids_are_404(client, org, users, api_login):
    other, foreign = _other_org_team()
    api_login(users["admin"])
    fid = str(foreign.id)
    assert client.get(f"/api/v1/teams/{fid}").status_code == 404
    assert client.patch(f"/api/v1/teams/{fid}", json={"name": "Hijack"}).status_code == 404
    assert client.put(f"/api/v1/teams/{fid}/members", json={"members": []}).status_code == 404
    assert client.delete(f"/api/v1/teams/{fid}").status_code == 404
    assert client.get("/api/v1/teams/not-a-uuid").status_code == 404
    assert client.get(f"/api/v1/teams/{uuid.uuid4()}").status_code == 404

    as_parent = _post_team(client, name="Local", parent_team_id=fid)
    assert as_parent.status_code == 400 and set(as_parent.get_json()["errors"]) == {"parent_team_id"}

    listed = client.get("/api/v1/teams?filter[active]=all").get_json()["payload"]
    assert listed["total"] == 0
    assert _db.session.get(Team, foreign.id).name == "Foreign Team"
