"""``GET /changes?since=`` – the polling change feed."""

from __future__ import annotations

from datetime import datetime, timedelta

from asme.extensions import db as _db
from asme.ops import policy
from asme.ops.models import AuditEvent, Location, Milestone, OpsProject, Organization, ProjectMember, WorkOrder
from asme.ops.services import audit_events, changes, notifications
from asme.ops.types import utcnow
from asme.ops.validation import ValidationErrors
from tests.ops.conftest import make_user

EPOCH = "2020-01-01T00:00:00Z"


def _project(org, name, code, visibility="chapter"):
    row = OpsProject(organization_id=org.id, name=name, code=code, visibility=visibility)
    _db.session.add(row)
    _db.session.flush()
    return row


def _wo(org, number, creator, **kw):
    row = WorkOrder(organization_id=org.id, number=number, title=f"WO {number}", created_by_user_id=creator.id, **kw)
    _db.session.add(row)
    _db.session.flush()
    return row


def _milestone(org, project, name):
    row = Milestone(organization_id=org.id, project_id=project.id, name=name)
    _db.session.add(row)
    _db.session.flush()
    return row


def _event(ctx, event_type, entity, occurred_at=None, **kw):
    row = audit_events.record(ctx, event_type, entity, **kw)
    if occurred_at is not None:
        row.occurred_at = occurred_at
    _db.session.flush()
    return row


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _get(client, **params):
    query = "&".join(f"{key}={value}" for key, value in params.items())
    response = client.get(f"/api/v1/changes?{query}" if query else "/api/v1/changes")
    return response


def test_since_is_required_and_validated(client, org, users, api_login):
    api_login(users["member"])
    missing = _get(client)
    assert missing.status_code == 400 and missing.get_json()["code"] == "validation"
    assert set(missing.get_json()["errors"]) == {"since"}
    garbage = _get(client, since="yesterday-ish")
    assert garbage.status_code == 400 and set(garbage.get_json()["errors"]) == {"since"}
    both = _get(client, since="nope", limit="lots")
    assert both.status_code == 400 and set(both.get_json()["errors"]) == {"since", "limit"}
    zero = _get(client, since=EPOCH, limit=0)
    assert zero.status_code == 400 and set(zero.get_json()["errors"]) == {"limit"}
    # the service applies the same rules without a request
    ctx = policy.load_context(users["member"], org)
    try:
        changes.list_changes(ctx, {})
    except ValidationErrors as exc:
        assert set(exc.errors) == {"since"}
    else:  # pragma: no cover - the assertion above must trip
        raise AssertionError("since should be required")
    # naive timestamps are read as UTC and the offset form is accepted too
    assert _get(client, since="2020-01-01T00:00:00").status_code == 200
    assert _get(client, since="2020-01-01T00:00:00%2B00:00").status_code == 200


def test_feed_lists_visible_events_oldest_first_with_hrefs(client, org, users, ctx_admin, api_login):
    project = _project(org, "Rover", "CCR")
    wo = _wo(org, 1, users["admin"], project_id=project.id)
    milestone = _milestone(org, project, "PDR")
    location = Location(organization_id=org.id, name="Shop")
    _db.session.add(location)
    _db.session.flush()
    base = utcnow() - timedelta(hours=1)
    before_since = _event(ctx_admin, "location.created", location, occurred_at=base - timedelta(days=1))
    e_project = _event(ctx_admin, "project.created", project, occurred_at=base, summary="Created Rover")
    e_wo = _event(ctx_admin, "work_order.created", wo, occurred_at=base + timedelta(minutes=1))
    e_ms = _event(ctx_admin, "milestone.created", milestone, occurred_at=base + timedelta(minutes=2))
    e_loc = _event(ctx_admin, "location.updated", location, occurred_at=base + timedelta(minutes=3), before={"name": "x"}, after={"name": "Shop"})
    notifications.notify(ctx_admin, [users["member"].id], "system", "Hi")
    _db.session.commit()

    api_login(users["member"])
    started = utcnow()
    response = _get(client, since=(base - timedelta(minutes=1)).isoformat().replace("+00:00", "Z"))
    assert response.status_code == 200, response.get_json()
    payload = response.get_json()["payload"]
    assert set(payload) == {"events", "has_more", "now", "next_since", "unread_notifications"}
    assert payload["unread_notifications"] == 1 and payload["has_more"] is False
    now = _parse(payload["now"])
    assert started - timedelta(seconds=1) <= now <= utcnow() + timedelta(seconds=1)
    assert payload["next_since"] == payload["now"]
    events = payload["events"]
    assert [event["id"] for event in events] == [str(e.id) for e in (e_project, e_wo, e_ms, e_loc)]
    assert str(before_since.id) not in {event["id"] for event in events}
    # The feed tells a client what to refetch; the audit payload is not part of
    # that, so before/after/metadata are withheld from members without audit.read.
    assert set(events[0]) == {"id", "event_type", "entity_type", "entity_id", "actor", "summary", "occurred_at", "href"}
    assert events[0]["href"] == f"/app/projects/{project.id}" and events[0]["summary"] == "Created Rover"
    assert events[0]["actor"]["id"] == users["admin"].id
    assert events[1]["href"] == f"/app/work-orders/{wo.id}" and events[1]["entity_type"] == "work_order"
    assert events[2]["href"] is None and events[2]["entity_type"] == "milestone"
    assert events[3]["href"] is None and events[3]["entity_type"] == "location"
    assert [event["occurred_at"] for event in events] == sorted(event["occurred_at"] for event in events)

    # since is exclusive: asking from the last event's timestamp yields nothing new
    caught_up = _get(client, since=events[-1]["occurred_at"]).get_json()["payload"]
    assert caught_up["events"] == [] and caught_up["has_more"] is False

    # A holder of audit.read does get the payload, so the feed stays useful to admins.
    api_login(users["admin"])
    admin_events = _get(client, since=(base - timedelta(minutes=1)).isoformat().replace("+00:00", "Z")).get_json()["payload"]["events"]
    location_event = next(event for event in admin_events if event["entity_type"] == "location")
    assert location_event["before"] == {"name": "x"} and location_event["after"] == {"name": "Shop"}
    assert "metadata" in location_event


def test_feed_hides_events_the_user_may_not_read(client, org, users, ctx_admin, api_login):
    public = _project(org, "Rover", "CCR")
    secret = _project(org, "Sponsor Bid", "BID", visibility="private")
    joined = _project(org, "Showcase", "FES", visibility="private")
    joined.members.append(ProjectMember(user_id=users["member"].id))
    _db.session.flush()
    rows = {}
    for index, (label, project) in enumerate((("public", public), ("secret", secret), ("joined", joined))):
        wo = _wo(org, index + 1, users["admin"], project_id=project.id)
        ms = _milestone(org, project, f"M-{label}")
        rows[f"project:{label}"] = _event(ctx_admin, "project.updated", project)
        rows[f"wo:{label}"] = _event(ctx_admin, "work_order.created", wo)
        rows[f"ms:{label}"] = _event(ctx_admin, "milestone.created", ms)
    orphan_wo = _wo(org, 9, users["admin"])  # no project: visible to anyone with a read key
    rows["wo:orphan"] = _event(ctx_admin, "work_order.created", orphan_wo)
    rows["org"] = _event(ctx_admin, "organization.updated", org)
    rows["dangling"] = _event(ctx_admin, "work_order.deleted", "work_order", entity_id="not-a-uuid")
    _db.session.commit()

    def visible_for(user):
        api_login(user)
        payload = _get(client, since=EPOCH).get_json()["payload"]
        ids = {event["id"] for event in payload["events"]}
        return {label for label, row in rows.items() if str(row.id) in ids}

    # full member: work_order.read_all, project.read, no project.read_private
    assert visible_for(users["member"]) == {
        "project:public", "wo:public", "ms:public",
        "project:joined", "wo:joined", "ms:joined",
        "wo:orphan", "org",
    }
    # requester: no work-order read key at all, still sees chapter-wide things
    requester = make_user("Rae Requester", "rae@uiowa.edu", ops_role="requester", org=org)
    assert visible_for(requester) == {"project:public", "ms:public", "org"}
    # faculty advisor: project.read_private + work_order.read_all -> everything except the dangling id
    advisor = make_user("Dr. Advisor", "advisor@uiowa.edu", ops_role="faculty_advisor", org=org)
    assert visible_for(advisor) == set(rows) - {"dangling"}
    # shop operator: read_assigned only -> work orders they are on, plus chapter-wide rows
    operator = make_user("Ollie Operator", "ollie@uiowa.edu", ops_role="shop_operator", org=org)
    from asme.ops.models import WorkOrderWatcher

    orphan_wo.watchers.append(WorkOrderWatcher(user_id=operator.id))
    _db.session.commit()
    assert visible_for(operator) == {"project:public", "ms:public", "org", "wo:orphan"}


def test_feed_pages_with_limit_and_next_since(client, org, users, ctx_admin, api_login):
    location = Location(organization_id=org.id, name="Shop")
    _db.session.add(location)
    _db.session.flush()
    base = utcnow() - timedelta(hours=1)
    created = [_event(ctx_admin, "location.updated", location, occurred_at=base + timedelta(seconds=i)) for i in range(5)]
    _db.session.commit()

    api_login(users["member"])
    first = _get(client, since=EPOCH, limit=2).get_json()["payload"]
    assert [e["id"] for e in first["events"]] == [str(created[0].id), str(created[1].id)]
    assert first["has_more"] is True
    assert first["next_since"] == first["events"][-1]["occurred_at"]
    assert first["next_since"] != first["now"]

    seen = [e["id"] for e in first["events"]]
    cursor = first["next_since"]
    for _ in range(5):
        page = _get(client, since=cursor, limit=2).get_json()["payload"]
        seen.extend(e["id"] for e in page["events"])
        cursor = page["next_since"]
        if not page["has_more"]:
            break
    assert seen == [str(row.id) for row in created]
    assert page["next_since"] == page["now"]

    # limit is capped at 200 rather than rejected
    capped = _get(client, since=EPOCH, limit=999)
    assert capped.status_code == 200 and len(capped.get_json()["payload"]["events"]) == 5
    assert changes.MAX_LIMIT == 200


def test_feed_scans_past_long_runs_of_invisible_events(client, org, users, ctx_admin, api_login):
    secret = _project(org, "Sponsor Bid", "BID", visibility="private")
    wo = _wo(org, 1, users["admin"], project_id=secret.id)
    base = utcnow() - timedelta(hours=2)
    hidden_count = changes.SCAN_BATCH + 25
    for index in range(hidden_count):
        _event(ctx_admin, "work_order.updated", wo, occurred_at=base + timedelta(seconds=index))
    location = Location(organization_id=org.id, name="Shop")
    _db.session.add(location)
    _db.session.flush()
    visible = _event(ctx_admin, "location.created", location, occurred_at=base + timedelta(seconds=hidden_count))
    _db.session.commit()

    api_login(users["member"])
    payload = _get(client, since=EPOCH, limit=50).get_json()["payload"]
    assert [e["id"] for e in payload["events"]] == [str(visible.id)]
    assert payload["has_more"] is False and payload["next_since"] == payload["now"]


def test_feed_reports_a_watermark_when_the_scan_cap_is_hit(org, users, ctx_admin, monkeypatch):
    secret = _project(org, "Sponsor Bid", "BID", visibility="private")
    wo = _wo(org, 1, users["admin"], project_id=secret.id)
    base = utcnow() - timedelta(hours=2)
    hidden = [_event(ctx_admin, "work_order.updated", wo, occurred_at=base + timedelta(seconds=i)) for i in range(12)]
    location = Location(organization_id=org.id, name="Shop")
    _db.session.add(location)
    _db.session.flush()
    visible = _event(ctx_admin, "location.created", location, occurred_at=base + timedelta(seconds=99))
    _db.session.commit()
    monkeypatch.setattr(changes, "SCAN_BATCH", 5)
    monkeypatch.setattr(changes, "MAX_SCAN_BATCHES", 2)

    ctx = policy.load_context(users["member"], org)
    first = changes.list_changes(ctx, {"since": EPOCH, "limit": 3})
    assert first["events"] == [] and first["has_more"] is True
    assert first["next_since"] == hidden[9].occurred_at  # last scanned row, not `now`
    second = changes.list_changes(ctx, {"since": first["next_since"], "limit": 3})
    assert [e.id for e in second["events"]] == [visible.id]
    assert second["has_more"] is False and second["next_since"] == second["now"]


def test_feed_never_leaks_other_organizations(client, org, users, ctx_admin, api_login):
    other = Organization(name="Other", slug="other")
    _db.session.add(other)
    _db.session.flush()
    foreign_location = Location(organization_id=other.id, name="Elsewhere")
    _db.session.add(foreign_location)
    _db.session.flush()
    foreign_event = AuditEvent(
        organization_id=other.id,
        event_type="location.created",
        entity_type="location",
        entity_id=str(foreign_location.id),
        occurred_at=utcnow(),
    )
    _db.session.add(foreign_event)
    local = Location(organization_id=org.id, name="Shop")
    _db.session.add(local)
    _db.session.flush()
    local_event = _event(ctx_admin, "location.created", local)
    _db.session.commit()

    api_login(users["admin"])
    payload = _get(client, since=EPOCH).get_json()["payload"]
    assert [e["id"] for e in payload["events"]] == [str(local_event.id)]


def test_inventory_and_purchase_request_events_follow_their_read_rules(client, org, users, ctx_admin, api_login):
    from asme.ops.models import Part, PartType, PurchaseRequest

    part_type = PartType(organization_id=org.id, name="Fastener")
    _db.session.add(part_type)
    _db.session.flush()
    part = Part(organization_id=org.id, name="Hex Bolt", part_type_id=part_type.id)
    _db.session.add(part)
    _db.session.flush()
    project = _project(org, "Rover", "CCR")
    mine = PurchaseRequest(organization_id=org.id, number=1, title="Bolts", requester_user_id=users["member"].id)
    theirs = PurchaseRequest(organization_id=org.id, number=2, title="Paint", requester_user_id=users["lead"].id)
    on_project = PurchaseRequest(
        organization_id=org.id, number=3, title="Nuts", requester_user_id=users["lead"].id, project_id=project.id
    )
    _db.session.add_all([mine, theirs, on_project])
    _db.session.flush()
    rows = {
        "part": _event(ctx_admin, "part.created", part),
        "part_type": _event(ctx_admin, "part_type.created", part_type),
        "pr:mine": _event(ctx_admin, "purchase_request.created", mine),
        "pr:theirs": _event(ctx_admin, "purchase_request.created", theirs),
        "pr:project": _event(ctx_admin, "purchase_request.created", on_project),
        # the ledger is its own history: transactions are never audited
        "transaction": _event(ctx_admin, "inventory_transaction.created", "inventory_transaction", entity_id=str(part.id)),
    }
    _db.session.commit()

    def visible_for(user):
        api_login(user)
        ids = {event["id"] for event in _get(client, since=EPOCH).get_json()["payload"]["events"]}
        return {label for label, row in rows.items() if str(row.id) in ids}

    # full member: inventory.read, and only their own purchase requests
    assert visible_for(users["member"]) == {"part", "part_type", "pr:mine"}
    # requester: no inventory.read, no purchase requests of their own
    requester = make_user("Rae Requester", "rae@uiowa.edu", ops_role="requester", org=org)
    assert visible_for(requester) == set()
    # treasurer: purchase.review reads every request, inventory.read the parts
    treasurer = make_user("Tess Treasurer", "tess@uiowa.edu", ops_role="treasurer", org=org)
    assert visible_for(treasurer) == set(rows) - {"transaction"}
    # project lead: own plus the requests on projects they manage
    lead = make_user("Pat Projectlead", "pat@uiowa.edu", ops_role="project_lead", org=org)
    project.members.append(ProjectMember(user_id=lead.id))
    _db.session.commit()
    assert visible_for(lead) == {"part", "part_type", "pr:project"}


def test_feed_requires_login_but_any_member_may_poll(client, org, users, api_login):
    anonymous = _get(client, since=EPOCH)
    assert anonymous.status_code == 401
    guest = make_user("Gus Guest", "gus@uiowa.edu", ops_role="sponsor_guest", org=org)
    api_login(guest)
    response = _get(client, since=EPOCH)
    assert response.status_code == 200 and response.get_json()["payload"]["events"] == []
