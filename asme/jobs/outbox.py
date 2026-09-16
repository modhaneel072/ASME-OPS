"""Transactional outbox + in-process worker.

``enqueue`` adds an ``OutboxJob`` row to the *current* session without
committing, so it lands in the same transaction as the domain write that needs
it. The worker thread (or ``process_pending`` in tests) picks jobs up, retries
with exponential backoff, and marks them failed after ``max_attempts``.

At ~200 members on free-tier hosting a table and a thread is the proportionate
answer; the handler registry is the seam for moving to RQ later.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Callable

from asme.extensions import db
from asme.models import OutboxJob

log = logging.getLogger("asme.jobs")

_handlers: dict[str, Callable[[dict], None]] = {}
_failure_handlers: dict[str, Callable[["OutboxJob", dict, Exception], None]] = {}
_worker_threads: dict[int, threading.Thread] = {}
_stop_events: dict[int, threading.Event] = {}

#: How long a job keeps trying before it is given up on: (attempts, longest gap
#: between attempts, in seconds).
DEFAULT_RETRY_POLICY = (5, 3600)

#: Kinds that deserve more patience than the default. Five attempts with the
#: default backoff are all spent inside about eight minutes, which is shorter
#: than any real mail outage: outbound mail blocked at the host, an app password
#: rotated at officer handover, a provider throttle. A member who asked for a
#: password reset is waiting on these, so they ride out a working day instead
#: (ten attempts spread over roughly four hours).
RETRY_POLICY: dict[str, tuple[int, int]] = {
    "auth.password_reset": (10, 6 * 3600),
    "mail.send": (10, 6 * 3600),
}


def retry_policy(kind: str) -> tuple[int, int]:
    return RETRY_POLICY.get(kind, DEFAULT_RETRY_POLICY)


def handler(kind: str):
    def decorator(fn):
        _handlers[kind] = fn
        return fn

    return decorator


def failure_handler(kind: str):
    """Register what to do when a job of ``kind`` has used up every attempt.

    A permanently failed job that somebody is waiting on must end up somewhere a
    person will look. The hook runs after the job row is marked ``failed`` and is
    committed separately, so anything it raises is logged and never re-fails the
    job or stops the worker.
    """

    def decorator(fn):
        _failure_handlers[kind] = fn
        return fn

    return decorator


def registered_kinds():
    return sorted(_handlers)


def _report_permanent_failure(job: OutboxJob, payload: dict, exc: Exception) -> None:
    fn = _failure_handlers.get(job.kind)
    if fn is None:
        return
    try:
        fn(job, payload, exc)
        db.session.commit()
    except Exception:  # pragma: no cover - defensive; the job is already failed
        db.session.rollback()
        log.exception("outbox failure hook raised for job id=%s kind=%s", job.id, job.kind)


def enqueue(kind: str, payload: dict | None = None, run_at: datetime | None = None, max_attempts: int | None = None) -> OutboxJob:
    job = OutboxJob(
        kind=kind,
        payload_json=json.dumps(payload or {}, default=str),
        status="pending",
        run_at=run_at or datetime.utcnow(),
        max_attempts=max_attempts if max_attempts is not None else retry_policy(kind)[0],
    )
    db.session.add(job)
    return job


def enqueue_once(
    kind: str, idempotency_key: str, payload: dict | None = None, run_at: datetime | None = None, max_attempts: int | None = None
) -> OutboxJob | None:
    """Enqueue ``kind`` unless a job with ``idempotency_key`` already exists.

    Returns the new job, or ``None`` when the key was already used (any status).
    Safe under concurrent callers thanks to the unique constraint; the insert
    runs in a savepoint so a losing race does not poison the caller's transaction.
    """
    from sqlalchemy.exc import IntegrityError

    key = (idempotency_key or "").strip()[:160]
    if not key:
        raise ValueError("enqueue_once requires an idempotency key")
    if OutboxJob.query.filter(OutboxJob.idempotency_key == key).first() is not None:
        return None
    job = OutboxJob(
        kind=kind,
        payload_json=json.dumps(payload or {}, default=str),
        status="pending",
        run_at=run_at or datetime.utcnow(),
        max_attempts=max_attempts if max_attempts is not None else retry_policy(kind)[0],
        idempotency_key=key,
    )
    try:
        with db.session.begin_nested():
            db.session.add(job)
    except IntegrityError:
        return None
    return job


def _claim(job: OutboxJob) -> bool:
    updated = (
        OutboxJob.query.filter(OutboxJob.id == job.id, OutboxJob.status == "pending")
        .update({OutboxJob.status: "running", OutboxJob.locked_at: datetime.utcnow()}, synchronize_session=False)
    )
    db.session.commit()
    return updated == 1


def _run_one(job: OutboxJob) -> bool:
    fn = _handlers.get(job.kind)
    payload = json.loads(job.payload_json or "{}")
    try:
        if fn is None:
            raise RuntimeError(f"no handler registered for job kind '{job.kind}'")
        fn(payload)
        db.session.refresh(job)
        job.status = "done"
        job.completed_at = datetime.utcnow()
        job.last_error = None
        db.session.commit()
        return True
    except Exception as exc:
        db.session.rollback()
        job = db.session.get(OutboxJob, job.id)
        job.attempts = (job.attempts or 0) + 1
        job.last_error = str(exc)[:1000]
        job.locked_at = None
        permanent = job.attempts >= (job.max_attempts or 1)
        if permanent:
            job.status = "failed"
            log.error("outbox job failed permanently id=%s kind=%s error=%s", job.id, job.kind, exc)
        else:
            job.status = "pending"
            job.run_at = datetime.utcnow() + timedelta(seconds=min(2 ** job.attempts * 15, retry_policy(job.kind)[1]))
            log.warning("outbox job retry id=%s kind=%s attempt=%s error=%s", job.id, job.kind, job.attempts, exc)
        db.session.commit()
        if permanent:
            # The log line above is kept for seven days on a free plan and read by
            # nobody. Give the kinds that somebody is waiting on a way to say so
            # inside the product as well (asme/jobs/handlers.py).
            _report_permanent_failure(job, payload, exc)
        return False


def process_pending(limit: int = 20) -> int:
    """Run due jobs once. Returns how many succeeded. Safe to call from anywhere
    inside an app context (tests call it directly)."""
    now = datetime.utcnow()
    # Release jobs stuck in "running" for more than 10 minutes (crashed worker).
    stale = now - timedelta(minutes=10)
    OutboxJob.query.filter(OutboxJob.status == "running", OutboxJob.locked_at < stale).update(
        {OutboxJob.status: "pending", OutboxJob.locked_at: None}, synchronize_session=False
    )
    db.session.commit()

    jobs = (
        OutboxJob.query.filter(OutboxJob.status == "pending", OutboxJob.run_at <= now)
        .order_by(OutboxJob.run_at.asc(), OutboxJob.id.asc())
        .limit(limit)
        .all()
    )
    succeeded = 0
    for job in jobs:
        if not _claim(job):
            continue
        if _run_one(job):
            succeeded += 1
    return succeeded


def recurring_key(kind: str, every: timedelta, now: datetime | None = None) -> str:
    """The idempotency key for ``kind`` in the window ``now`` falls into.

    Windows are fixed slices of the UTC clock rather than a sliding "was one
    enqueued recently" test, so every process computes the same key for the same
    moment. That is what makes :func:`ensure_recurring` safe to call from more
    than one web worker, or from a web worker and a dedicated worker process at
    the same time: they all race to insert the same key and the unique index
    ``uq_outbox_jobs_idempotency_key`` lets exactly one of them win.
    """
    seconds = max(1, int(every.total_seconds()))
    moment = now or datetime.utcnow()
    window = int(moment.replace(tzinfo=timezone.utc).timestamp()) // seconds
    return f"recurring:{kind}:{window}"[:160]


def ensure_recurring(kind: str, every: timedelta, payload: dict | None = None) -> bool:
    """Make sure exactly one job of ``kind`` is enqueued per ``every`` window.

    Returns ``True`` when this caller is the one that enqueued it. Concurrent
    callers - one per gunicorn worker, plus any dedicated worker process - get
    ``False`` and enqueue nothing.
    """
    now = datetime.utcnow()
    job = enqueue_once(kind, recurring_key(kind, every, now), payload or {}, run_at=now, max_attempts=3)
    if job is None:
        return False
    db.session.commit()
    return True


def stats():
    rows = db.session.query(OutboxJob.status, db.func.count(OutboxJob.id)).group_by(OutboxJob.status).all()
    return {status: int(count) for status, count in rows}


def recent_failures(limit=25):
    return OutboxJob.query.filter(OutboxJob.status == "failed").order_by(OutboxJob.id.desc()).limit(limit).all()


def retry(job: OutboxJob):
    job.status = "pending"
    job.attempts = 0
    job.run_at = datetime.utcnow()
    job.last_error = None
    db.session.commit()


# --------------------------------------------------------------------------- worker thread


#: The jobs nobody enqueues by hand: (kind, how often). One list, used by the
#: in-process worker thread and by ``python manage.py worker`` alike, so a
#: dedicated worker process is a complete replacement for the thread rather than
#: a silent downgrade that stops the schedule.
RECURRING_JOBS: tuple[tuple[str, timedelta], ...] = (
    ("stock.reconcile", timedelta(hours=24)),
    ("ops.work_order.scan", timedelta(hours=1)),
)


def schedule_recurring() -> int:
    """Enqueue every due recurring job. Returns how many this caller enqueued."""
    return sum(1 for kind, every in RECURRING_JOBS if ensure_recurring(kind, every))


def _loop(app, stop_event: threading.Event):
    cfg = app.config["SETTINGS"]
    with app.app_context():
        while not stop_event.is_set():
            try:
                schedule_recurring()
                process_pending()
            except Exception:  # pragma: no cover - defensive
                log.exception("outbox worker iteration failed")
                try:
                    db.session.rollback()
                except Exception:
                    pass
            finally:
                db.session.remove()
            stop_event.wait(cfg.outbox_poll_seconds)


def start_worker(app) -> threading.Thread | None:
    key = id(app)
    if key in _worker_threads and _worker_threads[key].is_alive():
        return _worker_threads[key]
    stop_event = threading.Event()
    thread = threading.Thread(target=_loop, args=(app, stop_event), name="asme-outbox", daemon=True)
    thread.start()
    _worker_threads[key] = thread
    _stop_events[key] = stop_event
    return thread


def stop_worker(app):
    key = id(app)
    event = _stop_events.pop(key, None)
    if event:
        event.set()
    thread = _worker_threads.pop(key, None)
    if thread:
        thread.join(timeout=2)
