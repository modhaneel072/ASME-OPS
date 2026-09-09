"""Review claim 3: GET /projects/:id/activity must not leak work-order audit
snapshots to users who cannot read those work orders.

A ``requester`` holds ``project.read`` only (no ``work_order.read_*``); a
``shop_operator`` holds ``work_order.read_assigned``. Neither may read a work
order they are not assigned to, so the project activity feed must not surface
``work_order`` events (with ``before``/``after`` snapshots) for those work orders.
"""

from __future__ import annotations

from tests.ops.conftest import make_user
from tests.ops.test_work_orders_api import _create, _project

SECRET = "CONFIDENTIAL: sponsor NDA terms and budget notes"


def test_project_activity_hides_work_order_events_the_user_cannot_read(client, org, users, requester, ctx_admin, api_login):
    project = _project(org, "Crater Cruncher Rover", "CCR")
    wo = _create(ctx_admin, title="Secret work", description=SECRET, project_id=str(project.id))

    # --- requester: project.read only -----------------------------------------
    api_login(requester)
    assert client.get(f"/api/v1/work-orders/{wo.id}").status_code == 403

    response = client.get(f"/api/v1/projects/{project.id}/activity")
    assert response.status_code == 200, response.get_json()
    events = response.get_json()["payload"]["items"]
    leaked = [e for e in events if e["entity_type"] == "work_order"]
    assert leaked == [], f"requester sees work-order audit events: {leaked}"
    assert SECRET not in response.get_data(as_text=True)

    # --- shop operator: work_order.read_assigned, not assigned to this WO -----
    operator = make_user("Sam Shop", "sam@uiowa.edu", ops_role="shop_operator", org=org)
    api_login(operator)
    assert client.get(f"/api/v1/work-orders/{wo.id}").status_code == 404

    response = client.get(f"/api/v1/projects/{project.id}/activity")
    assert response.status_code == 200, response.get_json()
    events = response.get_json()["payload"]["items"]
    leaked = [e for e in events if e["entity_type"] == "work_order"]
    assert leaked == [], f"shop operator sees unassigned work-order audit events: {leaked}"
    assert SECRET not in response.get_data(as_text=True)
