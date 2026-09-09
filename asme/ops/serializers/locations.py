"""JSON shape for locations (``ops_locations``).

``path`` is the list of ancestor names ending with the location itself; the
counts are computed by ``asme.ops.services.locations.enrich`` so a list page
costs a fixed number of queries regardless of its size.
"""

from __future__ import annotations

from asme.ops.serializers import iso, uid


def location(row, *, path: list[str], asset_count: int = 0, open_work_order_count: int = 0, children: list | None = None) -> dict:
    data = {
        "id": uid(row.id),
        "name": row.name,
        "description": row.description,
        "parent_id": uid(row.parent_location_id),
        "building": row.building,
        "room": row.room,
        "address": row.address_json,
        "is_default": bool(row.is_default),
        "is_active": bool(row.is_active),
        "path": list(path),
        "asset_count": int(asset_count),
        "open_work_order_count": int(open_work_order_count),
        "created_at": iso(row.created_at),
        "updated_at": iso(row.updated_at),
    }
    if children is not None:
        data["children"] = children
    return data
