"""Tenancy and access-control tables."""

from __future__ import annotations

from asme.extensions import db
from asme.ops.types import UUID, JSONDoc, OpsBase, TimestampMixin, UTCDateTime, user_fk, utcnow, uuid_fk, uuid_pk

MEMBER_STATUSES = ("active", "invited", "suspended")


class Organization(TimestampMixin, db.Model):
    __tablename__ = "ops_organizations"

    id = uuid_pk()
    name = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(80), nullable=False, unique=True, index=True)
    logo_url = db.Column(db.String(500), nullable=True)
    timezone = db.Column(db.String(64), nullable=False, default="America/Chicago")
    academic_year_start_month = db.Column(db.Integer, nullable=False, default=8)
    settings_json = db.Column(JSONDoc, nullable=False, default=dict)
    setup_completed_at = db.Column(UTCDateTime(), nullable=True)

    @property
    def settings(self) -> dict:
        return dict(self.settings_json or {})


class Permission(db.Model):
    """Global catalogue of action keys (seeded from ``asme.ops.permissions``)."""

    __tablename__ = "ops_permissions"

    id = uuid_pk()
    key = db.Column(db.String(80), nullable=False, unique=True, index=True)
    description = db.Column(db.String(300), nullable=False, default="")
    created_at = db.Column(UTCDateTime(), nullable=False, default=utcnow)


class Role(OpsBase, db.Model):
    __tablename__ = "ops_roles"
    __table_args__ = (db.UniqueConstraint("organization_id", "system_key", name="uq_ops_roles_org_system_key"),)

    name = db.Column(db.String(120), nullable=False)
    system_key = db.Column(db.String(40), nullable=True)
    is_custom = db.Column(db.Boolean, nullable=False, default=False)
    description = db.Column(db.String(300), nullable=True)

    grants = db.relationship("RolePermission", back_populates="role", cascade="all, delete-orphan", lazy="selectin")

    def grant_map(self) -> dict[str, str]:
        return {grant.permission.key: grant.scope_type for grant in self.grants if grant.permission}


class RolePermission(db.Model):
    __tablename__ = "ops_role_permissions"
    __table_args__ = (db.UniqueConstraint("role_id", "permission_id", name="uq_ops_role_permissions_role_permission"),)

    id = uuid_pk()
    role_id = uuid_fk("ops_roles.id", nullable=False, ondelete="CASCADE")
    permission_id = uuid_fk("ops_permissions.id", nullable=False)
    scope_type = db.Column(db.String(20), nullable=False, default="chapter")
    created_at = db.Column(UTCDateTime(), nullable=False, default=utcnow)

    role = db.relationship("Role", back_populates="grants")
    permission = db.relationship("Permission", lazy="joined")


class Membership(OpsBase, db.Model):
    __tablename__ = "ops_memberships"
    __table_args__ = (db.UniqueConstraint("organization_id", "user_id", name="uq_ops_memberships_org_user"),)

    user_id = user_fk(nullable=False, index=True)
    role_id = uuid_fk("ops_roles.id", nullable=False)
    member_status = db.Column(db.String(20), nullable=False, default="active", index=True)
    title = db.Column(db.String(120), nullable=True)
    joined_at = db.Column(UTCDateTime(), nullable=False, default=utcnow)
    last_seen_at = db.Column(UTCDateTime(), nullable=True)

    user = db.relationship("User", foreign_keys=[user_id], lazy="joined")
    role = db.relationship("Role", foreign_keys=[role_id], lazy="joined")
    organization = db.relationship("Organization", foreign_keys="Membership.organization_id")

    @property
    def is_active(self) -> bool:
        return self.member_status == "active"


class UserPreference(OpsBase, db.Model):
    __tablename__ = "ops_user_preferences"
    __table_args__ = (db.UniqueConstraint("organization_id", "user_id", "key", name="uq_ops_user_preferences_org_user_key"),)

    user_id = user_fk(nullable=False, index=True)
    key = db.Column(db.String(80), nullable=False)
    value_json = db.Column(JSONDoc, nullable=True)


class Sequence(db.Model):
    """Per-organization counters (work-order numbers, request numbers, ...)."""

    __tablename__ = "ops_sequences"
    __table_args__ = (db.UniqueConstraint("organization_id", "key", name="uq_ops_sequences_org_key"),)

    id = uuid_pk()
    organization_id = db.Column(UUID, db.ForeignKey("ops_organizations.id"), nullable=False, index=True)
    key = db.Column(db.String(40), nullable=False)
    next_value = db.Column(db.Integer, nullable=False, default=1)
