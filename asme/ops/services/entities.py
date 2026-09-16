"""Resolve the polymorphic ``/:entity/:id`` prefix shared by comments and attachments.

``resolve`` turns a URL segment (``work-orders`` | ``projects`` | ``assets`` |
``parts`` | ``purchase-requests``) and an id into ``(entity_type, obj)`` after
applying the tenant and read checks. Anything the caller may not read - unknown
segment, malformed id, another organization's row, a private project they are
not part of, someone else's purchase request - is reported as ``NotFound`` so
existence is never revealed.

``can_read_purchase_request`` and ``visible_purchase_requests_query`` are the
cross-slice handles on the plan's purchase-request read rule (approvers and
inventory managers read everything; everyone else reads their own requests plus
the ones on projects they manage). They delegate to the purchase-requests
vertical so the rule is written once; comments, attachments, the change feed and
search all come through here.
"""

from __future__ import annotations

from asme.ops import policy
from asme.ops.models import Asset, OpsProject, Part, PurchaseRequest, WorkOrder
from asme.ops.types import parse_uuid
from asme.services.errors import NotFound

SEGMENT_TO_TYPE = {
    "work-orders": "work_order",
    "projects": "project",
    "assets": "asset",
    "parts": "part",
    "purchase-requests": "purchase_request",
}
TYPE_TO_SEGMENT = {value: key for key, value in SEGMENT_TO_TYPE.items()}
MODELS = {
    "work_order": WorkOrder,
    "project": OpsProject,
    "asset": Asset,
    "part": Part,
    "purchase_request": PurchaseRequest,
}
ENTITY_TYPES = tuple(MODELS)

# Keys that manage the parent entity: holders may edit/delete other people's
# comments and attachments on it.
MANAGE_KEYS = {
    "work_order": "work_order.edit",
    "project": "project.manage",
    "asset": "asset.manage",
    "part": "inventory.manage",
    "purchase_request": "purchase.review",
}

def entity_type_for_segment(entity_segment: str) -> str:
    entity_type = SEGMENT_TO_TYPE.get((entity_segment or "").strip().lower())
    if entity_type is None:
        raise NotFound()
    return entity_type


# --------------------------------------------------------------------------- purchase request read rule


def can_read_purchase_request(ctx, purchase_request) -> bool:
    """Object form of the plan's read rule (approvers and inventory managers read
    everything; everyone else their own plus the requests on projects they
    manage). Implemented by the purchase-requests vertical."""
    from asme.ops.services.purchase_requests import can_read

    if purchase_request is None or purchase_request.organization_id != ctx.org.id:
        return False
    return can_read(ctx, purchase_request)


def visible_purchase_requests_query(ctx):
    """Query form of the same rule, for list-shaped callers (search, change feed)."""
    from asme.ops.services.purchase_requests import visible_query

    return visible_query(ctx)


# --------------------------------------------------------------------------- read / manage


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
    if entity_type == "part":
        return ctx.has("inventory.read")
    if entity_type == "purchase_request":
        return can_read_purchase_request(ctx, obj)
    return False


def can_manage(ctx, entity_type: str, obj) -> bool:
    key = MANAGE_KEYS.get(entity_type)
    if key is None or obj is None:
        return False
    return policy.can(ctx, key, obj)


def load(ctx, entity_type: str, entity_id):
    """Load a readable entity by type name (``work_order`` | ``project`` |
    ``asset`` | ``part`` | ``purchase_request``)."""
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
    if entity_type == "purchase_request":
        return f"PR-{obj.number} {obj.title}".strip()
    return getattr(obj, "name", None) or str(getattr(obj, "id", ""))
