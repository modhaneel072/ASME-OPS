"""Parts, part types and inventory.

``GET|POST /parts``, ``GET|PATCH /parts/:id``, ``GET /parts/by-code/:code``,
``PUT /parts/:id/vendors``, ``PUT /parts/:id/assets``, ``GET /parts/:id/inventory``,
``GET|POST /parts/:id/transactions``, ``GET|POST /part-types``,
``POST /inventory/transfers``, ``POST /inventory/cycle-counts``,
``GET /inventory/cycle-counts/sheet``, ``GET /inventory/low-stock`` and the
chapter-wide ``GET /inventory/transactions``.

There is no delete: retire a part with ``PATCH {"is_active": false}`` and correct
a movement with a new one - the ledger is append-only.
"""

from __future__ import annotations

from flask import request

from asme.blueprints.ops import bp, json_body, list_payload, ok, paginate, parse_filters, parse_sort, query_text
from asme.ops import policy
from asme.ops.serializers import location_ref
from asme.ops.serializers.parts import (
    balance as serialize_balance,
    cycle_count_line,
    cycle_count_sheet_line,
    inventory_transaction as serialize_transaction,
    low_stock_item,
    open_purchase_request,
    part as serialize_part,
    part_detail as serialize_part_detail,
    part_type as serialize_part_type,
    stock_totals,
)
from asme.ops.services import inventory, parts

READ = "inventory.read"
MANAGE = "inventory.manage"


# --------------------------------------------------------------------------- serialization helpers


def _serialize_page(rows):
    totals, states = parts.enrich(rows)
    return [serialize_part(row, totals=totals.get(row.id), stock_state=states.get(row.id, "untracked")) for row in rows]


def _serialize_one(row):
    return _serialize_page([row])[0]


def _serialize_transactions(ctx, rows):
    readable_work_orders = inventory.readable_work_order_ids(ctx, rows)
    readable_requests = inventory.readable_purchase_request_ids(ctx, rows)
    return [
        serialize_transaction(
            row,
            work_order_readable=row.work_order_id in readable_work_orders,
            purchase_request_readable=row.purchase_request_id in readable_requests,
        )
        for row in rows
    ]


def _serialize_detail(ctx, row):
    totals, states = parts.enrich([row])
    recent = inventory.transactions_query(ctx, part=row).limit(parts.RECENT_TRANSACTION_LIMIT).all()
    return serialize_part_detail(
        row,
        totals=totals.get(row.id),
        stock_state=states.get(row.id, "untracked"),
        balances=parts.balances(ctx, row),
        open_purchase_requests=[open_purchase_request(request_row, quantity) for request_row, quantity in parts.open_purchase_requests(ctx, row)],
        recent_transactions=_serialize_transactions(ctx, recent),
    )


# --------------------------------------------------------------------------- parts


@bp.get("/parts")
@policy.require_permission(READ)
def parts_list():
    ctx = policy.current_context()
    text = query_text()
    filters = parse_filters(parts.FILTERS)
    query = parts.list_query(ctx, q=text, filters=filters, sort=parse_sort(parts.SORTS, parts.DEFAULT_SORT))
    rows, next_cursor, total = paginate(query)
    payload = list_payload("parts", _serialize_page(rows), next_cursor, total)
    payload["stock_counts"] = parts.stock_counts(ctx, q=text, filters=filters)
    return ok(payload)


@bp.post("/parts")
@policy.require_permission(MANAGE)
def parts_create():
    ctx = policy.current_context()
    row = parts.create(ctx, json_body())
    return ok({"part": _serialize_detail(ctx, row)}, status=201)


@bp.get("/parts/by-code/<path:code>")
@policy.require_permission(READ)
def parts_by_code(code):
    ctx = policy.current_context()
    return ok({"part": _serialize_detail(ctx, parts.by_code(ctx, code))})


@bp.get("/parts/<part_id>")
@policy.require_permission(READ)
def parts_get(part_id):
    ctx = policy.current_context()
    return ok({"part": _serialize_detail(ctx, parts.get(ctx, part_id))})


@bp.patch("/parts/<part_id>")
@policy.require_permission(MANAGE)
def parts_patch(part_id):
    ctx = policy.current_context()
    row = parts.update(ctx, parts.get(ctx, part_id), json_body())
    return ok({"part": _serialize_detail(ctx, row)})


@bp.put("/parts/<part_id>/vendors")
@policy.require_permission(MANAGE)
def parts_set_vendors(part_id):
    ctx = policy.current_context()
    row = parts.set_vendors(ctx, parts.get(ctx, part_id), json_body())
    return ok({"part": _serialize_detail(ctx, row)})


@bp.put("/parts/<part_id>/assets")
@policy.require_permission(MANAGE)
def parts_set_assets(part_id):
    ctx = policy.current_context()
    row = parts.set_assets(ctx, parts.get(ctx, part_id), json_body())
    return ok({"part": _serialize_detail(ctx, row)})


@bp.get("/parts/<part_id>/inventory")
@policy.require_permission(READ)
def parts_inventory(part_id):
    ctx = policy.current_context()
    row = parts.get(ctx, part_id)
    totals, _states = parts.enrich([row])
    return ok(
        {
            "balances": [serialize_balance(entry) for entry in parts.balances(ctx, row)],
            "totals": stock_totals(totals.get(row.id)),
        }
    )


@bp.get("/parts/<part_id>/transactions")
@policy.require_permission(READ)
def parts_transactions(part_id):
    ctx = policy.current_context()
    row = parts.get(ctx, part_id)
    query = inventory.transactions_query(ctx, part=row, filters=parse_filters(inventory.PART_LEDGER_FILTERS))
    rows, next_cursor, total = paginate(query)
    return ok(list_payload("transactions", _serialize_transactions(ctx, rows), next_cursor, total))


@bp.post("/parts/<part_id>/transactions")
@policy.require_permission(MANAGE, "work_order.log_time", any_of=True)
def parts_record_transaction(part_id):
    ctx = policy.current_context()
    row = parts.get(ctx, part_id)
    transaction = inventory.record_transaction(ctx, row, json_body())
    return ok(
        {"transaction": _serialize_transactions(ctx, [transaction])[0], "part": _serialize_one(row)},
        status=201,
    )


# --------------------------------------------------------------------------- part types


@bp.get("/part-types")
@policy.require_permission(READ)
def part_types_list():
    ctx = policy.current_context()
    items = [serialize_part_type(row, part_count=count) for row, count in parts.list_types(ctx)]
    return ok(list_payload("part_types", items, None, len(items)))


@bp.post("/part-types")
@policy.require_permission(MANAGE)
def part_types_create():
    ctx = policy.current_context()
    row = parts.create_type(ctx, json_body())
    return ok({"part_type": serialize_part_type(row, part_count=0)}, status=201)


# --------------------------------------------------------------------------- inventory


@bp.post("/inventory/transfers")
@policy.require_permission(MANAGE)
def inventory_transfer():
    ctx = policy.current_context()
    out_row, in_row = inventory.transfer(ctx, json_body())
    return ok(
        {"transactions": _serialize_transactions(ctx, [out_row, in_row]), "part": _serialize_one(out_row.part)},
        status=201,
    )


@bp.post("/inventory/cycle-counts")
@policy.require_permission(MANAGE)
def inventory_cycle_count():
    ctx = policy.current_context()
    lines = inventory.cycle_count(ctx, json_body())
    return ok(
        {"lines": [cycle_count_line(line["part"], line["expected"], line["counted"], line["delta"]) for line in lines]},
        status=201,
    )


@bp.get("/inventory/cycle-counts/sheet")
@policy.require_permission(READ)
def inventory_cycle_count_sheet():
    ctx = policy.current_context()
    location, rows = inventory.cycle_count_sheet(ctx, request.args.get("location_id"))
    return ok(
        {
            "location": location_ref(location),
            "lines": [cycle_count_sheet_line(part, on_hand=on_hand, reserved=reserved) for part, on_hand, reserved in rows],
        }
    )


@bp.get("/inventory/low-stock")
@policy.require_permission(READ)
def inventory_low_stock():
    ctx = policy.current_context()
    items = [
        low_stock_item(
            entry["part"],
            totals=entry["totals"],
            stock_state=entry["stock_state"],
            link=entry["link"],
            suggested_quantity=entry["suggested_quantity"],
        )
        for entry in inventory.low_stock(ctx)
    ]
    return ok(list_payload("parts", items, None, len(items)))


@bp.get("/inventory/transactions")
@policy.require_permission(READ)
def inventory_transactions():
    ctx = policy.current_context()
    date_from, date_to = inventory.parse_date_range(request.args.get("from"), request.args.get("to"))
    query = inventory.transactions_query(
        ctx,
        filters=parse_filters(inventory.LEDGER_FILTERS),
        date_from=date_from,
        date_to=date_to,
    )
    rows, next_cursor, total = paginate(query)
    return ok(list_payload("transactions", _serialize_transactions(ctx, rows), next_cursor, total))
