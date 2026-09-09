"""JSON shape for comments.

``comment`` follows the plan's shape plus ``deleted`` and ``mentions``. A
soft-deleted comment keeps its place in the thread but exposes no text.
"""

from __future__ import annotations

from asme.ops.serializers import iso, uid, user_ref


def comment(row, mentioned_users=()) -> dict:
    deleted = row.deleted_at is not None
    return {
        "id": uid(row.id),
        "entity_type": row.entity_type,
        "entity_id": uid(row.entity_id),
        "author": user_ref(row.author),
        "body": "" if deleted else row.body,
        "parent_comment_id": uid(row.parent_comment_id),
        "edited_at": iso(row.edited_at),
        "created_at": iso(row.created_at),
        "deleted": deleted,
        "mentions": [] if deleted else [user_ref(user) for user in mentioned_users],
    }
