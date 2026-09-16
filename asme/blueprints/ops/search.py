"""Global search: ``GET /search?q=&limit=``."""

from __future__ import annotations

from flask import request

from asme.blueprints.ops import bp, ok, query_text
from asme.ops import policy
from asme.ops.serializers import asset_ref, category_ref, location_ref, part_ref, project_ref, purchase_request_ref, uid, user_ref
from asme.ops.services import search as search_service


def _work_order_hit(work_order) -> dict:
    return {
        "id": uid(work_order.id),
        "number": work_order.number,
        "title": work_order.title,
        "status": work_order.status,
        "priority": work_order.priority,
    }


@bp.get("/search")
@policy.require_permission()
def global_search():
    ctx = policy.current_context()
    limit = search_service.clamp_limit(request.args.get("limit", search_service.DEFAULT_LIMIT))
    found = search_service.search(ctx, query_text(), limit)
    results = found["results"]
    return ok(
        {
            "query": found["query"],
            "results": {
                "work_orders": [_work_order_hit(row) for row in results["work_orders"]],
                "projects": [project_ref(row) for row in results["projects"]],
                "assets": [asset_ref(row) for row in results["assets"]],
                "parts": [part_ref(row) for row in results["parts"]],
                "purchase_requests": [purchase_request_ref(row) for row in results["purchase_requests"]],
                "locations": [location_ref(row) for row in results["locations"]],
                "categories": [category_ref(row) for row in results["categories"]],
                "users": [user_ref(row) for row in results["users"]],
            },
        }
    )
