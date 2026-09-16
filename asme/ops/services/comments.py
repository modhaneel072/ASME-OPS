"""Comments on work orders, projects, assets, parts and purchase requests
(``ops_comments``).

* Anyone who can read the parent may comment on projects, assets, parts and
  purchase requests; work orders additionally require ``work_order.comment``.
  A purchase request has no single read key - the read rule itself (approvers
  and inventory managers see everything, everyone else their own requests plus
  the ones on projects they manage) is applied by ``entities.resolve`` and is
  stricter than any key would be, so ``COMMENT_KEYS`` maps it to ``None``.
* Mentions are written as ``@[Display Name](user:123)``; every mentioned active
  member is notified (``work_order.mentioned``). On work orders the assignees,
  watchers and creator are told about the new comment (``work_order.commented``).
* Edits and deletes are allowed for the author or anyone who may manage the
  parent entity. Deletes are soft: the row keeps its place in the thread.
* Audit events are recorded against the parent entity (so they show in its
  activity feed and inherit its visibility) with the comment id, entity type
  and entity id in the metadata.
"""

from __future__ import annotations

import re

from sqlalchemy import select

from asme.extensions import db
from asme.models import User
from asme.ops import policy
from asme.ops.models import Comment, Membership
from asme.ops.services import audit_events, entities, notifications
from asme.ops.types import parse_uuid, utcnow
from asme.ops.validation import Field, ValidationErrors, validate
from asme.services.errors import Conflict, Forbidden, NotFound

MAX_BODY_LENGTH = 8000
MENTION_RE = re.compile(r"@\[[^\]\n]{1,160}\]\(user:(\d{1,10})\)")
COMMENT_FIELDS = ("id", "entity_type", "entity_id", "author_user_id", "body", "parent_comment_id", "edited_at", "deleted_at")
COMMENT_KEYS = {
    "work_order": "work_order.comment",
    "project": "project.read",
    "asset": "asset.read",
    "part": "inventory.read",
    # Readability is the rule; see the module docstring.
    "purchase_request": None,
}
NOTIFY_BODY_LENGTH = 500

CREATE_SPEC = {
    "body": Field("text", required=True, max_len=MAX_BODY_LENGTH, min_len=1),
    "parent_comment_id": Field("uuid"),
}
UPDATE_SPEC = {
    "body": Field("text", required=True, max_len=MAX_BODY_LENGTH, min_len=1),
}


# --------------------------------------------------------------------------- mentions


def mentioned_user_ids(body: str) -> list[int]:
    """Distinct user ids mentioned in ``body``, in order of first appearance."""
    seen: list[int] = []
    for match in MENTION_RE.finditer(body or ""):
        user_id = int(match.group(1))
        if user_id not in seen:
            seen.append(user_id)
    return seen


def _active_member_ids(ctx, user_ids: list[int]) -> list[int]:
    if not user_ids:
        return []
    stmt = (
        select(Membership.user_id)
        .join(User, User.id == Membership.user_id)
        .where(
            Membership.organization_id == ctx.org.id,
            Membership.user_id.in_(user_ids),
            Membership.member_status == "active",
            User.is_active.is_(True),
        )
    )
    active = set(db.session.scalars(stmt))
    return [user_id for user_id in user_ids if user_id in active]


def mentioned_users(ctx, rows) -> dict[int, User]:
    """Users mentioned across ``rows`` that belong to the organization, keyed by id."""
    ids: set[int] = set()
    for row in rows:
        if row.deleted_at is None:
            ids.update(mentioned_user_ids(row.body))
    if not ids:
        return {}
    stmt = select(User).join(Membership, Membership.user_id == User.id).where(Membership.organization_id == ctx.org.id, User.id.in_(ids))
    return {user.id: user for user in db.session.scalars(stmt)}


def mentions_for(row, users_by_id: dict[int, User]) -> list[User]:
    if row.deleted_at is not None:
        return []
    return [users_by_id[user_id] for user_id in mentioned_user_ids(row.body) if user_id in users_by_id]


# --------------------------------------------------------------------------- reads


def list_for(ctx, entity_segment: str, entity_id) -> tuple[str, object, list[Comment]]:
    """``(entity_type, obj, comments)`` oldest first; raises ``NotFound`` when unreadable."""
    entity_type, obj = entities.resolve(ctx, entity_segment, entity_id)
    rows = (
        Comment.query.filter_by(organization_id=ctx.org.id, entity_type=entity_type, entity_id=obj.id)
        .order_by(Comment.created_at.asc(), Comment.id.asc())
        .all()
    )
    return entity_type, obj, rows


def _load(ctx, comment_id) -> tuple[Comment, object]:
    """A comment plus its readable parent; either missing -> ``NotFound``."""
    parsed = parse_uuid(comment_id)
    if parsed is None:
        raise NotFound()
    comment = policy.get_or_404(ctx, Comment, parsed)
    parent = entities.load(ctx, comment.entity_type, comment.entity_id)
    return comment, parent


def get(ctx, comment_id) -> Comment:
    comment, _parent = _load(ctx, comment_id)
    return comment


# --------------------------------------------------------------------------- writes


def _audit(ctx, event_type: str, comment: Comment, parent, *, before=None, after=None, summary=None):
    # ``record`` reserves the ``entity_id`` keyword for the audit row itself, so the
    # parent's id is added to the metadata after the row is built.
    event = audit_events.record(
        ctx,
        event_type,
        parent,
        before=before,
        after=after,
        summary=summary,
        comment_id=str(comment.id),
        entity_type=comment.entity_type,
    )
    event.metadata_json = {**(event.metadata_json or {}), "entity_id": str(comment.entity_id)}
    return event


def _notify(ctx, entity_type: str, obj, comment: Comment) -> None:
    actor = ctx.user.display_name if hasattr(ctx.user, "display_name") else ctx.user.name
    target = entities.label(entity_type, obj)
    excerpt = comment.body[:NOTIFY_BODY_LENGTH]
    mentioned = _active_member_ids(ctx, mentioned_user_ids(comment.body))
    if mentioned:
        notifications.notify(ctx, mentioned, "work_order.mentioned", f"{actor} mentioned you on {target}", excerpt, entity=obj)
    if entity_type != "work_order":
        return
    audience = set(obj.assignee_user_ids) | set(obj.watcher_user_ids)
    if obj.created_by_user_id:
        audience.add(obj.created_by_user_id)
    audience -= set(mentioned)
    if audience:
        notifications.notify(ctx, sorted(audience), "work_order.commented", f"{actor} commented on {target}", excerpt, entity=obj)


def create(ctx, entity_segment: str, entity_id, payload: dict) -> Comment:
    entity_type, obj = entities.resolve(ctx, entity_segment, entity_id)
    key = COMMENT_KEYS[entity_type]
    if key is not None:
        policy.authorize(ctx, key, obj)
    data = validate(payload, CREATE_SPEC)
    parent_id = data.get("parent_comment_id")
    if parent_id is not None:
        parent = db.session.get(Comment, parent_id)
        if parent is None or parent.organization_id != ctx.org.id or parent.entity_type != entity_type or parent.entity_id != obj.id:
            raise ValidationErrors({"parent_comment_id": "Reply to a comment on the same item."})
    comment = Comment(
        organization_id=ctx.org.id,
        entity_type=entity_type,
        entity_id=obj.id,
        author_user_id=ctx.user.id,
        body=data["body"],
        parent_comment_id=parent_id,
        created_by_user_id=ctx.user.id,
        updated_by_user_id=ctx.user.id,
    )
    db.session.add(comment)
    db.session.flush()
    _audit(
        ctx,
        "comment.created",
        comment,
        obj,
        after=audit_events.snapshot(comment, COMMENT_FIELDS),
        summary=f"Commented on {entities.label(entity_type, obj)}",
    )
    _notify(ctx, entity_type, obj, comment)
    db.session.commit()
    return comment


def _authorize_change(ctx, comment: Comment, parent) -> None:
    if comment.author_user_id == ctx.user.id:
        return
    if entities.can_manage(ctx, comment.entity_type, parent):
        return
    raise Forbidden("Only the author or someone who manages this item can change this comment.", permission=entities.MANAGE_KEYS[comment.entity_type])


def update(ctx, comment_id, payload: dict) -> Comment:
    comment, parent = _load(ctx, comment_id)
    _authorize_change(ctx, comment, parent)
    if comment.deleted_at is not None:
        raise Conflict("This comment was deleted.", code="comment_deleted")
    data = validate(payload, UPDATE_SPEC)
    before = audit_events.snapshot(comment, COMMENT_FIELDS)
    comment.body = data["body"]
    comment.edited_at = utcnow()
    comment.updated_by_user_id = ctx.user.id
    _audit(
        ctx,
        "comment.updated",
        comment,
        parent,
        before=before,
        after=audit_events.snapshot(comment, COMMENT_FIELDS),
        summary=f"Edited a comment on {entities.label(comment.entity_type, parent)}",
    )
    db.session.commit()
    return comment


def delete(ctx, comment_id) -> Comment:
    comment, parent = _load(ctx, comment_id)
    _authorize_change(ctx, comment, parent)
    if comment.deleted_at is not None:
        raise Conflict("This comment was already deleted.", code="comment_deleted")
    before = audit_events.snapshot(comment, COMMENT_FIELDS)
    comment.deleted_at = utcnow()
    comment.updated_by_user_id = ctx.user.id
    _audit(
        ctx,
        "comment.deleted",
        comment,
        parent,
        before=before,
        after=audit_events.snapshot(comment, COMMENT_FIELDS),
        summary=f"Deleted a comment on {entities.label(comment.entity_type, parent)}",
    )
    db.session.commit()
    return comment
