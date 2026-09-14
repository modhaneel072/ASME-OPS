"""Account flows for the ASME Ops SPA: forgot password, reset / set password from
an e-mailed or invite link, change password and editing one's own profile."""

from __future__ import annotations

import dataclasses
import json
import logging
import re
import smtplib
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import event
from werkzeug.security import check_password_hash, generate_password_hash

from asme.extensions import db as _db
from asme.integrations import mail
from asme.jobs import outbox
from asme.models import OutboxJob, PasswordResetToken, User
from asme.services import identity, password_reset
from tests.conftest import PASSWORD

NEW_PASSWORD = "a-brand-new-secret"
DEV_LOG_PREFIX = password_reset.DEV_LOG_PREFIX
LINK_RE = re.compile(r"(https?://[^\s]+/app/auth/reset-password#token=([A-Za-z0-9_\-]+))")


def _settings(app, **changes):
    app.config["SETTINGS"] = dataclasses.replace(app.config["SETTINGS"], **changes)


@pytest.fixture
def no_smtp(app):
    _settings(app, smtp_user="", smtp_pass="")


@pytest.fixture
def outbox_mail(app, monkeypatch):
    """SMTP configured; messages are captured instead of sent."""
    _settings(app, smtp_user="chapter@uiowa.edu", smtp_pass="app-password")
    sent: list[dict] = []

    def _send(cfg, to, subject, body):
        sent.append({"to": to, "subject": subject, "body": body})

    monkeypatch.setattr(mail, "send_email", _send)
    return sent


@pytest.fixture
def limiter(app):
    row = app.extensions["asme_login_rate_limiter"]
    original = row.max_attempts
    row.max_attempts = 2
    yield row
    row.max_attempts = original


def _reset_jobs():
    return [json.loads(job.payload_json) for job in OutboxJob.query.filter_by(kind=password_reset.JOB_KIND).order_by(OutboxJob.id).all()]


def _token_for(user) -> PasswordResetToken:
    return PasswordResetToken.query.filter_by(user_id=user.id).order_by(PasswordResetToken.id.desc()).first()


def _add_token(user, *, hours=2, used=False) -> str:
    token = f"tok-{user.id}-{hours}-{int(used)}-{PasswordResetToken.query.count()}"
    _db.session.add(
        PasswordResetToken(
            user_id=user.id,
            token=identity.hash_reset_token(token),
            expires_at=datetime.utcnow() + timedelta(hours=hours),
            used_at=datetime.utcnow() if used else None,
        )
    )
    _db.session.commit()
    return token


def _link(text: str) -> tuple[str, str]:
    match = LINK_RE.search(text)
    assert match, text
    return match.group(1), match.group(2)


def _status(client, token):
    return client.post("/api/v1/auth/reset-password/status", json={"token": token})


def _login_status(client, email, password):
    return client.post("/api/v1/auth/login", json={"identifier": email, "password": password}).status_code


# --------------------------------------------------------------------------- forgot password


def test_forgot_password_queues_a_job_and_the_worker_mails_a_fragment_link(client, org, users, outbox_mail):
    response = client.post("/api/v1/auth/forgot-password", json={"email": "  MO@UIowa.edu "})
    assert response.status_code == 200, response.get_json()
    assert response.get_json() == {"ok": True, "payload": {"sent": True}}

    # The request itself only queues work: no account lookup, no token yet.
    assert _reset_jobs() == [{"email": "mo@uiowa.edu", "origin": "http://localhost"}]
    assert PasswordResetToken.query.count() == 0 and outbox_mail == []

    assert outbox.process_pending() == 1
    assert len(outbox_mail) == 1
    message = outbox_mail[0]
    assert message["to"] == "mo@uiowa.edu" and message["subject"] == "Reset your ASME Ops password"
    link, token = _link(message["body"])
    assert link.startswith("http://localhost/app/auth/reset-password#token=")

    reset = _token_for(users["member"])
    assert reset is not None and reset.used_at is None
    assert reset.token == identity.hash_reset_token(token) and reset.token != token
    assert reset.expires_at > datetime.utcnow() + timedelta(minutes=110)
    assert identity.find_valid_reset(token).id == reset.id

    # The link never sits in the outbox table.
    assert OutboxJob.query.filter_by(kind="mail.send").count() == 0
    assert not any(token in (job.payload_json or "") for job in OutboxJob.query.all())


def test_forgot_password_unknown_or_inactive_email_is_indistinguishable(client, org, users, outbox_mail):
    users["lead"].is_active = False
    _db.session.commit()

    unknown = client.post("/api/v1/auth/forgot-password", json={"email": "nobody@uiowa.edu"})
    inactive = client.post("/api/v1/auth/forgot-password", json={"email": "lee@uiowa.edu"})
    known = client.post("/api/v1/auth/forgot-password", json={"email": "mo@uiowa.edu"})
    for response in (unknown, inactive, known):
        assert response.status_code == 200
        assert response.get_json() == {"ok": True, "payload": {"sent": True}}
    assert [set(job) for job in _reset_jobs()] == [{"email", "origin"}] * 3

    assert outbox.process_pending() == 3
    assert [message["to"] for message in outbox_mail] == ["mo@uiowa.edu"]
    assert PasswordResetToken.query.filter_by(user_id=users["lead"].id).count() == 0
    assert PasswordResetToken.query.count() == 1


def test_forgot_password_request_does_the_same_database_work_for_any_address(app, client, org, users, no_smtp):
    statements: list[str] = []

    def _record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.split(None, 1)[0].upper())

    event.listen(_db.engine, "before_cursor_execute", _record)
    try:
        client.post("/api/v1/auth/forgot-password", json={"email": "mo@uiowa.edu"})
        known = list(statements)
        statements.clear()
        client.post("/api/v1/auth/forgot-password", json={"email": "nobody@uiowa.edu"})
        unknown = list(statements)
    finally:
        event.remove(_db.engine, "before_cursor_execute", _record)
    assert known == unknown and known


def test_forgot_password_validation(client, org, users):
    missing = client.post("/api/v1/auth/forgot-password", json={})
    assert missing.status_code == 400 and missing.get_json()["code"] == "validation"
    assert set(missing.get_json()["errors"]) == {"email"}
    malformed = client.post("/api/v1/auth/forgot-password", json={"email": "not-an-email"})
    assert malformed.status_code == 400 and malformed.get_json()["code"] == "validation"
    assert set(malformed.get_json()["errors"]) == {"email"}
    wrong_type = client.post("/api/v1/auth/forgot-password", json={"email": 42})
    assert wrong_type.status_code == 400 and "email" in wrong_type.get_json()["errors"]
    assert _reset_jobs() == [] and PasswordResetToken.query.count() == 0


def test_forgot_password_logs_link_in_development_without_smtp(app, client, org, users, caplog, no_smtp):
    _settings(app, env="development")
    response = client.post("/api/v1/auth/forgot-password", json={"email": "mo@uiowa.edu"})
    assert response.status_code == 200
    with caplog.at_level(logging.WARNING, logger="asme.ops.auth"):
        outbox.process_pending()
    warnings = [record for record in caplog.records if record.levelno == logging.WARNING and record.getMessage().startswith(DEV_LOG_PREFIX)]
    assert len(warnings) == 1
    _, token = _link(warnings[0].getMessage())
    assert identity.find_valid_reset(token) is not None
    assert token not in response.get_data(as_text=True)

    # Unknown addresses log nothing.
    caplog.clear()
    client.post("/api/v1/auth/forgot-password", json={"email": "nobody@uiowa.edu"})
    with caplog.at_level(logging.WARNING, logger="asme.ops.auth"):
        outbox.process_pending()
    assert not [record for record in caplog.records if DEV_LOG_PREFIX in record.getMessage()]


def test_production_never_logs_links_and_needs_smtp_and_a_public_url(app, client, org, users, caplog, monkeypatch):
    sent: list[str] = []
    monkeypatch.setattr(mail, "send_email", lambda cfg, to, subject, body: sent.append(body))

    # Production without SMTP: nothing is issued, and the log says why without a link.
    _settings(app, env="production", smtp_user="", smtp_pass="", public_base_url="https://ops.asme.example")
    with caplog.at_level(logging.DEBUG):
        response = client.post("/api/v1/auth/forgot-password", json={"email": "mo@uiowa.edu"})
        outbox.process_pending()
    assert response.status_code == 200 and response.get_json()["payload"] == {"sent": True}
    assert PasswordResetToken.query.count() == 0 and sent == []
    assert not [record for record in caplog.records if DEV_LOG_PREFIX in record.getMessage() or "#token=" in record.getMessage()]
    assert [record for record in caplog.records if "SMTP is not configured" in record.getMessage()]

    # Production without a public URL: the forged-able request host is never used.
    caplog.clear()
    _settings(app, smtp_user="chapter@uiowa.edu", smtp_pass="app-password", public_base_url="")
    with caplog.at_level(logging.DEBUG):
        client.post("/api/v1/auth/forgot-password", json={"email": "mo@uiowa.edu"}, headers={"Host": "attacker.example"})
        outbox.process_pending()
    assert _reset_jobs()[-1]["origin"] is None
    assert PasswordResetToken.query.count() == 0 and sent == []
    assert [record for record in caplog.records if "ASME_PUBLIC_BASE_URL is not set" in record.getMessage()]

    # Properly configured production: mailed, never logged.
    caplog.clear()
    _settings(app, public_base_url="https://ops.asme.example")
    with caplog.at_level(logging.DEBUG):
        client.post("/api/v1/auth/forgot-password", json={"email": "mo@uiowa.edu"})
        outbox.process_pending()
    assert len(sent) == 1
    link, token = _link(sent[0])
    assert link.startswith("https://ops.asme.example/app/auth/reset-password#token=")
    assert not [record for record in caplog.records if token in record.getMessage() or DEV_LOG_PREFIX in record.getMessage()]


def test_failed_mail_retires_the_token_and_keeps_it_out_of_the_job_error(app, client, org, users, monkeypatch):
    _settings(app, smtp_user="chapter@uiowa.edu", smtp_pass="app-password")

    def _boom(cfg, to, subject, body):
        raise smtplib.SMTPServerDisconnected(f"lost connection while sending {body}")

    monkeypatch.setattr(mail, "send_email", _boom)
    client.post("/api/v1/auth/forgot-password", json={"email": "mo@uiowa.edu"})
    assert outbox.process_pending() == 0

    job = OutboxJob.query.filter_by(kind=password_reset.JOB_KIND).one()
    assert job.status == "pending" and job.attempts == 1
    assert "reset-password" not in (job.last_error or "") and "SMTPServerDisconnected" in job.last_error
    rows = PasswordResetToken.query.filter_by(user_id=users["member"].id).all()
    assert len(rows) == 1 and rows[0].used_at is not None


def test_forgot_password_is_rate_limited(client, org, users, limiter, no_smtp):
    for _ in range(2):
        assert client.post("/api/v1/auth/forgot-password", json={"email": "mo@uiowa.edu"}).status_code == 200
    blocked = client.post("/api/v1/auth/forgot-password", json={"email": "MO@uiowa.edu"})
    assert blocked.status_code == 429
    body = blocked.get_json()
    assert body["code"] == "rate_limited" and body["retry_after"] >= 1
    assert len(_reset_jobs()) == 2
    # Unknown addresses are counted the same way, so the limiter reveals nothing.
    for _ in range(2):
        client.post("/api/v1/auth/forgot-password", json={"email": "ghost@uiowa.edu"})
    assert client.post("/api/v1/auth/forgot-password", json={"email": "ghost@uiowa.edu"}).status_code == 429
    # Reset requests never lock the account out of signing in.
    assert _login_status(client, "mo@uiowa.edu", PASSWORD) == 200


# --------------------------------------------------------------------------- reset password: status


def test_reset_token_status_invite_vs_reset_and_masked_email(client, org, users, api_login):
    invite_token = _add_token(users["member"])  # never signed in
    status = _status(client, invite_token)
    assert status.status_code == 200, status.get_json()
    payload = status.get_json()["payload"]
    assert payload["valid"] is True and payload["purpose"] == "invite"
    assert payload["email"] == "m***@uiowa.edu"
    assert payload["expires_at"].endswith("Z")
    expires = datetime.fromisoformat(payload["expires_at"][:-1])
    assert timedelta(minutes=110) < expires - datetime.utcnow() < timedelta(minutes=130)
    assert set(payload) == {"valid", "purpose", "email", "expires_at"}

    api_login(users["admin"])  # sets last_login_at
    client.post("/api/v1/auth/logout", json={})
    reset_token = _add_token(users["admin"])
    again = _status(client, reset_token).get_json()["payload"]
    assert again["purpose"] == "reset" and again["email"] == "a***@uiowa.edu"


def test_reset_token_status_rejects_unknown_used_expired_inactive_and_digests(client, org, users):
    expired = _add_token(users["member"], hours=-1)
    used = _add_token(users["member"], used=True)
    inactive = _add_token(users["lead"])
    live = _add_token(users["member"])
    users["lead"].is_active = False
    _db.session.commit()
    stored_digest = identity.hash_reset_token(live)  # what a database reader would see
    for token in ("definitely-not-a-token", expired, used, inactive, stored_digest):
        response = _status(client, token)
        assert response.status_code == 404, token
        assert response.get_json()["code"] == "invalid_token"

    missing = client.post("/api/v1/auth/reset-password/status", json={})
    assert missing.status_code == 400 and set(missing.get_json()["errors"]) == {"token"}
    # The token is never accepted in a URL.
    assert client.get(f"/api/v1/auth/reset-password/{live}").status_code in (404, 405)


# --------------------------------------------------------------------------- reset password: submit


def test_reset_password_sets_password_once_and_does_not_sign_in(client, org, users, outbox_mail):
    member = users["member"]
    client.post("/api/v1/auth/forgot-password", json={"email": member.email})
    outbox.process_pending()
    _, token = _link(outbox_mail[0]["body"])
    older = _add_token(member)  # an earlier link that must stop working too

    done = client.post("/api/v1/auth/reset-password", json={"token": token, "password": NEW_PASSWORD, "confirm_password": NEW_PASSWORD})
    assert done.status_code == 200, done.get_json()
    assert done.get_json() == {"ok": True, "payload": {"reset": True}}
    assert token not in done.get_data(as_text=True)

    # not signed in automatically
    assert client.get("/api/v1/session").status_code == 401

    _db.session.expire_all()
    row = PasswordResetToken.query.filter_by(token=identity.hash_reset_token(token)).one()
    assert row.used_at is not None
    assert check_password_hash(_db.session.get(User, member.id).password_hash, NEW_PASSWORD)

    # single use
    reuse = client.post("/api/v1/auth/reset-password", json={"token": token, "password": "another-secret-1", "confirm_password": "another-secret-1"})
    assert reuse.status_code == 404 and reuse.get_json()["code"] == "invalid_token"
    assert _status(client, token).status_code == 404
    # earlier outstanding links are retired by the successful reset
    stale = client.post("/api/v1/auth/reset-password", json={"token": older, "password": "another-secret-1", "confirm_password": "another-secret-1"})
    assert stale.status_code == 404

    assert _login_status(client, member.email, PASSWORD) == 401
    assert _login_status(client, member.email, "another-secret-1") == 401
    assert _login_status(client, member.email, NEW_PASSWORD) == 200


def test_reset_password_validation_and_invalid_tokens(client, org, users):
    member = users["member"]
    token = _add_token(member)

    empty = client.post("/api/v1/auth/reset-password", json={})
    assert empty.status_code == 400 and set(empty.get_json()["errors"]) == {"token", "password", "confirm_password"}

    short = client.post("/api/v1/auth/reset-password", json={"token": token, "password": "short", "confirm_password": "short"})
    assert short.status_code == 400 and short.get_json()["code"] == "validation"
    assert set(short.get_json()["errors"]) == {"password"}

    mismatch = client.post("/api/v1/auth/reset-password", json={"token": token, "password": NEW_PASSWORD, "confirm_password": NEW_PASSWORD + "x"})
    assert mismatch.status_code == 400 and set(mismatch.get_json()["errors"]) == {"confirm_password"}

    # validation failures do not burn the token
    assert _status(client, token).status_code == 200

    expired = _add_token(member, hours=-1)
    used = _add_token(member, used=True)
    for bad in ("unknown-token", expired, used, identity.hash_reset_token(token)):
        response = client.post("/api/v1/auth/reset-password", json={"token": bad, "password": NEW_PASSWORD, "confirm_password": NEW_PASSWORD})
        assert response.status_code == 404 and response.get_json()["code"] == "invalid_token", bad

    _db.session.expire_all()
    assert check_password_hash(_db.session.get(User, member.id).password_hash, PASSWORD)


def test_reset_password_is_rate_limited(client, org, users, limiter):
    token = _add_token(users["member"])
    for guess in ("guess-1", "guess-2"):
        response = client.post("/api/v1/auth/reset-password", json={"token": guess, "password": NEW_PASSWORD, "confirm_password": NEW_PASSWORD})
        assert response.status_code == 404
    blocked = client.post("/api/v1/auth/reset-password", json={"token": token, "password": NEW_PASSWORD, "confirm_password": NEW_PASSWORD})
    assert blocked.status_code == 429 and blocked.get_json()["code"] == "rate_limited" and blocked.get_json()["retry_after"] >= 1
    assert identity.find_valid_reset(token) is not None


# --------------------------------------------------------------------------- change password


def test_change_password(client, org, users, api_login):
    member = users["member"]
    api_login(member)

    wrong = client.post("/api/v1/auth/change-password", json={"current_password": "not-it", "new_password": NEW_PASSWORD, "confirm_password": NEW_PASSWORD})
    assert wrong.status_code == 400 and wrong.get_json()["code"] == "validation"
    assert set(wrong.get_json()["errors"]) == {"current_password"}

    short = client.post("/api/v1/auth/change-password", json={"current_password": PASSWORD, "new_password": "short", "confirm_password": "short"})
    assert short.status_code == 400 and set(short.get_json()["errors"]) == {"new_password"}

    mismatch = client.post("/api/v1/auth/change-password", json={"current_password": PASSWORD, "new_password": NEW_PASSWORD, "confirm_password": "different-one"})
    assert mismatch.status_code == 400 and set(mismatch.get_json()["errors"]) == {"confirm_password"}

    missing = client.post("/api/v1/auth/change-password", json={})
    assert missing.status_code == 400 and set(missing.get_json()["errors"]) == {"current_password", "new_password", "confirm_password"}

    outstanding = _add_token(member)
    done = client.post("/api/v1/auth/change-password", json={"current_password": PASSWORD, "new_password": NEW_PASSWORD, "confirm_password": NEW_PASSWORD})
    assert done.status_code == 200, done.get_json()
    assert done.get_json() == {"ok": True, "payload": {"changed": True}}
    # still signed in, and links issued before the change no longer work
    assert client.get("/api/v1/session").status_code == 200
    assert _status(client, outstanding).status_code == 404

    client.post("/api/v1/auth/logout", json={})
    assert _login_status(client, member.email, PASSWORD) == 401
    assert _login_status(client, member.email, NEW_PASSWORD) == 200


def test_administrator_password_reset_ends_existing_sessions(app, client, org, users, api_login):
    member = users["member"]
    other = app.test_client()
    assert other.post("/api/v1/auth/login", json={"identifier": member.email, "password": PASSWORD}).status_code == 200
    assert other.get("/api/v1/session").status_code == 200

    member.password_hash = generate_password_hash("set-by-an-admin-1")
    _db.session.commit()
    assert other.get("/api/v1/session").status_code == 401


def test_change_password_requires_sign_in_and_is_rate_limited(client, org, users, api_login, limiter):
    signed_out = client.post("/api/v1/auth/change-password", json={"current_password": PASSWORD, "new_password": NEW_PASSWORD, "confirm_password": NEW_PASSWORD})
    assert signed_out.status_code == 401 and signed_out.get_json()["code"] == "login_required"

    api_login(users["member"])
    for _ in range(2):
        assert client.post("/api/v1/auth/change-password", json={"current_password": "guess", "new_password": NEW_PASSWORD, "confirm_password": NEW_PASSWORD}).status_code == 400
    blocked = client.post("/api/v1/auth/change-password", json={"current_password": PASSWORD, "new_password": NEW_PASSWORD, "confirm_password": NEW_PASSWORD})
    assert blocked.status_code == 429 and blocked.get_json()["code"] == "rate_limited"
    _db.session.expire_all()
    assert check_password_hash(_db.session.get(User, users["member"].id).password_hash, PASSWORD)


# --------------------------------------------------------------------------- profile


def test_patch_profile_updates_and_returns_session(client, org, users, api_login):
    lead = users["lead"]
    api_login(lead)
    response = client.patch(
        "/api/v1/session/profile",
        json={"name": "  Lee Q. Lead ", "major": "Mechanical Engineering", "graduation_year": 2028, "phone": "+1 (319) 555-0100"},
    )
    assert response.status_code == 200, response.get_json()
    session = response.get_json()["payload"]["session"]
    assert session == client.get("/api/v1/session").get_json()["payload"]
    assert session["user"]["name"] == "Lee Q. Lead"
    assert session["user"]["major"] == "Mechanical Engineering" and session["user"]["graduation_year"] == 2028
    assert session["user"]["email"] == "lee@uiowa.edu"
    assert session["user"]["phone"] == "+1 (319) 555-0100"

    _db.session.expire_all()
    fresh = _db.session.get(User, lead.id)
    assert fresh.phone == "+1 (319) 555-0100" and fresh.email == "lee@uiowa.edu"

    # partial update leaves other fields alone; null clears an optional field
    partial = client.patch("/api/v1/session/profile", json={"major": None, "phone": ""})
    assert partial.status_code == 200, partial.get_json()
    user = partial.get_json()["payload"]["session"]["user"]
    assert user["major"] is None and user["graduation_year"] == 2028 and user["name"] == "Lee Q. Lead"
    assert user["phone"] is None
    _db.session.expire_all()
    assert _db.session.get(User, lead.id).phone is None


def test_patch_profile_validation_and_auth(client, org, users, api_login):
    signed_out = client.patch("/api/v1/session/profile", json={"name": "Nobody"})
    assert signed_out.status_code == 401

    api_login(users["member"])
    bad = client.patch(
        "/api/v1/session/profile",
        json={"name": "", "major": "m" * 121, "graduation_year": 1800, "phone": "call me maybe"},
    )
    assert bad.status_code == 400 and bad.get_json()["code"] == "validation"
    assert set(bad.get_json()["errors"]) == {"name", "major", "graduation_year", "phone"}

    wrong_types = client.patch("/api/v1/session/profile", json={"name": 7, "graduation_year": "soon"})
    assert wrong_types.status_code == 400 and set(wrong_types.get_json()["errors"]) == {"name", "graduation_year"}

    email = client.patch("/api/v1/session/profile", json={"email": "someone.else@uiowa.edu"})
    assert email.status_code == 400 and set(email.get_json()["errors"]) == {"email"}

    _db.session.expire_all()
    fresh = _db.session.get(User, users["member"].id)
    assert fresh.name == "Mo Member" and fresh.email == "mo@uiowa.edu" and fresh.graduation_year is None


# --------------------------------------------------------------------------- JSON-only guard


def test_account_flow_mutations_require_json(client, org, users, api_login):
    token = _add_token(users["member"])
    for path, data in (
        ("/api/v1/auth/forgot-password", {"email": "mo@uiowa.edu"}),
        ("/api/v1/auth/reset-password/status", {"token": token}),
        ("/api/v1/auth/reset-password", {"token": token, "password": NEW_PASSWORD, "confirm_password": NEW_PASSWORD}),
    ):
        response = client.post(path, data=data)
        assert response.status_code == 415 and response.get_json()["code"] == "json_required", path
    assert _reset_jobs() == []
    assert identity.find_valid_reset(token) is not None

    api_login(users["member"])
    change = client.post("/api/v1/auth/change-password", data={"current_password": PASSWORD, "new_password": NEW_PASSWORD, "confirm_password": NEW_PASSWORD})
    assert change.status_code == 415
    profile = client.patch("/api/v1/session/profile", data={"name": "Form Post"})
    assert profile.status_code == 415


def test_invite_link_opens_spa_reset_flow(client, org, users, api_login):
    api_login(users["admin"])
    invited = client.post("/api/v1/users/invite", json={"email": "newbie@uiowa.edu", "name": "New Bie"})
    assert invited.status_code == 201, invited.get_json()
    invite_url = invited.get_json()["payload"]["invite_url"]
    parsed = urlparse(invite_url)
    assert parsed.scheme == "http" and parsed.netloc == "localhost" and parsed.path == "/app/auth/reset-password"
    assert parsed.query == ""
    token = parse_qs(parsed.fragment)["token"][0]

    client.post("/api/v1/auth/logout", json={})
    status = _status(client, token).get_json()["payload"]
    assert status["purpose"] == "invite" and status["email"] == "n***@uiowa.edu"
    done = client.post("/api/v1/auth/reset-password", json={"token": token, "password": NEW_PASSWORD, "confirm_password": NEW_PASSWORD})
    assert done.status_code == 200
    assert _login_status(client, "newbie@uiowa.edu", NEW_PASSWORD) == 200


def test_reset_links_use_public_base_url_not_the_host_header(app, client, org, users, api_login, outbox_mail):
    _settings(app, public_base_url="https://ops.asme.example")
    forged = {"Host": "attacker.example"}
    response = client.post("/api/v1/auth/forgot-password", json={"email": "mo@uiowa.edu"}, headers=forged)
    assert response.status_code == 200, response.get_json()
    outbox.process_pending()
    body = outbox_mail[0]["body"]
    link, _ = _link(body)
    assert link.startswith("https://ops.asme.example/app/auth/reset-password#token=")
    assert "attacker.example" not in body

    # The session cookie belongs to the real host, so an invite is always made
    # from the administrator's own request; the configured origin still wins.
    api_login(users["admin"])
    invited = client.post("/api/v1/users/invite", json={"email": "host@uiowa.edu", "name": "Host Header"})
    assert invited.status_code == 201, invited.get_json()
    parsed = urlparse(invited.get_json()["payload"]["invite_url"])
    assert (parsed.scheme, parsed.netloc, parsed.path) == ("https", "ops.asme.example", "/app/auth/reset-password")
