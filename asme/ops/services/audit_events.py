"""Immutable audit history for ASME Ops (``ops_audit_events``).

Services call ``record`` inside the transaction that performs the change so
the audit row commits with it. Nothing ever updates or deletes these rows.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select

from asme.extensions import db
from asme.ops.models import AuditEvent
from asme.ops.types import utcnow

_ENTITY_TYPE_OVERRIDES = {"OpsProject": "project"}


def entity_type_of(entity) -> str:
    if isinstance(entity, str):
        return entity
    name = type(entity).__name__
    if name in _ENTITY_TYPE_OVERRIDES:
        return _ENTITY_TYPE_OVERRIDES[name]
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def jsonable(value):
    """Convert ORM/py values into JSON-serialisable primitives."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [jsonable(v) for v in value]
    return str(value)


def snapshot(entity, fields: tuple[str, ...] | list[str]) -> dict:
    return {name: jsonable(getattr(entity, name, None)) for name in fields}


def record(
    ctx,
    event_type: str,
    entity,
    *,
    entity_id=None,
    before: dict | None = None,
    after: dict | None = None,
    summary: str | None = None,
    **metadata,
) -> AuditEvent:
    """Append an audit event. ``entity`` may be an ORM object or an entity-type
    string (then pass ``entity_id``)."""
    if isinstance(entity, str):
        etype = entity
        eid = entity_id
    else:
        etype = entity_type_of(entity)
        eid = entity_id if entity_id is not None else getattr(entity, "id", None)
    row = AuditEvent(
        organization_id=ctx.org.id,
        actor_user_id=getattr(ctx, "user_id", None),
        event_type=event_type[:80],
        entity_type=etype[:40],
        entity_id=str(eid)[:40] if eid is not None else "",
        summary=(summary or "")[:400] or None,
        before_json=jsonable(before) if before is not None else None,
        after_json=jsonable(after) if after is not None else None,
        metadata_json=jsonable(metadata) if metadata else None,
        occurred_at=utcnow(),
    )
    db.session.add(row)
    return row


def list_for_entity(ctx, entity_type: str, entity_id, *, limit: int = 100) -> list[AuditEvent]:
    stmt = (
        select(AuditEvent)
        .where(AuditEvent.organization_id == ctx.org.id, AuditEvent.entity_type == entity_type, AuditEvent.entity_id == str(entity_id))
        .order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc())
        .limit(limit)
    )
    return list(db.session.scalars(stmt))


def recent(ctx, *, since: datetime | None = None, limit: int = 100, entity_types: tuple[str, ...] | None = None) -> list[AuditEvent]:
    stmt = select(AuditEvent).where(AuditEvent.organization_id == ctx.org.id)
    if since is not None:
        stmt = stmt.where(AuditEvent.occurred_at > since)
    if entity_types:
        stmt = stmt.where(AuditEvent.entity_type.in_(entity_types))
    stmt = stmt.order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc()).limit(limit)
    return list(db.session.scalars(stmt))
