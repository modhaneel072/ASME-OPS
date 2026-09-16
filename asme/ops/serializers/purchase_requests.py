"""JSON shapes for purchase requests (see the Stage 4 plan's "Serializer shapes").

``purchase_request`` is the list/item shape; ``purchase_request_detail`` adds the
line items, the approval timeline, the attachment count and the actions the
caller may take right now. ``line_total`` is the one definition of a line's
money value and is reused by the service when it recomputes ``estimated_total``.
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from asme.ops.models.inventory import PURCHASE_REQUEST_CLOSED_STATUSES
from asme.ops.serializers import iso, location_ref, money, part_ref, project_ref, purchase_request_ref, uid, user_ref, vendor_ref
from asme.ops.serializers.projects import today_utc
from asme.ops.services.inventory_ledger import quantity_number, unit_cost_number

MONEY_PLACES = Decimal("0.01")
ZERO = Decimal("0")

SNAPSHOT_FIELDS = (
    "number",
    "title",
    "status",
    "requester_user_id",
    "project_id",
    "vendor_id",
    "needed_by",
    "purpose",
    "budget_code",
    "shipping_amount",
    "tax_amount",
    "estimated_total",
    "approved_total",
    "order_reference",
    "decline_reason",
)


def to_money(value) -> Decimal:
    """A money value as an exact ``Decimal`` with 2 places (SQLite hands back floats)."""
    if value is None:
        return ZERO
    if isinstance(value, float):
        value = Decimal(repr(value))
    return Decimal(value).quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)


def _exact(value) -> Decimal:
    if value is None:
        return ZERO
    if isinstance(value, float):
        return Decimal(repr(value))
    return Decimal(value)


def line_total(item) -> Decimal:
    """``quantity * unit_price`` rounded to cents - the only line-total rule."""
    return (_exact(item.quantity) * _exact(item.unit_price)).quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)


def is_overdue(request, today: date | None = None) -> bool:
    if request.needed_by is None or request.status in PURCHASE_REQUEST_CLOSED_STATUSES:
        return False
    return request.needed_by < (today or today_utc())


def purchase_request(request, *, today: date | None = None) -> dict:
    data = purchase_request_ref(request)
    data.update(
        {
            "requester": user_ref(request.requester),
            "project": project_ref(request.project),
            "vendor": vendor_ref(request.vendor),
            "needed_by": iso(request.needed_by),
            "purpose": request.purpose,
            "budget_code": request.budget_code,
            "shipping_amount": money(to_money(request.shipping_amount)),
            "tax_amount": money(to_money(request.tax_amount)),
            "estimated_total": money(to_money(request.estimated_total)),
            "approved_total": money(request.approved_total) if request.approved_total is not None else None,
            "item_count": len(request.items),
            "order_reference": request.order_reference,
            "submitted_at": iso(request.submitted_at),
            "approved_at": iso(request.approved_at),
            "ordered_at": iso(request.ordered_at),
            "received_at": iso(request.received_at),
            "created_at": iso(request.created_at),
            "updated_at": iso(request.updated_at),
            "is_overdue": is_overdue(request, today),
        }
    )
    return data


def serialize_many(requests) -> list[dict]:
    today = today_utc()
    return [purchase_request(row, today=today) for row in requests]


def purchase_request_item(item) -> dict:
    return {
        "id": uid(item.id),
        "part": part_ref(item.part),
        "description": item.description,
        "vendor_part_number": item.vendor_part_number,
        "url": item.url,
        "quantity": quantity_number(item.quantity),
        "unit_price": unit_cost_number(item.unit_price),
        "line_total": money(line_total(item)),
        "received_quantity": quantity_number(item.received_quantity),
        "receive_location": location_ref(item.receive_location),
    }


def purchase_request_event(event) -> dict:
    return {
        "id": uid(event.id),
        "action": event.action,
        "from_status": event.from_status,
        "to_status": event.to_status,
        "step": event.step,
        "comment": event.comment,
        "actor": user_ref(event.actor),
        "created_at": iso(event.created_at),
    }


def purchase_request_detail(request, *, available_actions=(), attachment_count: int = 0) -> dict:
    data = purchase_request(request)
    data.update(
        {
            "items": [purchase_request_item(item) for item in request.items],
            "events": [purchase_request_event(event) for event in request.events],
            "decline_reason": request.decline_reason,
            "attachment_count": int(attachment_count),
            "available_actions": list(available_actions),
        }
    )
    return data


def purchasing_settings(settings: dict) -> dict:
    """The chapter's ``settings_json["purchasing"]`` block as JSON."""
    threshold = settings.get("advisor_review_threshold")
    return {
        "advisor_review_threshold": money(threshold) if threshold is not None else None,
        "require_project_lead_approval": bool(settings.get("require_project_lead_approval")),
        "critical_parts_team_id": uid(settings.get("critical_parts_team_id")),
    }
