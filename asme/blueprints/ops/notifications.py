"""In-app notifications: ``GET /notifications`` and ``POST /notifications/read``.

Reads and writes go through ``asme.ops.services.notifications``; this module
only parses the request and shapes the response.
"""

from __future__ import annotations

from sqlalchemy import func, select

from asme.blueprints.ops import bp, encode_cursor, json_body, list_payload, ok, page_cursor, page_limit, parse_filters
from asme.extensions import db
from asme.ops import policy
from asme.ops.models import Notification
from asme.ops.serializers.notifications import notification as serialize_notification
from asme.ops.services import notifications
from asme.ops.validation import Field, ValidationErrors, validate
from asme.services.errors import Validation

LIST_FILTERS = {"unread": "single"}
LIST_SPEC = {"unread": Field("bool", default=False, nullable=False)}
READ_SPEC = {
    "ids": Field("list", item=Field("uuid"), max_len=500),
    "all": Field("bool"),
}


@bp.get("/notifications")
@policy.require_permission("notification.read")
def list_notifications():
    ctx = policy.current_context()
    filters = parse_filters(LIST_FILTERS)
    options = validate({name: values[0] for name, values in filters.items()}, LIST_SPEC)
    unread_only = options["unread"]
    limit = page_limit()
    offset = _cursor_offset(page_cursor())

    # list_for_user is newest-first; the cursor is an offset into that ordering.
    rows = notifications.list_for_user(ctx, unread_only=unread_only, limit=offset + limit + 1)
    page = rows[offset : offset + limit]
    next_cursor = encode_cursor({"offset": offset + limit}) if len(rows) > offset + limit else None
    unread = notifications.unread_count(ctx)
    total = unread if unread_only else _count_for_user(ctx)

    payload = list_payload("notifications", [serialize_notification(row) for row in page], next_cursor, total)
    payload["unread_count"] = unread
    return ok(payload)


@bp.post("/notifications/read")
@policy.require_permission("notification.read")
def mark_notifications_read():
    ctx = policy.current_context()
    data = validate(json_body(), READ_SPEC)
    ids = data.get("ids") or []
    if data.get("all"):
        updated = notifications.mark_read(ctx, all_unread=True)
    elif ids:
        updated = notifications.mark_read(ctx, ids)
    else:
        raise ValidationErrors({"ids": "Provide notification ids, or set all to true."})
    return ok({"updated": updated})


# --------------------------------------------------------------------------- helpers


def _cursor_offset(cursor) -> int:
    if cursor is None:
        return 0
    offset = cursor.get("offset") if isinstance(cursor, dict) else None
    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
        raise Validation("Invalid cursor.", field="cursor", code="bad_cursor")
    return offset


def _count_for_user(ctx) -> int:
    stmt = select(func.count(Notification.id)).where(
        Notification.organization_id == ctx.org.id, Notification.user_id == ctx.user.id
    )
    return int(db.session.scalar(stmt) or 0)
