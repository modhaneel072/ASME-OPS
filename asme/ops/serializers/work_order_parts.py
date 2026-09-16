"""JSON shapes for the parts planned on a work order.

The part reference carries the chapter-wide stock picture (``stock_state`` and
``totals``) so the work-order screen can show availability without a second
request. ``serialize_many`` reads those totals once for the whole list.
"""

from __future__ import annotations

from asme.ops.serializers import iso, location_ref, part_ref, uid
from asme.ops.services import inventory_ledger as ledger

TOTAL_KEYS = ("on_hand", "reserved", "available", "ordered")


def _totals_payload(totals: dict | None) -> dict:
    totals = totals or {}
    return {key: ledger.quantity_number(totals.get(key, 0)) for key in TOTAL_KEYS}


def part_with_stock(part, totals: dict | None = None) -> dict | None:
    """``part_ref`` plus ``stock_state`` and ``totals``."""
    data = part_ref(part)
    if data is None:
        return None
    if totals is None:
        totals = ledger.part_totals([part.id]).get(part.id)
    data["stock_state"] = ledger.stock_state(totals or {}, part)
    data["totals"] = _totals_payload(totals)
    return data


def work_order_part(row, *, totals: dict | None = None) -> dict:
    return {
        "id": uid(row.id),
        "part": part_with_stock(row.part, totals),
        "location": location_ref(row.location),
        "quantity_planned": ledger.quantity_number(row.quantity_planned),
        "quantity_reserved": ledger.quantity_number(row.quantity_reserved),
        "quantity_issued": ledger.quantity_number(row.quantity_issued),
        "quantity_returned": ledger.quantity_number(row.quantity_returned),
        "readiness": row.readiness,
        "note": row.note,
        "created_at": iso(row.created_at),
    }


def serialize_many(rows) -> list[dict]:
    rows = list(rows)
    totals = ledger.part_totals([row.part_id for row in rows])
    return [work_order_part(row, totals=totals.get(row.part_id)) for row in rows]
