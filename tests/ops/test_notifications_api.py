"""``GET /notifications`` and ``POST /notifications/read``."""

from __future__ import annotations

from datetime import timedelta

from asme.extensions import db as _db
from asme.ops import policy
from asme.ops.models import Asset, Notification, OpsProject, Organization, WorkOrder
from asme.ops.services import notifications
from asme.ops.types import utcnow
from tests.ops.conftest import make_user


def _wo(org, number, creator, **kw):
    row = WorkOrder(organization_id=org.id, number=number, title=f"WO {number}", created_by_user_id=creator.id, **kw)
    _db.session.add(row)
    _db.session.flush()
    return row


def _seed_notifications(ctx_admin, org, users, count=3):
    """``count`` unread notifications for the member, each on its own work order,
    with strictly increasing ``created_at`` so ordering is deterministic."""
    rows = []
    base = utcnow() - timedelta(minutes=count)
    for index in range(count):
        wo = _wo(org, index + 1, users["admin"])
        created = notifications.notify(ctx_admin, [users["member"].id], "work_order.assigned", f"Assigned #{wo.number}", "body", entity=wo)
        created[0].created_at = base + timedelta(minutes=index)
        rows.append((wo, created[0]))
    _db.session.commit()
    return rows


def test_list_notifications_shapes_hrefs_and_unread_count(client, org, users, ctx_admin, api_login):
    rows = _seed_notifications(ctx_admin, org, users, count=2)
    project = OpsProject(organization_id=org.id, name="Rover", code="CCR")
    asset = Asset(organization_id=org.id, name="Printer", code="P1")
    _db.session.add_all([project, asset])
    _db.session.flush()
    notifications.notify(ctx_admin, [users["member"].id], "project.added", "Added to Rover", entity=project)
    notifications.notify(ctx_admin, [users["member"].id], "asset.offline", "Printer offline", entity=asset)
    notifications.notify(ctx_admin, [users["member"].id], "system", "Welcome")
    # another user's notification never shows up in the member's list
    notifications.notify(ctx_admin, [users["lead"].id], "system", "For Lee")
    _db.session.commit()

    api_login(users["member"])
    response = client.get("/api/v1/notifications")
    assert response.status_code == 200, response.get_json()
    payload = response.get_json()["payload"]
    assert set(payload) >= {"items", "next_cursor", "total", "notifications", "unread_count"}
    assert payload["total"] == 5 and payload["unread_count"] == 5 and payload["next_cursor"] is None
    assert payload["notifications"] == payload["items"]
    items = payload["items"]
    assert [item["title"] for item in items[-2:]] == ["Assigned #2", "Assigned #1"]  # newest first
    assert set(items[0]) == {"id", "type", "title", "body", "entity_type", "entity_id", "read_at", "created_at", "href"}
    by_title = {item["title"]: item for item in items}
    wo = rows[0][0]
    assert by_title["Assigned #1"]["href"] == f"/app/work-orders/{wo.id}"
    assert by_title["Assigned #1"]["entity_type"] == "work_order" and by_title["Assigned #1"]["entity_id"] == str(wo.id)
    assert by_title["Added to Rover"]["href"] == f"/app/projects/{project.id}"
    assert by_title["Printer offline"]["href"] == f"/app/assets/{asset.id}"
    assert by_title["Welcome"]["href"] is None and by_title["Welcome"]["entity_type"] is None
    assert all(item["read_at"] is None for item in items)
    assert "For Lee" not in by_title


def test_list_notifications_unread_filter_and_cursor(client, org, users, ctx_admin, ctx_member, api_login):
    rows = _seed_notifications(ctx_admin, org, users, count=3)
    notifications.mark_read(ctx_member, [rows[0][1].id])

    api_login(users["member"])
    unread = client.get("/api/v1/notifications?unread=1")
    payload = unread.get_json()["payload"]
    assert payload["total"] == 2 and payload["unread_count"] == 2
    assert [item["title"] for item in payload["items"]] == ["Assigned #3", "Assigned #2"]

    everything = client.get("/api/v1/notifications?unread=0").get_json()["payload"]
    assert everything["total"] == 3 and everything["unread_count"] == 2
    read_item = next(item for item in everything["items"] if item["title"] == "Assigned #1")
    assert read_item["read_at"] is not None

    first = client.get("/api/v1/notifications?limit=2").get_json()["payload"]
    assert [item["title"] for item in first["items"]] == ["Assigned #3", "Assigned #2"]
    assert first["next_cursor"] and first["total"] == 3
    second = client.get(f"/api/v1/notifications?limit=2&cursor={first['next_cursor']}").get_json()["payload"]
    assert [item["title"] for item in second["items"]] == ["Assigned #1"]
    assert second["next_cursor"] is None

    bad_flag = client.get("/api/v1/notifications?unread=maybe")
    assert bad_flag.status_code == 400 and set(bad_flag.get_json()["errors"]) == {"unread"}
    bad_cursor = client.get("/api/v1/notifications?cursor=%%%")
    assert bad_cursor.status_code == 400 and bad_cursor.get_json()["code"] == "bad_cursor"


def test_mark_read_by_ids_only_touches_the_callers_rows(client, org, users, ctx_admin, api_login):
    rows = _seed_notifications(ctx_admin, org, users, count=2)
    lead_row = notifications.notify(ctx_admin, [users["lead"].id], "system", "For Lee")[0]
    _db.session.commit()

    api_login(users["member"])
    response = client.post("/api/v1/notifications/read", json={"ids": [str(rows[0][1].id), str(lead_row.id)]})
    assert response.status_code == 200, response.get_json()
    assert response.get_json()["payload"] == {"updated": 1}
    _db.session.expire_all()
    assert rows[0][1].read_at is not None
    assert rows[1][1].read_at is None
    assert lead_row.read_at is None  # another user's id is ignored

    # marking the same id again is a no-op
    again = client.post("/api/v1/notifications/read", json={"ids": [str(rows[0][1].id)]})
    assert again.get_json()["payload"] == {"updated": 0}
    assert client.get("/api/v1/notifications").get_json()["payload"]["unread_count"] == 1


def test_mark_all_read(client, org, users, ctx_admin, api_login):
    _seed_notifications(ctx_admin, org, users, count=3)
    lead_row = notifications.notify(ctx_admin, [users["lead"].id], "system", "For Lee")[0]
    _db.session.commit()

    api_login(users["member"])
    response = client.post("/api/v1/notifications/read", json={"all": True})
    assert response.status_code == 200 and response.get_json()["payload"] == {"updated": 3}
    payload = client.get("/api/v1/notifications").get_json()["payload"]
    assert payload["unread_count"] == 0 and all(item["read_at"] for item in payload["items"])
    _db.session.expire_all()
    assert lead_row.read_at is None
    assert client.post("/api/v1/notifications/read", json={"all": True}).get_json()["payload"] == {"updated": 0}


def test_mark_read_validation_lists_every_bad_field(client, org, users, api_login):
    api_login(users["member"])
    both_bad = client.post("/api/v1/notifications/read", json={"ids": "not-a-list", "all": "maybe"})
    assert both_bad.status_code == 400 and both_bad.get_json()["code"] == "validation"
    assert set(both_bad.get_json()["errors"]) == {"ids", "all"}
    bad_item = client.post("/api/v1/notifications/read", json={"ids": ["nope"]})
    assert bad_item.status_code == 400 and set(bad_item.get_json()["errors"]) == {"ids"}
    empty = client.post("/api/v1/notifications/read", json={})
    assert empty.status_code == 400 and set(empty.get_json()["errors"]) == {"ids"}
    empty_list = client.post("/api/v1/notifications/read", json={"ids": [], "all": False})
    assert empty_list.status_code == 400 and set(empty_list.get_json()["errors"]) == {"ids"}
    form = client.post("/api/v1/notifications/read", data={"all": "true"})
    assert form.status_code == 415 and form.get_json()["code"] == "json_required"


def test_notifications_require_permission(client, org, users, api_login):
    anonymous = client.get("/api/v1/notifications")
    assert anonymous.status_code == 401 and anonymous.get_json()["code"] == "login_required"
    guest = make_user("Gus Guest", "gus@uiowa.edu", ops_role="sponsor_guest", org=org)
    assert not policy.load_context(guest, org).has("notification.read")
    api_login(guest)
    denied = client.get("/api/v1/notifications")
    assert denied.status_code == 403 and denied.get_json()["permission"] == ["notification.read"]
    denied_post = client.post("/api/v1/notifications/read", json={"all": True})
    assert denied_post.status_code == 403
    # every ordinary member holds notification.read
    requester = make_user("Rae Requester", "rae@uiowa.edu", ops_role="requester", org=org)
    api_login(requester)
    assert client.get("/api/v1/notifications").status_code == 200


def test_other_organizations_notifications_are_invisible_and_untouchable(client, org, users, ctx_admin, api_login):
    _seed_notifications(ctx_admin, org, users, count=1)
    other = Organization(name="Other", slug="other")
    _db.session.add(other)
    _db.session.flush()
    foreign = Notification(organization_id=other.id, user_id=users["member"].id, type="system", title="Foreign")
    _db.session.add(foreign)
    _db.session.commit()

    api_login(users["member"])
    payload = client.get("/api/v1/notifications").get_json()["payload"]
    assert payload["total"] == 1 and payload["unread_count"] == 1
    assert [item["title"] for item in payload["items"]] == ["Assigned #1"]
    response = client.post("/api/v1/notifications/read", json={"ids": [str(foreign.id)]})
    assert response.status_code == 200 and response.get_json()["payload"] == {"updated": 0}
    _db.session.expire_all()
    assert foreign.read_at is None
    assert client.post("/api/v1/notifications/read", json={"all": True}).get_json()["payload"] == {"updated": 1}
    _db.session.expire_all()
    assert foreign.read_at is None
