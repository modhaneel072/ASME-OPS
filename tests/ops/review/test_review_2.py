"""Review reproducer: PATCH /work-orders/:id must enforce ``work_order.assign``
when the payload touches assignees, assignee teams, watchers or the team.

A full_member holds ``work_order.edit`` @own but never ``work_order.assign``.
PUT /assignees and PUT /watchers already refuse them; PATCH on their own work
order must refuse the same fields the same way instead of applying them."""

from __future__ import annotations

from asme.ops.models import Notification
from tests.ops.conftest import make_user
from tests.ops.test_work_orders_api import _team


def _permission(response) -> set[str]:
    """Route decorators report a list, the service reports a string; compare as a set."""
    value = response.get_json()["permission"]
    return set(value) if isinstance(value, list) else {value}


def test_patch_requires_assign_permission_for_assignment_fields(client, org, users, api_login):
    team = _team(org, "Electrical", lead=users["lead"], members=[users["member"]])
    victim = make_user("Vic Victim", "vic@uiowa.edu", org=org)

    api_login(users["member"])  # full_member: edit@own, no work_order.assign
    created = client.post("/api/v1/work-orders", json={"title": "Mine"})
    assert created.status_code == 201, created.get_json()
    wo_id = created.get_json()["payload"]["work_order"]["id"]

    # sanity: the dedicated endpoints already enforce the assign key
    denied = client.put(f"/api/v1/work-orders/{wo_id}/assignees", json={"user_ids": [victim.id]})
    assert denied.status_code == 403 and _permission(denied) == {"work_order.assign"}
    Notification.query.delete()

    # desired behaviour: PATCH with any assignment-governed field is refused the same way
    for payload in (
        {"assignee_user_ids": [victim.id]},
        {"assignee_team_ids": [str(team.id)]},
        {"watcher_user_ids": [victim.id]},
        {"team_id": str(team.id)},
    ):
        response = client.patch(f"/api/v1/work-orders/{wo_id}", json=payload)
        assert response.status_code == 403, (payload, response.status_code, response.get_json())
        assert _permission(response) == {"work_order.assign"}, (payload, response.get_json())

    detail = client.get(f"/api/v1/work-orders/{wo_id}").get_json()["payload"]["work_order"]
    assert detail["assignees"] == []
    assert detail["assignee_teams"] == []
    assert detail["watchers"] == []
    assert detail["team"] is None
    assert Notification.query.filter_by(type="work_order.assigned").count() == 0
