"""Review 8: work-order transition endpoints must validate ``note``.

A non-string ``note`` (int, list, object) posted to /start, /hold, /cancel ...
must answer a 400 validation error naming ``note`` - never a 500 from
``(note or "").strip()`` blowing up on a non-string. Notes must also be
length-bounded rather than persisted verbatim at any size.
"""

from __future__ import annotations

import pytest

from asme.extensions import db as _db
from asme.ops.models import WorkOrder
from asme.ops.types import parse_uuid


def _create_open_wo(client, title):
    response = client.post("/api/v1/work-orders", json={"title": title})
    assert response.status_code == 201, response.get_json()
    return response.get_json()["payload"]["work_order"]["id"]


@pytest.mark.parametrize(
    "action,prep,note",
    [
        ("start", (), 5),
        ("start", (), ["x"]),
        ("hold", ("start",), ["x"]),
        ("hold", ("start",), {"a": 1}),
        ("cancel", (), 1),
    ],
)
def test_transition_rejects_non_string_note_with_400(client, org, users, api_login, action, prep, note):
    api_login(users["admin"])
    wo_id = _create_open_wo(client, f"note type check {action}")
    for step in prep:
        assert client.post(f"/api/v1/work-orders/{wo_id}/{step}", json={}).status_code == 200

    response = client.post(f"/api/v1/work-orders/{wo_id}/{action}", json={"note": note})

    assert response.status_code == 400, (response.status_code, response.get_data(as_text=True)[:300])
    body = response.get_json()
    assert body["ok"] is False
    assert "note" in body.get("errors", {}), body


def test_transition_rejects_oversized_note(client, org, users, api_login):
    api_login(users["admin"])
    wo_id = _create_open_wo(client, "note size check")
    huge = "x" * (2 * 1024 * 1024)

    response = client.post(f"/api/v1/work-orders/{wo_id}/start", json={"note": huge})

    assert response.status_code == 400, response.status_code
    assert "note" in response.get_json().get("errors", {})
    wo = _db.session.get(WorkOrder, parse_uuid(wo_id))  # the PK is a real UUID column
    assert wo.status == "open"
    assert all(h.note is None or len(h.note) < 2 * 1024 * 1024 for h in wo.status_history)
