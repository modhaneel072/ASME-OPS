"""One member's stale reset links lock the whole chapter out of password reset.

``asme/auth/rate_limit.py`` deliberately keeps two counters, and says why::

    # How many failures the identifier-only counter allows, as a multiple of the
    # per-address allowance. Generous enough that a shared campus NAT does not lock
    # a real member out, ...

That safety net exists because every member working in the shop, on campus wifi,
or in the residence halls reaches ASME Ops from one shared university NAT
address - and ``ASME_TRUSTED_PROXY_COUNT=2`` in ``render.yaml`` makes
``request_client_ip`` resolve that shared address correctly, so the whole
chapter really does arrive as one IP.

``asme/blueprints/ops/auth.py::reset_password`` then passes the client address as
*both* key components::

    counter = ip  # per address: tokens differ on every guess
    blocked, retry_after = limiter.is_limited(ip, counter, RESET_NAMESPACE)

so ``key(ip, identifier)`` and ``identifier_key(identifier)`` are the same
bucket, differing only in ceiling. The identifier counter is no longer a
separate net; it is the same net with a bigger number on it.

Result over a semester: eight expired or already-used reset links clicked from
campus in fifteen minutes - the ordinary outcome of an officer mailing invite
links to a dozen new members, several of whom click twice or click the one they
already used - and every other member on campus is told "Too many password
reset attempts. Try again later." for the rest of the window, including members
holding a perfectly valid, unused link. ``ASME_LOGIN_RATE_WINDOW_SECONDS=900``
means the chapter is locked out in fifteen-minute blocks for as long as the
clicking continues.

The per-address ceiling has to be spent on guessing, not on the whole chapter at
once: the second counter must be keyed on something that identifies the person
or their link, as the login and forgot-password flows do with the e-mail
address.
"""

from __future__ import annotations

import pytest
from werkzeug.security import generate_password_hash

from asme.extensions import db
from asme.models import User
from asme.services import identity
from tests.conftest import make_app

CAMPUS_NAT = "128.255.45.7"          # one university egress address for everyone
NETLIFY_EDGE = "44.210.11.9"         # appended by Render's router in front of us
# Two proxies in front of the app (Netlify's edge, then Render's router), which
# is exactly what render.yaml declares with ASME_TRUSTED_PROXY_COUNT=2.
FORWARDED_FOR = f"{CAMPUS_NAT}, {NETLIFY_EDGE}"
MAX_ATTEMPTS = 8


@pytest.fixture
def campus_app():
    application = make_app(
        login_rate_max_attempts=MAX_ATTEMPTS,
        login_rate_window_seconds=900,
        trusted_proxy_count=2,
    )
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()


def _post_reset(client, token):
    return client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "password": "a-good-new-password", "confirm_password": "a-good-new-password"},
        headers={"X-Forwarded-For": FORWARDED_FOR},
    )


def test_stale_links_from_campus_do_not_block_a_member_holding_a_valid_link(campus_app):
    client = campus_app.test_client()

    member = User(
        name="Mo Member",
        email="mo@uiowa.edu",
        username="mo",
        password_hash=generate_password_hash("old-password-value"),
        role="member",
        is_active=True,
    )
    db.session.add(member)
    db.session.commit()

    # A real member requested a reset and is holding a valid, unused link.
    good_token = identity.create_password_reset(member)

    # Meanwhile other people on the same campus address click links that have
    # already been used or have expired. Eight of them fills the per-address
    # allowance; the identifier counter is the same bucket, so nothing is held
    # in reserve.
    for attempt in range(MAX_ATTEMPTS):
        response = _post_reset(client, f"stale-link-{attempt}")
        assert response.status_code == 404, response.get_json()

    response = _post_reset(client, good_token)
    assert response.status_code != 429, (
        "a member holding a valid reset link was refused because other people on "
        f"the same campus address had clicked stale links: {response.get_json()}"
    )
    assert response.status_code == 200, response.get_json()
    assert response.get_json()["payload"]["reset"] is True
