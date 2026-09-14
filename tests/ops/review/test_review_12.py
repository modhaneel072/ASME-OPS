"""Review 12: the change feed must not leak audit rows for assets inside projects
the caller cannot read.

``changes._visible`` only guards ``work_order`` / ``project`` / ``milestone``
rows; every other entity type is delivered chapter-wide. An ``asset.created``
row for an asset attached to a *private* project therefore reaches a member who
is neither a project member nor a ``project.read_private`` holder, complete with
the asset's name, serial number and project id in ``after_json``.

Desired behaviour: a full member who gets 404 on ``GET /assets/<id>`` for such an
asset must not receive that asset's audit rows from ``GET /changes`` either.
"""

from __future__ import annotations

from asme.extensions import db as _db
from asme.ops.models import OpsProject
from asme.ops.services import assets

EPOCH = "2020-01-01T00:00:00Z"


def test_change_feed_hides_asset_events_from_private_projects(client, org, users, ctx_admin, api_login):
    secret = OpsProject(organization_id=org.id, name="Sponsor Bid", code="BID", visibility="private")
    _db.session.add(secret)
    _db.session.commit()

    # Real service call so the audit row is shaped exactly as production writes it.
    hidden = assets.create(
        ctx_admin,
        {"name": "Secret Rig", "serial_number": "SN-SECRET-001", "project_id": str(secret.id)},
    )
    public = assets.create(ctx_admin, {"name": "Bench Grinder"})

    api_login(users["member"])  # full_member: project.read only, not a member of `secret`
    assert client.get(f"/api/v1/assets/{hidden.id}").status_code == 404
    assert client.get(f"/api/v1/assets/{public.id}").status_code == 200

    payload = client.get(f"/api/v1/changes?since={EPOCH}").get_json()["payload"]
    asset_events = [event for event in payload["events"] if event["entity_type"] == "asset"]
    delivered_ids = {event["entity_id"] for event in asset_events}

    # control: the chapter-visible asset's event is delivered
    assert str(public.id) in delivered_ids

    leaked = [event for event in asset_events if event["entity_id"] == str(hidden.id)]
    assert leaked == [], (
        "change feed delivered private-project asset events to a non-member: "
        + repr([(e["event_type"], e["summary"], e["after"]) for e in leaked])
    )
    body = str(payload)
    assert "SN-SECRET-001" not in body and "Secret Rig" not in body
