"""Review 5: decimal fields must reject NaN / Infinity / huge exponents with a
400 validation envelope instead of leaking decimal.InvalidOperation as a 500."""

from __future__ import annotations

import pytest


@pytest.mark.parametrize("amount", ["NaN", "sNaN", "Infinity", "1e30", "1e999"])
def test_cost_entry_non_finite_or_huge_amount_is_validation_error(client, org, users, api_login, amount):
    api_login(users["admin"])
    wo = client.post("/api/v1/work-orders", json={"title": "Costed"}).get_json()["payload"]["work_order"]
    url = f"/api/v1/work-orders/{wo['id']}/cost-entries"

    response = client.post(url, json={"type": "parts", "amount": amount})

    assert response.status_code == 400, response.data[:300]
    body = response.get_json()
    assert body["code"] == "validation"
    assert "amount" in body["errors"]
