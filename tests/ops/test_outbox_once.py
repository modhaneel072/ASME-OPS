from asme.jobs import enqueue_once
from asme.models import OutboxJob
from asme.ops.models import Notification
from asme.ops.services import notifications


def test_enqueue_once_is_idempotent(app, db):
    first = enqueue_once("ops.work_order.scan", "scan:2026-09-08T10", {"hour": 10})
    db.session.commit()
    again = enqueue_once("ops.work_order.scan", "scan:2026-09-08T10", {"hour": 10})
    db.session.commit()
    assert first is not None and again is None
    assert OutboxJob.query.filter_by(kind="ops.work_order.scan").count() == 1
    other = enqueue_once("ops.work_order.scan", "scan:2026-09-08T11")
    db.session.commit()
    assert other is not None and other.idempotency_key == "scan:2026-09-08T11"


def test_notify_dedupes_and_skips_actor(ctx_admin, ctx_member, users, db):
    rows = notifications.notify(ctx_admin, [users["admin"].id, users["member"].id, users["member"].id], "system", "Hello", dedupe_key="hello:1")
    db.session.commit()
    assert [r.user_id for r in rows] == [users["member"].id]  # actor excluded, duplicate collapsed
    repeat = notifications.notify(ctx_admin, [users["member"].id], "system", "Hello again", dedupe_key="hello:1")
    db.session.commit()
    assert repeat == []
    assert Notification.query.count() == 1
    assert notifications.unread_count(ctx_member) == 1
    assert notifications.mark_read(ctx_member, all_unread=True) == 1
    assert notifications.unread_count(ctx_member) == 0
    assert notifications.list_for_user(ctx_member)[0].title == "Hello"
