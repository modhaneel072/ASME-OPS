"""A purchase request's stored money must stay inside ``Numeric(12, 2)``.

``ops_purchase_requests.estimated_total`` and ``approved_total`` are
``Numeric(12, 2)`` columns, so the largest value they hold is
``asme.ops.validation.MONEY_MAX`` (9999999999.99). Every money field that
arrives from a client is bounded against that limit before it is stored, but
``estimated_total`` is not sent by the client - the service multiplies each
line's ``quantity`` (up to 99999999999.999) by its ``unit_price`` (up to
99999999.9999) and adds shipping and tax. Those per-field bounds leave the
product free to be many orders of magnitude larger than the column, and a
fat-fingered quantity is enough to reach it.

On SQLite the oversized value is stored anyway; on PostgreSQL, which the
chapter deploys on, the INSERT raises ``numeric field overflow`` and the caller
gets a 500 instead of a field error. Either way the request is accepted with a
total the column cannot represent, so this test asserts the rule directly: a
purchase request is either rejected with a 400 naming a field, or the total it
comes back with fits the column.
"""

from __future__ import annotations

from decimal import Decimal

from asme.ops.validation import MONEY_MAX

API = "/api/v1/purchase-requests"


def _assert_within_money_column(response, what: str) -> None:
    payload = response.get_json()
    if response.status_code == 400:
        assert payload["code"] == "validation" and payload["errors"], payload
        return
    assert response.status_code in (200, 201), payload
    request = payload["payload"]["purchase_request"]
    for field in ("estimated_total", "approved_total"):
        value = request.get(field)
        if value is None:
            continue
        assert Decimal(str(value)) <= MONEY_MAX, (
            f"{what}: {field} is {value}, which does not fit the Numeric(12, 2) column "
            f"(at most {MONEY_MAX}); PostgreSQL refuses the write with numeric field overflow"
        )


def test_line_totals_cannot_exceed_the_money_column(client, org, users, api_login):
    api_login(users["member"])
    created = client.post(
        API,
        json={
            "title": "Bulk fasteners",
            # Both numbers pass their own field bounds; their product does not.
            "items": [{"description": "M6 bolts", "quantity": "1000000", "unit_price": "99999"}],
        },
    )
    _assert_within_money_column(created, "POST /purchase-requests")


def test_patching_a_draft_cannot_exceed_the_money_column(client, org, users, api_login):
    api_login(users["member"])
    created = client.post(
        API,
        json={"title": "Fasteners", "items": [{"description": "M6 bolts", "quantity": "10", "unit_price": "1.00"}]},
    )
    assert created.status_code == 201, created.get_json()
    request_id = created.get_json()["payload"]["purchase_request"]["id"]

    patched = client.patch(
        f"{API}/{request_id}",
        json={"items": [{"description": "M6 bolts", "quantity": "99999999999", "unit_price": "10"}]},
    )
    _assert_within_money_column(patched, "PATCH /purchase-requests/:id")
