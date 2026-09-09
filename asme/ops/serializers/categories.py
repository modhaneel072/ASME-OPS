"""JSON shape for categories (``ops_categories``)."""

from __future__ import annotations

from asme.ops.serializers import iso, uid, user_ref


def category(row, *, usage: int = 0, created_by=None) -> dict:
    return {
        "id": uid(row.id),
        "name": row.name,
        "color": row.color,
        "icon": row.icon,
        "description": row.description,
        "usage": {"work_orders": int(usage)},
        "created_at": iso(row.created_at),
        "updated_at": iso(row.updated_at),
        "created_by": user_ref(created_by),
    }
