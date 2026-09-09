"""Comments on work orders, projects and assets: threads, mentions, edit/delete rules,
visibility and tenancy."""

from __future__ import annotations

import uuid

from asme.extensions import db as _db
from asme.ops import policy
from asme.ops.models import (
    Asset,
    AuditEvent,
    Comment,
    Notification,
    OpsProject,
    Organization,
    ProjectMember,
    WorkOrder,
    WorkOrderAssignee,
    WorkOrderWatcher,
)
from asme.ops.services import comments as comments_service
from tests.ops.conftest import make_user

_counter = {"n": 0}


def _next_number() -> int:
    _counter["n"] += 1
    return _counter["n"]


def _project(org, name="Rover", code=None, visibility="chapter", **kw):
    row = OpsProject(organization_id=org.id, name=name, code=code or name[:3].upper() + str(_next_number()), visibility=visibility, **kw)
    _db.session.add(row)
    _db.session.commit()
    return row


def _work_order(org, creator, **kw):
    row = WorkOrder(organization_id=org.id, number=_next_number(), title=kw.pop("title", "Replace wheel hub"), created_by_user_id=creator.id, **kw)
    _db.session.add(row)
    _db.session.commit()
    return row


def _asset(org, name="3D Printer 01", **kw):
    row = Asset(organization_id=org.id, name=name, **kw)
    _db.session.add(row)
    _db.session.commit()
    return row


def _other_org():
    other = Organization(name="Other Chapter", slug=f"other-{uuid.uuid4().hex[:6]}")
    _db.session.add(other)
    _db.session.flush()
    return other


def _mention(user) -> str:
    return f"@[{user.name}](user:{user.id})"


# --------------------------------------------------------------------------- happy path


def test_create_and_list_comments_on_work_order(client, org, users, api_login):
    wo = _work_order(org, users["lead"])
    api_login(users["member"])

    empty = client.get(f"/api/v1/work-orders/{wo.id}/comments")
    assert empty.status_code == 200
    assert empty.get_json()["payload"] == {"items": [], "next_cursor": None, "total": 0, "comments": []}

    first = client.post(f"/api/v1/work-orders/{wo.id}/comments", json={"body": "Hub arrived, starting tomorrow."})
    assert first.status_code == 201, first.get_json()
    root = first.get_json()["payload"]["comment"]
    assert root["entity_type"] == "work_order" and root["entity_id"] == str(wo.id)
    assert root["author"]["id"] == users["member"].id and root["author"]["name"] == "Mo Member"
    assert root["body"] == "Hub arrived, starting tomorrow."
    assert root["parent_comment_id"] is None and root["edited_at"] is None
    assert root["deleted"] is False and root["mentions"] == []
    assert root["created_at"].endswith("Z")

    reply = client.post(f"/api/v1/work-orders/{wo.id}/comments", json={"body": "Great.", "parent_comment_id": root["id"]})
    assert reply.status_code == 201
    assert reply.get_json()["payload"]["comment"]["parent_comment_id"] == root["id"]

    listed = client.get(f"/api/v1/work-orders/{wo.id}/comments").get_json()["payload"]
    assert listed["total"] == 2
    assert [c["body"] for c in listed["items"]] == ["Hub arrived, starting tomorrow.", "Great."]

    event = AuditEvent.query.filter_by(event_type="comment.created").order_by(AuditEvent.occurred_at.asc()).first()
    assert event.entity_type == "work_order" and event.entity_id == str(wo.id)
    assert event.actor_user_id == users["member"].id
    assert event.metadata_json["comment_id"] == root["id"]
    assert event.metadata_json["entity_type"] == "work_order" and event.metadata_json["entity_id"] == str(wo.id)
    assert event.after_json["body"] == "Hub arrived, starting tomorrow."


def test_comments_on_projects_and_assets(client, org, users, api_login):
    project = _project(org, "Showcase")
    asset = _asset(org)
    api_login(users["member"])
    on_project = client.post(f"/api/v1/projects/{project.id}/comments", json={"body": "Booth layout attached."})
    assert on_project.status_code == 201
    assert on_project.get_json()["payload"]["comment"]["entity_type"] == "project"
    on_asset = client.post(f"/api/v1/assets/{asset.id}/comments", json={"body": "Nozzle replaced."})
    assert on_asset.status_code == 201
    assert on_asset.get_json()["payload"]["comment"]["entity_type"] == "asset"
    # threads are per entity
    assert client.get(f"/api/v1/projects/{project.id}/comments").get_json()["payload"]["total"] == 1
    assert client.get(f"/api/v1/assets/{asset.id}/comments").get_json()["payload"]["total"] == 1


# --------------------------------------------------------------------------- validation


def test_create_reports_every_bad_field(client, org, users, api_login):
    wo = _work_order(org, users["lead"])
    other_wo = _work_order(org, users["lead"], title="Other")
    api_login(users["member"])
    foreign_parent = client.post(f"/api/v1/work-orders/{other_wo.id}/comments", json={"body": "elsewhere"}).get_json()["payload"]["comment"]

    missing = client.post(f"/api/v1/work-orders/{wo.id}/comments", json={})
    assert missing.status_code == 400 and missing.get_json()["code"] == "validation"
    assert missing.get_json()["errors"] == {"body": "This field is required."}

    blank = client.post(f"/api/v1/work-orders/{wo.id}/comments", json={"body": "   ", "parent_comment_id": "not-a-uuid"})
    assert blank.status_code == 400
    assert set(blank.get_json()["errors"]) == {"body", "parent_comment_id"}

    too_long = client.post(f"/api/v1/work-orders/{wo.id}/comments", json={"body": "x" * 8001})
    assert too_long.status_code == 400 and "body" in too_long.get_json()["errors"]

    wrong_thread = client.post(f"/api/v1/work-orders/{wo.id}/comments", json={"body": "reply", "parent_comment_id": foreign_parent["id"]})
    assert wrong_thread.status_code == 400
    assert set(wrong_thread.get_json()["errors"]) == {"parent_comment_id"}

    unknown_parent = client.post(f"/api/v1/work-orders/{wo.id}/comments", json={"body": "reply", "parent_comment_id": str(uuid.uuid4())})
    assert unknown_parent.status_code == 400 and "parent_comment_id" in unknown_parent.get_json()["errors"]

    exactly_max = client.post(f"/api/v1/work-orders/{wo.id}/comments", json={"body": "y" * 8000})
    assert exactly_max.status_code == 201


def test_edit_validation(client, org, users, api_login):
    wo = _work_order(org, users["lead"])
    api_login(users["member"])
    created = client.post(f"/api/v1/work-orders/{wo.id}/comments", json={"body": "first"}).get_json()["payload"]["comment"]
    bad = client.patch(f"/api/v1/comments/{created['id']}", json={"body": ""})
    assert bad.status_code == 400 and bad.get_json()["errors"] == {"body": "This field is required."}


# --------------------------------------------------------------------------- mentions + notifications


def test_mentions_notify_members_and_work_order_audience(client, org, users, api_login):
    admin, lead, member = users["admin"], users["lead"], users["member"]
    watcher = make_user("Wes Watcher", "wes@uiowa.edu", org=org)
    suspended = make_user("Sue Suspended", "sue@uiowa.edu", org=org)
    from asme.ops import bootstrap

    bootstrap.membership_for(suspended, org).member_status = "suspended"
    _db.session.commit()

    wo = _work_order(org, lead)
    wo.assignees.append(WorkOrderAssignee(user_id=member.id))
    wo.watchers.append(WorkOrderWatcher(user_id=watcher.id))
    _db.session.commit()

    api_login(member)
    body = f"{_mention(admin)} can you check the torque spec? {_mention(suspended)} {_mention(member)} @[Nobody](user:999999)"
    response = client.post(f"/api/v1/work-orders/{wo.id}/comments", json={"body": body})
    assert response.status_code == 201
    payload = response.get_json()["payload"]["comment"]
    # mentions list shows chapter members (any status) but never unknown ids
    assert [m["id"] for m in payload["mentions"]] == [admin.id, suspended.id, member.id]

    mentioned = {n.user_id for n in Notification.query.filter_by(type="work_order.mentioned").all()}
    assert mentioned == {admin.id}  # suspended member and the actor are skipped
    commented = Notification.query.filter_by(type="work_order.commented").all()
    assert {n.user_id for n in commented} == {lead.id, watcher.id}  # creator + watcher; the assignee is the actor
    note = next(n for n in commented if n.user_id == lead.id)
    assert note.entity_type == "work_order" and note.entity_id == str(wo.id)
    assert "Mo Member commented on WO-" in note.title
    assert Notification.query.filter_by(user_id=member.id).count() == 0

    mention_note = Notification.query.filter_by(type="work_order.mentioned", user_id=admin.id).one()
    assert mention_note.body.startswith("@[Ada Admin]")
    assert "mentioned you" in mention_note.title


def test_mentions_on_projects_use_mentioned_type_only(client, org, users, api_login):
    project = _project(org, "Showcase")
    api_login(users["member"])
    response = client.post(f"/api/v1/projects/{project.id}/comments", json={"body": f"{_mention(users['lead'])} thoughts?"})
    assert response.status_code == 201
    assert [n.type for n in Notification.query.all()] == ["work_order.mentioned"]
    assert Notification.query.one().user_id == users["lead"].id


def test_mention_parser():
    assert comments_service.mentioned_user_ids("@[A B](user:1) and @[C](user:2) again @[A B](user:1)") == [1, 2]
    assert comments_service.mentioned_user_ids("plain @someone user:3 @[](user:4)") == []
    assert comments_service.mentioned_user_ids("") == []


# --------------------------------------------------------------------------- permissions


def test_work_order_comment_requires_comment_key(client, org, users, api_login):
    advisor = make_user("Dr. Advisor", "advisor@uiowa.edu", ops_role="faculty_advisor", org=org)
    wo = _work_order(org, users["lead"])
    api_login(advisor)
    readable = client.get(f"/api/v1/work-orders/{wo.id}/comments")
    assert readable.status_code == 200
    denied = client.post(f"/api/v1/work-orders/{wo.id}/comments", json={"body": "Looks fine."})
    assert denied.status_code == 403
    assert denied.get_json()["code"] == "forbidden" and denied.get_json()["permission"] == "work_order.comment"


def test_any_reader_may_comment_on_projects_but_not_hidden_entities(client, org, users, requester, api_login):
    project = _project(org, "Showcase")
    asset = _asset(org)
    wo = _work_order(org, users["lead"])
    api_login(requester)
    allowed = client.post(f"/api/v1/projects/{project.id}/comments", json={"body": "When is the showcase?"})
    assert allowed.status_code == 201
    # requester has no asset.read and no work_order read key: both look missing
    assert client.post(f"/api/v1/assets/{asset.id}/comments", json={"body": "x"}).status_code == 404
    assert client.get(f"/api/v1/assets/{asset.id}/comments").status_code == 404
    assert client.post(f"/api/v1/work-orders/{wo.id}/comments", json={"body": "x"}).status_code == 404
    assert client.get(f"/api/v1/work-orders/{wo.id}/comments").status_code == 404


def test_edit_and_delete_by_author_or_manager_only(client, org, users, api_login):
    admin, member = users["admin"], users["member"]
    creator = make_user("Cal Creator", "cal@uiowa.edu", org=org)  # full member: work_order.edit@own
    stranger = make_user("Ola Other", "ola@uiowa.edu", org=org)  # full member, unrelated to the work order
    wo = _work_order(org, creator)

    api_login(member)
    created = client.post(f"/api/v1/work-orders/{wo.id}/comments", json={"body": "draft text"}).get_json()["payload"]["comment"]
    cid = created["id"]

    edited = client.patch(f"/api/v1/comments/{cid}", json={"body": "final text"})
    assert edited.status_code == 200
    body = edited.get_json()["payload"]["comment"]
    assert body["body"] == "final text" and body["edited_at"] is not None
    assert AuditEvent.query.filter_by(event_type="comment.updated").one().before_json["body"] == "draft text"

    api_login(stranger)
    denied = client.patch(f"/api/v1/comments/{cid}", json={"body": "hijack"})
    assert denied.status_code == 403 and denied.get_json()["permission"] == "work_order.edit"
    assert client.delete(f"/api/v1/comments/{cid}").status_code == 403

    # the work-order creator holds work_order.edit@own -> can_manage
    api_login(creator)
    by_manager = client.patch(f"/api/v1/comments/{cid}", json={"body": "managed text"})
    assert by_manager.status_code == 200

    api_login(admin)
    deleted = client.delete(f"/api/v1/comments/{cid}")
    assert deleted.status_code == 200
    assert deleted.get_json()["payload"]["comment"]["deleted"] is True
    row = _db.session.get(Comment, uuid.UUID(cid))
    assert row.deleted_at is not None and row.body == "managed text"  # soft delete keeps the row
    assert AuditEvent.query.filter_by(event_type="comment.deleted").one().metadata_json["comment_id"] == cid

    listed = client.get(f"/api/v1/work-orders/{wo.id}/comments").get_json()["payload"]
    assert listed["total"] == 1
    assert listed["items"][0]["deleted"] is True and listed["items"][0]["body"] == "" and listed["items"][0]["mentions"] == []

    api_login(member)
    assert client.patch(f"/api/v1/comments/{cid}", json={"body": "resurrect"}).status_code == 409
    assert client.patch(f"/api/v1/comments/{cid}", json={"body": "resurrect"}).get_json()["code"] == "comment_deleted"
    assert client.delete(f"/api/v1/comments/{cid}").status_code == 409


def test_project_lead_manages_comments_on_own_project(client, org, users, api_login):
    pl = make_user("Pat Lead", "pat@uiowa.edu", ops_role="project_lead", org=org)
    mine = _project(org, "Rover", lead_user_id=pl.id)
    mine.members.append(ProjectMember(user_id=pl.id, project_role="lead"))
    theirs = _project(org, "Showcase")
    _db.session.commit()

    api_login(users["member"])
    on_mine = client.post(f"/api/v1/projects/{mine.id}/comments", json={"body": "a"}).get_json()["payload"]["comment"]
    on_theirs = client.post(f"/api/v1/projects/{theirs.id}/comments", json={"body": "b"}).get_json()["payload"]["comment"]

    api_login(pl)
    assert client.delete(f"/api/v1/comments/{on_mine['id']}").status_code == 200
    assert client.delete(f"/api/v1/comments/{on_theirs['id']}").status_code == 403


# --------------------------------------------------------------------------- visibility + tenancy


def test_private_project_work_order_is_hidden_from_non_members(client, org, users, api_login):
    secret = _project(org, "Sponsor Bid", visibility="private")
    wo = _work_order(org, users["lead"], project_id=secret.id)
    api_login(users["admin"])
    seeded = client.post(f"/api/v1/work-orders/{wo.id}/comments", json={"body": "confidential"}).get_json()["payload"]["comment"]

    api_login(users["member"])
    assert client.get(f"/api/v1/work-orders/{wo.id}/comments").status_code == 404
    assert client.post(f"/api/v1/work-orders/{wo.id}/comments", json={"body": "peek"}).status_code == 404
    assert client.get(f"/api/v1/projects/{secret.id}/comments").status_code == 404
    assert client.patch(f"/api/v1/comments/{seeded['id']}", json={"body": "peek"}).status_code == 404
    assert client.delete(f"/api/v1/comments/{seeded['id']}").status_code == 404

    secret.members.append(ProjectMember(user_id=users["member"].id))
    _db.session.commit()
    assert client.get(f"/api/v1/work-orders/{wo.id}/comments").get_json()["payload"]["total"] == 1


def test_asset_in_private_project_is_hidden(client, org, users, api_login):
    secret = _project(org, "Sponsor Bid", visibility="private")
    asset = _asset(org, project_id=secret.id)
    api_login(users["member"])
    assert client.get(f"/api/v1/assets/{asset.id}/comments").status_code == 404
    api_login(users["admin"])
    assert client.get(f"/api/v1/assets/{asset.id}/comments").status_code == 200


def test_cross_organization_ids_are_not_found(client, org, users, api_login, ctx_admin):
    other = _other_org()
    foreign_wo = WorkOrder(organization_id=other.id, number=1, title="Foreign", created_by_user_id=users["admin"].id)
    foreign_project = OpsProject(organization_id=other.id, name="Foreign", code="FRN")
    _db.session.add_all([foreign_wo, foreign_project])
    _db.session.flush()
    foreign_comment = Comment(organization_id=other.id, entity_type="work_order", entity_id=foreign_wo.id, author_user_id=users["admin"].id, body="x")
    _db.session.add(foreign_comment)
    _db.session.commit()

    api_login(users["admin"])
    assert client.get(f"/api/v1/work-orders/{foreign_wo.id}/comments").status_code == 404
    assert client.post(f"/api/v1/work-orders/{foreign_wo.id}/comments", json={"body": "x"}).status_code == 404
    assert client.get(f"/api/v1/projects/{foreign_project.id}/comments").status_code == 404
    assert client.patch(f"/api/v1/comments/{foreign_comment.id}", json={"body": "x"}).status_code == 404
    assert client.delete(f"/api/v1/comments/{foreign_comment.id}").status_code == 404
    assert Comment.query.filter_by(organization_id=org.id).count() == 0


def test_unknown_segment_and_malformed_ids(client, org, users, api_login):
    api_login(users["admin"])
    assert client.get("/api/v1/teams/abc/comments").status_code == 404
    assert client.get("/api/v1/work-orders/not-a-uuid/comments").status_code == 404
    assert client.get(f"/api/v1/work-orders/{uuid.uuid4()}/comments").status_code == 404
    assert client.patch("/api/v1/comments/not-a-uuid", json={"body": "x"}).status_code == 404
    assert client.patch(f"/api/v1/comments/{uuid.uuid4()}", json={"body": "x"}).status_code == 404


def test_login_and_membership_required(client, org, users):
    wo = _work_order(org, users["lead"])
    anonymous = client.get(f"/api/v1/work-orders/{wo.id}/comments")
    assert anonymous.status_code == 401 and anonymous.get_json()["code"] == "login_required"


def test_service_functions_take_context_first(org, users, ctx_admin, ctx_member):
    wo = _work_order(org, users["lead"])
    row = comments_service.create(ctx_member, "work-orders", str(wo.id), {"body": "via service"})
    assert row.author_user_id == users["member"].id
    entity_type, obj, rows = comments_service.list_for(ctx_admin, "work-orders", wo.id)
    assert entity_type == "work_order" and obj is wo and rows == [row]
    assert policy.can(ctx_admin, "work_order.edit", wo)
