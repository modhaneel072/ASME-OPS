"""Account review 2: resetting or changing a password must end the account's
other sessions.

Sessions are signed client-side cookies holding only ``auth_user_id`` plus a
process-wide boot token, so nothing ties a session to the password it was
created with. Someone who has stolen a session cookie (or is still signed in on
a shared lab computer) keeps full access after the owner uses "Forgot password"
or "Change password" to lock them out.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from asme.extensions import db as _db
from asme.models import PasswordResetToken
from asme.services import identity
from tests.conftest import PASSWORD

NEW_PASSWORD = "a-brand-new-secret"


def _signed_in_client(app, email, password=PASSWORD):
    other = app.test_client()
    response = other.post("/api/v1/auth/login", json={"identifier": email, "password": password})
    assert response.status_code == 200, response.get_json()
    assert other.get("/api/v1/session").status_code == 200
    return other


def test_password_reset_and_change_end_other_sessions(app, client, org, users):
    member = users["member"]

    # --- reset from an e-mailed link ends a session opened before it
    stolen = _signed_in_client(app, member.email)
    token = "review2-reset-token-0123456789abcdefghijklmnopqrstuv"
    _db.session.add(PasswordResetToken(user_id=member.id, token=identity.hash_reset_token(token), expires_at=datetime.utcnow() + timedelta(hours=2)))
    _db.session.commit()
    done = client.post("/api/v1/auth/reset-password", json={"token": token, "password": NEW_PASSWORD, "confirm_password": NEW_PASSWORD})
    assert done.status_code == 200, done.get_json()
    assert stolen.get("/api/v1/session").status_code == 401, "a session opened before the reset still works"

    # --- change password from one browser ends the session in another
    stolen_again = _signed_in_client(app, member.email, NEW_PASSWORD)
    owner = _signed_in_client(app, member.email, NEW_PASSWORD)
    changed = owner.post(
        "/api/v1/auth/change-password",
        json={"current_password": NEW_PASSWORD, "new_password": "yet-another-secret", "confirm_password": "yet-another-secret"},
    )
    assert changed.status_code == 200, changed.get_json()
    assert stolen_again.get("/api/v1/session").status_code == 401, "another session survived a password change"
