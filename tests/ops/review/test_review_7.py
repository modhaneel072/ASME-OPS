"""Review 7: unbounded integer inputs must produce a 4xx validation envelope,
never an OverflowError/DB bind error surfacing as a 500."""

from __future__ import annotations

import pytest


def _call(client, method, url, **kwargs):
    """Perform a request; a propagated server exception counts as a 500."""
    try:
        response = getattr(client, method)(url, **kwargs)
    except Exception as exc:  # noqa: BLE001 - TESTING mode propagates 500s
        pytest.fail(f"{method.upper()} {url} raised {type(exc).__name__}: {exc}")
    return response


def _assert_validation_error(response, field):
    assert response.status_code == 400, (response.status_code, response.data[:300])
    body = response.get_json()
    assert body["code"] == "validation"
    assert field in body["errors"]


@pytest.mark.parametrize("value", [10**30, 1e30, 2**63, 2**31])
def test_patch_estimated_minutes_huge_int_is_validation_error(client, org, users, api_login, value):
    api_login(users["admin"])
    wo = client.post("/api/v1/work-orders", json={"title": "Bounded"}).get_json()["payload"]["work_order"]

    response = _call(client, "patch", f"/api/v1/work-orders/{wo['id']}", json={"estimated_minutes": value})

    _assert_validation_error(response, "estimated_minutes")


def test_patch_estimated_minutes_json_infinity_is_validation_error(client, org, users, api_login):
    api_login(users["admin"])
    wo = client.post("/api/v1/work-orders", json={"title": "Bounded"}).get_json()["payload"]["work_order"]

    response = _call(
        client,
        "patch",
        f"/api/v1/work-orders/{wo['id']}",
        data='{"estimated_minutes": Infinity}',
        content_type="application/json",
    )

    _assert_validation_error(response, "estimated_minutes")


def test_time_entry_huge_minutes_is_validation_error(client, org, users, api_login):
    api_login(users["admin"])
    wo = client.post("/api/v1/work-orders", json={"title": "Timed"}).get_json()["payload"]["work_order"]

    response = _call(client, "post", f"/api/v1/work-orders/{wo['id']}/time-entries", json={"minutes": 10**30})

    _assert_validation_error(response, "minutes")


def test_get_user_with_huge_id_is_not_found(client, org, users, api_login):
    api_login(users["admin"])

    response = _call(client, "get", "/api/v1/users/99999999999999999999999")

    assert response.status_code == 404, (response.status_code, response.data[:300])
