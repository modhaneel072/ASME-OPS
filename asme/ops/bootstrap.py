"""Default organization, roles, grants, memberships and reference data.

Everything here is idempotent and additive. ``ensure_default_organization`` is
called from ``asme.services.bootstrap.seed_defaults`` (boot / ``manage.py
upgrade``); ``ensure_membership`` also runs at sign-in so users created by
legacy flows (signup, roster import) get an ops membership the first time they
log in after the upgrade.
"""

from __future__ import annotations

import logging

from sqlalchemy import func

from asme.extensions import db
from asme.models import User
from asme.ops import permissions as registry
from asme.ops.models import Category, Location, Membership, Organization, Permission, Role, RolePermission, Sequence
from asme.ops.types import utcnow

log = logging.getLogger("asme.ops.bootstrap")

DEFAULT_ORG_SLUG = "uiowa"
DEFAULT_ORG_NAME = "ASME at the University of Iowa"
DEFAULT_TIMEZONE = "America/Chicago"
DEFAULT_LOCATION_NAME = "General"
WORK_ORDER_SEQUENCE = "work_order"

SEED_CATEGORIES: tuple[tuple[str, str, str], ...] = (
    ("Mechanical", "#0878d1", "wrench"),
    ("Electrical", "#e58a00", "zap"),
    ("Software", "#7c5ce7", "code"),
    ("Embedded Systems", "#0f766e", "cpu"),
    ("Fabrication", "#b45309", "hammer"),
    ("Inspection", "#2563eb", "search-check"),
    ("Safety", "#d84a4a", "shield-alert"),
    ("Preventive", "#00a878", "calendar-check"),
    ("Damage", "#9f1239", "alert-triangle"),
    ("Project", "#475569", "folder-kanban"),
    ("Event", "#c026d3", "calendar"),
    ("Procurement", "#0e7490", "shopping-cart"),
    ("Documentation", "#4b5563", "file-text"),
    ("Standard Operating Procedure", "#1d4ed8", "clipboard-list"),
)


# --------------------------------------------------------------------------- lookups


def default_organization() -> Organization | None:
    return Organization.query.filter_by(slug=DEFAULT_ORG_SLUG).first()


def role_by_key(org: Organization, key: str) -> Role | None:
    return Role.query.filter_by(organization_id=org.id, system_key=key).first()


def membership_for(user, org: Organization | None = None) -> Membership | None:
    org = org or default_organization()
    if not org or not user:
        return None
    return Membership.query.filter_by(organization_id=org.id, user_id=user.id).first()


# --------------------------------------------------------------------------- ensure_*


def ensure_permissions() -> int:
    existing = {row.key: row for row in Permission.query.all()}
    created = 0
    for key, description in registry.PERMISSIONS.items():
        row = existing.get(key)
        if row is None:
            db.session.add(Permission(key=key, description=description))
            created += 1
        elif row.description != description:
            row.description = description
    if created:
        db.session.flush()
    return created


def ensure_system_roles(org: Organization) -> int:
    created = 0
    existing = {role.system_key: role for role in Role.query.filter_by(organization_id=org.id).all() if role.system_key}
    for spec in registry.SYSTEM_ROLES:
        role = existing.get(spec["key"])
        if role is None:
            role = Role(organization_id=org.id, name=spec["name"], system_key=spec["key"], is_custom=False, description=spec["description"])
            db.session.add(role)
            created += 1
        elif not role.description:
            role.description = spec["description"]
    db.session.flush()
    sync_role_grants(org)
    return created


def sync_role_grants(org: Organization) -> int:
    """Add missing default grants to system roles. Never removes grants, so a
    chapter's manual customisation survives upgrades."""
    permissions = {row.key: row for row in Permission.query.all()}
    added = 0
    for role in Role.query.filter_by(organization_id=org.id).all():
        defaults = registry.DEFAULT_GRANTS.get(role.system_key or "", {})
        if not defaults:
            continue
        current = {grant.permission.key for grant in role.grants if grant.permission}
        for key, scope in defaults.items():
            if key in current:
                continue
            permission = permissions.get(key)
            if permission is None:
                continue
            role.grants.append(RolePermission(permission_id=permission.id, scope_type=scope))
            added += 1
    if added:
        db.session.flush()
    return added


def ensure_membership(user, org: Organization | None = None, *, commit: bool = True) -> Membership | None:
    """Give ``user`` a membership in ``org`` (default organization) if missing.

    The ops role is derived from the legacy ``users.role`` only when the
    membership is first created; existing memberships are never changed here.
    """
    org = org or default_organization()
    if org is None or user is None or user.id is None:
        return None
    membership = Membership.query.filter_by(organization_id=org.id, user_id=user.id).first()
    if membership:
        # An invited member becomes active the first time they sign in.
        if membership.member_status == "invited" and user.is_active:
            membership.member_status = "active"
            membership.joined_at = membership.joined_at or utcnow()
            if commit:
                db.session.commit()
            else:
                db.session.flush()
        return membership
    role_key = registry.LEGACY_ROLE_MAP.get((user.role or "").strip().lower(), "full_member")
    role = role_by_key(org, role_key) or role_by_key(org, "full_member")
    if role is None:
        ensure_permissions()
        ensure_system_roles(org)
        role = role_by_key(org, role_key)
    membership = Membership(
        organization_id=org.id,
        user_id=user.id,
        role_id=role.id,
        member_status="active" if user.is_active else "suspended",
    )
    db.session.add(membership)
    if commit:
        db.session.commit()
    else:
        db.session.flush()
    return membership


def ensure_memberships(org: Organization) -> int:
    have = {row.user_id for row in Membership.query.filter_by(organization_id=org.id).all()}
    created = 0
    for user in User.query.order_by(User.id.asc()).all():
        if user.id in have:
            continue
        ensure_membership(user, org, commit=False)
        created += 1
    return created


def ensure_default_location(org: Organization) -> Location:
    location = Location.query.filter_by(organization_id=org.id, is_default=True).first()
    if location:
        return location
    location = Location.query.filter(Location.organization_id == org.id, func.lower(Location.name) == DEFAULT_LOCATION_NAME.lower()).first()
    if location is None:
        location = Location(organization_id=org.id, name=DEFAULT_LOCATION_NAME, description="Default location for assets and parts created without one.")
        db.session.add(location)
    location.is_default = True
    db.session.flush()
    return location


def ensure_seed_categories(org: Organization) -> int:
    existing = {c.name.lower() for c in Category.query.filter_by(organization_id=org.id).all()}
    if existing:
        return 0
    for name, color, icon in SEED_CATEGORIES:
        db.session.add(Category(organization_id=org.id, name=name, color=color, icon=icon))
    db.session.flush()
    return len(SEED_CATEGORIES)


def ensure_sequence(org: Organization, key: str) -> Sequence:
    row = Sequence.query.filter_by(organization_id=org.id, key=key).first()
    if row is None:
        row = Sequence(organization_id=org.id, key=key, next_value=1)
        db.session.add(row)
        db.session.flush()
    return row


def ensure_default_organization(*, commit: bool = True) -> Organization:
    org = default_organization()
    if org is None:
        org = Organization(name=DEFAULT_ORG_NAME, slug=DEFAULT_ORG_SLUG, timezone=DEFAULT_TIMEZONE, settings_json={})
        db.session.add(org)
        db.session.flush()
        log.info("created default organization %s", DEFAULT_ORG_SLUG)
    ensure_permissions()
    ensure_system_roles(org)
    ensure_memberships(org)
    ensure_default_location(org)
    ensure_seed_categories(org)
    ensure_sequence(org, WORK_ORDER_SEQUENCE)
    if commit:
        db.session.commit()
    else:
        db.session.flush()
    return org
