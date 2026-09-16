"""A password-reset e-mail that never leaves the platform is invisible to everyone.

``POST /api/v1/auth/forgot-password`` answers ``{"ok": true, "sent": true}``
before anything is sent - correctly, so the response cannot be used to discover
which addresses belong to members - and queues an ``auth.password_reset`` outbox
job. From there the failure path is silent end to end:

* ``asme/jobs/outbox.py`` retries with ``min(2 ** attempts * 15, 3600)`` seconds
  of backoff and ``max_attempts=5`` from ``enqueue``'s default, so all five
  attempts are spent inside about eight minutes. Any SMTP problem lasting longer
  than that - outbound mail blocked on the hosting platform, an Office 365 app
  password rotated at the end of the year, a tenant throttle, a mailbox that
  needed re-consent - burns the job out on its first afternoon.
* the job is then set to ``status="failed"`` and one line goes to the platform
  log, which on the free plan is kept for seven days and which nobody reads;
* ``asme.jobs.outbox.recent_failures`` and ``stats`` exist but no blueprint
  calls them, so nothing in the product shows a failed job;
* ``asme/services/password_reset.deliver`` retires the token it minted before
  re-raising, so there is no usable link left behind either.

The member sees "check your e-mail", waits, asks an officer, and the officer has
nowhere to look. The chapter concludes that password reset "doesn't work" and
goes back to an officer resetting passwords by hand - which is what the
Launchpad invite flow was built to avoid.

A permanently failed job that a person was waiting on has to surface somewhere a
person will see it: an in-app notification to the administrators, or an audit
event on the chapter, alongside the log line.
"""

from __future__ import annotations

import pytest
from werkzeug.security import generate_password_hash

from asme.extensions import db
from asme.integrations import mail
from asme.jobs import outbox
from asme.models import OutboxJob, User
from asme.ops import bootstrap
from asme.ops.models import AuditEvent, Notification
from tests.conftest import make_app

SMTP_FAILURE = "[Errno 101] Network is unreachable"


@pytest.fixture
def mail_app(monkeypatch):
    application = make_app(smtp_host="smtp.office365.com", smtp_port=587, smtp_user="ops@uiowa.edu", smtp_pass="app-password")
    with application.app_context():
        db.create_all()
        bootstrap.ensure_default_organization()

        def _always_fails(*args, **kwargs):
            raise OSError(SMTP_FAILURE)

        monkeypatch.setattr(mail.smtplib, "SMTP", _always_fails)
        yield application
        db.session.remove()
        db.drop_all()


def test_a_permanently_failed_reset_mail_is_visible_to_someone(mail_app):
    client = mail_app.test_client()
    member = User(
        name="Mo Member",
        email="mo@uiowa.edu",
        username="mo",
        password_hash=generate_password_hash("old-password-value"),
        role="member",
        is_active=True,
    )
    db.session.add(member)
    db.session.commit()

    response = client.post("/api/v1/auth/forgot-password", json={"email": "mo@uiowa.edu"})
    assert response.status_code == 200
    assert response.get_json()["payload"]["sent"] is True, "the member was told the mail was on its way"

    job = OutboxJob.query.filter_by(kind="auth.password_reset").one()
    # Burn through every attempt, as the worker does over the following minutes:
    # the backoff only delays the retries, it never changes the outcome.
    for _ in range(job.max_attempts):
        OutboxJob.query.filter_by(id=job.id).update({OutboxJob.run_at: outbox.datetime.utcnow()})
        db.session.commit()
        outbox.process_pending()
    db.session.refresh(job)
    assert job.status == "failed", f"expected the job to burn out, got {job.status!r}"

    surfaced = Notification.query.count() + AuditEvent.query.count()
    assert surfaced > 0, (
        "the password reset mail failed permanently and nothing in the product says so: "
        "no notification to an administrator, no audit event - only a log line on a free "
        "plan that keeps logs for seven days"
    )
