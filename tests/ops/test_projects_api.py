"""Projects vertical: list/create/read/update, archive/restore, members (with the
legacy mirror), health, activity, visibility and cross-organization isolation."""

from __future__ import annotations

import uuid
from datetime import timedelta

from asme.extensions import db as _db
from asme.models.content import Project as LegacyProject
from asme.models.content import ProjectMembership as LegacyProjectMembership
from asme.ops.models import AuditEvent, CostEntry, Milestone, Notification, OpsProject, Organization, Team, WorkOrder
from asme.ops.types import utcnow
from tests.ops.conftest import make_user

API = "/api/v1/projects"


def _create(client, **payload):
    response = client.post(API, json=payload)
    assert response.status_code == 201, response.get_json()
    return response.get_json()["payload"]["project"]


def _project(project_id) -> OpsProject:
    return _db.session.get(OpsProject, uuid.UUID(project_id))


def _wo(org, number, creator, project_id, **kw):
    row = WorkOrder(organization_id=org.id, number=number, title=f"WO {number}", created_by_user_id=creator.id, project_id=uuid.UUID(project_id), **kw)
    _db.session.add(row)
    _db.session.flush()
    return row


def _milestone(org, project_id, name, **kw):
    row = Milestone(organization_id=org.id, project_id=uuid.UUID(project_id), name=name, **kw)
    _db.session.add(row)
    _db.session.flush()
    return row


def _names(response) -> list[str]:
    assert response.status_code == 200, response.get_json()
    return [item["name"] for item in response.get_json()["payload"]["items"]]


def _foreign_project():
    other = Organization(name="Other Chapter", slug="other")
    _db.session.add(other)
    _db.session.flush()
    foreign = OpsProject(organization_id=other.id, name="Foreign", code="FRN")
    _db.session.add(foreign)
    _db.session.flush()
    _db.session.commit()
    return other, foreign


# --------------------------------------------------------------------------- create


def test_create_project_generates_code_adds_members_audits_notifies_and_emits(client, org, users, api_login, captured_events):
    api_login(users["admin"])
    body = _create(
        client,
        name="Crater Cruncher Rover",
        lead_user_id=users["lead"].id,
        faculty_advisor_user_id=users["member"].id,
        start_date="2026-08-20",
        target_date="2027-05-01",
        budget_amount="1500.50",
        repository_url="https://github.com/asme/rover",
        competition="NASA Lunabotics",
        academic_year="2026-27",
        risk_level="medium",
    )
    assert body["code"] == "CCR"
    assert body["lead"]["id"] == users["lead"].id and body["lead"]["email"] == users["lead"].email
    assert body["faculty_advisor"]["id"] == users["member"].id
    assert body["budget_amount"] == 1500.5
    assert body["start_date"] == "2026-08-20" and body["target_date"] == "2027-05-01"
    assert body["status"] == "active" and body["visibility"] == "chapter" and body["risk_level"] == "medium"
    assert body["academic_year"] == "2026-27" and body["competition"] == "NASA Lunabotics"
    assert body["archived_at"] is None and body["public_project_id"] is None
    assert body["stats"] == {"open_work_orders": 0, "overdue_work_orders": 0, "completion_percent": 0, "next_milestone": None, "member_count": 3}
    assert body["created_at"].endswith("Z")

    project = _project(body["id"])
    assert project.created_by_user_id == users["admin"].id
    assert {m.user_id: m.project_role for m in project.members} == {
        users["lead"].id: "lead",
        users["member"].id: "advisor",
        users["admin"].id: "member",
    }
    event = AuditEvent.query.filter_by(event_type="project.created").one()
    assert event.entity_type == "project" and event.entity_id == body["id"]
    assert event.actor_user_id == users["admin"].id and event.after_json["code"] == "CCR"
    assert ("ops.project.created", {"project_id": body["id"], "organization_id": str(org.id)}) in captured_events
    note = Notification.query.filter_by(user_id=users["lead"].id, type="project.added").one()
    assert note.entity_type == "project" and note.entity_id == body["id"]
    assert Notification.query.filter_by(user_id=users["admin"].id).count() == 0


def test_create_code_fallback_uniqueness_and_normalisation(client, org, users, api_login):
    api_login(users["admin"])
    rover = _create(client, name="Rover", lead_user_id=users["admin"].id)
    assert rover["code"] == "ROV"
    assert {m.user_id: m.project_role for m in _project(rover["id"]).members} == {users["admin"].id: "lead"}
    assert Notification.query.count() == 0  # the actor is never notified about their own action

    assert _create(client, name="Rover")["code"] == "ROV2"
    assert _create(client, name="Rover")["code"] == "ROV3"
    assert _create(client, name="Crater Cruncher Rover")["code"] == "CCR"
    assert _create(client, name="Crater Cruncher Rover")["code"] == "CCR2"
    assert _create(client, name="X")["code"] == "X"
    assert _create(client, name="!!!")["code"] == "PRJ"

    explicit = _create(client, name="Explicit", code="abc-1")
    assert explicit["code"] == "ABC-1"
    duplicate = client.post(API, json={"name": "Duplicate", "code": "ccr"})
    assert duplicate.status_code == 400 and set(duplicate.get_json()["errors"]) == {"code"}


def test_create_validation_lists_every_bad_field(client, org, users, api_login):
    api_login(users["admin"])
    shape = client.post(
        API,
        json={
            "name": "",
            "code": "has space!",
            "status": "bogus",
            "visibility": "secret",
            "risk_level": "extreme",
            "budget_amount": -5,
            "repository_url": "ftp://example.org",
            "cad_url": "not a url",
            "academic_year": "2026",
            "start_date": "yesterday",
            "public_project_id": "abc",
        },
    )
    assert shape.status_code == 400 and shape.get_json()["code"] == "validation"
    assert set(shape.get_json()["errors"]) == {
        "name",
        "code",
        "status",
        "visibility",
        "risk_level",
        "budget_amount",
        "repository_url",
        "cad_url",
        "academic_year",
        "start_date",
        "public_project_id",
    }

    outsider = make_user("Out Sider", "outsider@example.edu")  # legacy user without a membership
    suspended = make_user("Sue Spended", "sue@uiowa.edu", org=org)
    from asme.ops import bootstrap

    bootstrap.membership_for(suspended, org).member_status = "suspended"
    _db.session.commit()
    references = client.post(
        API,
        json={
            "name": "Dates",
            "start_date": "2026-09-01",
            "target_date": "2026-08-31",
            "lead_user_id": outsider.id,
            "faculty_advisor_user_id": suspended.id,
            "public_project_id": 424242,
        },
    )
    assert references.status_code == 400
    assert set(references.get_json()["errors"]) == {"target_date", "lead_user_id", "faculty_advisor_user_id", "public_project_id"}
    assert references.get_json()["errors"]["target_date"] == "The target date must be on or after the start date."

    equal_dates = client.post(API, json={"name": "Same day", "start_date": "2026-09-01", "target_date": "2026-09-01"})
    assert equal_dates.status_code == 201
    assert OpsProject.query.count() == 1


def test_permissions_for_list_and_create(client, org, users, requester, api_login):
    api_login(requester)
    assert client.get(API).status_code == 200
    denied = client.post(API, json={"name": "Nope"})
    assert denied.status_code == 403 and denied.get_json()["permission"] == ["project.create"]

    guest = make_user("Gus Guest", "gus@uiowa.edu", ops_role="sponsor_guest", org=org)
    api_login(guest)
    listing = client.get(API)
    assert listing.status_code == 403 and listing.get_json()["permission"] == ["project.read"]

    api_login(users["member"])  # full_member: project.read but no project.create
    assert client.get(API).status_code == 200
    assert client.post(API, json={"name": "Nope"}).status_code == 403


# --------------------------------------------------------------------------- list


def test_list_views_filters_search_and_sort(client, org, users, api_login):
    api_login(users["admin"])
    alpha = _create(
        client, name="Alpha Rover", risk_level="high", lead_user_id=users["lead"].id, academic_year="2026-27", competition="Lunabotics", target_date="2027-03-01"
    )
    beta = _create(client, name="Beta Arm", risk_level="low", status="planning", academic_year="2025-26", target_date="2026-12-01")
    gamma = _create(client, name="Gamma Showcase", risk_level="critical", status="on_hold")
    assert client.post(f"{API}/{gamma['id']}/archive", json={}).status_code == 200

    team_alpha = Team(organization_id=org.id, name="Alpha Team", project_id=uuid.UUID(alpha["id"]))
    team_beta = Team(organization_id=org.id, name="Beta Team")
    _db.session.add_all([team_alpha, team_beta])
    _db.session.flush()
    beta_project = _project(beta["id"])
    beta_project.members[0].team_id = team_beta.id
    _db.session.commit()

    default = client.get(API)
    assert _names(default) == ["Alpha Rover", "Beta Arm"]
    assert default.get_json()["payload"]["total"] == 2 and default.get_json()["payload"]["next_cursor"] is None
    assert _names(client.get(API, query_string={"view": "all"})) == ["Alpha Rover", "Beta Arm", "Gamma Showcase"]
    assert _names(client.get(API, query_string={"view": "archived"})) == ["Gamma Showcase"]
    bad_view = client.get(API, query_string={"view": "bogus"})
    assert bad_view.status_code == 400 and bad_view.get_json()["code"] == "bad_view"

    assert _names(client.get(API, query_string={"q": "beta"})) == ["Beta Arm"]
    assert _names(client.get(API, query_string={"q": "ar"})) == ["Alpha Rover", "Beta Arm"]  # code AR + name Arm
    assert _names(client.get(API, query_string={"filter[status]": "planning"})) == ["Beta Arm"]
    assert _names(client.get(API, query_string={"view": "all", "filter[risk]": "high,critical"})) == ["Alpha Rover", "Gamma Showcase"]
    assert _names(client.get(API, query_string={"filter[lead]": str(users["lead"].id)})) == ["Alpha Rover"]
    assert _names(client.get(API, query_string={"filter[academic_year]": "2025-26"})) == ["Beta Arm"]
    assert _names(client.get(API, query_string={"filter[competition]": "lunabotics"})) == ["Alpha Rover"]
    assert _names(client.get(API, query_string={"filter[team]": str(team_alpha.id)})) == ["Alpha Rover"]
    assert _names(client.get(API, query_string={"filter[team]": f"{team_alpha.id},{team_beta.id}"})) == ["Alpha Rover", "Beta Arm"]

    assert client.get(API, query_string={"filter[team]": "not-a-uuid"}).status_code == 400
    assert client.get(API, query_string={"filter[lead]": "abc"}).status_code == 400
    unknown = client.get(API, query_string={"filter[bogus]": "1"})
    assert unknown.status_code == 400 and unknown.get_json()["code"] == "bad_filter"

    assert _names(client.get(API, query_string={"view": "all", "sort": "-risk"})) == ["Gamma Showcase", "Alpha Rover", "Beta Arm"]
    assert _names(client.get(API, query_string={"view": "all", "sort": "risk"})) == ["Beta Arm", "Alpha Rover", "Gamma Showcase"]
    assert _names(client.get(API, query_string={"view": "all", "sort": "target_date"})) == ["Beta Arm", "Alpha Rover", "Gamma Showcase"]
    assert _names(client.get(API, query_string={"view": "all", "sort": "-name"})) == ["Gamma Showcase", "Beta Arm", "Alpha Rover"]
    assert _names(client.get(API, query_string={"view": "all", "sort": "-updated_at"}))[0] == "Gamma Showcase"  # archived last
    bad_sort = client.get(API, query_string={"sort": "bogus"})
    assert bad_sort.status_code == 400 and bad_sort.get_json()["code"] == "bad_sort"

    paged = client.get(API, query_string={"view": "all", "limit": 2})
    payload = paged.get_json()["payload"]
    assert [i["name"] for i in payload["items"]] == ["Alpha Rover", "Beta Arm"] and payload["total"] == 3 and payload["next_cursor"]
    rest = client.get(API, query_string={"view": "all", "limit": 2, "cursor": payload["next_cursor"]})
    assert _names(rest) == ["Gamma Showcase"]


def test_list_and_detail_stats_come_from_work_orders_and_milestones(client, org, users, api_login):
    api_login(users["admin"])
    body = _create(client, name="Stats Project")
    pid = body["id"]
    now = utcnow()
    _wo(org, 1, users["admin"], pid, status="open", due_at=now - timedelta(days=1))
    _wo(org, 2, users["admin"], pid, status="in_progress", due_at=now + timedelta(days=3))
    _wo(org, 3, users["admin"], pid, status="draft")
    _wo(org, 4, users["admin"], pid, status="done", due_at=now - timedelta(days=5))  # closed: never overdue
    _wo(org, 5, users["admin"], pid, status="canceled")
    _milestone(org, pid, "Kickoff", status="done", due_date=(now - timedelta(days=30)).date(), order_index=0)
    _milestone(org, pid, "Final demo", status="planned", due_date=(now + timedelta(days=60)).date(), order_index=1)
    _milestone(org, pid, "Design review", status="in_progress", due_date=(now + timedelta(days=10)).date(), order_index=2)
    _milestone(org, pid, "Someday", status="planned", due_date=None, order_index=3)
    _db.session.commit()

    listing = client.get(API)
    stats = listing.get_json()["payload"]["items"][0]["stats"]
    assert stats["open_work_orders"] == 3
    assert stats["overdue_work_orders"] == 1
    assert stats["completion_percent"] == 25  # 1 done / (5 total - 1 canceled)
    assert stats["member_count"] == 1
    assert stats["next_milestone"]["name"] == "Design review" and stats["next_milestone"]["status"] == "in_progress"
    assert stats["next_milestone"]["project_id"] == pid

    detail = client.get(f"{API}/{pid}")
    assert detail.status_code == 200
    payload = detail.get_json()["payload"]
    assert payload["project"]["stats"] == stats
    assert [m["user"]["id"] for m in payload["members"]] == [users["admin"].id]
    assert payload["members"][0]["project_role"] == "member" and payload["members"][0]["team"] is None


def test_private_projects_hidden_unless_member_or_read_private(client, org, users, api_login):
    api_login(users["admin"])
    _create(client, name="Rover")
    secret = _create(client, name="Sponsor Bid", visibility="private")
    _create(client, name="Showcase", visibility="private", lead_user_id=users["lead"].id)

    api_login(users["member"])
    assert _names(client.get(API)) == ["Rover"]
    for path in ("", "/health", "/activity", "/milestones"):
        response = client.get(f"{API}/{secret['id']}{path}")
        assert response.status_code == 404, path
    assert client.patch(f"{API}/{secret['id']}", json={"name": "x"}).status_code == 403  # no project.manage at all

    api_login(users["lead"])
    assert _names(client.get(API)) == ["Rover", "Showcase"]
    assert client.get(f"{API}/{secret['id']}").status_code == 404

    advisor = make_user("Dr. Advisor", "advisor@uiowa.edu", ops_role="faculty_advisor", org=org)
    api_login(advisor)
    assert _names(client.get(API)) == ["Rover", "Showcase", "Sponsor Bid"]
    assert client.get(f"{API}/{secret['id']}").status_code == 200


# --------------------------------------------------------------------------- update / archive


def test_patch_project_respects_project_scope_and_updates_lead_role(client, org, users, api_login):
    pat = make_user("Pat Lead", "pat@uiowa.edu", ops_role="project_lead", org=org)
    api_login(users["admin"])
    mine = _create(client, name="Mine", lead_user_id=pat.id, faculty_advisor_user_id=users["member"].id)
    other = _create(client, name="Other", code="OTH")

    api_login(pat)
    response = client.patch(
        f"{API}/{mine['id']}",
        json={"name": "Mine Renamed", "risk_level": "high", "lead_user_id": users["lead"].id, "code": "mn-2", "budget_amount": 250},
    )
    assert response.status_code == 200, response.get_json()
    body = response.get_json()["payload"]["project"]
    assert body["name"] == "Mine Renamed" and body["code"] == "MN-2" and body["risk_level"] == "high" and body["budget_amount"] == 250.0
    assert body["lead"]["id"] == users["lead"].id and body["stats"]["member_count"] == 4
    roles = {m.user_id: m.project_role for m in _project(mine["id"]).members}
    assert roles == {pat.id: "member", users["lead"].id: "lead", users["member"].id: "advisor", users["admin"].id: "member"}
    event = AuditEvent.query.filter_by(event_type="project.updated").one()
    assert event.before_json["name"] == "Mine" and event.after_json["name"] == "Mine Renamed"
    assert event.metadata_json["changed"] == ["budget_amount", "code", "lead_user_id", "name", "risk_level"]

    advisor_change = client.patch(f"{API}/{mine['id']}", json={"faculty_advisor_user_id": users["admin"].id})
    assert advisor_change.status_code == 200
    roles = {m.user_id: m.project_role for m in _project(mine["id"]).members}
    assert roles[users["admin"].id] == "advisor" and roles[users["member"].id] == "member"

    denied = client.patch(f"{API}/{other['id']}", json={"name": "Hijack"})
    assert denied.status_code == 403 and denied.get_json()["permission"] == "project.manage"

    archived_status = client.patch(f"{API}/{mine['id']}", json={"status": "archived"})
    assert archived_status.status_code == 400 and set(archived_status.get_json()["errors"]) == {"status"}
    empty_code = client.patch(f"{API}/{mine['id']}", json={"code": ""})
    assert empty_code.status_code == 400 and set(empty_code.get_json()["errors"]) == {"code"}
    taken_code = client.patch(f"{API}/{mine['id']}", json={"code": "oth"})
    assert taken_code.status_code == 400 and set(taken_code.get_json()["errors"]) == {"code"}
    bad_dates = client.patch(f"{API}/{mine['id']}", json={"start_date": "2027-01-01", "target_date": "2026-01-01", "lead_user_id": 999999})
    assert set(bad_dates.get_json()["errors"]) == {"target_date", "lead_user_id"}
    same_code = client.patch(f"{API}/{mine['id']}", json={"code": "mn-2", "status": "completed"})
    assert same_code.status_code == 200 and same_code.get_json()["payload"]["project"]["status"] == "completed"

    api_login(users["member"])
    forbidden = client.patch(f"{API}/{mine['id']}", json={"name": "Nope"})
    assert forbidden.status_code == 403 and forbidden.get_json()["permission"] == ["project.manage"]


def test_archive_and_restore(client, org, users, api_login):
    pat = make_user("Pat Lead", "pat@uiowa.edu", ops_role="project_lead", org=org)
    api_login(users["admin"])
    project = _create(client, name="Archive Me", lead_user_id=pat.id)

    api_login(pat)
    denied = client.post(f"{API}/{project['id']}/archive", json={})
    assert denied.status_code == 403 and denied.get_json()["permission"] == ["project.archive"]

    api_login(users["admin"])
    archived = client.post(f"{API}/{project['id']}/archive", json={})
    assert archived.status_code == 200
    body = archived.get_json()["payload"]["project"]
    assert body["status"] == "archived" and body["archived_at"] is not None
    again = client.post(f"{API}/{project['id']}/archive", json={})
    assert again.status_code == 409 and again.get_json()["code"] == "already_archived"
    assert _names(client.get(API)) == []
    assert _names(client.get(API, query_string={"view": "archived"})) == ["Archive Me"]
    assert client.get(f"{API}/{project['id']}").status_code == 200  # archived projects stay readable

    restored = client.post(f"{API}/{project['id']}/restore", json={})
    assert restored.status_code == 200
    body = restored.get_json()["payload"]["project"]
    assert body["status"] == "active" and body["archived_at"] is None
    not_archived = client.post(f"{API}/{project['id']}/restore", json={})
    assert not_archived.status_code == 409 and not_archived.get_json()["code"] == "not_archived"
    assert _names(client.get(API)) == ["Archive Me"]

    types = [e.event_type for e in AuditEvent.query.filter_by(entity_id=project["id"]).order_by(AuditEvent.occurred_at).all()]
    assert types == ["project.created", "project.archived", "project.restored"]
    archived_event = AuditEvent.query.filter_by(event_type="project.archived").one()
    assert archived_event.before_json["status"] == "active" and archived_event.after_json["status"] == "archived"


# --------------------------------------------------------------------------- members


def test_replace_members_rules_legacy_mirror_events_and_notifications(client, org, users, requester, api_login, captured_events):
    legacy = LegacyProject(slug="rover", title="Rover", summary="s", description="d", is_joinable=True)
    _db.session.add(legacy)
    _db.session.commit()
    team = Team(organization_id=org.id, name="Arm")
    other_org, _foreign = _foreign_project()
    foreign_team = Team(organization_id=other_org.id, name="Foreign Team")
    _db.session.add_all([team, foreign_team])
    _db.session.commit()

    api_login(users["admin"])
    project = _create(client, name="Crater Cruncher Rover", lead_user_id=users["lead"].id, public_project_id=legacy.id)
    assert project["public_project_id"] == legacy.id
    url = f"{API}/{project['id']}/members"
    lead_id, member_id, admin_id = users["lead"].id, users["member"].id, users["admin"].id

    outsider = make_user("Out Sider", "outsider@example.edu")
    inactive = client.put(url, json={"members": [{"user_id": lead_id}, {"user_id": outsider.id}]})
    assert inactive.status_code == 400 and set(inactive.get_json()["errors"]) == {"members"}
    assert str(outsider.id) in inactive.get_json()["errors"]["members"]

    no_lead = client.put(url, json={"members": [{"user_id": member_id, "project_role": "member"}]})
    assert no_lead.status_code == 400
    assert no_lead.get_json()["errors"] == {"members": "The project lead must remain a member."}

    not_a_list = client.put(url, json={"members": "nope"})
    assert not_a_list.status_code == 400 and set(not_a_list.get_json()["errors"]) == {"members"}
    missing = client.put(url, json={})
    assert missing.status_code == 400 and set(missing.get_json()["errors"]) == {"members"}
    bad_items = client.put(url, json={"members": [{"project_role": "boss", "team_id": "zzz"}, "text", {"user_id": lead_id}, {"user_id": lead_id}]})
    assert bad_items.status_code == 400
    assert set(bad_items.get_json()["errors"]) == {"members[0].user_id", "members[0].project_role", "members[0].team_id", "members[1]", "members[3].user_id"}
    foreign = client.put(url, json={"members": [{"user_id": lead_id}, {"user_id": member_id, "team_id": str(foreign_team.id)}]})
    assert foreign.status_code == 400 and set(foreign.get_json()["errors"]) == {"members"}
    assert {m.user_id for m in _project(project["id"]).members} == {lead_id, admin_id}
    assert LegacyProjectMembership.query.count() == 0

    good = client.put(
        url,
        json={"members": [{"user_id": lead_id, "project_role": "member"}, {"user_id": member_id, "project_role": "viewer", "team_id": str(team.id)}]},
    )
    assert good.status_code == 200, good.get_json()
    payload = good.get_json()["payload"]
    assert payload["project"]["id"] == project["id"] and payload["project"]["stats"]["member_count"] == 2
    members = {m["user"]["id"]: m for m in payload["members"]}
    assert set(members) == {lead_id, member_id}
    assert members[lead_id]["project_role"] == "lead"  # lead_user_id wins over the submitted role
    assert members[member_id]["project_role"] == "viewer" and members[member_id]["team"] == {"id": str(team.id), "name": "Arm"}
    assert members[member_id]["joined_at"].endswith("Z")

    mirror = {row.user_id: row for row in LegacyProjectMembership.query.filter_by(project_id=legacy.id).all()}
    assert set(mirror) == {lead_id, member_id}
    assert mirror[lead_id].role == "lead" and mirror[lead_id].left_at is None
    assert mirror[member_id].role == "member" and mirror[member_id].left_at is None
    joined = [payload for name, payload in captured_events if name == "team.joined"]
    assert joined == [{"user_id": member_id, "project_id": legacy.id}]
    note = Notification.query.filter_by(user_id=member_id, type="project.added").one()
    assert note.entity_id == project["id"]
    assert Notification.query.filter_by(user_id=admin_id).count() == 0
    event = AuditEvent.query.filter_by(event_type="project.members_changed").one()
    assert event.metadata_json == {"added": [member_id], "removed": [admin_id]}
    assert sorted(m["user_id"] for m in event.before_json["members"]) == sorted([lead_id, admin_id])
    assert sorted(m["user_id"] for m in event.after_json["members"]) == sorted([lead_id, member_id])

    removed = client.put(url, json={"members": [{"user_id": lead_id, "project_role": "lead"}]})
    assert removed.status_code == 200
    assert [m["user"]["id"] for m in removed.get_json()["payload"]["members"]] == [lead_id]
    left = LegacyProjectMembership.query.filter_by(project_id=legacy.id, user_id=member_id).one()
    assert left.left_at is not None
    first_joined_at = left.joined_at

    readded = client.put(url, json={"members": [{"user_id": lead_id}, {"user_id": member_id}]})
    assert readded.status_code == 200
    rejoined = LegacyProjectMembership.query.filter_by(project_id=legacy.id, user_id=member_id).one()
    assert rejoined.left_at is None and rejoined.joined_at >= first_joined_at
    assert LegacyProjectMembership.query.filter_by(project_id=legacy.id).count() == 2
    joined = [payload for name, payload in captured_events if name == "team.joined"]
    assert joined == [{"user_id": member_id, "project_id": legacy.id}] * 2
    assert Notification.query.filter_by(user_id=member_id, type="project.added").count() == 2

    api_login(requester)
    denied = client.put(url, json={"members": [{"user_id": lead_id}]})
    assert denied.status_code == 403 and denied.get_json()["permission"] == ["project.manage"]


def test_replace_members_without_legacy_link_does_not_touch_legacy_table(client, org, users, api_login, captured_events):
    pat = make_user("Pat Lead", "pat@uiowa.edu", ops_role="project_lead", org=org)
    api_login(users["admin"])
    mine = _create(client, name="Unlinked", lead_user_id=pat.id)
    other = _create(client, name="Other")

    api_login(pat)
    response = client.put(f"{API}/{mine['id']}/members", json={"members": [{"user_id": pat.id}, {"user_id": users["member"].id}]})
    assert response.status_code == 200, response.get_json()
    assert {m["user"]["id"]: m["project_role"] for m in response.get_json()["payload"]["members"]} == {pat.id: "lead", users["member"].id: "member"}
    assert LegacyProjectMembership.query.count() == 0
    assert not [name for name, _ in captured_events if name == "team.joined"]
    denied = client.put(f"{API}/{other['id']}/members", json={"members": [{"user_id": pat.id}]})
    assert denied.status_code == 403


# --------------------------------------------------------------------------- health / activity


def test_health_and_activity(client, org, users, api_login):
    api_login(users["admin"])
    project = _create(client, name="Healthy", lead_user_id=users["lead"].id, budget_amount=1000)
    pid = project["id"]
    now = utcnow()
    overdue = _wo(org, 1, users["admin"], pid, status="open", due_at=now - timedelta(days=2), is_blocked=True)
    _wo(org, 2, users["admin"], pid, status="in_progress", due_at=now + timedelta(days=2))
    _wo(org, 3, users["admin"], pid, status="on_hold")
    done = _wo(org, 4, users["admin"], pid, status="done")
    _wo(org, 5, users["admin"], pid, status="canceled")
    _wo(org, 6, users["admin"], pid, status="draft", is_blocked=True)
    _db.session.add_all(
        [
            CostEntry(organization_id=org.id, work_order_id=done.id, type="parts", amount="250.25"),
            CostEntry(organization_id=org.id, work_order_id=done.id, type="labor", amount="100.00"),
        ]
    )
    team = Team(organization_id=org.id, name="Wheels", project_id=uuid.UUID(pid))
    _db.session.add(team)
    _db.session.commit()

    murl = f"{API}/{pid}/milestones"
    yesterday = (now - timedelta(days=1)).date().isoformat()
    assert client.post(murl, json={"name": "Kickoff", "status": "done", "due_date": yesterday}).status_code == 201
    assert client.post(murl, json={"name": "Late review", "due_date": yesterday}).status_code == 201
    for offset in (5, 10, 15, 20):
        due = (now + timedelta(days=offset)).date().isoformat()
        assert client.post(murl, json={"name": f"In {offset} days", "due_date": due}).status_code == 201
    other_project = _create(client, name="Other")
    recent = AuditEvent(
        organization_id=org.id, event_type="work_order.created", entity_type="work_order", entity_id=str(overdue.id), summary="recent", occurred_at=utcnow()
    )
    old = AuditEvent(
        organization_id=org.id,
        event_type="work_order.created",
        entity_type="work_order",
        entity_id=str(done.id),
        summary="old",
        occurred_at=utcnow() - timedelta(days=10),
    )
    unrelated = AuditEvent(organization_id=org.id, event_type="work_order.created", entity_type="work_order", entity_id=str(uuid.uuid4()), occurred_at=utcnow())
    _db.session.add_all([recent, old, unrelated])
    _db.session.commit()

    health = client.get(f"{API}/{pid}/health")
    assert health.status_code == 200, health.get_json()
    body = health.get_json()["payload"]
    assert body["completion_percent"] == 20  # 1 done / (6 - 1 canceled)
    assert body["work"] == {"total": 6, "open": 1, "in_progress": 1, "on_hold": 1, "done": 1, "canceled": 1, "overdue": 1, "blocked": 2}
    assert body["milestones"]["total"] == 6 and body["milestones"]["done"] == 1 and body["milestones"]["missed"] == 1
    assert [m["name"] for m in body["milestones"]["upcoming"]] == ["In 5 days", "In 10 days", "In 15 days"]
    assert body["budget"] == {"amount": 1000.0, "used": 350.25, "committed": 0.0, "remaining": 649.75}
    assert body["members"] == 2
    assert body["teams"] == [{"id": str(team.id), "name": "Wheels"}]
    # project.created + 6 milestone.created + the recent work-order event; not the old or unrelated ones
    assert body["activity_7d"] == 8

    activity = client.get(f"{API}/{pid}/activity")
    assert activity.status_code == 200
    payload = activity.get_json()["payload"]
    assert payload["total"] == 9 and payload["next_cursor"] is None
    events = payload["items"]
    assert events[0]["entity_type"] == "work_order" and events[0]["summary"] == "recent"
    assert events[-1]["summary"] == "old"  # the 10-day-old event is listed, just not counted in activity_7d
    created = [e for e in events if e["event_type"] == "project.created"]
    assert len(created) == 1 and created[0]["actor"]["id"] == users["admin"].id and created[0]["entity_id"] == pid
    assert {e["entity_type"] for e in events} == {"project", "milestone", "work_order"}
    assert other_project["id"] not in {e["entity_id"] for e in events}
    assert str(uuid.UUID(unrelated.entity_id)) not in {e["entity_id"] for e in events}
    paged = client.get(f"{API}/{pid}/activity", query_string={"limit": 4})
    assert len(paged.get_json()["payload"]["items"]) == 4 and paged.get_json()["payload"]["next_cursor"]

    no_budget = _create(client, name="No Budget")
    body = client.get(f"{API}/{no_budget['id']}/health").get_json()["payload"]
    assert body["budget"] == {"amount": None, "used": 0.0, "committed": 0.0, "remaining": None}
    assert body["completion_percent"] == 0 and body["milestones"]["upcoming"] == [] and body["teams"] == []

    api_login(users["member"])
    assert client.get(f"{API}/{pid}/health").status_code == 200
    assert client.get(f"{API}/{pid}/activity").status_code == 200


# --------------------------------------------------------------------------- cross-organization


def test_cross_organization_and_unknown_ids_are_404(client, org, users, api_login):
    _other, foreign = _foreign_project()
    api_login(users["admin"])
    checks = [
        ("get", "", None),
        ("patch", "", {"name": "x"}),
        ("post", "/archive", {}),
        ("post", "/restore", {}),
        ("put", "/members", {"members": []}),
        ("get", "/health", None),
        ("get", "/activity", None),
        ("get", "/milestones", None),
        ("post", "/milestones", {"name": "m"}),
    ]
    for project_id in (str(foreign.id), str(uuid.uuid4()), "not-a-uuid"):
        for method, suffix, body in checks:
            response = getattr(client, method)(f"{API}/{project_id}{suffix}", json=body) if body is not None else client.get(f"{API}/{project_id}{suffix}")
            assert response.status_code == 404, (project_id, method, suffix, response.get_json())
            assert response.get_json()["code"] == "not_found"
    assert foreign.name == "Foreign" and foreign.archived_at is None
    assert AuditEvent.query.count() == 0
