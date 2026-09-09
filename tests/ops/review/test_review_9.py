"""Review 9: POST /work-orders/:id/complete must validate ``time_entries`` and
``cost_entries`` types.

A non-list truthy scalar (int, bool) must answer a 400 validation error naming
the field - never a TypeError/500 from ``list(time_entries or [])`` running
before the ``Field('list')`` check in ``COMPLETE_SPEC``.
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
    "field,value",
    [
        ("time_entries", 5),
        ("time_entries", True),
        ("cost_entries", True),
        ("cost_entries", 1),
    ],
)
def test_complete_rejects_non_list_entries_with_400(client, org, users, api_login, field, value):
    api_login(users["admin"])
    wo_id = _create_open_wo(client, f"complete type check {field}")

    try:
        response = client.post(f"/api/v1/work-orders/{wo_id}/complete", json={field: value})
    except TypeError as exc:  # pragma: no cover - defect path
        pytest.fail(f"complete endpoint crashed with TypeError instead of returning 400: {exc}")

    assert response.status_code == 400, (response.status_code, response.get_data(as_text=True)[:300])
    body = response.get_json()
    assert body is not None and body.get("ok") is False, body
    assert field in body.get("errors", {}), body

    wo = _db.session.get(WorkOrder, parse_uuid(wo_id))  # the PK is a real UUID column
    assert wo.status == "open"
