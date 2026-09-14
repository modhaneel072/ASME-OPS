"""Saved filters (My Filters): ``GET|POST /saved-filters``, ``PATCH|DELETE /saved-filters/:id``."""

from __future__ import annotations

from flask import request

from asme.blueprints.ops import bp, json_body, ok
from asme.ops import policy
from asme.ops.serializers.saved_filters import saved_filter as serialize
from asme.ops.services import saved_filters


@bp.get("/saved-filters")
@policy.require_permission()
def list_saved_filters():
    ctx = policy.current_context()
    entity_type = (request.args.get("entity_type") or "").strip() or None
    personal, shared = saved_filters.list_for_user(ctx, entity_type)
    return ok({"personal": [serialize(row) for row in personal], "shared": [serialize(row) for row in shared]})


@bp.post("/saved-filters")
@policy.require_permission()
def create_saved_filter():
    ctx = policy.current_context()
    row = saved_filters.create(ctx, json_body())
    return ok({"saved_filter": serialize(row)}, status=201)


@bp.patch("/saved-filters/<filter_id>")
@policy.require_permission()
def update_saved_filter(filter_id):
    ctx = policy.current_context()
    row = saved_filters.update(ctx, filter_id, json_body())
    return ok({"saved_filter": serialize(row)})


@bp.delete("/saved-filters/<filter_id>")
@policy.require_permission()
def delete_saved_filter(filter_id):
    ctx = policy.current_context()
    saved_filters.delete(ctx, filter_id)
    return ok({"deleted": True})
