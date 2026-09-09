"""Categories: ``/api/v1/categories``.

GET /categories                 list (q, sort name|usage|created_at with ``-`` prefix)
POST /categories                create
GET|PATCH|DELETE /categories/:id
"""

from __future__ import annotations

from asme.blueprints.ops import bp, json_body, list_payload, ok, paginate, parse_filters, parse_sort, query_text
from asme.ops import policy
from asme.ops.serializers import uid
from asme.ops.serializers.categories import category as serialize_category
from asme.ops.services import categories
from asme.ops.types import parse_uuid

FILTERS: dict[str, str] = {}


def _serialize_many(ctx, rows) -> list[dict]:
    usage = categories.usage_for(ctx, rows)
    creators = categories.creators_for(rows)
    return [serialize_category(row, usage=usage.get(row.id, 0), created_by=creators.get(row.created_by_user_id)) for row in rows]


def _serialize_one(ctx, row) -> dict:
    return _serialize_many(ctx, [row])[0]


def _load(ctx, raw_id: str):
    return categories.get(ctx, parse_uuid(raw_id))


@bp.get("/categories")
@policy.require_permission("category.read")
def list_categories():
    ctx = policy.current_context()
    parse_filters(FILTERS)  # no filters yet; still rejects unknown filter[...] params
    sort = parse_sort(categories.SORTS, "name")
    query = categories.list_query(ctx, q=query_text(), sort=sort)
    rows, next_cursor, total = paginate(query)
    return ok(list_payload("categories", _serialize_many(ctx, rows), next_cursor, total))


@bp.post("/categories")
@policy.require_permission("category.manage")
def create_category():
    ctx = policy.current_context()
    row = categories.create(ctx, json_body())
    return ok({"category": _serialize_one(ctx, row)}, status=201)


@bp.get("/categories/<category_id>")
@policy.require_permission("category.read")
def get_category(category_id):
    ctx = policy.current_context()
    return ok({"category": _serialize_one(ctx, _load(ctx, category_id))})


@bp.patch("/categories/<category_id>")
@policy.require_permission("category.manage")
def patch_category(category_id):
    ctx = policy.current_context()
    row = categories.update(ctx, _load(ctx, category_id), json_body())
    return ok({"category": _serialize_one(ctx, row)})


@bp.delete("/categories/<category_id>")
@policy.require_permission("category.manage")
def delete_category(category_id):
    ctx = policy.current_context()
    row = _load(ctx, category_id)
    deleted_id = uid(row.id)
    categories.delete(ctx, row)
    return ok({"id": deleted_id, "deleted": True})
