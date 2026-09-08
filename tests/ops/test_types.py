import uuid
from datetime import datetime, timezone

from asme.ops.models import Organization
from asme.ops.types import UTCDateTime, as_utc, parse_uuid, utcnow


def test_utc_datetime_roundtrip_is_aware(app, db):
    org = Organization(name="Test Chapter", slug="test-chapter")
    db.session.add(org)
    db.session.commit()
    org_id = org.id
    db.session.expire_all()

    row = db.session.get(Organization, org_id)
    assert isinstance(row.id, uuid.UUID)
    assert row.created_at.tzinfo is timezone.utc
    assert row.updated_at.tzinfo is timezone.utc
    assert abs((utcnow() - row.created_at).total_seconds()) < 5


def test_utc_datetime_normalises_offsets():
    col = UTCDateTime()
    eastern = datetime(2026, 9, 8, 10, 0, tzinfo=timezone.utc).astimezone(timezone(offset=__import__("datetime").timedelta(hours=-5)))
    stored = col.process_bind_param(eastern, None)
    assert stored.tzinfo is None
    assert stored == datetime(2026, 9, 8, 10, 0)
    assert col.process_result_value(stored, None) == datetime(2026, 9, 8, 10, 0, tzinfo=timezone.utc)
    assert as_utc(None) is None


def test_parse_uuid_is_lenient():
    value = uuid.uuid4()
    assert parse_uuid(str(value)) == value
    assert parse_uuid(value) == value
    assert parse_uuid("not-a-uuid") is None
    assert parse_uuid("") is None
    assert parse_uuid(None) is None
