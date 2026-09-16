"""Column types and the base mixin shared by every ``ops_*`` table.

* ``UTCDateTime`` stores naive UTC in the database and always returns
  timezone-aware UTC values, so SQLite (dev) and PostgreSQL (prod) behave the
  same way.
* ``JSONDoc`` is plain JSON everywhere and JSONB on PostgreSQL.
* ``OpsBase`` carries the tenant columns required by the specification:
  UUID primary key, ``organization_id``, timestamps and actor references.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import JSON, DateTime, ForeignKey, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declared_attr
from sqlalchemy.types import TypeDecorator

from asme.extensions import db


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


_log = logging.getLogger("asme.ops.types")


def org_timezone(org) -> ZoneInfo:
    """The chapter's own time zone, falling back to UTC when it is unset or unknown."""
    name = (getattr(org, "timezone", None) or "").strip() or "UTC"
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        _log.warning("organization %s has unknown timezone %r; using UTC", getattr(org, "slug", "?"), name)
        return ZoneInfo("UTC")


def org_today(org, now: datetime | None = None) -> date:
    """Today's date where the chapter is.

    Due dates are days on a calendar, not instants: a milestone due on the 16th
    has until the end of the 16th in Iowa City, which is 05:00 UTC on the 17th.
    Comparing against the UTC date marks it missed while the team is still in
    the shop.
    """
    return (now or utcnow()).astimezone(org_timezone(org)).date()


def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class UTCDateTime(TypeDecorator):
    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if not isinstance(value, datetime):
            raise TypeError(f"UTCDateTime expects datetime, got {type(value)!r}")
        return as_utc(value).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        return as_utc(value)


JSONDoc = JSON().with_variant(JSONB(), "postgresql")
UUID = Uuid(as_uuid=True)


def uuid_pk():
    return db.Column(UUID, primary_key=True, default=uuid.uuid4)


def uuid_fk(target: str, *, nullable: bool = True, index: bool = True, ondelete: str | None = None, **column_kw):
    fk = ForeignKey(target, ondelete=ondelete) if ondelete else ForeignKey(target)
    return db.Column(UUID, fk, nullable=nullable, index=index, **column_kw)


def user_fk(*, nullable: bool = True, index: bool = False, **column_kw):
    return db.Column(db.Integer, ForeignKey("users.id"), nullable=nullable, index=index, **column_kw)


class TimestampMixin:
    created_at = db.Column(UTCDateTime(), nullable=False, default=utcnow)
    updated_at = db.Column(UTCDateTime(), nullable=False, default=utcnow, onupdate=utcnow)


class OpsBase(TimestampMixin):
    """Tenant-owned row: UUID id, organization scope, timestamps, actors."""

    id = uuid_pk()

    @declared_attr
    def organization_id(cls):  # noqa: N805
        return db.Column(UUID, ForeignKey("ops_organizations.id"), nullable=False, index=True)

    @declared_attr
    def created_by_user_id(cls):  # noqa: N805
        return db.Column(db.Integer, ForeignKey("users.id"), nullable=True)

    @declared_attr
    def updated_by_user_id(cls):  # noqa: N805
        return db.Column(db.Integer, ForeignKey("users.id"), nullable=True)


def new_uuid() -> uuid.UUID:
    return uuid.uuid4()


def parse_uuid(value) -> uuid.UUID | None:
    """Lenient UUID parser used by the API layer; returns ``None`` when invalid."""
    if value is None or value == "":
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return None
