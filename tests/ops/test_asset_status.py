from datetime import timedelta

import pytest

from asme import events
from asme.extensions import db as _db
from asme.ops import policy
from asme.ops.models import Asset, AssetStatusHistory, AuditEvent, Notification, OpsProject, Organization, ProjectMember, Team, TeamMember, WorkOrder
from asme.ops.services import assets as asset_service
from asme.ops.types import utcnow
from asme.ops.validation import ValidationErrors
from asme.services.errors import Forbidden, NotFound
from tests.ops.conftest import make_user

HISTORY_KEYS = {"id", "from_status", "to_status", "downtime_type", "downtime_reason", "note", "started_at", "ended_at", "changed_by", "work_order_id"}


def _asset(org, name, **kw):
    row = Asset(organization_id=org.id, name=name, **kw)
    _db.session.add(row)
    _db.session.commit()
    return row


def _team(org, name, lead=None, members=()):
    team = Team(organization_id=org.id, name=name)
    _db.session.add(team)
    _db.session.flush()
    if lead is not None:
        team.members.append(TeamMember(user_id=lead.id, is_lead=True))
    for user in members:
        team.members.append(TeamMember(user_id=user.id))
    _db.session.commit()
    return team


def _project(org, name, code, **kw):
    row = OpsProject(organization_id=org.id, name=name, code=code, **kw)
    _db.session.add(row)
    _db.session.commit()
    return row


def _events_named(captured, name):
    return [payload for event_name, payload in captured if event_name == name]


# --------------------------------------------------------------------------- change_status (service contract)


def test_change_status_closes_previous_row_and_audits(ctx_admin, org, users, captured_events):
    asset = _asset(org, "Bandsaw")
    before = utcnow() - timedelta(seconds=1)
    first = asset_service.change_status(ctx_admin, asset, "offline_planned", downtime_reason="Blade change", note="Back tomorrow")
    assert first.from_status == "online" and first.to_status == "offline_planned"
    assert first.downtime_type == "planned" and first.downtime_reason == "Blade change" and first.note == "Back tomorrow"
    assert first.ended_at is None and first.started_at >= before
    assert first.changed_by_user_id == users["admin"].id and first.work_order_id is None
    assert asset.status == "offline_planned" and asset.updated_by_user_id == users["admin"].id

    second = asset_service.change_status(ctx_admin, asset, "online")
    _db.session.refresh(first)
    assert first.ended_at is not None and first.ended_at >= first.started_at
    assert second.from_status == "offline_planned" and second.to_status == "online" and second.downtime_type is None
    assert AssetStatusHistory.query.filter_by(asset_id=asset.id).filter(AssetStatusHistory.ended_at.is_(None)).count() == 1

    audits = AuditEvent.query.filter_by(event_type="asset.status_changed", entity_id=str(asset.id)).order_by(AuditEvent.occurred_at).all()
    assert len(audits) == 2
    assert audits[0].before_json == {"status": "online"}
    assert audits[0].after_json == {"status": "offline_planned", "downtime_type": "planned", "downtime_reason": "Blade change"}
    assert audits[0].summary == "Bandsaw: online -> offline_planned" and audits[0].actor_user_id == users["admin"].id
    assert audits[0].metadata_json == {"work_order_id": None}

    emitted = _events_named(captured_events, events.ASSET_STATUS_CHANGED)
    assert emitted == [
        {"asset_id": str(asset.id), "organization_id": str(org.id), "status": "offline_planned", "previous": "online"},
        {"asset_id": str(asset.id), "organization_id": str(org.id), "status": "online", "previous": "offline_planned"},
    ]


def test_change_status_emits_only_after_commit(ctx_admin, org):
    asset = _asset(org, "Charger")
    seen = []

    def _handler(name, **payload):
        # if the write had not been committed yet, this rollback would discard it
        _db.session.rollback()
        seen.append(payload["status"])

    events.subscribe(events.ASSET_STATUS_CHANGED, _handler)
    try:
        asset_service.change_status(ctx_admin, asset, "do_not_track")
    finally:
        events.unsubscribe(events.ASSET_STATUS_CHANGED, _handler)
    assert seen == ["do_not_track"]
    _db.session.expire_all()
    assert _db.session.get(Asset, asset.id).status == "do_not_track"
    assert AssetStatusHistory.query.filter_by(asset_id=asset.id, to_status="do_not_track").count() == 1


def test_change_status_without_commit_defers_commit_and_emit(ctx_admin, org, captured_events):
    asset = _asset(org, "Power Supply")
    work_order = WorkOrder(organization_id=org.id, number=41, title="Repair PSU", status="in_progress")
    _db.session.add(work_order)
    _db.session.flush()
    history = asset_service.change_status(ctx_admin, asset, "offline_unplanned", work_order=work_order, commit=False)
    assert history.work_order_id == work_order.id
    assert _events_named(captured_events, events.ASSET_STATUS_CHANGED) == []
    audit = AuditEvent.query.filter_by(event_type="asset.status_changed", entity_id=str(asset.id)).one()
    assert audit.metadata_json == {"work_order_id": str(work_order.id)}
    _db.session.rollback()
    _db.session.expire_all()
    assert _db.session.get(Asset, asset.id).status == "online"
    assert AssetStatusHistory.query.filter_by(asset_id=asset.id).count() == 0


def test_offline_notifies_owner_team_leads_and_project_lead_once(ctx_admin, org, users):
    project_lead = make_user("Pat Lead", "pat@uiowa.edu", ops_role="project_lead", org=org)
    other_lead = make_user("Tia Lead", "tia@uiowa.edu", ops_role="team_lead", org=org)
    project = _project(org, "Rover", "CCR", lead_user_id=project_lead.id)
    team = _team(org, "Robotic Arm", lead=users["lead"], members=[users["member"]])
    team.members.append(TeamMember(user_id=other_lead.id, is_lead=True))
    _db.session.commit()
    asset = _asset(org, "Arm Controller", owner_user_id=users["member"].id, responsible_team_id=team.id, project_id=project.id)

    asset_service.change_status(ctx_admin, asset, "offline_unplanned", downtime_reason="Smoke")
    rows = Notification.query.filter_by(organization_id=org.id, type="asset.offline").all()
    assert sorted(row.user_id for row in rows) == sorted([users["member"].id, users["lead"].id, other_lead.id, project_lead.id])
    sample = rows[0]
    assert sample.title == "Arm Controller is offline (unplanned)" and sample.body == "Smoke"
    assert sample.entity_type == "asset" and sample.entity_id == str(asset.id) and sample.read_at is None

    # already offline: switching between offline states does not re-notify
    asset_service.change_status(ctx_admin, asset, "offline_planned", downtime_reason="Awaiting part")
    assert Notification.query.filter_by(organization_id=org.id, type="asset.offline").count() == 4

    # going online then offline again the same day is deduplicated per day
    asset_service.change_status(ctx_admin, asset, "online")
    asset_service.change_status(ctx_admin, asset, "offline_unplanned")
    assert Notification.query.filter_by(organization_id=org.id, type="asset.offline").count() == 4

    # the actor is never notified about their own change
    ctx_owner = policy.load_context(users["member"], org)
    solo = _asset(org, "Solo Bench", owner_user_id=users["member"].id)
    safety = make_user("Sam Safety", "sam@uiowa.edu", ops_role="safety_officer", org=org)
    ctx_safety = policy.load_context(safety, org)
    asset_service.change_status(ctx_safety, solo, "offline_planned")
    assert Notification.query.filter_by(user_id=users["member"].id, entity_id=str(solo.id)).count() == 1
    assert ctx_owner.has("asset.read")
    with pytest.raises(Forbidden):
        asset_service.change_status(ctx_owner, solo, "online")


def test_change_status_validation(ctx_admin, org):
    asset = _asset(org, "Oscilloscope")
    with pytest.raises(ValidationErrors) as bad_status:
        asset_service.change_status(ctx_admin, asset, "broken")
    assert set(bad_status.value.errors) == {"status"}
    with pytest.raises(ValidationErrors) as bad_downtime:
        asset_service.change_status(ctx_admin, asset, "offline_unplanned", downtime_type="weekend")
    assert bad_downtime.value.errors == {"downtime_type": "Choose planned or unplanned."}
    _db.session.rollback()
    _db.session.expire_all()
    assert _db.session.get(Asset, asset.id).status == "online"
    assert AssetStatusHistory.query.filter_by(asset_id=asset.id).count() == 0

    # an empty downtime_type falls back to the status default
    fallback = asset_service.change_status(ctx_admin, asset, "offline_planned", downtime_type="")
    assert fallback.downtime_type == "planned"
    # a non-offline status ignores downtime_type but keeps the free-text reason
    row = asset_service.change_status(ctx_admin, asset, "retired", downtime_type="planned", downtime_reason="n/a")
    assert row.downtime_type is None and row.downtime_reason == "n/a"


def test_change_status_permissions(org, users, ctx_member):
    asset = _asset(org, "Drill Press")
    with pytest.raises(Forbidden) as denied:
        asset_service.change_status(ctx_member, asset, "offline_planned")
    assert denied.value.extra["permission"] == "asset.status.update"

    safety = make_user("Sam Safety", "sam@uiowa.edu", ops_role="safety_officer", org=org)
    ctx_safety = policy.load_context(safety, org)
    assert asset_service.change_status(ctx_safety, asset, "offline_planned").to_status == "offline_planned"

    lead = make_user("Pat Lead", "pat@uiowa.edu", ops_role="project_lead", org=org)
    mine = _project(org, "Rover", "CCR", lead_user_id=lead.id)
    mine.members.append(ProjectMember(user_id=lead.id, project_role="lead"))
    theirs = _project(org, "Showcase", "FES")
    _db.session.commit()
    ctx_lead = policy.load_context(lead, org)
    owned = _asset(org, "Rover Chassis", project_id=mine.id)
    unowned = _asset(org, "Booth", project_id=theirs.id)
    assert asset_service.change_status(ctx_lead, owned, "offline_unplanned").to_status == "offline_unplanned"
    with pytest.raises(Forbidden):
        asset_service.change_status(ctx_lead, unowned, "offline_unplanned")
    with pytest.raises(Forbidden):
        asset_service.change_status(ctx_lead, asset, "online")

    other = Organization(name="Other", slug="other")
    _db.session.add(other)
    _db.session.flush()
    foreign = Asset(organization_id=other.id, name="Foreign")
    _db.session.add(foreign)
    _db.session.commit()
    ctx_admin = policy.load_context(users["admin"], org)
    with pytest.raises(NotFound):
        asset_service.change_status(ctx_admin, foreign, "retired")


# --------------------------------------------------------------------------- POST /assets/:id/status


def test_status_endpoint_roundtrip(client, org, users, api_login, captured_events):
    api_login(users["admin"])
    asset = _asset(org, "Soldering Station", code="SS-1")
    response = client.post(
        f"/api/v1/assets/{asset.id}/status",
        json={"status": "offline_unplanned", "downtime_reason": "Tip burned out", "note": "Ordered a replacement"},
    )
    assert response.status_code == 200, response.get_json()
    payload = response.get_json()["payload"]
    assert set(payload) == {"asset", "history"}
    assert payload["asset"]["id"] == str(asset.id) and payload["asset"]["status"] == "offline_unplanned"
    history = payload["history"]
    assert set(history) == HISTORY_KEYS
    assert history["from_status"] == "online" and history["to_status"] == "offline_unplanned"
    assert history["downtime_type"] == "unplanned" and history["downtime_reason"] == "Tip burned out"
    assert history["note"] == "Ordered a replacement" and history["ended_at"] is None and history["work_order_id"] is None
    assert history["changed_by"]["id"] == users["admin"].id and history["started_at"].endswith("Z")
    assert _events_named(captured_events, events.ASSET_STATUS_CHANGED)[-1]["status"] == "offline_unplanned"

    back = client.post(f"/api/v1/assets/{asset.id}/status", json={"status": "online"})
    assert back.status_code == 200
    assert back.get_json()["payload"]["history"]["from_status"] == "offline_unplanned"
    rows = AssetStatusHistory.query.filter_by(asset_id=asset.id).order_by(AssetStatusHistory.started_at).all()
    assert rows[0].ended_at is not None and rows[1].ended_at is None

    explicit = client.post(f"/api/v1/assets/{asset.id}/status", json={"status": "offline_planned", "downtime_type": "unplanned"})
    assert explicit.status_code == 200 and explicit.get_json()["payload"]["history"]["downtime_type"] == "unplanned"


def test_status_endpoint_validation_permissions_and_visibility(client, org, users, api_login):
    api_login(users["admin"])
    asset = _asset(org, "Lathe")
    missing = client.post(f"/api/v1/assets/{asset.id}/status", json={})
    assert missing.status_code == 400 and set(missing.get_json()["errors"]) == {"status"}
    bad = client.post(f"/api/v1/assets/{asset.id}/status", json={"status": "broken", "downtime_type": "weekend", "downtime_reason": "x" * 161})
    assert bad.status_code == 400 and set(bad.get_json()["errors"]) == {"status", "downtime_type", "downtime_reason"}
    assert AssetStatusHistory.query.filter_by(asset_id=asset.id).count() == 0

    api_login(users["member"])  # full_member: neither asset.status.update nor asset.manage
    denied = client.post(f"/api/v1/assets/{asset.id}/status", json={"status": "retired"})
    assert denied.status_code == 403 and denied.get_json()["permission"] == ["asset.status.update", "asset.manage"]

    safety = make_user("Sam Safety", "sam@uiowa.edu", ops_role="safety_officer", org=org)
    api_login(safety)
    allowed = client.post(f"/api/v1/assets/{asset.id}/status", json={"status": "offline_planned"})
    assert allowed.status_code == 200 and allowed.get_json()["payload"]["asset"]["status"] == "offline_planned"

    secret = _project(org, "Bid", "BID", visibility="private")
    hidden = _asset(org, "Secret Rig", project_id=secret.id)
    assert client.post(f"/api/v1/assets/{hidden.id}/status", json={"status": "retired"}).status_code == 404
    _db.session.refresh(hidden)
    assert hidden.status == "online"
