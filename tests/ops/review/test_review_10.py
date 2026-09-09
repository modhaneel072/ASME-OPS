"""Review 10: ``user.manage`` holders must not be able to mint ``chapter_admin``.

``executive_officer`` holds every chapter-scoped permission except
``role.manage`` and ``chapter.settings.manage`` - the two keys reserved for
chapter administrators. Because it holds ``user.manage`` it can call
``POST /users/invite`` and ``PATCH /users/:id``. Neither entry point must let
it assign the ``chapter_admin`` role (to a colleague or to a fresh account it
controls), or the withheld permissions - and legacy ``users.role='admin'`` via
``_sync_legacy_admin`` - are one request away.

Desired behaviour: the request is refused (403/400/409), no ``chapter_admin``
membership is created or promoted, and no legacy admin account appears.
"""

from __future__ import annotations

from sqlalchemy import func

from asme.models import User
from asme.ops import bootstrap
from asme.ops.models import Membership
from tests.ops.conftest import make_user

REJECTED = {400, 403, 409}


def _officer(org):
    return make_user("Eve Officer", "eve@uiowa.edu", ops_role="executive_officer", org=org)


def test_executive_officer_cannot_promote_colleague_to_chapter_admin(client, org, users, api_login):
    officer = _officer(org)
    colleague = users["member"]
    api_login(officer)

    response = client.patch(f"/api/v1/users/{colleague.id}", json={"role_key": "chapter_admin"})

    assert response.status_code in REJECTED, (response.status_code, response.get_data(as_text=True)[:300])
    membership = bootstrap.membership_for(colleague, org)
    assert membership.role.system_key != "chapter_admin"
    assert colleague.role != "admin"


def test_executive_officer_cannot_invite_a_fresh_chapter_admin(client, org, users, api_login):
    officer = _officer(org)
    api_login(officer)
    email = "eve+admin@uiowa.edu"

    response = client.post(
        "/api/v1/users/invite",
        json={"email": email, "name": "Eve Admin", "role_key": "chapter_admin"},
    )

    assert response.status_code in REJECTED, (response.status_code, response.get_data(as_text=True)[:300])
    invitee = User.query.filter(func.lower(User.email) == email).first()
    if invitee is not None:
        assert invitee.role != "admin"
        membership = Membership.query.filter_by(organization_id=org.id, user_id=invitee.id).first()
        assert membership is None or membership.role.system_key != "chapter_admin"
