"""JSON shapes for parts, part types and inventory transactions.

Quantities are JSON numbers with three decimal places and unit costs are
rounded to four, both through ``inventory_ledger`` so the API never disagrees
with the ledger about a number. ``totals`` always carries the same four keys
(``on_hand``, ``reserved``, ``available``, ``ordered``) so the frontend can
render a part row without checking for missing fields.
"""

from __future__ import annotations

from asme.ops.serializers import asset_ref, iso, location_ref, part_ref, purchase_request_ref, uid, user_ref, vendor_ref
from asme.ops.services.inventory_ledger import quantity_number, unit_cost_number

PART_SNAPSHOT_FIELDS = (
    "name",
    "sku",
    "description",
    "part_type_id",
    "manufacturer",
    "manufacturer_part_number",
    "unit",
    "unit_cost",
    "is_critical",
    "minimum_stock",
    "maximum_stock",
    "reorder_quantity",
    "default_location_id",
    "qr_code",
    "is_active",
)

PART_TYPE_SNAPSHOT_FIELDS = ("name", "color", "icon")

TOTAL_KEYS = ("on_hand", "reserved", "available", "ordered")


# --------------------------------------------------------------------------- part types


def part_type_brief(row) -> dict | None:
    if row is None:
        return None
    return {"id": uid(row.id), "name": row.name, "color": row.color, "icon": row.icon}


def part_type(row, *, part_count: int = 0) -> dict:
    return {**part_type_brief(row), "part_count": int(part_count)}


# --------------------------------------------------------------------------- parts


def stock_totals(values: dict | None) -> dict:
    """One entry of ``inventory_ledger.part_totals`` as JSON numbers."""
    values = values or {}
    return {key: quantity_number(values.get(key, 0)) or 0.0 for key in TOTAL_KEYS}


def part_vendor(link) -> dict:
    return {
        "vendor": vendor_ref(link.vendor),
        "vendor_part_number": link.vendor_part_number,
        "url": link.url,
        "preferred": bool(link.preferred),
        "last_price": unit_cost_number(link.last_price),
        "last_ordered_at": iso(link.last_ordered_at),
    }


def part(row, *, totals: dict | None = None, stock_state: str = "untracked") -> dict:
    preferred = row.preferred_vendor_link
    return {
        **part_ref(row),
        "description": row.description,
        "part_type": part_type_brief(row.part_type),
        "manufacturer": row.manufacturer,
        "manufacturer_part_number": row.manufacturer_part_number,
        "unit_cost": unit_cost_number(row.unit_cost),
        "is_critical": bool(row.is_critical),
        "minimum_stock": quantity_number(row.minimum_stock),
        "maximum_stock": quantity_number(row.maximum_stock),
        "reorder_quantity": quantity_number(row.reorder_quantity),
        "default_location": location_ref(row.default_location),
        "qr_code": row.qr_code,
        "is_active": bool(row.is_active),
        "totals": stock_totals(totals),
        "stock_state": stock_state,
        "preferred_vendor": vendor_ref(preferred.vendor) if preferred is not None else None,
        "created_at": iso(row.created_at),
        "updated_at": iso(row.updated_at),
    }


def balance(row) -> dict:
    return {
        "location": location_ref(row.location),
        "on_hand": quantity_number(row.on_hand) or 0.0,
        "reserved": quantity_number(row.reserved) or 0.0,
        "available": quantity_number(row.available) or 0.0,
    }


def open_purchase_request(request, outstanding) -> dict:
    return {**purchase_request_ref(request), "outstanding_quantity": quantity_number(outstanding) or 0.0}


def part_detail(
    row,
    *,
    totals: dict | None = None,
    stock_state: str = "untracked",
    balances: list | None = None,
    open_purchase_requests: list | None = None,
    recent_transactions: list | None = None,
) -> dict:
    return {
        **part(row, totals=totals, stock_state=stock_state),
        "balances": [balance(entry) for entry in (balances or [])],
        "vendors": [part_vendor(link) for link in sorted(row.vendor_links, key=_vendor_sort_key)],
        "assets": [asset_ref(link.asset) for link in row.asset_links if link.asset is not None],
        "open_purchase_requests": list(open_purchase_requests or []),
        "recent_transactions": list(recent_transactions or []),
    }


def _vendor_sort_key(link) -> tuple:
    name = link.vendor.name if link.vendor is not None else ""
    return (0 if link.preferred else 1, name.lower(), str(link.id))


# --------------------------------------------------------------------------- transactions


def work_order_brief(work_order) -> dict | None:
    if work_order is None:
        return None
    return {"id": uid(work_order.id), "number": work_order.number, "title": work_order.title}


def inventory_transaction(row, *, work_order_readable: bool = True, purchase_request_readable: bool = True) -> dict:
    """One ledger row.

    ``work_order_readable`` is False when the caller may not read the linked work
    order (a private project) and ``purchase_request_readable`` is False when the
    purchase-request read rule hides the linked request; the link is then null
    rather than leaking its number, title and status. The ledger itself is gated
    on ``inventory.read`` alone, which is a wider audience than either.
    """
    return {
        "id": uid(row.id),
        "type": row.transaction_type,
        "part": part_ref(row.part),
        "location": location_ref(row.location),
        "quantity": quantity_number(row.quantity) or 0.0,
        "on_hand_delta": quantity_number(row.on_hand_delta) or 0.0,
        "reserved_delta": quantity_number(row.reserved_delta) or 0.0,
        "on_hand_after": quantity_number(row.on_hand_after) or 0.0,
        "reserved_after": quantity_number(row.reserved_after) or 0.0,
        "counted_quantity": quantity_number(row.counted_quantity),
        "unit_cost": unit_cost_number(row.unit_cost),
        "work_order": work_order_brief(row.work_order) if work_order_readable else None,
        "purchase_request": purchase_request_ref(row.purchase_request) if purchase_request_readable else None,
        "reference_transaction_id": uid(row.reference_transaction_id),
        "note": row.note,
        "created_by": user_ref(row.created_by),
        "created_at": iso(row.created_at),
    }


# --------------------------------------------------------------------------- inventory screens


def cycle_count_line(row, expected, counted, delta) -> dict:
    return {
        "part": part_ref(row),
        "expected": quantity_number(expected) or 0.0,
        "counted": quantity_number(counted) or 0.0,
        "delta": quantity_number(delta) or 0.0,
    }


def cycle_count_sheet_line(row, *, on_hand, reserved) -> dict:
    return {
        "part": part_ref(row),
        "expected": quantity_number(on_hand) or 0.0,
        "reserved": quantity_number(reserved) or 0.0,
    }


def low_stock_item(row, *, totals: dict | None, stock_state: str, link, suggested_quantity) -> dict:
    return {
        **part(row, totals=totals, stock_state=stock_state),
        "suggested_quantity": quantity_number(suggested_quantity) or 0.0,
        "vendor_part_number": link.vendor_part_number if link is not None else None,
        "last_price": unit_cost_number(link.last_price) if link is not None else None,
    }
