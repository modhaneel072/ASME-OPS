"""Review 1: inviting an EXISTING account must not hand the inviter a working
password-reset token for that account (account takeover).

An executive officer (``user.manage`` only) invites a legacy site admin who is
not yet an Ops member.  The response must not contain a credential-reset link
for that live account, and whatever it does contain must not let the inviter
set a new password and sign in as the victim.
"""

from __future__ import annotations

from werkzeug.security import check_password_hash

from asme.extensions import db as _db
from asme.models import PasswordResetToken, User
from asme.services import identity
from tests.conftest import PASSWORD
from tests.ops.conftest import make_user


def test_inviting_existing_account_does_not_mint_reset_token_for_inviter(client, org, users, api_login):
    victim = make_user("Vic Victim", "victim@uiowa.edu", legacy_role="admin")  # live login, no ops membership
    attacker = make_user("Eve Officer", "eve@uiowa.edu", org=org, ops_role="executive_officer")
    victim_id = victim.id
    assert PasswordResetToken.query.filter_by(user_id=victim_id).count() == 0

    api_login(attacker)
    response = client.post(
        "/api/v1/users/invite",
        json={"email": "victim@uiowa.edu", "name": "Eve Proxy", "role_key": "chapter_admin"},
    )
    assert response.status_code in (201, 403), response.get_json()  # never a validation 400: the request itself is well-formed

    # Desired: no live reset credential for a pre-existing account is created / returned.
    live_tokens = [
        row
        for row in PasswordResetToken.query.filter_by(user_id=victim_id).all()
        if identity.find_valid_reset(row.token) is not None
    ]
    assert live_tokens == [], "invite minted a usable password-reset token for an existing account"

    invite_url = (response.get_json() or {}).get("payload", {}).get("invite_url")
    if invite_url:
        # Whatever was returned must not reset the victim's password.
        token = invite_url.rsplit("/", 1)[1]
        client.post(f"/reset-password/{token}", data={"password": "hijacked-secret", "confirm_password": "hijacked-secret"})

    _db.session.expire_all()
    fresh = _db.session.get(User, victim_id)
    assert check_password_hash(fresh.password_hash, PASSWORD), "victim's original password no longer works"
    assert not check_password_hash(fresh.password_hash, "hijacked-secret")

    # The inviter must not be able to sign in as the victim with a password they chose.
    client.post("/api/v1/auth/logout")
    hijack = client.post("/api/v1/auth/login", json={"identifier": "victim@uiowa.edu", "password": "hijacked-secret"})
    assert hijack.status_code == 401, hijack.get_json()
