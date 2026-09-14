"""Per-user, per-organization key/value preferences (setup banner, column layouts)."""

from __future__ import annotations

from asme.extensions import db
from asme.ops.models import UserPreference

SETUP_BANNER_DISMISSED = "setup_banner_dismissed"
ALLOWED_KEYS = {SETUP_BANNER_DISMISSED, "work_orders.columns", "work_orders.view", "sidebar.collapsed", "assets.view", "projects.view"}


def get_preference(ctx, key: str, default=None):
    row = UserPreference.query.filter_by(organization_id=ctx.org.id, user_id=ctx.user.id, key=key).first()
    return row.value_json if row is not None else default


def set_preference(ctx, key: str, value, *, commit: bool = True) -> UserPreference:
    if key not in ALLOWED_KEYS:
        raise ValueError(f"unknown preference key {key}")
    row = UserPreference.query.filter_by(organization_id=ctx.org.id, user_id=ctx.user.id, key=key).first()
    if row is None:
        row = UserPreference(organization_id=ctx.org.id, user_id=ctx.user.id, key=key, created_by_user_id=ctx.user.id)
        db.session.add(row)
    row.value_json = value
    row.updated_by_user_id = ctx.user.id
    if commit:
        db.session.commit()
    return row


def all_preferences(ctx) -> dict:
    rows = UserPreference.query.filter_by(organization_id=ctx.org.id, user_id=ctx.user.id).all()
    return {row.key: row.value_json for row in rows}
