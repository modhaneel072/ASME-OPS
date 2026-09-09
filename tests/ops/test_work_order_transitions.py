"""Work-order status transitions: the table, side effects, completion,
parent auto-complete and blocking."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest

from asme.extensions import db as _db
from asme.ops.models import AssetStatusHistory, AuditEvent, Notification, WorkOrder, WorkOrderDependency
from asme.ops.services import work_orders
from asme.ops.types import utcnow
from asme.ops.validation import ValidationErrors
from asme.services.errors import Conflict, Forbidden
from tests.ops.test_work_orders_api import _asset, _audit, _category, _create, _iso, _location, _project, _team


def _set_status(wo, status):
    wo.status = status
    _db.session.commit()
    return wo


def _history(wo):
    return [(h.from_status, h.to_status, h.note) for h in wo.status_history]


# --------------------------------------------------------------------------- table


@pytest.mark.parametrize(
    "action,from_status,to_status",
    [
        ("start", "open", "in_progress"),
        ("hold", "in_progress", "on_hold"),
        ("resume", "on_hold", "in_progress"),
        ("complete", "open", "done"),
        ("complete", "in_progress", "done"),
        ("cancel", "open", "canceled"),
        ("cancel", "in_progress", "canceled"),
        ("cancel", "on_hold", "canceled"),
        ("reopen", "done", "open"),
        ("reopen", "canceled", "open"),
    ],
)
def test_valid_transitions(ctx_admin, org, action, from_status, to_status):
    wo = _set_status(_create(ctx_admin, title=f"{action} from {from_status}"), from_status)
    work_orders.transition(ctx_admin, wo, action, note="because")
    assert wo.status == to_status
    assert _history(wo)[-1] == (from_status, to_status, "because")


@pytest.mark.parametrize(
    "action,from_status",
    [
        ("start", "draft"),
        ("start", "in_progress"),
        ("start", "done"),
        ("hold", "open"),
        ("resume", "open"),
        ("resume", "in_progress"),
        ("complete", "on_hold"),
        ("complete", "done"),
        ("complete", "draft"),
        ("cancel", "done"),
        ("cancel", "draft"),
        ("reopen", "open"),
        ("reopen", "in_progress"),
    ],
)
def test_invalid_transitions_conflict(ctx_admin, org, action, from_status):
    wo = _set_status(_create(ctx_admin, title="invalid"), from_status)
    with pytest.raises(Conflict) as excinfo:
        work_orders.transition(ctx_admin, wo, action, note="x")
    assert excinfo.value.code == "invalid_transition"
    assert excinfo.value.extra == {"from": from_status, "action": action}
    assert wo.status == from_status and len(wo.status_history) == 1


def test_invalid_transition_via_api_is_409(client, org, users, api_login):
    api_login(users["admin"])
    wo = client.post("/api/v1/work-orders", json={"title": "Hold me"}).get_json()["payload"]["work_order"]
    response = client.post(f"/api/v1/work-orders/{wo['id']}/hold", json={})
    assert response.status_code == 409
    body = response.get_json()
    assert body["code"] == "invalid_transition" and body["from"] == "open" and body["action"] == "hold"


def test_unknown_action_is_rejected(ctx_admin, org):
    wo = _create(ctx_admin)
    from asme.services.errors import Validation

    with pytest.raises(Validation):
        work_orders.transition(ctx_admin, wo, "teleport")


# --------------------------------------------------------------------------- side effects


def test_start_sets_start_at_history_audit_notifications_and_event(ctx_admin, org, users, captured_events):
    team = _team(org, "Arm", lead=users["lead"])
    wo = _create(ctx_admin, title="Start me", assignee_user_ids=[users["member"].id], assignee_team_ids=[str(team.id)])
    Notification.query.delete()
    _db.session.commit()
    assert wo.start_at is None

    work_orders.transition(ctx_admin, wo, "start")
    assert wo.status == "in_progress" and wo.start_at is not None
    assert wo.start_at <= utcnow()
    assert _history(wo) == [(None, "open", None), ("open", "in_progress", None)]

    events = _audit("work_order.status_changed", wo.id)
    assert len(events) == 1
    assert events[0].before_json == {"status": "open"} and events[0].after_json == {"status": "in_progress"}
    assert events[0].metadata_json["action"] == "start"

    notified = Notification.query.filter_by(type="work_order.status_changed").all()
    # direct assignee + team member (lead of Arm); the actor (creator) is excluded
    assert {n.user_id for n in notified} == {users["member"].id, users["lead"].id}
    assert notified[0].title == f"#{wo.number} Start me is now in progress"

    status_events = [p for name, p in captured_events if name == "ops.work_order.status_changed"]
    assert status_events == [{"work_order_id": str(wo.id), "organization_id": str(org.id), "status": "in_progress", "previous": "open"}]


def test_start_keeps_existing_start_at(ctx_admin, org):
    planned = utcnow() - timedelta(days=1)
    wo = _create(ctx_admin, start_at=_iso(planned))
    work_orders.transition(ctx_admin, wo, "start")
    assert abs((wo.start_at - planned).total_seconds()) < 1


def test_cancel_requires_note_and_sets_canceled_at(client, org, users, api_login):
    api_login(users["admin"])
    wo = client.post("/api/v1/work-orders", json={"title": "Cancel me"}).get_json()["payload"]["work_order"]
    for body in ({}, {"note": ""}, {"note": "   "}):
        response = client.post(f"/api/v1/work-orders/{wo['id']}/cancel", json=body)
        assert response.status_code == 400 and set(response.get_json()["errors"]) == {"note"}
    canceled = client.post(f"/api/v1/work-orders/{wo['id']}/cancel", json={"note": "Duplicate of #2"})
    assert canceled.status_code == 200
    body = canceled.get_json()["payload"]["work_order"]
    assert body["status"] == "canceled" and body["canceled_at"] is not None and body["completed_at"] is None
    assert body["status_history"][-1]["note"] == "Duplicate of #2"

    reopened = client.post(f"/api/v1/work-orders/{wo['id']}/reopen", json={})
    assert reopened.status_code == 200
    body = reopened.get_json()["payload"]["work_order"]
    assert body["status"] == "open" and body["canceled_at"] is None and body["completed_at"] is None


def test_creator_is_notified_when_someone_else_changes_status(org, users):
    from asme.ops import policy

    ctx_member = policy.load_context(users["member"], org)
    ctx_admin = policy.load_context(users["admin"], org)
    wo = _create(ctx_member, title="Mine", watcher_user_ids=[users["lead"].id])
    Notification.query.delete()
    _db.session.commit()
    work_orders.transition(ctx_admin, wo, "cancel", note="Not needed")
    recipients = {n.user_id for n in Notification.query.filter_by(type="work_order.status_changed").all()}
    assert recipients == {users["member"].id, users["lead"].id}
    assert Notification.query.filter_by(user_id=users["member"].id).one().body == "Not needed"


# --------------------------------------------------------------------------- complete


def test_complete_with_time_cost_asset_status_and_follow_up(client, org, users, api_login, captured_events):
    project = _project(org, "Rover", "CCR")
    team = _team(org, "Arm", lead=users["lead"])
    location = _location(org, "Lab")
    asset = _asset(org, "Robotic Arm", project=project)
    api_login(users["admin"])
    wo = client.post(
        "/api/v1/work-orders",
        json={
            "title": "Replace gear",
            "project_id": str(project.id),
            "location_id": str(location.id),
            "primary_asset_id": str(asset.id),
            "team_id": str(team.id),
            "priority": "high",
            "work_type": "reactive",
        },
    ).get_json()["payload"]["work_order"]
    assert client.post(f"/api/v1/work-orders/{wo['id']}/start", json={}).status_code == 200

    response = client.post(
        f"/api/v1/work-orders/{wo['id']}/complete",
        json={
            "note": "Gear replaced and tested.",
            "time_entries": [{"minutes": 40, "note": "swap"}, {"minutes": 20, "user_id": users["member"].id}],
            "cost_entries": [{"type": "parts", "amount": "18.99", "description": "gear"}, {"type": "labor", "amount": 0}],
            "asset_status": {"status": "offline_unplanned", "downtime_reason": "Awaiting calibration", "note": "recheck"},
            "follow_up": {"title": "Calibrate arm", "description": "Run the calibration routine.", "priority": "medium", "work_type": "inspection"},
        },
    )
    assert response.status_code == 200, response.get_json()
    payload = response.get_json()["payload"]
    body = payload["work_order"]
    assert body["status"] == "done" and body["completed_at"] is not None
    assert body["completion_note"] == "Gear replaced and tested."
    assert body["actual_minutes"] == 60
    assert sorted(e["minutes"] for e in body["time_entries"]) == [20, 40]
    assert {e["user"]["id"] for e in body["time_entries"]} == {users["admin"].id, users["member"].id}
    assert sorted(c["amount"] for c in body["cost_entries"]) == [0.0, 18.99]
    assert body["status_history"][-1]["note"] == "Gear replaced and tested."
    assert body["asset"]["status"] == "offline_unplanned"

    follow_up = payload["follow_up"]
    assert follow_up is not None and follow_up["status"] == "open" and follow_up["number"] == wo["number"] + 1
    assert follow_up["title"] == "Calibrate arm" and follow_up["priority"] == "medium" and follow_up["work_type"] == "inspection"
    assert follow_up["description"].startswith(f"Follow-up to #{wo['number']}")
    assert "Run the calibration routine." in follow_up["description"]
    for key in ("project", "location", "asset", "team"):
        assert follow_up[key]["id"] == body[key]["id"], key
    assert WorkOrderDependency.query.count() == 0
    created = _audit("work_order.created", follow_up["id"])
    assert created[0].metadata_json == {"follow_up_of": wo["id"]}
    status_changed = _audit("work_order.status_changed", wo["id"])
    assert status_changed[-1].metadata_json["follow_up_id"] == follow_up["id"]

    asset_row = _db.session.get(type(asset), asset.id)
    assert asset_row.status == "offline_unplanned"
    history = AssetStatusHistory.query.filter_by(asset_id=asset.id).order_by(AssetStatusHistory.started_at).all()
    assert history[-1].to_status == "offline_unplanned" and str(history[-1].work_order_id) == wo["id"]
    assert history[-1].downtime_reason == "Awaiting calibration"

    names = [name for name, _ in captured_events]
    assert names.count("ops.work_order.status_changed") >= 2  # start + complete
    assert "ops.asset.status_changed" in names and "ops.work_order.created" in names
    asset_event = [p for name, p in captured_events if name == "ops.asset.status_changed"][-1]
    assert asset_event["asset_id"] == str(asset.id) and asset_event["status"] == "offline_unplanned"
    assert len(_audit("work_order.time_logged", wo["id"])) == 2 and len(_audit("work_order.cost_added", wo["id"])) == 2


def test_complete_reports_every_nested_error(client, org, users, api_login):
    api_login(users["admin"])
    wo = client.post("/api/v1/work-orders", json={"title": "No asset"}).get_json()["payload"]["work_order"]
    response = client.post(
        f"/api/v1/work-orders/{wo['id']}/complete",
        json={
            "time_entries": [{"minutes": 0}, {"user_id": 999999, "minutes": 5}],
            "cost_entries": [{"type": "gold", "amount": "abc"}],
            "asset_status": {"status": "offline_planned"},
            "follow_up": {"description": "no title"},
        },
    )
    assert response.status_code == 400
    errors = response.get_json()["errors"]
    assert set(errors) == {
        "time_entries[0].minutes",
        "time_entries[1].user_id",
        "cost_entries[0].type",
        "cost_entries[0].amount",
        "asset_status",
        "follow_up.title",
    }
    assert errors["asset_status"] == "This work order has no primary asset."
    assert _db.session.get(WorkOrder, uuid.UUID(wo["id"])).status == "open"

    shapes = client.post(f"/api/v1/work-orders/{wo['id']}/complete", json={"time_entries": "lots", "cost_entries": [1], "asset_status": "x"})
    assert shapes.status_code == 400 and set(shapes.get_json()["errors"]) == {"time_entries", "cost_entries", "asset_status"}

    invalid_asset_status = client.post("/api/v1/work-orders", json={"title": "With asset", "primary_asset_id": str(_asset(org, "Drill").id)})
    with_asset = invalid_asset_status.get_json()["payload"]["work_order"]
    bad_status = client.post(f"/api/v1/work-orders/{with_asset['id']}/complete", json={"asset_status": {"status": "exploded"}})
    assert bad_status.status_code == 400 and set(bad_status.get_json()["errors"]) == {"asset_status.status"}
    assert _db.session.get(WorkOrder, uuid.UUID(with_asset["id"])).status == "open"


def test_complete_without_extras_and_service_return_shape(ctx_admin, org):
    wo = _create(ctx_admin, title="Plain")
    result = work_orders.complete(ctx_admin, wo)
    assert result == {"work_order": wo, "follow_up": None}
    assert wo.status == "done" and wo.completed_at is not None and wo.actual_minutes == 0
    assert wo.completion_note is None


def test_follow_up_requires_create_permission(org, users):
    from asme.ops import policy
    from tests.ops.conftest import make_user

    operator = make_user("Op Erator", "op@uiowa.edu", ops_role="shop_operator", org=org)
    ctx_admin = policy.load_context(users["admin"], org)
    wo = _create(ctx_admin, title="Assigned to operator", assignee_user_ids=[operator.id])
    ctx_op = policy.load_context(operator, org)
    with pytest.raises(Forbidden):
        work_orders.complete(ctx_op, wo, follow_up={"title": "Not allowed"})
    assert _db.session.get(WorkOrder, wo.id).status == "open"
    work_orders.complete(ctx_op, wo)
    assert wo.status == "done"


def test_follow_up_inherits_critical_priority_rule(org, users):
    from asme.ops import policy

    safety = _category(org, "Safety")
    ctx_admin = policy.load_context(users["admin"], org)
    ctx_member = policy.load_context(users["member"], org)
    wo = _create(ctx_admin, title="Critical", priority="critical", category_ids=[str(safety.id)], assignee_user_ids=[users["member"].id])
    with pytest.raises(ValidationErrors) as excinfo:
        work_orders.complete(ctx_member, wo, follow_up={"title": "Also critical"})
    assert set(excinfo.value.errors) == {"follow_up.priority"}
    result = work_orders.complete(ctx_member, wo, follow_up={"title": "Downgraded", "priority": "high"})
    assert result["follow_up"].priority == "high" and wo.status == "done"


# --------------------------------------------------------------------------- reopen / actual minutes


def test_reopen_clears_timestamps_and_complete_recomputes_actual_minutes(ctx_admin, org):
    wo = _create(ctx_admin, title="Reopen me")
    work_orders.add_time_entry(ctx_admin, wo, {"minutes": 15})
    work_orders.transition(ctx_admin, wo, "complete", note="first pass")
    assert wo.completed_at is not None and wo.actual_minutes == 15
    work_orders.transition(ctx_admin, wo, "reopen")
    assert wo.status == "open" and wo.completed_at is None and wo.canceled_at is None
    work_orders.add_time_entry(ctx_admin, wo, {"minutes": 5})
    work_orders.transition(ctx_admin, wo, "complete")
    assert wo.actual_minutes == 20
    assert [h.to_status for h in wo.status_history] == ["open", "done", "open", "done"]


# --------------------------------------------------------------------------- parent auto-complete


def test_parent_auto_completes_when_all_children_close(ctx_admin, org, users, captured_events):
    parent = _create(ctx_admin, title="Parent", parent_completion_policy="auto")
    first = _create(ctx_admin, title="Child 1", parent_id=str(parent.id))
    second = _create(ctx_admin, title="Child 2", parent_id=str(parent.id))
    third = _create(ctx_admin, title="Child 3", parent_id=str(parent.id))

    work_orders.transition(ctx_admin, first, "complete")
    assert parent.status == "open"
    work_orders.transition(ctx_admin, second, "cancel", note="not needed")
    assert parent.status == "open"
    work_orders.transition(ctx_admin, third, "complete")
    assert parent.status == "done" and parent.completed_at is not None
    assert _history(parent)[-1] == ("open", "done", "All sub-work orders completed")
    auto = _audit("work_order.status_changed", parent.id)
    assert len(auto) == 1 and auto[0].metadata_json["auto"] is True
    statuses = [(p["work_order_id"], p["status"]) for name, p in captured_events if name == "ops.work_order.status_changed"]
    assert (str(parent.id), "done") in statuses

    from asme.ops.serializers.work_orders import work_order

    assert work_order(parent)["sub_work_orders"] == {"total": 3, "done": 2}


def test_parent_auto_complete_cascades_and_respects_policy_and_state(ctx_admin, org):
    grand = _create(ctx_admin, title="Grand", parent_completion_policy="auto")
    parent = _create(ctx_admin, title="Parent", parent_id=str(grand.id), parent_completion_policy="auto")
    child = _create(ctx_admin, title="Child", parent_id=str(parent.id))
    work_orders.transition(ctx_admin, child, "complete")
    assert parent.status == "done" and grand.status == "done"

    manual = _create(ctx_admin, title="Manual parent", parent_completion_policy="manual")
    manual_child = _create(ctx_admin, title="Manual child", parent_id=str(manual.id))
    work_orders.transition(ctx_admin, manual_child, "complete")
    assert manual.status == "open"

    held = _create(ctx_admin, title="Held parent", parent_completion_policy="auto")
    held_child = _create(ctx_admin, title="Held child", parent_id=str(held.id))
    work_orders.transition(ctx_admin, held, "start")
    work_orders.transition(ctx_admin, held, "hold")
    work_orders.transition(ctx_admin, held_child, "complete")
    assert held.status == "on_hold"


def test_auto_complete_does_not_need_parent_permission(org, users):
    from asme.ops import policy

    ctx_admin = policy.load_context(users["admin"], org)
    parent = _create(ctx_admin, title="Admin's parent", parent_completion_policy="auto")
    child = _create(ctx_admin, title="Member's child", parent_id=str(parent.id), assignee_user_ids=[users["member"].id])
    ctx_member = policy.load_context(users["member"], org)
    assert not policy.can(ctx_member, "work_order.complete", parent)
    work_orders.transition(ctx_member, child, "complete")
    assert child.status == "done" and parent.status == "done"


# --------------------------------------------------------------------------- blocking


def test_blocked_work_order_cannot_start_until_blockers_close(ctx_admin, org):
    blocked = _create(ctx_admin, title="Blocked")
    blocker_a = _create(ctx_admin, title="Blocker A")
    blocker_b = _create(ctx_admin, title="Blocker B")
    work_orders.add_dependency(ctx_admin, blocked, str(blocker_a.id))
    work_orders.add_dependency(ctx_admin, blocked, str(blocker_b.id))
    assert blocked.is_blocked is True

    with pytest.raises(Conflict) as excinfo:
        work_orders.transition(ctx_admin, blocked, "start")
    assert excinfo.value.code == "blocked"
    assert excinfo.value.extra["blocking"] == sorted([blocker_a.number, blocker_b.number])
    assert blocked.status == "open"

    work_orders.transition(ctx_admin, blocker_a, "complete")
    assert blocked.is_blocked is True
    work_orders.transition(ctx_admin, blocker_b, "cancel", note="dropped")
    assert blocked.is_blocked is False
    work_orders.transition(ctx_admin, blocked, "start")
    assert blocked.status == "in_progress"

    # completing a blocked work order is still allowed; blocking only guards start
    other = _create(ctx_admin, title="Other blocked")
    work_orders.add_dependency(ctx_admin, other, str(blocked.id))
    assert other.is_blocked is True
    work_orders.transition(ctx_admin, other, "complete")
    assert other.status == "done"


def test_recompute_blocked_is_pure_recalculation(ctx_admin, org):
    wo = _create(ctx_admin, title="Recompute")
    blocker = _create(ctx_admin, title="Blocker")
    work_orders.add_dependency(ctx_admin, wo, str(blocker.id))
    blocker.status = "done"
    _db.session.flush()
    assert work_orders.recompute_blocked(wo) == [] and wo.is_blocked is False
    blocker.status = "open"
    _db.session.flush()
    assert work_orders.recompute_blocked(wo) == [blocker] and wo.is_blocked is True
    _db.session.rollback()
