"""Purchase requests: ``GET|POST /purchase-requests``, ``GET|PATCH
/purchase-requests/:id``, the workflow actions ``POST /purchase-requests/:id/<action>``
(submit, approve, decline, request-changes, order, receive, cancel, reopen),
``POST /purchase-requests/from-low-stock`` and the chapter's purchasing settings
at ``GET|PUT /purchasing/settings``.

Reading is gated by the service's read rule (approvers and inventory managers
see everything, everyone else their own requests plus the projects they manage),
so every route resolves the request through ``purchase_requests.get_readable``
and a request the caller may not read answers 404. The action endpoints carry no
single permission key - which permission applies depends on the step the request
sits at - so they authorize inside the service.
"""

from __future__ import annotations

from asme.blueprints.ops import bp, json_body, list_payload, ok, paginate, parse_filters, parse_sort, query_text
from asme.ops import policy
from asme.ops.serializers import purchase_requests as serialize
from asme.ops.services import purchase_requests
from flask import request as flask_request

ACTION_ROUTES = ("submit", "approve", "decline", "request-changes", "order", "receive", "cancel", "reopen")


def _detail(ctx, row) -> dict:
    return {
        "purchase_request": serialize.purchase_request_detail(
            row,
            available_actions=purchase_requests.available_actions(ctx, row),
            attachment_count=purchase_requests.attachment_count(row),
        )
    }


# --------------------------------------------------------------------------- list / create / detail / update


@bp.get("/purchase-requests")
@policy.require_permission()
def purchase_requests_list():
    ctx = policy.current_context()
    filters = parse_filters(purchase_requests.LIST_FILTERS)
    q = query_text()
    query = purchase_requests.list_query(
        ctx,
        filters=filters,
        sort=parse_sort(purchase_requests.LIST_SORTS, purchase_requests.DEFAULT_SORT),
        q=q,
        tab=flask_request.args.get("tab"),
    )
    rows, next_cursor, total = paginate(query)
    payload = list_payload("purchase_requests", serialize.serialize_many(rows), next_cursor, total)
    payload["tabs"] = purchase_requests.tab_counts(ctx, filters, q)
    return ok(payload)


@bp.post("/purchase-requests")
@policy.require_permission("purchase.submit")
def purchase_requests_create():
    ctx = policy.current_context()
    row = purchase_requests.create(ctx, json_body())
    return ok(_detail(ctx, row), status=201)


@bp.post("/purchase-requests/from-low-stock")
@policy.require_permission("purchase.submit", "inventory.read")
def purchase_requests_from_low_stock():
    ctx = policy.current_context()
    rows = purchase_requests.from_low_stock(ctx, json_body())
    return ok({"purchase_requests": [_detail(ctx, row)["purchase_request"] for row in rows]}, status=201)


@bp.get("/purchase-requests/<purchase_request_id>")
@policy.require_permission()
def purchase_requests_get(purchase_request_id):
    ctx = policy.current_context()
    row = purchase_requests.get_readable(ctx, purchase_request_id)
    return ok(_detail(ctx, row))


@bp.patch("/purchase-requests/<purchase_request_id>")
@policy.require_permission()
def purchase_requests_patch(purchase_request_id):
    ctx = policy.current_context()
    row = purchase_requests.get_readable(ctx, purchase_request_id)
    row = purchase_requests.update(ctx, row, json_body())
    return ok(_detail(ctx, row))


# --------------------------------------------------------------------------- workflow actions


def _register_action(action: str) -> None:
    def view(purchase_request_id):
        ctx = policy.current_context()
        row = purchase_requests.get_readable(ctx, purchase_request_id)
        row = purchase_requests.perform(ctx, row, action, json_body())
        return ok(_detail(ctx, row))

    view.__name__ = f"purchase_requests_{action.replace('-', '_')}"
    bp.post(f"/purchase-requests/<purchase_request_id>/{action}")(policy.require_permission()(view))


for _action in ACTION_ROUTES:
    _register_action(_action)


# --------------------------------------------------------------------------- chapter purchasing settings


@bp.get("/purchasing/settings")
@policy.require_permission("chapter.settings.manage")
def purchasing_settings_get():
    ctx = policy.current_context()
    return ok({"purchasing": serialize.purchasing_settings(purchase_requests.get_settings(ctx))})


@bp.put("/purchasing/settings")
@policy.require_permission("chapter.settings.manage")
def purchasing_settings_put():
    ctx = policy.current_context()
    settings = purchase_requests.update_settings(ctx, json_body())
    return ok({"purchasing": serialize.purchasing_settings(settings)})
