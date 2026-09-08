"""In-app notifications (``ops_notifications``).

``notify`` is called by other services inside their transaction; it never
commits. Pass ``dedupe_key`` for anything that may be evaluated repeatedly
(overdue scans, reminders) so a user is told once. The e-mail channel is a
Stage 3 follow-up and will be fed from the same call through the outbox.
"""

from __future__ import annotations

from typing import Iterable

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from asme.extensions import db
from asme.ops.models import Notification
from asme.ops.types import utcnow

NOTIFICATION_TYPES = (
    "work_order.assigned",
    "work_order.status_changed",
    "work_order.due_soon",
    "work_order.overdue",
    "work_order.commented",
    "work_order.mentioned",
    "project.added",
    "milestone.at_risk",
    "asset.offline",
    "membership.role_changed",
    "system",
)


def _entity_fields(entity) -> tuple[str | None, str | None]:
    if entity is None:
        return None, None
    from asme.ops.services.audit_events import entity_type_of

    return entity_type_of(entity), str(getattr(entity, "id", "")) or None


def notify(
    ctx,
    user_ids: Iterable[int],
    type: str,
    title: str,
    body: str | None = None,
    *,
    entity=None,
    dedupe_key: str | None = None,
    exclude_actor: bool = True,
) -> list[Notification]:
    """Create one notification per distinct user id. Returns the rows created
    (duplicates by ``dedupe_key`` are skipped silently)."""
    entity_type, entity_id = _entity_fields(entity)
    created: list[Notification] = []
    seen: set[int] = set()
    actor_id = getattr(ctx, "user_id", None)
    for user_id in user_ids:
        if not user_id or user_id in seen:
            continue
        seen.add(user_id)
        if exclude_actor and user_id == actor_id:
            continue
        if dedupe_key:
            existing = Notification.query.filter_by(organization_id=ctx.org.id, user_id=user_id, dedupe_key=dedupe_key[:160]).first()
            if existing:
                continue
        row = Notification(
            organization_id=ctx.org.id,
            user_id=user_id,
            type=type[:60],
            title=title[:240],
            body=body,
            entity_type=entity_type,
            entity_id=entity_id,
            dedupe_key=dedupe_key[:160] if dedupe_key else None,
        )
        try:
            with db.session.begin_nested():
                db.session.add(row)
        except IntegrityError:
            continue
        created.append(row)
    return created


def list_for_user(ctx, *, unread_only: bool = False, limit: int = 50, before=None) -> list[Notification]:
    stmt = select(Notification).where(Notification.organization_id == ctx.org.id, Notification.user_id == ctx.user.id)
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    if before is not None:
        stmt = stmt.where(Notification.created_at < before)
    stmt = stmt.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(limit)
    return list(db.session.scalars(stmt))


def unread_count(ctx) -> int:
    return int(
        db.session.scalar(
            select(func.count(Notification.id)).where(
                Notification.organization_id == ctx.org.id, Notification.user_id == ctx.user.id, Notification.read_at.is_(None)
            )
        )
        or 0
    )


def mark_read(ctx, notification_ids: Iterable | None = None, *, all_unread: bool = False, commit: bool = True) -> int:
    query = Notification.query.filter_by(organization_id=ctx.org.id, user_id=ctx.user.id).filter(Notification.read_at.is_(None))
    if not all_unread:
        ids = [i for i in (notification_ids or []) if i]
        if not ids:
            return 0
        query = query.filter(Notification.id.in_(ids))
    updated = query.update({Notification.read_at: utcnow()}, synchronize_session=False)
    if commit:
        db.session.commit()
    return int(updated)
