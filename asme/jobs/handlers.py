"""Outbox job handlers. Importing this module registers them."""

from __future__ import annotations

from datetime import datetime

from asme.config import settings
from asme.extensions import db
from asme.integrations import mail
from asme.integrations.calendar import CalendarError, get_provider
from asme.jobs.outbox import failure_handler, handler
from asme.models import CalendarSync, Event, User


@handler("calendar.create_event")
def calendar_create_event(payload: dict):
    event = db.session.get(Event, int(payload["event_id"]))
    if not event:
        return
    sync = CalendarSync.query.filter_by(subject_type="event", subject_id=event.id).order_by(CalendarSync.id.desc()).first()
    if sync is None:
        sync = CalendarSync(subject_type="event", subject_id=event.id, provider=get_provider().name, status="pending")
        db.session.add(sync)
    if sync.status == "synced" and sync.external_id:
        return
    provider = get_provider()
    details = [f"Organizer: {payload.get('organizer') or (event.requested_by.name if event.requested_by else '')}"]
    if event.description:
        details.append(event.description)
    try:
        created = provider.create_event(event.location or "", event.title, "\n".join(details), event.start_time, event.end_time)
    except CalendarError as exc:
        sync.status = "failed"
        sync.last_error = str(exc)[:500]
        db.session.commit()
        raise
    sync.provider = provider.name
    sync.external_id = created.external_id
    sync.calendar_id = created.calendar_id
    sync.link = created.link
    sync.status = "synced"
    sync.last_error = None
    sync.last_synced_at = datetime.utcnow()
    event.calendar_event_link = created.link
    if provider.name == "google":
        event.google_event_id = created.external_id
        event.google_calendar_id = created.calendar_id
    db.session.commit()


@handler("calendar.delete_event")
def calendar_delete_event(payload: dict):
    sync = db.session.get(CalendarSync, int(payload["sync_id"]))
    if not sync or not sync.external_id:
        return
    get_provider().delete_event(sync.calendar_id, sync.external_id)
    sync.status = "deleted"
    sync.last_synced_at = datetime.utcnow()
    db.session.commit()


@handler("mail.send")
def mail_send(payload: dict):
    mail.send_email(settings(), payload["to"], payload.get("subject") or "(no subject)", payload.get("body") or "")


@handler("auth.password_reset")
def auth_password_reset(payload: dict):
    from asme.services import password_reset

    password_reset.deliver(payload.get("email") or "", payload.get("origin"))


# --------------------------------------------------------------------------- permanent failures


def _chapter_administrator_ids(org) -> list[int]:
    from asme.ops.models import Membership, Role

    rows = (
        db.session.query(Membership.user_id)
        .join(Role, Role.id == Membership.role_id)
        .filter(
            Membership.organization_id == org.id,
            Membership.member_status == "active",
            Role.system_key == "chapter_admin",
        )
        .all()
    )
    return [row[0] for row in rows]


def _surface_to_administrators(job, title: str, body: str) -> None:
    """Record a permanently failed job on the chapter and tell its administrators.

    The audit event is the part that always happens: it is attached to the
    chapter rather than to a person, so it survives even when nobody holds an
    administrator membership yet, and the officers' change feed shows it. The
    notifications are best-effort on top of that.
    """
    from asme.ops.models import Organization
    from asme.ops.services import audit_events, notifications
    from asme.ops.services.scans import system_context

    org = Organization.query.order_by(Organization.created_at.asc(), Organization.slug.asc()).first()
    if org is None:
        return
    ctx = system_context(org)
    audit_events.record(
        ctx,
        "job.failed",
        "outbox_job",
        entity_id=job.id,
        summary=title,
        kind=job.kind,
        attempts=job.attempts,
        error=(job.last_error or "")[:400],
    )
    admin_ids = _chapter_administrator_ids(org)
    if admin_ids:
        notifications.notify(
            ctx,
            admin_ids,
            "system",
            title,
            body,
            dedupe_key=f"job.failed:{job.id}",
            exclude_actor=False,
        )


@failure_handler("auth.password_reset")
def auth_password_reset_failed(job, payload: dict, exc: Exception):
    address = (payload.get("email") or "").strip() or "an address we no longer have"
    _surface_to_administrators(
        job,
        "A password reset e-mail could not be sent",
        (
            f"ASME Ops tried {job.attempts} times over several hours to e-mail a password reset "
            f"link to {address} and the mail server refused every time. That person is still "
            "waiting and has no link: set their password for them from the people list, and "
            "check the chapter mailbox settings (ASME_SMTP_USER / ASME_SMTP_PASS).\n\n"
            f"Last error: {job.last_error or exc}"
        ),
    )


@failure_handler("mail.send")
def mail_send_failed(job, payload: dict, exc: Exception):
    address = (payload.get("to") or "").strip() or "an unknown address"
    _surface_to_administrators(
        job,
        "An e-mail from ASME Ops was never delivered",
        (
            f"ASME Ops gave up trying to send \"{payload.get('subject') or '(no subject)'}\" to "
            f"{address} after {job.attempts} attempts. Nobody was told. Check the chapter mailbox "
            f"settings, then send the message yourself if it mattered.\n\nLast error: {job.last_error or exc}"
        ),
    )


@handler("stock.reconcile")
def stock_reconcile(payload: dict):
    from asme.services import inventory

    inventory.reconcile_stock()


@handler("onboarding.evaluate")
def onboarding_evaluate(payload: dict):
    from asme.services.onboarding import engine

    if payload.get("user_id"):
        user = db.session.get(User, int(payload["user_id"]))
        if user:
            engine.evaluate_user(user)
    if payload.get("chapter"):
        engine.evaluate_chapter()


@handler("onboarding.evaluate_all")
def onboarding_evaluate_all(payload: dict):
    from asme.services.onboarding import engine

    for user in User.query.filter(User.is_active.is_(True)).all():
        engine.evaluate_user(user)
    engine.evaluate_chapter()


@handler("ops.work_order.scan")
def ops_work_order_scan(payload: dict):
    from asme.ops.services.scans import run_work_order_scan

    run_work_order_scan()
