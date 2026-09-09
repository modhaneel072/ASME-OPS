"""Locations (nested): ``/api/v1/locations``.

GET /locations                     list (q, filter[parent]=<id>|root, filter[active]=true|false, sort)
GET /locations?view=tree           roots with nested ``children`` (no pagination)
POST /locations                    create
GET|PATCH|DELETE /locations/:id
POST /locations/:id/make-default   swap the organization's default location
"""

from __future__ import annotations

from flask import request

from asme.blueprints.ops import bp, json_body, list_payload, ok, paginate, parse_filters, parse_sort, query_text
from asme.ops import policy
from asme.ops.serializers import uid
from asme.ops.serializers.locations import location as serialize_location
from asme.ops.services import locations
from asme.ops.types import parse_uuid
from asme.services.errors import Validation

FILTERS = {"parent": "single", "active": "single"}
VIEWS = ("list", "tree")
TRUE_WORDS = {"true", "1", "yes"}
FALSE_WORDS = {"false", "0", "no"}


def _parse_active(values: list[str] | None) -> bool:
    if not values:
        return True
    word = values[0].strip().lower()
    if word in TRUE_WORDS:
        return True
    if word in FALSE_WORDS:
        return False
    raise Validation("filter[active] must be true or false.", field="filter[active]", code="bad_filter")


def _parse_parent(values: list[str] | None):
    if not values:
        return None
    raw = values[0].strip()
    if raw.lower() == locations.ROOT:
        return locations.ROOT
    parent_id = parse_uuid(raw)
    if parent_id is None:
        raise Validation("filter[parent] must be a location id or 'root'.", field="filter[parent]", code="bad_filter")
    return parent_id


def _parse_view() -> str:
    view = (request.args.get("view") or "list").strip().lower()
    if view not in VIEWS:
        raise Validation("view must be 'list' or 'tree'.", field="view", code="bad_view")
    return view


def _serialize_many(ctx, rows) -> list[dict]:
    info = locations.enrich(ctx, rows)
    return [serialize_location(row, **info[row.id]) for row in rows]


def _serialize_one(ctx, row) -> dict:
    return _serialize_many(ctx, [row])[0]


def _serialize_tree(ctx, nodes) -> list[dict]:
    info = locations.enrich(ctx, locations.flatten(nodes))

    def node(entry) -> dict:
        return serialize_location(entry.location, **info[entry.location.id], children=[node(child) for child in entry.children])

    return [node(entry) for entry in nodes]


def _load(ctx, raw_id: str):
    return locations.get(ctx, parse_uuid(raw_id))


@bp.get("/locations")
@policy.require_permission("location.read")
def list_locations():
    ctx = policy.current_context()
    filters = parse_filters(FILTERS)
    active = _parse_active(filters.get("active"))
    q = query_text()
    if _parse_view() == "tree":
        return ok({"items": _serialize_tree(ctx, locations.tree(ctx, q=q, active=active))})
    sort = parse_sort(locations.SORTS, "name")
    query = locations.list_query(ctx, q=q, parent=_parse_parent(filters.get("parent")), active=active, sort=sort)
    rows, next_cursor, total = paginate(query)
    return ok(list_payload("locations", _serialize_many(ctx, rows), next_cursor, total))


@bp.post("/locations")
@policy.require_permission("location.manage")
def create_location():
    ctx = policy.current_context()
    row = locations.create(ctx, json_body())
    return ok({"location": _serialize_one(ctx, row)}, status=201)


@bp.get("/locations/<location_id>")
@policy.require_permission("location.read")
def get_location(location_id):
    ctx = policy.current_context()
    return ok({"location": _serialize_one(ctx, _load(ctx, location_id))})


@bp.patch("/locations/<location_id>")
@policy.require_permission("location.manage")
def patch_location(location_id):
    ctx = policy.current_context()
    row = locations.update(ctx, _load(ctx, location_id), json_body())
    return ok({"location": _serialize_one(ctx, row)})


@bp.delete("/locations/<location_id>")
@policy.require_permission("location.manage")
def delete_location(location_id):
    ctx = policy.current_context()
    row = _load(ctx, location_id)
    deleted_id = uid(row.id)
    locations.delete(ctx, row)
    return ok({"id": deleted_id, "deleted": True})


@bp.post("/locations/<location_id>/make-default")
@policy.require_permission("location.manage")
def make_default_location(location_id):
    ctx = policy.current_context()
    row = locations.make_default(ctx, _load(ctx, location_id))
    return ok({"location": _serialize_one(ctx, row)})
