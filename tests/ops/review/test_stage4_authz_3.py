"""One person must not clear two approval steps of the same purchase request.

The advisor step exists to put a second, independent signature on spending above
``purchasing.advisor_review_threshold``: ``treasurer_review`` -> (over the
threshold) ``advisor_review`` -> ``approved``.

``_authorize_action`` guards the requester (``self_approval``) but nothing stops
the *same* approver from signing both steps, and the shipped default grants give
``faculty_advisor`` both ``purchase.review`` and ``purchase.advisor_review``. So
in the default configuration a single faculty advisor approves at
``treasurer_review``, then approves again at ``advisor_review``, and the request
reaches ``approved`` with one human signature - the threshold buys nothing.

The second approval must be refused (the natural shape is the existing
``Conflict`` the self-approval rule already uses); a different advisor must still
be able to finish the request.
"""

from __future__ import annotations

from tests.ops.conftest import make_user

API = "/api/v1/purchase-requests"
SETTINGS = "/api/v1/purchasing/settings"


def _submitted_request_over_threshold(client, users, api_login):
    api_login(users["admin"])
    settings = client.put(SETTINGS, json={"advisor_review_threshold": "100"})
    assert settings.status_code == 200, settings.get_json()

    api_login(users["member"])
    created = client.post(
        API, json={"title": "Test bench power supply", "items": [{"description": "PSU", "quantity": 10, "unit_price": "50"}]}
    )
    assert created.status_code == 201, created.get_json()
    request = created.get_json()["payload"]["purchase_request"]
    assert request["estimated_total"] == 500.0
    assert client.post(f"{API}/{request['id']}/submit", json={}).status_code == 200
    return request


def test_the_same_approver_cannot_sign_both_review_steps(client, org, users, api_login):
    advisor = make_user("Avi Advisor", "avi.advisor@uiowa.edu", ops_role="faculty_advisor", org=org)
    request = _submitted_request_over_threshold(client, users, api_login)

    api_login(advisor)
    first = client.post(f"{API}/{request['id']}/approve", json={"comment": "as treasurer"})
    assert first.status_code == 200, first.get_json()
    assert first.get_json()["payload"]["purchase_request"]["status"] == "advisor_review"

    second = client.post(f"{API}/{request['id']}/approve", json={"comment": "as advisor"})
    assert second.status_code >= 400, (
        "the same person approved both the treasurer and the advisor step; the request is now "
        f"{second.get_json()['payload']['purchase_request']['status']} on one signature"
    )

    detail = client.get(f"{API}/{request['id']}")
    assert detail.get_json()["payload"]["purchase_request"]["status"] == "advisor_review"
    assert "approve" not in detail.get_json()["payload"]["purchase_request"]["available_actions"]


def test_a_second_advisor_can_still_finish_the_request(client, org, users, api_login):
    treasurer = make_user("Tess Treasurer", "tess.treasurer@uiowa.edu", ops_role="treasurer", org=org)
    advisor = make_user("Avi Advisor", "avi.advisor@uiowa.edu", ops_role="faculty_advisor", org=org)
    request = _submitted_request_over_threshold(client, users, api_login)

    api_login(treasurer)
    first = client.post(f"{API}/{request['id']}/approve", json={})
    assert first.status_code == 200, first.get_json()
    assert first.get_json()["payload"]["purchase_request"]["status"] == "advisor_review"

    api_login(advisor)
    second = client.post(f"{API}/{request['id']}/approve", json={})
    assert second.status_code == 200, second.get_json()
    assert second.get_json()["payload"]["purchase_request"]["status"] == "approved"
