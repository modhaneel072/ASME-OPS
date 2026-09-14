"""Cross-cutting tables: comments, attachments, audit, saved filters, notifications."""

from __future__ import annotations

from asme.extensions import db
from asme.ops.types import UUID, JSONDoc, OpsBase, UTCDateTime, user_fk, utcnow, uuid_fk, uuid_pk

COMMENT_ENTITY_TYPES = ("work_order", "project", "asset")
ATTACHMENT_ENTITY_TYPES = ("work_order", "project", "asset", "comment")
SAVED_FILTER_VISIBILITIES = ("private", "team", "chapter")


class Comment(OpsBase, db.Model):
    __tablename__ = "ops_comments"
    __table_args__ = (db.Index("ix_ops_comments_entity", "entity_type", "entity_id"),)

    entity_type = db.Column(db.String(30), nullable=False)
    entity_id = db.Column(UUID, nullable=False)
    author_user_id = user_fk(nullable=False, index=True)
    body = db.Column(db.Text, nullable=False)
    parent_comment_id = uuid_fk("ops_comments.id")
    edited_at = db.Column(UTCDateTime(), nullable=True)
    deleted_at = db.Column(UTCDateTime(), nullable=True)

    author = db.relationship("User", foreign_keys=[author_user_id], lazy="joined")


class Attachment(OpsBase, db.Model):
    __tablename__ = "ops_attachments"
    __table_args__ = (db.Index("ix_ops_attachments_entity", "entity_type", "entity_id"),)

    entity_type = db.Column(db.String(30), nullable=False)
    entity_id = db.Column(UUID, nullable=False)
    storage_key = db.Column(db.String(400), nullable=False, unique=True)
    original_name = db.Column(db.String(260), nullable=False)
    content_type = db.Column(db.String(120), nullable=False)
    size_bytes = db.Column(db.Integer, nullable=False)
    checksum_sha256 = db.Column(db.String(64), nullable=True)
    uploaded_by_user_id = user_fk(nullable=False)
    is_image = db.Column(db.Boolean, nullable=False, default=False)

    uploaded_by = db.relationship("User", foreign_keys=[uploaded_by_user_id], lazy="joined")


class AuditEvent(db.Model):
    """Immutable. Never updated or deleted by application code."""

    __tablename__ = "ops_audit_events"
    __table_args__ = (
        db.Index("ix_ops_audit_events_entity", "entity_type", "entity_id"),
        db.Index("ix_ops_audit_events_org_occurred", "organization_id", "occurred_at"),
    )

    id = uuid_pk()
    organization_id = db.Column(UUID, db.ForeignKey("ops_organizations.id"), nullable=False)
    actor_user_id = user_fk()
    event_type = db.Column(db.String(80), nullable=False, index=True)
    entity_type = db.Column(db.String(40), nullable=False)
    entity_id = db.Column(db.String(40), nullable=False)
    summary = db.Column(db.String(400), nullable=True)
    before_json = db.Column(JSONDoc, nullable=True)
    after_json = db.Column(JSONDoc, nullable=True)
    metadata_json = db.Column(JSONDoc, nullable=True)
    occurred_at = db.Column(UTCDateTime(), nullable=False, default=utcnow)

    actor = db.relationship("User", foreign_keys=[actor_user_id], lazy="joined")


class SavedFilter(OpsBase, db.Model):
    __tablename__ = "ops_saved_filters"

    entity_type = db.Column(db.String(40), nullable=False, index=True)
    owner_user_id = user_fk(nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    visibility = db.Column(db.String(20), nullable=False, default="private")
    team_id = uuid_fk("ops_teams.id")
    filter_json = db.Column(JSONDoc, nullable=False, default=dict)
    sort_json = db.Column(JSONDoc, nullable=True)
    view_type = db.Column(db.String(20), nullable=True)
    is_default = db.Column(db.Boolean, nullable=False, default=False)

    owner = db.relationship("User", foreign_keys=[owner_user_id], lazy="joined")


class Notification(db.Model):
    __tablename__ = "ops_notifications"
    __table_args__ = (
        db.UniqueConstraint("organization_id", "user_id", "dedupe_key", name="uq_ops_notifications_org_user_dedupe"),
        db.Index("ix_ops_notifications_user_unread", "user_id", "read_at"),
    )

    id = uuid_pk()
    organization_id = db.Column(UUID, db.ForeignKey("ops_organizations.id"), nullable=False, index=True)
    user_id = user_fk(nullable=False, index=True)
    type = db.Column(db.String(60), nullable=False)
    title = db.Column(db.String(240), nullable=False)
    body = db.Column(db.Text, nullable=True)
    entity_type = db.Column(db.String(40), nullable=True)
    entity_id = db.Column(db.String(40), nullable=True)
    dedupe_key = db.Column(db.String(160), nullable=True)
    read_at = db.Column(UTCDateTime(), nullable=True)
    created_at = db.Column(UTCDateTime(), nullable=False, default=utcnow, index=True)

    user = db.relationship("User", foreign_keys=[user_id])
