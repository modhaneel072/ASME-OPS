"""Review 6: a non-finite ``Infinity`` decimal must never poison a shared list.

Desired behaviour: ``budget_amount`` / ``purchase_cost`` of ``"Infinity"`` is either
rejected at validation (400) or, if stored, the list/health endpoints still emit
strict, standards-compliant JSON (no bare ``Infinity`` token). The parser below
mimics browser ``JSON.parse``, which rejects ``Infinity``/``NaN``."""

from __future__ import annotations

import json

import pytest


def _reject_constant(token):
    raise ValueError(f"non-standard JSON constant {token!r}")


def _strict_json(response):
    body = response.get_data(as_text=True)
    try:
        return json.loads(body, parse_constant=_reject_constant)
    except ValueError as exc:
        pytest.fail(f"{response.request.path} returned non-standard JSON ({exc}): {body[:300]}")


def test_infinity_money_values_do_not_break_list_endpoints(client, org, users, api_login):
    api_login(users["admin"])

    created = client.post("/api/v1/projects", json={"name": "Infinite Budget", "budget_amount": "Infinity"})
    assert created.status_code in (201, 400), created.get_data(as_text=True)
    project_id = created.get_json()["payload"]["project"]["id"] if created.status_code == 201 else None

    listing = client.get("/api/v1/projects")
    assert listing.status_code == 200
    _strict_json(listing)

    if project_id:
        health = client.get(f"/api/v1/projects/{project_id}/health")
        assert health.status_code == 200
        _strict_json(health)

    asset = client.post("/api/v1/assets", json={"name": "Priceless Lathe", "purchase_cost": "Infinity"})
    assert asset.status_code in (201, 400), asset.get_data(as_text=True)

    assets = client.get("/api/v1/assets")
    assert assets.status_code == 200
    _strict_json(assets)
