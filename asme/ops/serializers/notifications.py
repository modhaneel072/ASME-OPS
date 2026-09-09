"""JSON shapes for in-app notifications and the change feed."""

from __future__ import annotations

from asme.ops.serializers import audit_event, iso, uid

# entity_type -> SPA route. Anything not listed has no deep link (``href`` is null).
ENTITY_ROUTES = {
    "work_order": "/app/work-orders/{id}",
    "project": "/app/projects/{id}",
    "asset": "/app/assets/{id}",
}


def entity_href(entity_type, entity_id) -> str | None:
    template = ENTITY_ROUTES.get(entity_type or "")
    if template is None or not entity_id:
        return None
    return template.format(id=entity_id)


def notification(row) -> dict:
    return {
        "id": uid(row.id),
        "type": row.type,
        "title": row.title,
        "body": row.body,
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "read_at": iso(row.read_at),
        "created_at": iso(row.created_at),
        "href": entity_href(row.entity_type, row.entity_id),
    }


def change_event(event, *, include_payload: bool = False) -> dict:
    """One entry of the change feed.

    The feed exists so a client knows *what* to refetch, so the audit payload
    (``before``/``after``/``metadata``) is withheld unless the caller holds
    ``audit.read`` - otherwise polling would become a way to read field-level
    history that the entity's own endpoints gate.
    """
    data = audit_event(event)
    if not include_payload:
        for key in ("before", "after", "metadata"):
            data.pop(key, None)
    data["href"] = entity_href(event.entity_type, event.entity_id)
    return data
