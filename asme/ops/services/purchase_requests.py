"""Purchase requests service (``ops_purchase_requests``).

A purchase request walks a small approval workflow:

``draft`` -> ``submitted`` (project lead, optional) -> ``treasurer_review`` ->
``advisor_review`` (only above the chapter's threshold) -> ``approved`` ->
``ordered`` -> ``partially_received`` -> ``received``, with ``declined`` and
``canceled`` as the other closed states.

Every action is applied by :func:`perform`: it checks the from-state, then the
step's permission, writes a ``PurchaseRequestEvent`` timeline row and an audit
event in the same transaction, notifies the people who now have to act, commits
once and only then emits ``ops.purchase_request.status_changed``.

Receiving is the one action that moves stock: each line is posted through
``inventory_ledger.post`` inside the same transaction as the status change, so a
receipt and the status it caused can never disagree.

``purchasing_settings`` reads ``organization.settings_json["purchasing"]`` and is
the only reader of that block outside the ledger's critical-parts lookup.
"""

from __future__ import annotations

import re
from decimal import Decimal
from uuid import UUID

from sqlalchemy import false, func, or_, select

from asme import events
from asme.extensions import db
from asme.ops import policy
from asme.ops.models import (
    Attachment,
    Location,
    OpsProject,
    Part,
    PartVendor,
    PurchaseRequest,
    PurchaseRequestEvent,
    PurchaseRequestItem,
    Team,
    Vendor,
)
from asme.ops.models.inventory import (
    PURCHASE_REQUEST_CLOSED_STATUSES,
    PURCHASE_REQUEST_COMMITTED_STATUSES,
    PURCHASE_REQUEST_ORDERED_STATUSES,
    PURCHASE_REQUEST_REVIEW_STATUSES,
    PURCHASE_REQUEST_STATUSES,
)
from asme.ops.numbering import next_number
from asme.ops.serializers.purchase_requests import SNAPSHOT_FIELDS, line_total, to_money
from asme.ops.services import audit_events, notifications
from asme.ops.services import inventory_ledger as ledger
from asme.ops.types import parse_uuid, utcnow
from asme.ops.validation import MONEY_MAX, Field, ValidationErrors, validate
from asme.services.errors import Conflict, Forbidden, NotFound, Validation

SEQUENCE_KEY = "purchase_request"
ZERO = Decimal("0")
ONE = Decimal("1")

REVIEW_PERMISSION = "purchase.review"
ADVISOR_PERMISSION = "purchase.advisor_review"
SUBMIT_PERMISSION = "purchase.submit"
INVENTORY_MANAGE = "inventory.manage"
INVENTORY_READ = "inventory.read"
SETTINGS_PERMISSION = "chapter.settings.manage"

MAX_ITEMS = 100
MAX_RECEIVE_LINES = 100

NEEDS_REVIEW_NOTIFICATION = "purchase_request.needs_review"
STATUS_NOTIFICATION = "purchase_request.status_changed"

# --------------------------------------------------------------------------- workflow tables

ACTIONS = ("submit", "approve", "decline", "request_changes", "order", "receive", "cancel", "reopen")
CANCEL_REQUESTER_STATUSES = ("draft", "submitted", "treasurer_review", "advisor_review")
CANCEL_REVIEWER_STATUSES = ("draft", "submitted", "treasurer_review", "advisor_review", "approved")
ACTION_FROM_STATUSES: dict[str, tuple[str, ...]] = {
    "submit": ("draft",),
    "approve": PURCHASE_REQUEST_REVIEW_STATUSES,
    "decline": PURCHASE_REQUEST_REVIEW_STATUSES,
    "request_changes": PURCHASE_REQUEST_REVIEW_STATUSES,
    "order": ("approved",),
    "receive": PURCHASE_REQUEST_ORDERED_STATUSES,
    "cancel": CANCEL_REVIEWER_STATUSES,
    "reopen": ("declined", "canceled"),
}
# The review status a request sits in -> the approval step that owns it.
STEP_BY_STATUS = {"submitted": "project_lead", "treasurer_review": "treasurer", "advisor_review": "advisor"}
STATUS_LABELS = {
    "draft": "a draft",
    "submitted": "waiting for the project lead",
    "treasurer_review": "with the treasurer",
    "advisor_review": "with the faculty advisor",
    "approved": "approved",
    "ordered": "ordered",
    "partially_received": "partially received",
    "received": "received",
    "declined": "declined",
    "canceled": "canceled",
}

SELF_APPROVAL = "self_approval"
ALREADY_APPROVED = "already_approved"
INVALID_TRANSITION = "invalid_transition"

# ``estimated_total`` and ``approved_total`` are Numeric(12, 2). Client-supplied
# money is bounded by the validator; the computed total is bounded here.
LINE_TOO_LARGE = f"This line comes to more than {MONEY_MAX}. Lower the quantity or the price."
TOTAL_TOO_LARGE = f"The request comes to more than {MONEY_MAX}. Lower the quantities, prices, shipping or tax."

# --------------------------------------------------------------------------- listing

LIST_FILTERS = {"status": "multi", "project": "multi", "vendor": "multi", "requester": "multi"}
LIST_SORTS = ("updated_at", "created_at", "needed_by", "estimated_total", "number")
DEFAULT_SORT = "-updated_at"
TABS = ("mine", "review", "open", "closed", "all")
NUMBER_RE = re.compile(r"^(?:pr[-\s]?)?#?(\d+)$", re.IGNORECASE)

# --------------------------------------------------------------------------- specs

ITEM_SPEC = {
    "part_id": Field("uuid"),
    "description": Field("str", max_len=300),
    "vendor_part_number": Field("str", max_len=160),
    "url": Field("url", max_len=500),
    "quantity": Field("decimal", required=True, nullable=False, minimum=0, maximum=ledger.QUANTITY_MAX, check=ledger.quantity_check),
    "unit_price": Field("decimal", minimum=0, maximum=ledger.UNIT_COST_MAX, check=ledger.unit_cost_check, default=ZERO),
    "receive_location_id": Field("uuid"),
}

CREATE_SPEC = {
    "title": Field("str", required=True, nullable=False, max_len=200, min_len=1),
    "project_id": Field("uuid"),
    "vendor_id": Field("uuid"),
    "needed_by": Field("date"),
    "purpose": Field("text"),
    "budget_code": Field("str", max_len=60),
    "shipping_amount": Field("decimal", minimum=0, nullable=False, default=ZERO),
    "tax_amount": Field("decimal", minimum=0, nullable=False, default=ZERO),
    "items": Field("list", item=Field("any"), required=True, nullable=False, max_len=MAX_ITEMS),
}
UPDATE_SPEC = dict(CREATE_SPEC)
UPDATE_SPEC["items"] = Field("list", item=Field("any"), nullable=False, max_len=MAX_ITEMS)

COMMENT_SPEC = {"comment": Field("text", required=True, nullable=False, max_len=4000, min_len=1)}
OPTIONAL_COMMENT_SPEC = {"comment": Field("text", max_len=4000)}
APPROVE_SPEC = {
    "comment": Field("text", max_len=4000),
    "approved_total": Field("decimal", minimum=0),
}
ORDER_SPEC = {
    "order_reference": Field("str", max_len=120),
    "ordered_at": Field("datetime"),
    "approved_total": Field("decimal", minimum=0),
    "comment": Field("text", max_len=4000),
}
RECEIVE_SPEC = {
    "lines": Field("list", item=Field("any"), required=True, nullable=False, max_len=MAX_RECEIVE_LINES),
    "note": Field("text", max_len=4000),
}
RECEIVE_LINE_SPEC = {
    "item_id": Field("uuid", required=True, nullable=False),
    "quantity": Field("decimal", required=True, nullable=False, minimum=0, maximum=ledger.QUANTITY_MAX, check=ledger.quantity_check),
    "location_id": Field("uuid"),
}
FROM_LOW_STOCK_SPEC = {"part_ids": Field("list", item=Field("uuid"), required=True, nullable=False, max_len=MAX_ITEMS)}

PURCHASING_KEY = "purchasing"
PURCHASING_DEFAULTS = {"advisor_review_threshold": None, "require_project_lead_approval": False, "critical_parts_team_id": None}
PURCHASING_SPEC = {
    "advisor_review_threshold": Field("decimal", minimum=0, default=None),
    "require_project_lead_approval": Field("bool", nullable=False, default=False),
    "critical_parts_team_id": Field("uuid", default=None),
}


# --------------------------------------------------------------------------- stored numbers


def _quantity(value) -> Decimal:
    """A quantity read back from the database (SQLite may hand back a float)."""
    if value is None:
        return ZERO
    if isinstance(value, float):
        value = Decimal(repr(value))
    return ledger.to_quantity(value)


def _price(value) -> Decimal:
    """A unit price read back from the database."""
    if value is None:
        return ZERO
    if isinstance(value, float):
        value = Decimal(repr(value))
    return ledger.to_unit_cost(value)


# --------------------------------------------------------------------------- chapter settings


def purchasing_settings(org) -> dict:
    """``{"advisor_review_threshold": Decimal|None, "require_project_lead_approval": bool,
    "critical_parts_team_id": UUID|None}`` with the plan's defaults. Anything
    stored that cannot be parsed falls back to its default."""
    settings = dict(PURCHASING_DEFAULTS)
    raw = org.settings_json if isinstance(org.settings_json, dict) else {}
    stored = raw.get(PURCHASING_KEY)
    stored = stored if isinstance(stored, dict) else {}
    threshold = None
    if stored.get("advisor_review_threshold") is not None:
        try:
            threshold = to_money(Decimal(str(stored["advisor_review_threshold"])))
        except (ArithmeticError, ValueError):
            threshold = None
        else:
            if not threshold.is_finite() or threshold < 0:
                threshold = None
    settings.update(
        {
            "advisor_review_threshold": threshold,
            "require_project_lead_approval": bool(stored.get("require_project_lead_approval", PURCHASING_DEFAULTS["require_project_lead_approval"])),
            "critical_parts_team_id": parse_uuid(stored.get("critical_parts_team_id")),
        }
    )
    return settings


def get_settings(ctx) -> dict:
    policy.authorize(ctx, SETTINGS_PERMISSION)
    return purchasing_settings(ctx.org)


def update_settings(ctx, payload: dict) -> dict:
    """Replace the whole ``purchasing`` block (PUT semantics: omitted keys reset
    to their default)."""
    policy.authorize(ctx, SETTINGS_PERMISSION)
    data = validate(payload, PURCHASING_SPEC)
    errors: dict[str, str] = {}
    threshold = data.get("advisor_review_threshold")
    if threshold is not None:
        threshold = to_money(threshold)
    team_id = data.get("critical_parts_team_id")
    if team_id is not None:
        team = db.session.get(Team, team_id)
        if team is None or team.organization_id != ctx.org.id:
            errors["critical_parts_team_id"] = "Unknown team."
    if errors:
        raise ValidationErrors(errors)

    before = purchasing_settings(ctx.org)
    block = {
        "advisor_review_threshold": str(threshold) if threshold is not None else None,
        "require_project_lead_approval": bool(data.get("require_project_lead_approval", False)),
        "critical_parts_team_id": str(team_id) if team_id is not None else None,
    }
    merged = dict(ctx.org.settings_json or {})
    merged[PURCHASING_KEY] = block
    ctx.org.settings_json = merged
    ctx.org.updated_by_user_id = ctx.user.id
    audit_events.record(
        ctx,
        "organization.purchasing_settings_updated",
        ctx.org,
        before=_settings_snapshot(before),
        after=_settings_snapshot(purchasing_settings(ctx.org)),
        summary="Updated purchasing settings",
    )
    db.session.commit()
    return purchasing_settings(ctx.org)


def _settings_snapshot(settings: dict) -> dict:
    return {
        "advisor_review_threshold": str(settings["advisor_review_threshold"]) if settings["advisor_review_threshold"] is not None else None,
        "require_project_lead_approval": settings["require_project_lead_approval"],
        "critical_parts_team_id": str(settings["critical_parts_team_id"]) if settings["critical_parts_team_id"] else None,
    }


# --------------------------------------------------------------------------- read rule


def _reads_everything(ctx) -> bool:
    return ctx.has(REVIEW_PERMISSION) or ctx.has(ADVISOR_PERMISSION) or ctx.has(INVENTORY_MANAGE)


def can_read(ctx, request: PurchaseRequest) -> bool:
    """The plan's read rule: approvers and inventory managers read everything,
    everyone else reads their own requests plus requests on projects they manage."""
    if request.organization_id != ctx.org.id:
        return False
    if _reads_everything(ctx):
        return True
    if request.requester_user_id == ctx.user.id:
        return True
    project = request.project if request.project_id else None
    return project is not None and policy.can(ctx, "project.manage", project)


def visible_query(ctx):
    """Query of the purchase requests in ``ctx.org`` the user may read."""
    query = PurchaseRequest.query.filter(PurchaseRequest.organization_id == ctx.org.id)
    if _reads_everything(ctx):
        return query
    criteria = [PurchaseRequest.requester_user_id == ctx.user.id]
    criteria.extend(_managed_project_criteria(ctx))
    return query.filter(or_(*criteria))


def _managed_project_criteria(ctx) -> list:
    """Criteria matching requests on projects the user may manage."""
    scopes = ctx.scopes("project.manage")
    if "chapter" in scopes:
        return [PurchaseRequest.project_id.isnot(None)]
    ids = sorted(ctx.project_ids, key=str) if ("project" in scopes or "own" in scopes) else []
    if ids:
        return [PurchaseRequest.project_id.in_(list(ids))]
    return []


def get_readable(ctx, request_id) -> PurchaseRequest:
    """Load a request the user may read; anything else (including another
    chapter's id and a malformed id) is a 404."""
    parsed = parse_uuid(request_id)
    if parsed is None:
        raise NotFound()
    request = policy.get_or_404(ctx, PurchaseRequest, parsed)
    if not can_read(ctx, request):
        raise NotFound()
    return request


def attachment_count(request: PurchaseRequest) -> int:
    return int(
        db.session.scalar(
            select(func.count(Attachment.id)).where(
                Attachment.organization_id == request.organization_id,
                Attachment.entity_type == "purchase_request",
                Attachment.entity_id == request.id,
            )
        )
        or 0
    )


# --------------------------------------------------------------------------- listing


def _bad_filter(name: str, message: str | None = None):
    return Validation(message or f"Invalid value for filter '{name}'.", field=name, code="bad_filter")


def _uuids(name: str, values) -> list[UUID]:
    parsed = [parse_uuid(value) for value in values]
    if any(item is None for item in parsed):
        raise _bad_filter(name)
    return parsed


def _user_ids(ctx, name: str, values) -> list[int]:
    ids: list[int] = []
    for value in values:
        if str(value).strip().lower() == "me":
            ids.append(ctx.user.id)
            continue
        try:
            ids.append(int(value))
        except (TypeError, ValueError):
            raise _bad_filter(name)
    return ids


def _apply_filters(ctx, query, filters: dict | None, q: str):
    filters = filters or {}
    if filters.get("status"):
        values = filters["status"]
        if any(value not in PURCHASE_REQUEST_STATUSES for value in values):
            raise _bad_filter("status", "Filter 'status' must be one of: " + ", ".join(PURCHASE_REQUEST_STATUSES) + ".")
        query = query.filter(PurchaseRequest.status.in_(values))
    if filters.get("project"):
        query = query.filter(PurchaseRequest.project_id.in_(_uuids("project", filters["project"])))
    if filters.get("vendor"):
        query = query.filter(PurchaseRequest.vendor_id.in_(_uuids("vendor", filters["vendor"])))
    if filters.get("requester"):
        query = query.filter(PurchaseRequest.requester_user_id.in_(_user_ids(ctx, "requester", filters["requester"])))
    q = (q or "").strip()
    if q:
        match = NUMBER_RE.match(q)
        if match:
            query = query.filter(PurchaseRequest.number == int(match.group(1)))
        else:
            like = f"%{q}%"
            items = select(PurchaseRequestItem.purchase_request_id).where(PurchaseRequestItem.description.ilike(like))
            query = query.filter(or_(PurchaseRequest.title.ilike(like), PurchaseRequest.id.in_(items)))
    return query


def _review_criteria(ctx) -> list:
    """Criteria matching requests sitting at a step this user can act on."""
    criteria = []
    for criterion in _managed_project_criteria(ctx):
        criteria.append((PurchaseRequest.status == "submitted") & criterion)
    if ctx.has(REVIEW_PERMISSION):
        criteria.append(PurchaseRequest.status == "treasurer_review")
    if ctx.has(ADVISOR_PERMISSION):
        criteria.append(PurchaseRequest.status == "advisor_review")
    return criteria


def _apply_tab(ctx, query, tab: str):
    if tab == "mine":
        return query.filter(PurchaseRequest.requester_user_id == ctx.user.id)
    if tab == "review":
        criteria = _review_criteria(ctx)
        if not criteria:
            return query.filter(false())
        # Nobody approves their own request, so those never need the caller's review.
        return query.filter(or_(*criteria), PurchaseRequest.requester_user_id != ctx.user.id)
    if tab == "open":
        return query.filter(PurchaseRequest.status.notin_(PURCHASE_REQUEST_CLOSED_STATUSES))
    if tab == "closed":
        return query.filter(PurchaseRequest.status.in_(PURCHASE_REQUEST_CLOSED_STATUSES))
    return query


def _order_by(sort: str):
    descending = sort.startswith("-")
    key = sort[1:] if descending else sort
    if key not in LIST_SORTS:
        raise Validation(f"Unknown sort '{sort}'.", field="sort", code="bad_sort")
    if key == "needed_by":
        primary = [PurchaseRequest.needed_by.is_(None), PurchaseRequest.needed_by.desc() if descending else PurchaseRequest.needed_by.asc()]
    else:
        column = getattr(PurchaseRequest, key)
        primary = [column.desc() if descending else column.asc()]
    return [*primary, PurchaseRequest.number.desc(), PurchaseRequest.id.asc()]


def list_query(ctx, *, filters: dict | None = None, sort: str = DEFAULT_SORT, q: str = "", tab: str | None = None):
    tab = (tab or "all").strip().lower()
    if tab not in TABS:
        raise Validation("tab must be one of: " + ", ".join(TABS) + ".", field="tab", code="bad_filter")
    query = _apply_filters(ctx, visible_query(ctx), filters, q)
    return _apply_tab(ctx, query, tab).order_by(*_order_by(sort or DEFAULT_SORT))


def tab_counts(ctx, filters: dict | None = None, q: str = "") -> dict:
    base = _apply_filters(ctx, visible_query(ctx), filters, q)
    return {tab: int(_apply_tab(ctx, base, tab).order_by(None).count()) for tab in TABS}


# --------------------------------------------------------------------------- resolving references


def _resolve_project(ctx, project_id, errors: dict) -> OpsProject | None:
    if project_id is None:
        return None
    project = db.session.get(OpsProject, project_id)
    if project is None or not policy.can_read_project(ctx, project):
        errors["project_id"] = "Unknown project."
        return None
    return project


def _resolve_vendor(ctx, vendor_id, errors: dict, field: str = "vendor_id") -> Vendor | None:
    if vendor_id is None:
        return None
    vendor = db.session.get(Vendor, vendor_id)
    if vendor is None or vendor.organization_id != ctx.org.id:
        errors[field] = "Unknown vendor."
        return None
    return vendor


def _resolve_location(ctx, location_id, errors: dict, field: str) -> Location | None:
    if location_id is None:
        return None
    location = db.session.get(Location, location_id)
    if location is None or location.organization_id != ctx.org.id:
        errors[field] = "Unknown location."
        return None
    return location


def _default_location(ctx) -> Location | None:
    return (
        Location.query.filter(Location.organization_id == ctx.org.id, Location.is_default.is_(True))
        .order_by(Location.created_at.asc(), Location.id.asc())
        .first()
    )


def _clean_items(ctx, raw_items, errors: dict) -> list[dict]:
    """Validate the line items. Errors are keyed ``items[i].<field>``."""
    cleaned: list[dict] = []
    if not isinstance(raw_items, (list, tuple)) or not raw_items:
        errors["items"] = "Add at least one line item."
        return cleaned
    for index, raw in enumerate(raw_items):
        prefix = f"items[{index}]."
        if not isinstance(raw, dict):
            errors[f"items[{index}]"] = "Must be an object."
            continue
        try:
            data = validate(raw, ITEM_SPEC)
        except ValidationErrors as exc:
            errors.update({f"{prefix}{key}": message for key, message in exc.errors.items()})
            continue
        part = None
        if data.get("part_id") is not None:
            part = db.session.get(Part, data["part_id"])
            if part is None or part.organization_id != ctx.org.id:
                errors[f"{prefix}part_id"] = "Unknown part."
                part = None
        description = (data.get("description") or "").strip()
        if not description:
            description = part.name if part is not None else ""
        if not description:
            errors[f"{prefix}description"] = "This field is required."
        quantity = data["quantity"]
        if quantity <= 0:
            errors[f"{prefix}quantity"] = "Must be greater than 0."
        elif to_money(quantity * (data.get("unit_price") or ZERO)) > MONEY_MAX:
            # quantity and unit_price each pass their own bound; their product is
            # what the Numeric(12, 2) total has to hold.
            errors[f"{prefix}quantity"] = LINE_TOO_LARGE
        location = None
        if data.get("receive_location_id") is not None:
            location = _resolve_location(ctx, data["receive_location_id"], errors, f"{prefix}receive_location_id")
        cleaned.append(
            {
                "part_id": part.id if part is not None else None,
                "description": description[:300],
                "vendor_part_number": data.get("vendor_part_number"),
                "url": data.get("url"),
                "quantity": quantity,
                "unit_price": data.get("unit_price") or ZERO,
                "receive_location_id": location.id if location is not None else None,
            }
        )
    return cleaned


def _replace_items(request: PurchaseRequest, items: list[dict]) -> None:
    for existing in list(request.items):
        request.items.remove(existing)
    db.session.flush()
    for position, item in enumerate(items):
        request.items.append(
            PurchaseRequestItem(
                part_id=item["part_id"],
                description=item["description"],
                vendor_part_number=item["vendor_part_number"],
                url=item["url"],
                quantity=item["quantity"],
                unit_price=item["unit_price"],
                received_quantity=ZERO,
                receive_location_id=item["receive_location_id"],
                position=position,
            )
        )
    db.session.flush()


def recompute_total(request: PurchaseRequest) -> Decimal:
    """``sum(line totals) + shipping + tax``, stored on the request.

    The sum is refused above ``MONEY_MAX``: the column is ``Numeric(12, 2)`` and
    a hundred in-bounds lines can still add up past it, which PostgreSQL rejects
    with ``numeric field overflow`` at INSERT time.
    """
    total = sum((line_total(item) for item in request.items), ZERO)
    total = total + to_money(request.shipping_amount) + to_money(request.tax_amount)
    if total > MONEY_MAX:
        raise ValidationErrors({"items": TOTAL_TOO_LARGE})
    request.estimated_total = total
    return total


# --------------------------------------------------------------------------- create / update


def _apply_header(ctx, request: PurchaseRequest, data: dict, resolved: dict) -> None:
    for key in ("title", "needed_by", "purpose", "budget_code"):
        if key in data:
            setattr(request, key, data[key])
    for key in ("shipping_amount", "tax_amount"):
        if key in data:
            setattr(request, key, to_money(data[key]))
    if "project" in resolved:
        request.project_id = resolved["project"].id if resolved["project"] is not None else None
    if "vendor" in resolved:
        request.vendor_id = resolved["vendor"].id if resolved["vendor"] is not None else None


def create(ctx, payload: dict) -> PurchaseRequest:
    policy.authorize(ctx, SUBMIT_PERMISSION)
    data = validate(payload, CREATE_SPEC)
    errors: dict[str, str] = {}
    resolved = {
        "project": _resolve_project(ctx, data.get("project_id"), errors),
        "vendor": _resolve_vendor(ctx, data.get("vendor_id"), errors),
    }
    items = _clean_items(ctx, data.get("items"), errors)
    if errors:
        raise ValidationErrors(errors)
    request = _build(ctx, data, resolved, items)
    db.session.commit()
    return request


def _build(ctx, data: dict, resolved: dict, items: list[dict]) -> PurchaseRequest:
    """Create the row inside the caller's transaction (flush, no commit)."""
    request = PurchaseRequest(
        organization_id=ctx.org.id,
        number=next_number(ctx.org.id, SEQUENCE_KEY),
        title=data["title"],
        requester_user_id=ctx.user.id,
        status="draft",
        shipping_amount=ZERO,
        tax_amount=ZERO,
        estimated_total=ZERO,
        created_by_user_id=ctx.user.id,
        updated_by_user_id=ctx.user.id,
    )
    _apply_header(ctx, request, data, resolved)
    db.session.add(request)
    db.session.flush()
    _replace_items(request, items)
    recompute_total(request)
    db.session.flush()
    audit_events.record(
        ctx,
        "purchase_request.created",
        request,
        after=audit_events.snapshot(request, SNAPSHOT_FIELDS),
        summary=f"Created {request.display_number} {request.title}",
    )
    return request


def update(ctx, request: PurchaseRequest, payload: dict) -> PurchaseRequest:
    """Edit a draft. The requester or a ``purchase.review`` holder may edit;
    ``items`` replaces every line when it is present."""
    if not can_read(ctx, request):
        raise NotFound()
    if request.requester_user_id != ctx.user.id and not ctx.has(REVIEW_PERMISSION):
        raise Forbidden("Only the requester can edit this purchase request.", permission=REVIEW_PERMISSION)
    if request.status != "draft":
        raise Conflict(
            f"This purchase request is {STATUS_LABELS.get(request.status, request.status)} and can no longer be edited.",
            code=INVALID_TRANSITION,
            **{"from": request.status, "action": "update"},
        )
    data = validate(payload, UPDATE_SPEC, partial=True)
    errors: dict[str, str] = {}
    resolved: dict = {}
    if "project_id" in data:
        resolved["project"] = _resolve_project(ctx, data["project_id"], errors)
    if "vendor_id" in data:
        resolved["vendor"] = _resolve_vendor(ctx, data["vendor_id"], errors)
    items = _clean_items(ctx, data["items"], errors) if "items" in data else None
    if errors:
        raise ValidationErrors(errors)

    before = audit_events.snapshot(request, SNAPSHOT_FIELDS)
    _apply_header(ctx, request, data, resolved)
    if items is not None:
        _replace_items(request, items)
    recompute_total(request)
    request.updated_by_user_id = ctx.user.id
    db.session.flush()
    after = audit_events.snapshot(request, SNAPSHOT_FIELDS)
    changed = sorted(key for key in after if after[key] != before[key])
    audit_events.record(
        ctx,
        "purchase_request.updated",
        request,
        before={key: before[key] for key in changed},
        after={key: after[key] for key in changed},
        summary=f"Updated {request.display_number} {request.title}",
        changed_fields=changed,
        items_replaced=items is not None,
    )
    db.session.commit()
    return request


# --------------------------------------------------------------------------- permissions per action


def _step_of(request: PurchaseRequest) -> str | None:
    return STEP_BY_STATUS.get(request.status)


def _can_review_step(ctx, request: PurchaseRequest) -> bool:
    step = _step_of(request)
    if step == "project_lead":
        project = request.project if request.project_id else None
        return project is not None and policy.can(ctx, "project.manage", project)
    if step == "treasurer":
        return ctx.has(REVIEW_PERMISSION)
    if step == "advisor":
        return ctx.has(ADVISOR_PERMISSION)
    return False


def _step_permission(request: PurchaseRequest) -> str:
    return {"project_lead": "project.manage", "treasurer": REVIEW_PERMISSION, "advisor": ADVISOR_PERMISSION}.get(_step_of(request) or "", REVIEW_PERMISSION)


def _is_requester(ctx, request: PurchaseRequest) -> bool:
    return request.requester_user_id == ctx.user.id


def has_approved(ctx, request: PurchaseRequest) -> bool:
    """True when this caller already signed a step of the round of review the
    request is currently in.

    The advisor step exists to put a second, independent signature on spending
    above the chapter's threshold, and the default grants give a faculty advisor
    both ``purchase.review`` and ``purchase.advisor_review`` - without this the
    same person clears both steps and the threshold buys nothing. A request sent
    back to ``draft`` starts a fresh round (``submitted_at`` is cleared), so an
    earlier round's signature never blocks the new one.
    """
    if request.id is None:
        return False
    stmt = select(PurchaseRequestEvent.id).where(
        PurchaseRequestEvent.purchase_request_id == request.id,
        PurchaseRequestEvent.action == "approve",
        PurchaseRequestEvent.actor_user_id == ctx.user.id,
    )
    if request.submitted_at is not None:
        stmt = stmt.where(PurchaseRequestEvent.created_at >= request.submitted_at)
    return db.session.scalar(stmt.limit(1)) is not None


def can_perform(ctx, request: PurchaseRequest, action: str) -> bool:
    """True when ``action`` is allowed right now for this caller (no raise)."""
    if action not in ACTION_FROM_STATUSES or request.status not in ACTION_FROM_STATUSES[action]:
        return False
    if action == "submit":
        return _is_requester(ctx, request) and bool(request.items)
    if action in ("approve", "decline", "request_changes"):
        if not _can_review_step(ctx, request):
            return False
        if action != "approve":
            return True
        return not _is_requester(ctx, request) and not has_approved(ctx, request)
    if action == "order":
        return ctx.has(INVENTORY_MANAGE) or ctx.has(REVIEW_PERMISSION)
    if action == "receive":
        return ctx.has(INVENTORY_MANAGE)
    if action == "cancel":
        if ctx.has(REVIEW_PERMISSION):
            return True
        return _is_requester(ctx, request) and request.status in CANCEL_REQUESTER_STATUSES
    if action == "reopen":
        return ctx.has(REVIEW_PERMISSION)
    return False


def available_actions(ctx, request: PurchaseRequest) -> list[str]:
    return [action for action in ACTIONS if can_perform(ctx, request, action)]


def _require_state(request: PurchaseRequest, action: str) -> None:
    if request.status not in ACTION_FROM_STATUSES[action]:
        raise Conflict(
            f"Cannot {action.replace('_', ' ')} a purchase request that is {STATUS_LABELS.get(request.status, request.status)}.",
            code=INVALID_TRANSITION,
            **{"from": request.status, "action": action},
        )


def _authorize_action(ctx, request: PurchaseRequest, action: str) -> None:
    """From-state first, then the step's permission, then the self-approval rule."""
    _require_state(request, action)
    if action == "submit":
        if not _is_requester(ctx, request):
            raise Forbidden("Only the requester can submit this purchase request.", permission=SUBMIT_PERMISSION)
        return
    if action in ("approve", "decline", "request_changes"):
        if not _can_review_step(ctx, request):
            raise Forbidden("You cannot act on this purchase request at this step.", permission=_step_permission(request))
        if action == "approve":
            if _is_requester(ctx, request):
                raise Conflict(
                    "You cannot approve a purchase request you submitted.",
                    code=SELF_APPROVAL,
                    purchase_request_id=str(request.id),
                )
            if has_approved(ctx, request):
                raise Conflict(
                    "You already approved this purchase request. Another approver has to sign this step.",
                    code=ALREADY_APPROVED,
                    purchase_request_id=str(request.id),
                )
        return
    if action == "order":
        if not (ctx.has(INVENTORY_MANAGE) or ctx.has(REVIEW_PERMISSION)):
            raise Forbidden("You do not have permission to do that.", permission=INVENTORY_MANAGE)
        return
    if action == "receive":
        policy.authorize(ctx, INVENTORY_MANAGE, request)
        return
    if action == "cancel":
        if ctx.has(REVIEW_PERMISSION):
            return
        if _is_requester(ctx, request) and request.status in CANCEL_REQUESTER_STATUSES:
            return
        raise Forbidden("You cannot cancel this purchase request.", permission=REVIEW_PERMISSION)
    if action == "reopen":
        policy.authorize(ctx, REVIEW_PERMISSION, request)
        return
    raise Validation(f"Unknown action '{action}'.", field="action", code="bad_action")


# --------------------------------------------------------------------------- timeline, audit, notifications


def _timeline(ctx, request: PurchaseRequest, action: str, previous: str, comment: str | None) -> PurchaseRequestEvent:
    row = PurchaseRequestEvent(
        organization_id=ctx.org.id,
        purchase_request_id=request.id,
        from_status=previous,
        to_status=request.status,
        action=action,
        step=STEP_BY_STATUS.get(previous),
        comment=comment,
        actor_user_id=ctx.user.id,
    )
    db.session.add(row)
    return row


def _holders(ctx, key: str) -> set[int]:
    return ledger.active_member_ids_with_permission(ctx.org.id, key)


def _project_lead_ids(ctx, request: PurchaseRequest) -> set[int]:
    project = request.project if request.project_id else None
    if project is not None and project.lead_user_id:
        return {project.lead_user_id}
    # No lead on the project: the treasurers still need to see it so it does not stall.
    return _holders(ctx, REVIEW_PERMISSION)


def _notify_recipients(ctx, request: PurchaseRequest) -> None:
    label = STATUS_LABELS.get(request.status, request.status)
    title = f"{request.display_number} {request.title} is {label}"
    if request.status == "submitted":
        notifications.notify(
            ctx, _project_lead_ids(ctx, request), NEEDS_REVIEW_NOTIFICATION, f"{request.display_number} {request.title} needs your approval", entity=request
        )
        return
    if request.status == "treasurer_review":
        notifications.notify(
            ctx, _holders(ctx, REVIEW_PERMISSION), NEEDS_REVIEW_NOTIFICATION, f"{request.display_number} {request.title} needs treasurer approval", entity=request
        )
        return
    if request.status == "advisor_review":
        notifications.notify(
            ctx, _holders(ctx, ADVISOR_PERMISSION), NEEDS_REVIEW_NOTIFICATION, f"{request.display_number} {request.title} needs advisor sign-off", entity=request
        )
        return
    notifications.notify(ctx, [request.requester_user_id], STATUS_NOTIFICATION, title, request.decline_reason if request.status == "declined" else None, entity=request)


# --------------------------------------------------------------------------- actions


def perform(ctx, request: PurchaseRequest, action: str, payload: dict | None = None) -> PurchaseRequest:
    """Apply one workflow action. ``action`` accepts the hyphenated route spelling."""
    action = (action or "").strip().lower().replace("-", "_")
    if action not in ACTION_FROM_STATUSES:
        raise Validation(f"Unknown action '{action}'.", field="action", code="bad_action")
    if not can_read(ctx, request):
        raise NotFound()
    payload = payload if isinstance(payload, dict) else {}
    _authorize_action(ctx, request, action)

    previous = request.status
    now = utcnow()
    handler = {
        "submit": _do_submit,
        "approve": _do_approve,
        "decline": _do_decline,
        "request_changes": _do_request_changes,
        "order": _do_order,
        "receive": _do_receive,
        "cancel": _do_cancel,
        "reopen": _do_reopen,
    }[action]
    comment = handler(ctx, request, payload, now)

    request.updated_by_user_id = ctx.user.id
    db.session.flush()
    _timeline(ctx, request, action, previous, comment)
    audit_events.record(
        ctx,
        f"purchase_request.{action}",
        request,
        before={"status": previous},
        after={"status": request.status, "estimated_total": audit_events.jsonable(request.estimated_total)},
        summary=f"{request.display_number} {request.title}: {previous} -> {request.status}",
        action=action,
        comment=comment,
    )
    _notify_recipients(ctx, request)
    db.session.commit()
    ledger.emit_pending_events()
    events.emit(
        events.PURCHASE_REQUEST_STATUS_CHANGED,
        organization_id=str(ctx.org.id),
        purchase_request_id=str(request.id),
        status=request.status,
        previous=previous,
        action=action,
    )
    return request


def _comment_of(payload: dict, *, required: bool) -> str | None:
    data = validate(payload, COMMENT_SPEC if required else OPTIONAL_COMMENT_SPEC, partial=not required)
    comment = (data.get("comment") or "").strip()
    return comment or None


def _do_submit(ctx, request: PurchaseRequest, payload: dict, now) -> str | None:
    if not request.items:
        raise ValidationErrors({"items": "Add at least one line item before submitting."})
    recompute_total(request)
    settings = purchasing_settings(ctx.org)
    if settings["require_project_lead_approval"] and request.project_id is not None:
        request.status = "submitted"
    else:
        request.status = "treasurer_review"
    request.submitted_at = now
    request.declined_at = None
    request.decline_reason = None
    request.canceled_at = None
    return _comment_of(payload, required=False)


def _do_approve(ctx, request: PurchaseRequest, payload: dict, now) -> str | None:
    data = validate(payload, APPROVE_SPEC, partial=True)
    if data.get("approved_total") is not None:
        request.approved_total = to_money(data["approved_total"])
    recompute_total(request)
    settings = purchasing_settings(ctx.org)
    if request.status == "submitted":
        request.status = "treasurer_review"
    elif request.status == "treasurer_review":
        threshold = settings["advisor_review_threshold"]
        if threshold is not None and to_money(request.estimated_total) >= threshold:
            request.status = "advisor_review"
        else:
            request.status = "approved"
    else:
        request.status = "approved"
    if request.status == "approved":
        request.approved_at = now
        if request.approved_total is None:
            request.approved_total = to_money(request.estimated_total)
    comment = (data.get("comment") or "").strip()
    return comment or None


def _do_decline(ctx, request: PurchaseRequest, payload: dict, now) -> str | None:
    comment = _comment_of(payload, required=True)
    request.status = "declined"
    request.declined_at = now
    request.decline_reason = comment
    return comment


def _do_request_changes(ctx, request: PurchaseRequest, payload: dict, now) -> str | None:
    comment = _comment_of(payload, required=True)
    request.status = "draft"
    request.submitted_at = None
    # The approval this round produced is abandoned: the requester is about to
    # change the very amounts it signed off on, so the next approval has to
    # record what it actually approved rather than inheriting the old number.
    request.approved_at = None
    request.approved_total = None
    return comment


def _do_order(ctx, request: PurchaseRequest, payload: dict, now) -> str | None:
    data = validate(payload, ORDER_SPEC, partial=True)
    if data.get("approved_total") is not None:
        request.approved_total = to_money(data["approved_total"])
    if request.approved_total is None:
        request.approved_total = to_money(request.estimated_total)
    request.order_reference = data.get("order_reference") or request.order_reference
    ordered_at = data.get("ordered_at") or now
    request.ordered_at = ordered_at
    request.status = "ordered"
    _touch_vendor_links(request, ordered_at=ordered_at)
    comment = (data.get("comment") or "").strip()
    return comment or None


def _do_cancel(ctx, request: PurchaseRequest, payload: dict, now) -> str | None:
    comment = _comment_of(payload, required=False)
    request.status = "canceled"
    request.canceled_at = now
    return comment


def _do_reopen(ctx, request: PurchaseRequest, payload: dict, now) -> str | None:
    comment = _comment_of(payload, required=False)
    request.status = "draft"
    request.declined_at = None
    request.decline_reason = None
    request.canceled_at = None
    request.submitted_at = None
    request.approved_at = None
    request.approved_total = None
    return comment


def _part_vendor_link(part_id, vendor_id) -> PartVendor | None:
    if part_id is None or vendor_id is None:
        return None
    return PartVendor.query.filter_by(part_id=part_id, vendor_id=vendor_id).first()


def _touch_vendor_links(request: PurchaseRequest, *, ordered_at) -> None:
    for item in request.items:
        link = _part_vendor_link(item.part_id, request.vendor_id)
        if link is not None:
            link.last_ordered_at = ordered_at


# --------------------------------------------------------------------------- receiving


def _outstanding(item: PurchaseRequestItem) -> Decimal:
    return _quantity(item.quantity) - _quantity(item.received_quantity)


def _receive_location(ctx, item: PurchaseRequestItem, location_id, errors: dict, field: str) -> Location | None:
    if location_id is not None:
        return _resolve_location(ctx, location_id, errors, field)
    for candidate_id in (item.receive_location_id, item.part.default_location_id if item.part is not None else None):
        if candidate_id is not None:
            location = db.session.get(Location, candidate_id)
            if location is not None and location.organization_id == ctx.org.id:
                return location
    return _default_location(ctx)


def _do_receive(ctx, request: PurchaseRequest, payload: dict, now) -> str | None:
    data = validate(payload, RECEIVE_SPEC)
    note = (data.get("note") or "").strip() or None
    raw_lines = data.get("lines") or []
    if not raw_lines:
        raise ValidationErrors({"lines": "Record at least one received line."})

    items = {item.id: item for item in request.items}
    errors: dict[str, str] = {}
    planned: list[tuple[PurchaseRequestItem, Decimal, Location | None]] = []
    seen: set = set()
    for index, raw in enumerate(raw_lines):
        prefix = f"lines[{index}]."
        if not isinstance(raw, dict):
            errors[f"lines[{index}]"] = "Must be an object."
            continue
        try:
            line = validate(raw, RECEIVE_LINE_SPEC)
        except ValidationErrors as exc:
            errors.update({f"{prefix}{key}": message for key, message in exc.errors.items()})
            continue
        item = items.get(line["item_id"])
        if item is None:
            errors[f"{prefix}item_id"] = "Unknown line item."
            continue
        if item.id in seen:
            errors[f"{prefix}item_id"] = "This line appears more than once."
            continue
        seen.add(item.id)
        quantity = line["quantity"]
        if quantity <= 0:
            errors[f"{prefix}quantity"] = "Must be greater than 0."
            continue
        outstanding = _outstanding(item)
        if quantity > outstanding:
            errors[f"{prefix}quantity"] = f"Only {outstanding} of this line is still outstanding."
            continue
        location = None
        if item.part_id is not None:
            location = _receive_location(ctx, item, line.get("location_id"), errors, f"{prefix}location_id")
            if location is None and f"{prefix}location_id" not in errors:
                errors[f"{prefix}location_id"] = "Choose a location to receive this part into."
        planned.append((item, quantity, location))
    if errors:
        raise ValidationErrors(errors)

    for item, quantity, location in planned:
        if item.part_id is not None and location is not None:
            part = item.part if item.part is not None else db.session.get(Part, item.part_id)
            ledger.post(
                ctx,
                part=part,
                location=location,
                transaction_type="receipt",
                on_hand_delta=quantity,
                quantity=quantity,
                unit_cost=_price(item.unit_price),
                purchase_request=request,
                purchase_request_item=item,
                note=note,
            )
            link = _part_vendor_link(item.part_id, request.vendor_id)
            if link is not None:
                link.last_price = _price(item.unit_price)
        item.received_quantity = _quantity(item.received_quantity) + quantity

    db.session.flush()
    if all(_outstanding(item) <= 0 for item in request.items):
        request.status = "received"
        request.received_at = now
    else:
        request.status = "partially_received"
    return note


# --------------------------------------------------------------------------- from low stock


def suggested_order_quantity(part: Part, totals: dict) -> Decimal:
    """``reorder_quantity``, else ``maximum_stock - available``, else
    ``minimum_stock - available``, never below 1."""
    available = _quantity(totals.get("available"))
    if part.reorder_quantity is not None:
        quantity = _quantity(part.reorder_quantity)
    elif part.maximum_stock is not None:
        quantity = _quantity(part.maximum_stock) - available
    elif part.minimum_stock is not None:
        quantity = _quantity(part.minimum_stock) - available
    else:
        quantity = ONE
    return quantity if quantity >= ONE else ONE


def _suggested_price(part: Part, link: PartVendor | None) -> Decimal:
    if link is not None and link.last_price is not None:
        return _price(link.last_price)
    if part.unit_cost is not None:
        return _price(part.unit_cost)
    return ZERO


def from_low_stock(ctx, payload: dict) -> list[PurchaseRequest]:
    """One draft per preferred vendor (parts without one share a vendorless draft),
    with the documented suggested quantities and prices."""
    policy.authorize(ctx, SUBMIT_PERMISSION)
    policy.authorize(ctx, INVENTORY_READ)
    data = validate(payload, FROM_LOW_STOCK_SPEC)
    wanted = list(dict.fromkeys(data["part_ids"]))
    if not wanted:
        raise ValidationErrors({"part_ids": "Choose at least one part."})
    rows = {row.id: row for row in db.session.scalars(select(Part).where(Part.organization_id == ctx.org.id, Part.id.in_(wanted)))}
    missing = [str(part_id) for part_id in wanted if part_id not in rows]
    if missing:
        raise ValidationErrors({"part_ids": f"Unknown part: {', '.join(missing)}."})

    totals = ledger.part_totals(wanted)
    groups: dict = {}
    for part_id in wanted:
        part = rows[part_id]
        link = part.preferred_vendor_link
        vendor_id = link.vendor_id if link is not None else None
        groups.setdefault(vendor_id, []).append((part, link))

    created: list[PurchaseRequest] = []
    for vendor_id, entries in groups.items():
        vendor = db.session.get(Vendor, vendor_id) if vendor_id is not None else None
        items = []
        for part, link in entries:
            items.append(
                {
                    "part_id": part.id,
                    "description": part.name[:300],
                    "vendor_part_number": link.vendor_part_number if link is not None else None,
                    "url": link.url if link is not None else None,
                    "quantity": suggested_order_quantity(part, totals.get(part.id, {})),
                    "unit_price": _suggested_price(part, link),
                    "receive_location_id": part.default_location_id,
                }
            )
        title = f"Restock: {vendor.name}" if vendor is not None else "Restock"
        request = _build(
            ctx,
            {"title": title[:200], "purpose": "Created from low stock."},
            {"project": None, "vendor": vendor},
            items,
        )
        created.append(request)
    db.session.commit()
    return created


# --------------------------------------------------------------------------- project budget


def committed_total(project) -> Decimal:
    """Money the chapter has committed to this project through purchase requests."""
    value = db.session.scalar(
        select(func.coalesce(func.sum(func.coalesce(PurchaseRequest.approved_total, PurchaseRequest.estimated_total)), 0)).where(
            PurchaseRequest.project_id == project.id,
            PurchaseRequest.organization_id == project.organization_id,
            PurchaseRequest.status.in_(PURCHASE_REQUEST_COMMITTED_STATUSES),
        )
    )
    return to_money(value or 0)
