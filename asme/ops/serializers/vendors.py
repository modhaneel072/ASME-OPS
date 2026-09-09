"""JSON shape for vendors."""

from __future__ import annotations

from asme.ops.serializers import iso, uid

VENDOR_SNAPSHOT_FIELDS = ("name", "contact_name", "email", "phone", "website", "address_json", "notes", "is_active")


def vendor(row) -> dict:
    return {
        "id": uid(row.id),
        "name": row.name,
        "contact_name": row.contact_name,
        "email": row.email,
        "phone": row.phone,
        "website": row.website,
        "address": dict(row.address_json or {}),
        "notes": row.notes,
        "is_active": bool(row.is_active),
        "created_at": iso(row.created_at),
        "updated_at": iso(row.updated_at),
    }
