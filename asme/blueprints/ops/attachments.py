"""Private attachments with signed downloads.

``GET|POST /<entity>/:id/attachments``, ``GET|DELETE /attachments/:id`` and the
session-less ``GET /attachments/:id/download?token=`` (endpoint
``download_attachment``). Uploads are multipart with a ``file`` field; the
blueprint already insists on ``X-Requested-With: ASME-Ops`` for multipart.
"""

from __future__ import annotations

import logging

from flask import jsonify, request, send_file

from asme.blueprints.ops import bp, list_payload, ok
from asme.ops import policy, storage
from asme.ops.serializers.attachments import attachment as serialize_attachment
from asme.ops.services import attachments

log = logging.getLogger("asme.ops.attachments")

ENTITY_RULE = "/<any('work-orders','projects','assets','parts','purchase-requests'):segment>/<entity_id>/attachments"


@bp.get(ENTITY_RULE)
@policy.require_permission()
def list_attachments(segment, entity_id):
    ctx = policy.current_context()
    _entity_type, _obj, rows = attachments.list_for(ctx, segment, entity_id)
    items = [serialize_attachment(row, user_id=ctx.user.id) for row in rows]
    return ok(list_payload("attachments", items, None, len(rows)))


@bp.post(ENTITY_RULE)
@policy.require_permission("work_order.attach")
def upload_attachment(segment, entity_id):
    ctx = policy.current_context()
    attachments.ensure_request_size(request.content_length)
    row = attachments.upload(ctx, segment, entity_id, request.files.get("file"))
    return ok({"attachment": serialize_attachment(row, user_id=ctx.user.id)}, status=201)


@bp.get("/attachments/<attachment_id>")
@policy.require_permission()
def get_attachment(attachment_id):
    ctx = policy.current_context()
    row = attachments.get(ctx, attachment_id)
    return ok({"attachment": serialize_attachment(row, user_id=ctx.user.id)})


@bp.delete("/attachments/<attachment_id>")
@policy.require_permission()
def delete_attachment(attachment_id):
    ctx = policy.current_context()
    row = attachments.delete(ctx, attachment_id)
    return ok({"deleted": True, "id": str(row.id)})


@bp.get("/attachments/<attachment_id>/download", endpoint="download_attachment")
def download_attachment(attachment_id):
    token = request.args.get("token", "")
    if not token or storage.verify_download(token) != attachment_id:
        return jsonify({"ok": False, "code": "invalid_token", "error": "This download link is invalid or has expired."}), 403
    row = attachments.for_download(attachment_id)
    if row is None:
        return jsonify({"ok": False, "code": "not_found", "error": "Not found."}), 404
    try:
        handle = storage.get_storage().open(row.storage_key)
    except FileNotFoundError:
        log.warning("attachment %s has no stored object at %s", row.id, row.storage_key)
        return jsonify({"ok": False, "code": "file_missing", "error": "The stored file is missing."}), 404
    response = send_file(
        handle,
        as_attachment=True,
        download_name=row.original_name,
        mimetype=row.content_type,
        conditional=False,
        etag=False,
        max_age=0,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response
