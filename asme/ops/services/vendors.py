"""Vendors service (``ops_vendors``).

Vendors are never deleted: ``update(ctx, vendor, {"is_active": false})``
retires one while keeping the purchase and work-order history that points at it.
"""

from __future__ import annotations

from sqlalchemy import func, or_

from asme.extensions import db
from asme.ops import policy
from asme.ops.models import Vendor
from asme.ops.serializers.vendors import VENDOR_SNAPSHOT_FIELDS
from asme.ops.services import audit_events
from asme.ops.types import parse_uuid
from asme.ops.validation import Field, ValidationErrors, validate
from asme.services.errors import NotFound, Validation

SORTS = ("name", "created_at")
DEFAULT_SORT = "name"
FILTERS = {"active": "single"}


def _object_only(value) -> str | None:
    return None if isinstance(value, dict) else "Must be an object."


VENDOR_SPEC = {
    "name": Field("str", required=True, nullable=False, max_len=200, min_len=1),
    "contact_name": Field("str", max_len=160),
    "email": Field("email", max_len=160),
    "phone": Field("str", max_len=40),
    "website": Field("url", max_len=300),
    "address": Field("json", check=_object_only),
    "notes": Field("text"),
    "is_active": Field("bool", nullable=False),
}

ASSIGNABLE = ("contact_name", "email", "phone", "website", "notes", "is_active")


# --------------------------------------------------------------------------- reads


def get(ctx, vendor_id) -> Vendor:
    policy.authorize(ctx, "vendor.read")
    parsed = parse_uuid(vendor_id)
    if parsed is None:
        raise NotFound()
    return policy.get_or_404(ctx, Vendor, parsed)


def _parse_active(values: list[str] | None) -> bool | None:
    if not values:
        return None
    raw = values[0].strip().lower()
    if raw in {"true", "1", "yes"}:
        return True
    if raw in {"false", "0", "no"}:
        return False
    if raw == "all":
        return None
    raise Validation("filter[active] must be true, false or all.", field="active", code="bad_filter")


def list_query(ctx, *, q: str = "", filters: dict[str, list[str]] | None = None, sort: str = DEFAULT_SORT):
    """Query of the organization's vendors, filtered and ordered. The route paginates."""
    policy.authorize(ctx, "vendor.read")
    filters = filters or {}
    query = Vendor.query.filter(Vendor.organization_id == ctx.org.id)
    if q:
        needle = f"%{q.lower()}%"
        query = query.filter(
            or_(
                func.lower(Vendor.name).like(needle),
                func.lower(func.coalesce(Vendor.contact_name, "")).like(needle),
                func.lower(func.coalesce(Vendor.email, "")).like(needle),
            )
        )
    active = _parse_active(filters.get("active"))
    if active is not None:
        query = query.filter(Vendor.is_active.is_(active))
    descending = sort.startswith("-")
    key = sort[1:] if descending else sort
    if key not in SORTS:
        raise Validation(f"Unknown sort '{sort}'.", field="sort", code="bad_sort")
    column = {"name": func.lower(Vendor.name), "created_at": Vendor.created_at}[key]
    primary = column.desc() if descending else column.asc()
    return query.order_by(primary, Vendor.id.asc())


# --------------------------------------------------------------------------- writes


def _name_taken(ctx, name: str, *, exclude_id=None) -> bool:
    query = Vendor.query.filter(Vendor.organization_id == ctx.org.id, func.lower(Vendor.name) == name.lower())
    if exclude_id is not None:
        query = query.filter(Vendor.id != exclude_id)
    return db.session.query(query.exists()).scalar()


def create(ctx, payload: dict) -> Vendor:
    policy.authorize(ctx, "vendor.manage")
    data = validate(payload, VENDOR_SPEC)
    if _name_taken(ctx, data["name"]):
        raise ValidationErrors({"name": "A vendor with this name already exists."})
    vendor = Vendor(organization_id=ctx.org.id, name=data["name"], created_by_user_id=ctx.user.id, updated_by_user_id=ctx.user.id)
    for key in ASSIGNABLE:
        if key in data:
            setattr(vendor, key, data[key])
    if "address" in data:
        vendor.address_json = data["address"]
    db.session.add(vendor)
    db.session.flush()
    audit_events.record(
        ctx,
        "vendor.created",
        vendor,
        after=audit_events.snapshot(vendor, VENDOR_SNAPSHOT_FIELDS),
        summary=f"Created vendor {vendor.name}",
    )
    db.session.commit()
    return vendor


def update(ctx, vendor: Vendor, payload: dict) -> Vendor:
    policy.authorize(ctx, "vendor.manage", vendor)
    data = validate(payload, VENDOR_SPEC, partial=True)
    if "name" in data and data["name"] != vendor.name and _name_taken(ctx, data["name"], exclude_id=vendor.id):
        raise ValidationErrors({"name": "A vendor with this name already exists."})
    before = audit_events.snapshot(vendor, VENDOR_SNAPSHOT_FIELDS)
    if "name" in data:
        vendor.name = data["name"]
    for key in ASSIGNABLE:
        if key in data:
            setattr(vendor, key, data[key])
    if "address" in data:
        vendor.address_json = data["address"]
    vendor.updated_by_user_id = ctx.user.id
    after = audit_events.snapshot(vendor, VENDOR_SNAPSHOT_FIELDS)
    changed = sorted(key for key in after if after[key] != before[key])
    audit_events.record(
        ctx,
        "vendor.updated",
        vendor,
        before=before,
        after=after,
        summary=f"Updated vendor {vendor.name}",
        changed_fields=changed,
    )
    db.session.commit()
    return vendor
