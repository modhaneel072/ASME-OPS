"""JSON shapes for assets, asset types and asset status history."""

from __future__ import annotations

from asme.ops.serializers import audit_event, iso, location_ref, money, project_ref, team_ref, uid, user_ref

ASSET_SNAPSHOT_FIELDS = (
    "name",
    "code",
    "description",
    "parent_asset_id",
    "project_id",
    "location_id",
    "responsible_team_id",
    "owner_user_id",
    "manufacturer",
    "model",
    "serial_number",
    "purchase_date",
    "purchase_cost",
    "warranty_end",
    "criticality",
    "status",
    "qr_code",
    "custom_fields_json",
    "is_active",
)


def asset_type_brief(asset_type) -> dict:
    return {"id": uid(asset_type.id), "name": asset_type.name, "color": asset_type.color}


def asset_type(asset_type, *, asset_count: int = 0) -> dict:
    return {
        "id": uid(asset_type.id),
        "name": asset_type.name,
        "color": asset_type.color,
        "icon": asset_type.icon,
        "asset_count": int(asset_count),
    }


def asset(row, *, child_count: int = 0, open_work_order_count: int = 0) -> dict:
    return {
        "id": uid(row.id),
        "name": row.name,
        "code": row.code,
        "description": row.description,
        "parent_id": uid(row.parent_asset_id),
        "project": project_ref(row.project),
        "location": location_ref(row.location),
        "team": team_ref(row.responsible_team),
        "owner": user_ref(row.owner),
        "manufacturer": row.manufacturer,
        "model": row.model,
        "serial_number": row.serial_number,
        "purchase_date": iso(row.purchase_date),
        "purchase_cost": money(row.purchase_cost),
        "warranty_end": iso(row.warranty_end),
        "criticality": row.criticality,
        "status": row.status,
        "qr_code": row.qr_code,
        "custom_fields": dict(row.custom_fields_json or {}),
        "is_active": bool(row.is_active),
        "types": [asset_type_brief(t) for t in row.types],
        "child_count": int(child_count),
        "open_work_order_count": int(open_work_order_count),
        "created_at": iso(row.created_at),
        "updated_at": iso(row.updated_at),
    }


def status_history(row) -> dict:
    return {
        "id": uid(row.id),
        "from_status": row.from_status,
        "to_status": row.to_status,
        "downtime_type": row.downtime_type,
        "downtime_reason": row.downtime_reason,
        "note": row.note,
        "started_at": iso(row.started_at),
        "ended_at": iso(row.ended_at),
        "changed_by": user_ref(row.changed_by),
        "work_order_id": uid(row.work_order_id),
    }


def timeline_entry(kind: str, row, at) -> dict:
    """One row of ``GET /assets/:id/history``: a status change, an audit event or
    a work order that references the asset, tagged with ``kind`` and ``at``."""
    if kind == "status":
        body = status_history(row)
    elif kind == "audit":
        body = audit_event(row)
    elif kind == "work_order":
        body = {"id": uid(row.id), "number": row.number, "title": row.title, "status": row.status}
    else:  # pragma: no cover - programming error
        raise ValueError(f"unknown timeline kind {kind}")
    return {"kind": kind, **body, "at": iso(at)}


def hierarchy_node(row, children: list[dict], *, child_count: int, open_work_order_count: int) -> dict:
    node = asset(row, child_count=child_count, open_work_order_count=open_work_order_count)
    node["children"] = children
    return node
