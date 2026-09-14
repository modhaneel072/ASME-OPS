"""Account review 6: reset / invite tokens must not be stored in a directly
usable form.

``identity.create_password_reset`` and ``identity.admin_invite_link_token`` store
the raw bearer token in ``password_reset_tokens.token`` and look it up by
equality. Anyone with read access to the database or a backup (invite tokens
live 72 hours) can take any listed token straight to
``POST /auth/reset-password`` and set that account's password. Storing a digest
(and hashing the presented token before lookup) closes this.
"""

from __future__ import annotations

from asme.jobs import outbox
from asme.models import PasswordResetToken
from asme.services import password_reset


def test_forgot_password_does_not_store_raw_token(app, client, org, users, monkeypatch):
    captured = {}
    original = password_reset.reset_link

    def _capture(origin, token):
        captured["token"] = token
        return original(origin, token)

    monkeypatch.setattr(password_reset, "reset_link", _capture)
    response = client.post("/api/v1/auth/forgot-password", json={"email": users["member"].email})
    assert response.status_code == 200
    outbox.process_pending()  # the worker mints the token
    raw = captured["token"]
    assert raw
    stored = [row.token for row in PasswordResetToken.query.filter_by(user_id=users["member"].id).all()]
    assert stored, "expected a reset row"
    assert raw not in stored, "the bearer token is stored verbatim"
