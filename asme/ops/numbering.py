"""Per-organization sequential numbers (work orders, requests, purchases).

Uses ``UPDATE ... RETURNING`` so two concurrent transactions can never hand
out the same number on PostgreSQL; SQLite serialises writers anyway and
supports RETURNING since 3.35.
"""

from __future__ import annotations

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from asme.extensions import db
from asme.ops.models import Sequence


def next_number(org_id, key: str) -> int:
    """Reserve and return the next number for ``key`` inside the current transaction."""
    for _attempt in range(2):
        stmt = (
            update(Sequence)
            .where(Sequence.organization_id == org_id, Sequence.key == key)
            .values(next_value=Sequence.next_value + 1)
            .returning(Sequence.next_value)
        )
        row = db.session.execute(stmt).first()
        if row is not None:
            return int(row[0]) - 1
        # First number for this key: create the counter, then loop to claim.
        try:
            with db.session.begin_nested():
                db.session.add(Sequence(organization_id=org_id, key=key, next_value=1))
        except IntegrityError:
            # Another transaction created it between our UPDATE and INSERT.
            pass
    raise RuntimeError(f"could not allocate a number for {key}")


def peek_number(org_id, key: str) -> int:
    row = Sequence.query.filter_by(organization_id=org_id, key=key).first()
    return int(row.next_value) if row else 1
