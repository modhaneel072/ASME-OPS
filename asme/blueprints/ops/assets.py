"""Assets, asset types, status history.

``GET|POST /asset-types``, ``GET|POST /assets``, ``GET|PATCH /assets/:id``,
``POST /assets/:id/status``, ``GET /assets/:id/history``. ``GET /assets?view=hierarchy``
returns roots with nested ``children`` instead of a page."""

from __future__ import annotations

from flask import request

from asme.blueprints.ops import bp, json_body, list_payload, ok, paginate, parse_filters, parse_sort, query_text
from asme.ops import policy
from asme.ops.serializers.assets import asset as serialize_asset
from asme.ops.serializers.assets import asset_type as serialize_asset_type
from asme.ops.serializers.assets import hierarchy_node, status_history, timeline_entry
from asme.ops.services import assets
from asme.utils import parse_positive_int


def _serialize_page(ctx, rows):
    counts = assets.counts_for(ctx, rows)
    return [serialize_asset(row, **counts[row.id]) for row in rows]


def _tree(nodes, children_of, counts):
    return [hierarchy_node(node, _tree(children_of.get(node.id, []), children_of, counts), **counts[node.id]) for node in nodes]


@bp.get("/assets")
@policy.require_permission("asset.read")
def assets_list():
    ctx = policy.current_context()
    filters = parse_filters(assets.FILTERS)
    if (request.args.get("view") or "").strip().lower() == "hierarchy":
        roots, children_of = assets.hierarchy(ctx, filters=filters)
        every = list(roots) + [child for siblings in children_of.values() for child in siblings]
        counts = assets.counts_for(ctx, every)
        return ok(list_payload("assets", _tree(roots, children_of, counts), None, len(every)))
    query = assets.list_query(ctx, q=query_text(), filters=filters, sort=parse_sort(assets.SORTS, assets.DEFAULT_SORT))
    rows, next_cursor, total = paginate(query)
    return ok(list_payload("assets", _serialize_page(ctx, rows), next_cursor, total))


@bp.post("/assets")
@policy.require_permission("asset.manage")
def assets_create():
    ctx = policy.current_context()
    row = assets.create(ctx, json_body())
    return ok({"asset": _serialize_page(ctx, [row])[0]}, status=201)


@bp.get("/assets/<asset_id>")
@policy.require_permission("asset.read")
def assets_get(asset_id):
    ctx = policy.current_context()
    row = assets.get(ctx, asset_id)
    return ok({"asset": _serialize_page(ctx, [row])[0]})


@bp.patch("/assets/<asset_id>")
@policy.require_permission("asset.manage")
def assets_patch(asset_id):
    ctx = policy.current_context()
    row = assets.update(ctx, assets.get(ctx, asset_id), json_body())
    return ok({"asset": _serialize_page(ctx, [row])[0]})


@bp.post("/assets/<asset_id>/status")
@policy.require_permission("asset.status.update", "asset.manage", any_of=True)
def assets_change_status(asset_id):
    ctx = policy.current_context()
    row = assets.get(ctx, asset_id)
    history = assets.change_status_from_payload(ctx, row, json_body())
    return ok({"asset": _serialize_page(ctx, [row])[0], "history": status_history(history)})


@bp.get("/assets/<asset_id>/history")
@policy.require_permission("asset.read")
def assets_history(asset_id):
    ctx = policy.current_context()
    row = assets.get(ctx, asset_id)
    limit = parse_positive_int(request.args.get("limit"), default=assets.DEFAULT_HISTORY_LIMIT)
    entries = assets.history(ctx, row, limit=limit)
    return ok({"items": [timeline_entry(kind, item, at) for kind, at, item in entries]})


@bp.get("/asset-types")
@policy.require_permission("asset.read")
def asset_types_list():
    ctx = policy.current_context()
    items = [serialize_asset_type(row, asset_count=count) for row, count in assets.list_types(ctx)]
    return ok(list_payload("asset_types", items, None, len(items)))


@bp.post("/asset-types")
@policy.require_permission("asset.manage")
def asset_types_create():
    ctx = policy.current_context()
    row = assets.create_type(ctx, json_body())
    return ok({"asset_type": serialize_asset_type(row, asset_count=0)}, status=201)
