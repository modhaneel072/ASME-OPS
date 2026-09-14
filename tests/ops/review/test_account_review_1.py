"""Account review 1: the structured request log must not record a live
password-reset / invite token.

``GET /api/v1/auth/reset-password/<token>`` carries the token in the URL path,
and ``asme.logging_setup`` writes ``request.path`` for every request at INFO in
every environment (production included). Anyone who can read application logs
(log aggregation, CloudWatch, support staff) could lift a valid token from the
log line the SPA produces the moment a person opens their e-mailed or invite
link, and set that account's password. The only sanctioned log of a link is the
development-only WARNING when SMTP is not configured.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

from asme.extensions import db as _db
from asme.models import PasswordResetToken
from asme.services import identity


def _all_log_text(records) -> str:
    parts = []
    for record in records:
        parts.append(record.getMessage())
        extra = getattr(record, "asme", None)
        if extra is not None:
            parts.append(json.dumps(extra, default=str))
    return "\n".join(parts)


def test_request_log_does_not_contain_reset_token(app, client, org, users):
    token = "review1-live-reset-token-abcdefghijklmnopqrstuvwxyz0123"
    _db.session.add(
        PasswordResetToken(user_id=users["member"].id, token=identity.hash_reset_token(token), expires_at=datetime.utcnow() + timedelta(hours=2))
    )
    _db.session.commit()

    request_logger = logging.getLogger("asme.request")
    records: list[logging.LogRecord] = []

    class _Collect(logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = _Collect(level=logging.DEBUG)
    request_logger.addHandler(handler)
    previous = request_logger.level
    request_logger.setLevel(logging.DEBUG)
    try:
        status = client.post("/api/v1/auth/reset-password/status", json={"token": token})
        assert status.status_code == 200, status.get_json()
        done = client.post(
            "/api/v1/auth/reset-password",
            json={"token": token, "password": "a-brand-new-secret", "confirm_password": "a-brand-new-secret"},
        )
        assert done.status_code == 200, done.get_json()
    finally:
        request_logger.removeHandler(handler)
        request_logger.setLevel(previous)

    assert records, "expected the request logger to emit request lines"
    assert token not in _all_log_text(records)
