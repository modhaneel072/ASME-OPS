"""Milestones vertical: CRUD with ordering, done/completed_at rules, computed
``missed`` status, validation, permissions, project/organization isolation."""

from __future__ import annotations

import uuid
from datetime import timedelta

from asme.extensions import db as _db
from asme.ops.models import AuditEvent, Milestone, Organization, OpsProject
from asme.ops.types import utcnow
from tests.ops.conftest import make_user

API = "/api/v1/projects"


def _create_project(client, **payload):
    response = client.post(API, json=payload)
    assert response.status_code == 201, response.get_json()
    return response.get_json()["payload"]["project"]


def _post(client, project_id, **payload):
    response = client.post(f"{API}/{project_id}/milestones", json=payload)
    assert response.status_code == 201, response.get_json()
    return response.get_json()["payload"]["milestone"]


def _list(client, project_id) -> list[dict]:
    response = client.get(f"{API}/{project_id}/milestones")
    assert response.status_code == 200, response.get_json()
    return response.get_json()["payload"]["items"]


def test_milestone_crud_ordering_and_completed_at(client, org, users, api_login):
    api_login(users["admin"])
    project = _create_project(client, name="Rover")
    pid = project["id"]

    first = _post(client, pid, name="Design review", due_date="2027-01-15", owner_user_id=users["lead"].id, weight=3, description="CDR")
    assert first["project_id"] == pid and first["order_index"] == 0 and first["weight"] == 3
    assert first["status"] == "planned" and first["completed_at"] is None and first["due_date"] == "2027-01-15"
    assert first["owner"]["id"] == users["lead"].id and first["description"] == "CDR"
    second = _post(client, pid, name="Build")
    assert second["order_index"] == 1 and second["weight"] == 1 and second["owner"] is None and second["due_date"] is None
    third = _post(client, pid, name="Explicit", order_index=10, status="done")
    assert third["order_index"] == 10 and third["status"] == "done" and third["completed_at"] is not None
    fourth = _post(client, pid, name="Appended after explicit")
    assert fourth["order_index"] == 11

    listing = client.get(f"{API}/{pid}/milestones")
    payload = listing.get_json()["payload"]
    assert [m["name"] for m in payload["items"]] == ["Design review", "Build", "Explicit", "Appended after explicit"]
    assert payload["total"] == 4 and payload["next_cursor"] is None

    done = client.patch(f"{API}/{pid}/milestones/{first['id']}", json={"status": "done"})
    assert done.status_code == 200 and done.get_json()["payload"]["milestone"]["completed_at"] is not None
    reopened = client.patch(f"{API}/{pid}/milestones/{first['id']}", json={"status": "in_progress"})
    assert reopened.status_code == 200
    body = reopened.get_json()["payload"]["milestone"]
    assert body["status"] == "in_progress" and body["completed_at"] is None
    still_done = client.patch(f"{API}/{pid}/milestones/{third['id']}", json={"name": "Explicit v2"})
    assert still_done.get_json()["payload"]["milestone"]["completed_at"] == third["completed_at"]

    edited = client.patch(f"{API}/{pid}/milestones/{second['id']}", json={"name": "Build v2", "due_date": None, "weight": 2, "owner_user_id": None, "order_index": 5})
    assert edited.status_code == 200
    body = edited.get_json()["payload"]["milestone"]
    assert body["name"] == "Build v2" and body["weight"] == 2 and body["due_date"] is None and body["order_index"] == 5

    deleted = client.delete(f"{API}/{pid}/milestones/{third['id']}")
    assert deleted.status_code == 200 and deleted.get_json()["payload"] == {"deleted": third["id"]}
    assert _db.session.get(Milestone, uuid.UUID(third["id"])) is None
    assert [m["name"] for m in _list(client, pid)] == ["Design review", "Build v2", "Appended after explicit"]
    assert client.delete(f"{API}/{pid}/milestones/{third['id']}").status_code == 404

    types = [e.event_type for e in AuditEvent.query.filter_by(entity_type="milestone").order_by(AuditEvent.occurred_at).all()]
    assert types.count("milestone.created") == 4 and types.count("milestone.updated") == 4 and types.count("milestone.deleted") == 1
    created = AuditEvent.query.filter_by(event_type="milestone.created").first()
    assert created.entity_id == first["id"] and created.metadata_json["project_id"] == pid and created.after_json["name"] == "Design review"
    removed = AuditEvent.query.filter_by(event_type="milestone.deleted").one()
    assert removed.entity_id == third["id"] and removed.before_json["name"] == "Explicit v2"
    updated = AuditEvent.query.filter_by(event_type="milestone.updated").first()
    assert updated.before_json["status"] == "planned" and updated.after_json["status"] == "done"

    stats = client.get(f"{API}/{pid}").get_json()["payload"]["project"]["stats"]
    assert stats["next_milestone"]["name"] == "Design review"


def test_milestone_validation_lists_every_bad_field(client, org, users, api_login):
    api_login(users["admin"])
    pid = _create_project(client, name="Rover")["id"]
    url = f"{API}/{pid}/milestones"
    shape = client.post(url, json={"name": "", "weight": 0, "status": "later", "due_date": "not-a-date", "order_index": -1, "owner_user_id": "x"})
    assert shape.status_code == 400 and shape.get_json()["code"] == "validation"
    assert set(shape.get_json()["errors"]) == {"name", "weight", "status", "due_date", "order_index", "owner_user_id"}

    outsider = make_user("Out Sider", "outsider@example.edu")
    owner = client.post(url, json={"name": "Owned", "owner_user_id": outsider.id})
    assert owner.status_code == 400 and set(owner.get_json()["errors"]) == {"owner_user_id"}

    milestone = _post(client, pid, name="Valid")
    patch = client.patch(f"{url}/{milestone['id']}", json={"order_index": None, "weight": "many", "name": None})
    assert patch.status_code == 400 and set(patch.get_json()["errors"]) == {"order_index", "weight", "name"}
    assert Milestone.query.count() == 1


def test_missed_status_is_computed_not_persisted(client, org, users, api_login):
    api_login(users["admin"])
    pid = _create_project(client, name="Rover")["id"]
    yesterday = (utcnow() - timedelta(days=1)).date().isoformat()
    tomorrow = (utcnow() + timedelta(days=1)).date().isoformat()

    late = _post(client, pid, name="Late", due_date=yesterday)
    assert late["status"] == "missed"
    assert _db.session.get(Milestone, uuid.UUID(late["id"])).status == "planned"
    late_in_progress = _post(client, pid, name="Late in progress", due_date=yesterday, status="in_progress")
    assert late_in_progress["status"] == "missed"
    on_time = _post(client, pid, name="On time", due_date=tomorrow)
    assert on_time["status"] == "planned"
    finished_late = _post(client, pid, name="Finished", due_date=yesterday, status="done")
    assert finished_late["status"] == "done"

    by_name = {m["name"]: m["status"] for m in _list(client, pid)}
    assert by_name == {"Late": "missed", "Late in progress": "missed", "On time": "planned", "Finished": "done"}
    stats = client.get(f"{API}/{pid}").get_json()["payload"]["project"]["stats"]
    assert stats["next_milestone"]["name"] == "Late" and stats["next_milestone"]["status"] == "missed"
    health = client.get(f"{API}/{pid}/health").get_json()["payload"]["milestones"]
    assert health["missed"] == 2 and health["done"] == 1 and [m["name"] for m in health["upcoming"]] == ["On time"]

    completed = client.patch(f"{API}/{pid}/milestones/{late['id']}", json={"status": "done"})
    assert completed.get_json()["payload"]["milestone"]["status"] == "done"


def test_milestone_permissions(client, org, users, requester, api_login):
    pat = make_user("Pat Lead", "pat@uiowa.edu", ops_role="project_lead", org=org)
    api_login(users["admin"])
    mine = _create_project(client, name="Mine", lead_user_id=pat.id)["id"]
    other = _create_project(client, name="Other")["id"]
    existing = _post(client, other, name="Other's milestone")

    api_login(pat)
    assert client.post(f"{API}/{mine}/milestones", json={"name": "Ok"}).status_code == 201
    denied = client.post(f"{API}/{other}/milestones", json={"name": "Nope"})
    assert denied.status_code == 403 and denied.get_json()["permission"] == "milestone.manage"
    assert client.patch(f"{API}/{other}/milestones/{existing['id']}", json={"name": "Nope"}).status_code == 403
    assert client.delete(f"{API}/{other}/milestones/{existing['id']}").status_code == 403
    assert len(_list(client, other)) == 1  # readable through project.read

    api_login(users["member"])  # full_member: no milestone.manage at any scope
    assert len(_list(client, mine)) == 1
    forbidden = client.post(f"{API}/{mine}/milestones", json={"name": "Nope"})
    assert forbidden.status_code == 403 and forbidden.get_json()["permission"] == ["milestone.manage"]
    assert client.patch(f"{API}/{other}/milestones/{existing['id']}", json={"name": "Nope"}).status_code == 403
    assert client.delete(f"{API}/{other}/milestones/{existing['id']}").status_code == 403

    api_login(requester)
    assert len(_list(client, other)) == 1
    assert client.post(f"{API}/{other}/milestones", json={"name": "Nope"}).status_code == 403
    assert Milestone.query.count() == 2


def test_milestone_from_other_project_or_organization_is_404(client, org, users, api_login):
    api_login(users["admin"])
    first = _create_project(client, name="First")["id"]
    second = _create_project(client, name="Second")["id"]
    milestone = _post(client, first, name="Belongs to first")

    other = Organization(name="Other Chapter", slug="other")
    _db.session.add(other)
    _db.session.flush()
    foreign_project = OpsProject(organization_id=other.id, name="Foreign", code="FRN")
    _db.session.add(foreign_project)
    _db.session.flush()
    foreign_milestone = Milestone(organization_id=other.id, project_id=foreign_project.id, name="Foreign milestone")
    _db.session.add(foreign_milestone)
    _db.session.commit()

    wrong_project = [
        f"{API}/{second}/milestones/{milestone['id']}",
        f"{API}/{first}/milestones/{foreign_milestone.id}",
        f"{API}/{first}/milestones/{uuid.uuid4()}",
        f"{API}/{first}/milestones/not-a-uuid",
        f"{API}/{foreign_project.id}/milestones/{foreign_milestone.id}",
    ]
    for url in wrong_project:
        assert client.patch(url, json={"name": "x"}).status_code == 404, url
        assert client.delete(url).status_code == 404, url
    assert client.get(f"{API}/{foreign_project.id}/milestones").status_code == 404
    assert client.post(f"{API}/{foreign_project.id}/milestones", json={"name": "x"}).status_code == 404
    assert _db.session.get(Milestone, uuid.UUID(milestone["id"])).name == "Belongs to first"
    assert _db.session.get(Milestone, foreign_milestone.id).name == "Foreign milestone"
    assert AuditEvent.query.filter_by(entity_type="milestone").count() == 1


def test_milestone_list_respects_project_visibility(client, org, users, api_login):
    api_login(users["admin"])
    private = _create_project(client, name="Private", visibility="private")["id"]
    _post(client, private, name="Secret plan")

    api_login(users["member"])
    assert client.get(f"{API}/{private}/milestones").status_code == 404

    advisor = make_user("Dr. Advisor", "advisor@uiowa.edu", ops_role="faculty_advisor", org=org)
    api_login(advisor)
    assert [m["name"] for m in _list(client, private)] == ["Secret plan"]
    assert client.post(f"{API}/{private}/milestones", json={"name": "Nope"}).status_code == 403
