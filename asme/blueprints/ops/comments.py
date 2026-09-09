"""Comments on work orders, projects and assets.

``GET|POST /<entity>/:id/comments`` and ``PATCH|DELETE /comments/:id`` where
``entity`` is ``work-orders`` | ``projects`` | ``assets``. Read access to the
parent entity is checked by the service (unreadable parents are 404).
"""

from __future__ import annotations

from asme.blueprints.ops import bp, json_body, list_payload, ok
from asme.ops import policy
from asme.ops.serializers.comments import comment as serialize_comment
from asme.ops.services import comments

ENTITY_RULE = "/<any('work-orders','projects','assets'):segment>/<entity_id>/comments"


def _serialize_many(ctx, rows) -> list[dict]:
    users_by_id = comments.mentioned_users(ctx, rows)
    return [serialize_comment(row, comments.mentions_for(row, users_by_id)) for row in rows]


def _serialize_one(ctx, row) -> dict:
    return _serialize_many(ctx, [row])[0]


@bp.get(ENTITY_RULE)
@policy.require_permission()
def list_comments(segment, entity_id):
    ctx = policy.current_context()
    _entity_type, _obj, rows = comments.list_for(ctx, segment, entity_id)
    return ok(list_payload("comments", _serialize_many(ctx, rows), None, len(rows)))


@bp.post(ENTITY_RULE)
@policy.require_permission()
def create_comment(segment, entity_id):
    ctx = policy.current_context()
    row = comments.create(ctx, segment, entity_id, json_body())
    return ok({"comment": _serialize_one(ctx, row)}, status=201)


@bp.patch("/comments/<comment_id>")
@policy.require_permission()
def update_comment(comment_id):
    ctx = policy.current_context()
    row = comments.update(ctx, comment_id, json_body())
    return ok({"comment": _serialize_one(ctx, row)})


@bp.delete("/comments/<comment_id>")
@policy.require_permission()
def delete_comment(comment_id):
    ctx = policy.current_context()
    row = comments.delete(ctx, comment_id)
    return ok({"comment": _serialize_one(ctx, row)})
