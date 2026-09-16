"""Two web workers, one database.

The hosting platform runs the app as one or more worker processes, each with its
own copy of the app object, its own database session and its own outbox worker
thread. These tests stand in two independent apps up against a single SQLite
file - the closest thing to that arrangement that runs offline - and check the
two things that must hold no matter how many workers there are:

* a job is executed once, not once per worker;
* the recurring schedule is enqueued once per window, not once per worker.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from asme.extensions import db as _db
from asme.jobs import outbox
from asme.models import OutboxJob
from tests.conftest import make_app


@pytest.fixture
def workers(tmp_path):
    """Two apps sharing one database file, as two web workers would."""
    url = f"sqlite:///{(tmp_path / 'workers.db').as_posix()}"
    first = make_app(database_url=url)
    second = make_app(database_url=url)
    with first.app_context():
        _db.create_all()
    yield first, second
    with first.app_context():
        _db.session.remove()
        _db.drop_all()


def test_a_job_runs_once_even_when_every_worker_polls(workers):
    first, second = workers
    calls = []

    @outbox.handler("test.multiworker.echo")
    def _echo(payload):
        calls.append(payload)

    with first.app_context():
        outbox.enqueue("test.multiworker.echo", {"n": 1})
        _db.session.commit()

    ran = 0
    for app in (first, second, first, second):
        with app.app_context():
            ran += outbox.process_pending()

    assert ran == 1
    assert calls == [{"n": 1}]
    with first.app_context():
        assert [job.status for job in OutboxJob.query.all()] == ["done"]


def test_a_claimed_job_is_invisible_to_the_other_worker(workers):
    first, second = workers
    with first.app_context():
        outbox.enqueue("test.multiworker.claimed", {})
        _db.session.commit()
        job = OutboxJob.query.one()
        assert outbox._claim(job) is True

    with second.app_context():
        assert outbox.process_pending() == 0
        assert OutboxJob.query.one().status == "running"

    # A second claim of the same row loses, whoever makes it.
    with first.app_context():
        assert outbox._claim(OutboxJob.query.one()) is False


def test_the_recurring_schedule_is_enqueued_once_per_window(workers):
    first, second = workers

    with first.app_context():
        assert outbox.schedule_recurring() == len(outbox.RECURRING_JOBS)
    # The second worker, polling moments later, adds nothing.
    with second.app_context():
        assert outbox.schedule_recurring() == 0
    with first.app_context():
        assert outbox.schedule_recurring() == 0

    with first.app_context():
        kinds = sorted(job.kind for job in OutboxJob.query.all())
        assert kinds == sorted(kind for kind, _ in outbox.RECURRING_JOBS)
        assert all(job.idempotency_key for job in OutboxJob.query.all())


def test_a_finished_recurring_job_does_not_come_straight_back(workers):
    first, _second = workers
    with first.app_context():
        assert outbox.ensure_recurring("ops.work_order.scan", timedelta(hours=1)) is True
        job = OutboxJob.query.one()
        job.status = "done"
        job.completed_at = datetime.utcnow()
        _db.session.commit()
        # Still inside the same hour, so nothing is enqueued again.
        assert outbox.ensure_recurring("ops.work_order.scan", timedelta(hours=1)) is False
        assert OutboxJob.query.count() == 1


def test_each_window_gets_its_own_key():
    every = timedelta(hours=1)
    base = datetime(2026, 5, 1, 10, 30, 0)
    assert outbox.recurring_key("k", every, base) == outbox.recurring_key("k", every, base.replace(minute=59))
    assert outbox.recurring_key("k", every, base) != outbox.recurring_key("k", every, base.replace(hour=11))
    assert outbox.recurring_key("a", every, base) != outbox.recurring_key("b", every, base)
    assert len(outbox.recurring_key("k" * 300, every, base)) <= 160


def test_a_duplicate_key_is_refused_by_the_database(workers):
    """The idempotency index, not the lookup before it, is what makes this safe.

    Two workers can both find nothing and both try to insert; the unique index
    decides. ``enqueue_once`` must survive losing that race with its caller's
    transaction intact.
    """
    from sqlalchemy.exc import IntegrityError

    first, _second = workers
    with first.app_context():
        assert outbox.enqueue_once("test.multiworker.key", "same-key") is not None
        _db.session.commit()

        duplicate = OutboxJob(kind="test.multiworker.key", payload_json="{}", status="pending", run_at=datetime.utcnow(), idempotency_key="same-key")
        _db.session.add(duplicate)
        with pytest.raises(IntegrityError):
            _db.session.commit()
        _db.session.rollback()

        assert outbox.enqueue_once("test.multiworker.key", "same-key") is None
        # The session is still usable afterwards.
        outbox.enqueue("test.multiworker.key", {})
        _db.session.commit()
        assert OutboxJob.query.count() == 2
