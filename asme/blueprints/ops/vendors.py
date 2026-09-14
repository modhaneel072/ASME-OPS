"""Vendors: ``GET|POST /vendors``, ``GET|PATCH /vendors/:id``.

There is no delete; retire a vendor with ``PATCH {"is_active": false}``."""

from __future__ import annotations

from asme.blueprints.ops import bp, json_body, list_payload, ok, paginate, parse_filters, parse_sort, query_text
from asme.ops import policy
from asme.ops.serializers.vendors import vendor as serialize_vendor
from asme.ops.services import vendors


@bp.get("/vendors")
@policy.require_permission("vendor.read")
def vendors_list():
    ctx = policy.current_context()
    query = vendors.list_query(
        ctx,
        q=query_text(),
        filters=parse_filters(vendors.FILTERS),
        sort=parse_sort(vendors.SORTS, vendors.DEFAULT_SORT),
    )
    rows, next_cursor, total = paginate(query)
    return ok(list_payload("vendors", [serialize_vendor(row) for row in rows], next_cursor, total))


@bp.post("/vendors")
@policy.require_permission("vendor.manage")
def vendors_create():
    ctx = policy.current_context()
    row = vendors.create(ctx, json_body())
    return ok({"vendor": serialize_vendor(row)}, status=201)


@bp.get("/vendors/<vendor_id>")
@policy.require_permission("vendor.read")
def vendors_get(vendor_id):
    ctx = policy.current_context()
    return ok({"vendor": serialize_vendor(vendors.get(ctx, vendor_id))})


@bp.patch("/vendors/<vendor_id>")
@policy.require_permission("vendor.manage")
def vendors_patch(vendor_id):
    ctx = policy.current_context()
    row = vendors.update(ctx, vendors.get(ctx, vendor_id), json_body())
    return ok({"vendor": serialize_vendor(row)})
