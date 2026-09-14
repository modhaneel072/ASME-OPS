from asme.ops.models import Organization
from asme.ops.numbering import next_number, peek_number


def test_numbers_are_sequential_and_created_on_demand(org, db):
    assert next_number(org.id, "work_order") == 1
    assert next_number(org.id, "work_order") == 2
    assert next_number(org.id, "request") == 1
    assert next_number(org.id, "request") == 2
    db.session.commit()
    assert peek_number(org.id, "work_order") == 3


def test_numbers_are_scoped_per_organization(org, db):
    other = Organization(name="Other Chapter", slug="other")
    db.session.add(other)
    db.session.flush()
    assert next_number(org.id, "work_order") == 1
    assert next_number(other.id, "work_order") == 1
    assert next_number(other.id, "work_order") == 2
    assert next_number(org.id, "work_order") == 2
