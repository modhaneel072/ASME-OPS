"""Resolve the polymorphic ``/:entity/:id`` prefix shared by comments and attachments.

``resolve`` turns a URL segment (``work-orders`` | ``projects`` | ``assets``) and
an id into ``(entity_type, obj)`` after applying the tenant and read checks.
Anything the caller may not read - unknown segment, malformed id, another
organization's row, a private project they are not part of - is reported as
``NotFound`` so existence is never revealed.
"""

from __future__ import annotations

from asme.ops import policy
from asme.ops.models import Asset, OpsProject, WorkOrder
from asme.ops.types import parse_uuid
from asme.services.errors import NotFound

SEGMENT_TO_TYPE = {"work-orders": "work_order", "projects": "project", "assets": "asset"}
TYPE_TO_SEGMENT = {value: key for key, value in SEGMENT_TO_TYPE.items()}
MODELS = {"work_order": WorkOrder, "project": OpsProject, "asset": Asset}
ENTITY_TYPES = tuple(MODELS)

# Keys that manage the parent entity: holders may edit/delete other people's
# comments and attachments on it.
MANAGE_KEYS = {"work_order": "work_order.edit", "project": "project.manage", "asset": "asset.manage"}


def entity_type_for_segment(entity_segment: str) -> str:
    entity_type = SEGMENT_TO_TYPE.get((entity_segment or "").strip().lower())
    if entity_type is None:
        raise NotFound()
    return entity_type


def can_read(ctx, entity_type: str, obj) -> bool:
    if obj is None or getattr(obj, "organization_id", None) != ctx.org.id:
        return False
    if entity_type == "work_order":
        from asme.ops.services.work_orders import can_read_work_order

        return can_read_work_order(ctx, obj)
    if entity_type == "project":
        return policy.can_read_project(ctx, obj)
    if entity_type == "asset":
        if not ctx.has("asset.read"):
            return False
        return obj.project is None or policy.can_read_project(ctx, obj.project)
    return False


def can_manage(ctx, entity_type: str, obj) -> bool:
    key = MANAGE_KEYS.get(entity_type)
    if key is None or obj is None:
        return False
    return policy.can(ctx, key, obj)


def load(ctx, entity_type: str, entity_id):
    """Load a readable entity by type name (``work_order`` | ``project`` | ``asset``)."""
    model = MODELS.get(entity_type)
    if model is None:
        raise NotFound()
    parsed = parse_uuid(entity_id)
    if parsed is None:
        raise NotFound()
    obj = policy.get_or_404(ctx, model, parsed)
    if not can_read(ctx, entity_type, obj):
        raise NotFound()
    return obj


def resolve(ctx, entity_segment: str, entity_id):
    """``(entity_type, obj)`` for a URL segment + id, or ``NotFound``."""
    entity_type = entity_type_for_segment(entity_segment)
    return entity_type, load(ctx, entity_type, entity_id)


def label(entity_type: str, obj) -> str:
    """Short human label used in notification titles and audit summaries."""
    if entity_type == "work_order":
        return f"WO-{obj.number} {obj.title}".strip()
    return getattr(obj, "name", None) or str(getattr(obj, "id", ""))
