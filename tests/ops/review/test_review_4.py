"""Review 4: ``GET /changes`` must not leak audit events for assets (and the
comments recorded against them) that belong to a private project the caller
cannot read. The guarded endpoints already hide the asset; the feed must too."""

from __future__ import annotations

import json

from asme.extensions import db as _db
from asme.ops.models import OpsProject

EPOCH = "2000-01-01T00:00:00Z"
SECRET_SERIAL = "SN-PRIVATE-7781"
SECRET_BODY = "Sponsor pricing is confidential: 4200 USD"


def test_change_feed_hides_private_project_asset_events(client, org, users, api_login):
    secret = OpsProject(organization_id=org.id, name="Sponsor Bid", code="BID", visibility="private")
    _db.session.add(secret)
    _db.session.commit()

    # Admin (project.read_private) creates an asset inside the private project
    # and comments on it; both actions record audit events against the asset.
    api_login(users["admin"])
    created = client.post(
        "/api/v1/assets",
        json={
            "name": "Secret Rig",
            "project_id": str(secret.id),
            "serial_number": SECRET_SERIAL,
            "purchase_cost": "4200.00",
        },
    )
    assert created.status_code == 201, created.get_json()
    asset_id = created.get_json()["payload"]["asset"]["id"]
    commented = client.post(f"/api/v1/assets/{asset_id}/comments", json={"body": SECRET_BODY})
    assert commented.status_code == 201, commented.get_json()

    # A full member without project.read_private cannot read the asset directly...
    api_login(users["member"])
    assert client.get(f"/api/v1/assets/{asset_id}").status_code == 404

    # ...so the change feed must not hand them the same asset's audit events either.
    response = client.get(f"/api/v1/changes?since={EPOCH}&limit=200")
    assert response.status_code == 200, response.get_json()
    events = response.get_json()["payload"]["events"]

    leaked = [e for e in events if e["entity_type"] == "asset" and e["entity_id"] == asset_id]
    assert leaked == [], f"private-project asset events leaked via /changes: {[e['event_type'] for e in leaked]}"

    serialized = json.dumps(events)
    assert SECRET_SERIAL not in serialized
    assert SECRET_BODY not in serialized
