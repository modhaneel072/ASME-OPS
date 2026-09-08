"""Fixtures for ASME Ops tests: a bootstrapped organization, policy contexts for
each role, and an API login helper."""

from __future__ import annotations

import pytest
from werkzeug.security import generate_password_hash

from asme.extensions import db as _db
from asme.models import User
from asme.ops import bootstrap, policy
from tests.conftest import PASSWORD


@pytest.fixture
def org(app, users):
    return bootstrap.ensure_default_organization()


def _ctx(user, org):
    return policy.load_context(user, org)


@pytest.fixture
def ctx_admin(org, users):
    return _ctx(users["admin"], org)


@pytest.fixture
def ctx_lead(org, users):
    return _ctx(users["lead"], org)


@pytest.fixture
def ctx_member(org, users):
    return _ctx(users["member"], org)


def make_user(name, email, legacy_role="member", ops_role=None, org=None, **extra):
    """Create a legacy user (and, when ``org`` is given, a membership with ``ops_role``)."""
    user = User(
        name=name,
        email=email,
        username=email.split("@")[0],
        password_hash=generate_password_hash(PASSWORD),
        role=legacy_role,
        is_active=True,
        **extra,
    )
    _db.session.add(user)
    _db.session.flush()
    if org is not None:
        membership = bootstrap.ensure_membership(user, org, commit=False)
        if ops_role:
            membership.role = bootstrap.role_by_key(org, ops_role)
    _db.session.commit()
    return user


@pytest.fixture
def requester(org):
    return make_user("Rae Requester", "rae@uiowa.edu", ops_role="requester", org=org)


@pytest.fixture
def ctx_requester(org, requester):
    return _ctx(requester, org)


@pytest.fixture
def api_login(client):
    def _login(user, password=PASSWORD):
        response = client.post("/api/v1/auth/login", json={"identifier": user.email, "password": password})
        assert response.status_code == 200, response.get_json()
        return client

    return _login
