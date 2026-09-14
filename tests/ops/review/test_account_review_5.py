"""Account review 5: forgot-password response time must not reveal whether an
account exists.

For a known, active address the request synchronously creates a token (INSERT +
COMMIT), queues the e-mail (INSERT) and commits again before answering; for an
unknown address it answers after one SELECT. Against a production database
reached over the network every statement costs a round trip, so the two answers
are separable by timing even though status and body are identical.

The test models a networked database by adding a fixed delay to every SQL
statement, then compares median response times for a known and an unknown
address.
"""

from __future__ import annotations

import statistics
import time

import pytest
from sqlalchemy import event

from asme.extensions import db as _db

STATEMENT_DELAY_SECONDS = 0.004
ROUNDS = 9


@pytest.fixture
def slow_database(app):
    engine = _db.engine

    def _delay(conn, cursor, statement, parameters, context, executemany):
        time.sleep(STATEMENT_DELAY_SECONDS)

    event.listen(engine, "before_cursor_execute", _delay)
    yield
    event.remove(engine, "before_cursor_execute", _delay)


def _elapsed(client, email) -> float:
    started = time.perf_counter()
    response = client.post("/api/v1/auth/forgot-password", json={"email": email})
    elapsed = time.perf_counter() - started
    assert response.status_code == 200, response.get_json()
    assert response.get_json() == {"ok": True, "payload": {"sent": True}}
    return elapsed


def test_forgot_password_timing_does_not_reveal_account_existence(app, org, users, slow_database):
    known, unknown = [], []
    for n in range(ROUNDS):
        client = app.test_client()
        client.environ_base["REMOTE_ADDR"] = f"192.0.2.{n + 1}"
        known.append(_elapsed(client, users["member"].email))
        unknown.append(_elapsed(client, f"nobody{n}@uiowa.edu"))
    gap = statistics.median(known) - statistics.median(unknown)
    # Allow two statements' worth of jitter; the defect costs several.
    assert abs(gap) < STATEMENT_DELAY_SECONDS * 2, f"known={statistics.median(known):.4f}s unknown={statistics.median(unknown):.4f}s"
