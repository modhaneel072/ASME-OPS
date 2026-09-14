"""Change feed for polling clients: ``GET /changes?since=<iso>&limit=``.

Any member may poll; the service trims the events to what the caller may read.
"""

from __future__ import annotations

from flask import request

from asme.blueprints.ops import bp, ok
from asme.ops import policy
from asme.ops.serializers import iso
from asme.ops.serializers.notifications import change_event
from asme.ops.services import changes, notifications

FEED_PARAMS = ("since", "limit")


@bp.get("/changes")
@policy.require_permission()
def list_changes():
    ctx = policy.current_context()
    params = {name: request.args.get(name) for name in FEED_PARAMS if name in request.args}
    feed = changes.list_changes(ctx, params)
    include_payload = ctx.has("audit.read")
    return ok(
        {
            "events": [change_event(event, include_payload=include_payload) for event in feed["events"]],
            "has_more": feed["has_more"],
            "now": iso(feed["now"]),
            "next_since": iso(feed["next_since"]),
            "unread_notifications": notifications.unread_count(ctx),
        }
    )
