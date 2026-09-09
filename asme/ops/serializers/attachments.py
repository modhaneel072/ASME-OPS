"""JSON shape for attachments.

``download_url`` is a relative URL carrying a short-lived token bound to the
attachment id and the viewer, minted fresh on every serialisation.
"""

from __future__ import annotations

from flask import url_for

from asme.ops import storage
from asme.ops.serializers import iso, uid, user_ref


def download_url(row, user_id: int | None) -> str:
    token = storage.sign_download(row.id, user_id)
    return url_for("ops_api.download_attachment", attachment_id=uid(row.id), token=token)


def attachment(row, *, user_id: int | None) -> dict:
    return {
        "id": uid(row.id),
        "entity_type": row.entity_type,
        "entity_id": uid(row.entity_id),
        "original_name": row.original_name,
        "content_type": row.content_type,
        "size_bytes": int(row.size_bytes or 0),
        "is_image": bool(row.is_image),
        "uploaded_by": user_ref(row.uploaded_by),
        "download_url": download_url(row, user_id),
        "created_at": iso(row.created_at),
    }
