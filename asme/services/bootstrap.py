"""Schema sync and default data.

* ``sync_schema`` - bring the database to the current Alembic head. A database
  created by the old ``db.create_all()`` code path (no ``alembic_version``) is
  stamped at the baseline revision first, then upgraded.
* ``seed_defaults`` - idempotent seed of the bootstrap admin, the Launchpad
  tracks and the ASME Ops organization (roles, memberships, default location,
  categories). It creates no example projects, people or content: everything
  else in the system is entered by the chapter.
"""

from __future__ import annotations

import logging

from flask import current_app
from sqlalchemy import func, inspect, text
from werkzeug.security import generate_password_hash

from asme.config import settings
from asme.extensions import db
from asme.models import Member, User
from asme.services.onboarding.seeds import seed_default_tracks

log = logging.getLogger("asme.bootstrap")

BASELINE_REVISION = "0001_baseline"


def _has_alembic_version() -> bool:
    return "alembic_version" in inspect(db.engine).get_table_names()


def _is_legacy_database() -> bool:
    tables = set(inspect(db.engine).get_table_names())
    return bool(tables) and "alembic_version" not in tables and "users" in tables


def sync_schema() -> str:
    """Upgrade to head. Returns a short description of what happened."""
    from flask_migrate import stamp, upgrade

    migrations_dir = current_app.extensions["migrate"].directory
    if _is_legacy_database():
        log.warning("legacy database detected (no alembic_version); stamping %s", BASELINE_REVISION)
        stamp(directory=migrations_dir, revision=BASELINE_REVISION)
        upgrade(directory=migrations_dir)
        return "stamped-baseline+upgraded"
    upgrade(directory=migrations_dir)
    return "upgraded"


def current_revision() -> str | None:
    if not _has_alembic_version():
        return None
    row = db.session.execute(text("SELECT version_num FROM alembic_version")).first()
    return row[0] if row else None


def seed_defaults(commit=True) -> dict:
    cfg = settings()
    created = {"users": 0}

    if User.query.count() == 0:
        from asme.auth.session import is_admin_member

        members = Member.query.order_by(Member.id.asc()).all()
        for member in members:
            role = "member"
            if "lead" in (member.member_class or "").lower():
                role = "team_leader"
            if is_admin_member(member):
                role = "admin"
            db.session.add(
                User(
                    name=member.name,
                    email=member.email,
                    username=(member.email.split("@", 1)[0] if member.email and "@" in member.email else None),
                    password_hash=generate_password_hash(cfg.default_user_password),
                    role=role,
                    is_active=True,
                    member_id=member.id,
                )
            )
            created["users"] += 1
        if not members:
            db.session.add(_bootstrap_admin(cfg))
            created["users"] += 1
    elif not User.query.filter(func.lower(User.email) == cfg.default_admin_email).first():
        db.session.add(_bootstrap_admin(cfg))
        created["users"] += 1

    seed_default_tracks(commit=False)

    from asme.ops import bootstrap as ops_bootstrap

    db.session.flush()
    ops_bootstrap.ensure_default_organization(commit=False)
    if commit:
        db.session.commit()
    return created


def _bootstrap_admin(cfg) -> User:
    email = cfg.default_admin_email
    return User(
        name="ASME Admin",
        email=email,
        username=(email.split("@", 1)[0] if "@" in email else "admin"),
        password_hash=generate_password_hash(cfg.default_admin_password),
        role="admin",
        is_active=True,
    )
