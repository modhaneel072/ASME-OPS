"""Account review 4: failed sign-ins must not be able to lock someone else out
of changing their password.

The account flows reuse the login limiter with string prefixes
(``"change-password:" + user_id``, ``"reset-password:" + ip``,
``"forgot-password:" + email``) in the same key space as login identifiers, and
``/auth/login`` accepts any identifier string. An unauthenticated attacker
failing sign-in with ``identifier = "change-password:<victim id>"`` bumps the
victim's identifier-wide change-password counter from any address, so the
victim gets 429 when they try to change their (possibly compromised) password.
"""

from __future__ import annotations

import pytest

from tests.conftest import PASSWORD


@pytest.fixture
def tight_limiter(app):
    limiter = app.extensions["asme_login_rate_limiter"]
    original = limiter.max_attempts
    limiter.max_attempts = 2
    limiter.reset_all()
    yield limiter
    limiter.max_attempts = original
    limiter.reset_all()


def test_login_failures_cannot_lock_victim_out_of_change_password(app, org, users, tight_limiter):
    victim = users["member"]
    victim_id = victim.id
    victim_email = victim.email

    # Attacker: many failed sign-ins from rotating addresses, crafted identifier.
    for n in range(tight_limiter.max_identifier_attempts + 2):
        attacker = app.test_client()
        attacker.environ_base["REMOTE_ADDR"] = f"203.0.113.{n + 1}"
        attacker.post("/api/v1/auth/login", json={"identifier": f"change-password:{victim_id}", "password": "x"})

    # Victim, from their own address, with the correct current password.
    owner = app.test_client()
    owner.environ_base["REMOTE_ADDR"] = "198.51.100.7"
    assert owner.post("/api/v1/auth/login", json={"identifier": victim_email, "password": PASSWORD}).status_code == 200
    response = owner.post(
        "/api/v1/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "a-brand-new-secret", "confirm_password": "a-brand-new-secret"},
    )
    assert response.status_code == 200, response.get_json()
