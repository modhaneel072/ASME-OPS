"""Review 11: the JSON login rate limiter must not be resettable by the client.

``POST /api/v1/auth/login`` keys ``LoginRateLimiter`` on ``(client_ip, identifier)``
where ``client_ip`` comes from ``request_client_ip``.  That helper trusts the first
element of ``X-Forwarded-For`` unconditionally, so a client that is NOT behind a
trusted proxy (``remote_addr`` is the raw peer) can pick a fresh key on every
request and never accumulate failures.

Desired behaviour: with no trusted proxy configured, a single peer that fails
``max_attempts`` times against one identifier is answered 429 on the next attempt
regardless of what it puts in ``X-Forwarded-For``.
"""

from __future__ import annotations

import pytest
from werkzeug.security import generate_password_hash

from asme.extensions import db as _db
from asme.models import User
from tests.conftest import PASSWORD, make_app

MAX_ATTEMPTS = 3


@pytest.fixture
def strict_app():
    application = make_app(login_rate_max_attempts=MAX_ATTEMPTS)
    with application.app_context():
        _db.create_all()
        victim = User(
            name="Vic Victim",
            email="vic@uiowa.edu",
            username="vic",
            password_hash=generate_password_hash(PASSWORD),
            role="member",
            is_active=True,
        )
        _db.session.add(victim)
        _db.session.commit()
        yield application
        _db.session.remove()
        _db.drop_all()


def _attempt(client, i, headers=None):
    return client.post(
        "/api/v1/auth/login",
        json={"identifier": "vic@uiowa.edu", "password": f"wrong-guess-{i}"},
        headers=headers or {},
    )


def test_login_limiter_triggers_without_forwarded_header(strict_app):
    """Control: same peer, no header games -> limiter kicks in after MAX_ATTEMPTS."""
    client = strict_app.test_client()
    for i in range(MAX_ATTEMPTS):
        assert _attempt(client, i).status_code == 401
    assert _attempt(client, 99).status_code == 429


def test_login_limiter_not_bypassed_by_rotating_x_forwarded_for(strict_app):
    """Same peer (remote_addr 127.0.0.1, no trusted proxy) rotating X-Forwarded-For
    must still be rate limited against the victim identifier."""
    client = strict_app.test_client()
    statuses = []
    # Well beyond the threshold: every request spoofs a new client IP.
    for i in range(MAX_ATTEMPTS * 4):
        response = _attempt(client, i, headers={"X-Forwarded-For": f"10.0.{i}.{i}"})
        statuses.append(response.status_code)
        assert response.status_code != 200
    assert 429 in statuses, (
        f"limiter never fired across {len(statuses)} failed attempts with rotating "
        f"X-Forwarded-For (statuses={statuses}); client-controlled header resets the key"
    )
    # And by now the identifier must be locked for this peer no matter the header.
    assert _attempt(client, 999, headers={"X-Forwarded-For": "203.0.113.7"}).status_code == 429


def test_trusted_proxy_count_uses_the_proxy_appended_address():
    """With ASME_TRUSTED_PROXY_COUNT=1 the right-most X-Forwarded-For entry (the one
    the proxy appended) is the client address; anything further left is ignored."""
    from asme.utils.http import request_client_ip

    application = make_app(trusted_proxy_count=1)
    with application.test_request_context("/", headers={"X-Forwarded-For": "198.51.100.9, 203.0.113.7"}):
        assert request_client_ip() == "203.0.113.7"
    with application.test_request_context("/", environ_base={"REMOTE_ADDR": "10.0.0.2"}):
        assert request_client_ip() == "10.0.0.2"
