"""Work orders: list, detail, create, transitions, sub-work orders, assignment,
watchers, time and cost entries, dependencies and duplication.

Every route resolves the work order through ``work_orders.get_readable`` so a
foreign-organization id, a malformed id or a work order the user may not read
all answer 404. Object-level permission (own / assigned / team / project
scope) is enforced inside the service.
"""

from __future__ import annotations

from asme.blueprints.ops import bp, json_body, list_payload, ok, paginate, parse_filters, parse_sort, query_text
from asme.ops import policy
from asme.ops.serializers import work_orders as serialize
from asme.ops.services import work_orders
from flask import request

READ_KEYS = ("work_order.read_all", "work_order.read_assigned")


def _detail(wo) -> dict:
    return {"work_order": serialize.work_order_detail(wo)}


# --------------------------------------------------------------------------- list / create / detail / update


@bp.get("/work-orders")
@policy.require_permission(*READ_KEYS, any_of=True)
def list_work_orders():
    ctx = policy.current_context()
    filters = parse_filters(work_orders.LIST_FILTERS)
    sort = parse_sort(work_orders.LIST_SORTS, work_orders.DEFAULT_SORT)
    q = query_text()
    tab = request.args.get("tab")
    query = work_orders.list_query(ctx, filters, sort, q, tab)
    rows, next_cursor, total = paginate(query)
    payload = list_payload("work_orders", serialize.serialize_many(rows), next_cursor, total)
    payload["tabs"] = work_orders.tab_counts(ctx, filters, q)
    return ok(payload)


@bp.post("/work-orders")
@policy.require_permission("work_order.create")
def create_work_order():
    ctx = policy.current_context()
    wo = work_orders.create(ctx, json_body())
    return ok(_detail(wo), status=201)


@bp.get("/work-orders/<work_order_id>")
@policy.require_permission(*READ_KEYS, any_of=True)
def get_work_order(work_order_id):
    ctx = policy.current_context()
    wo = work_orders.get_readable(ctx, work_order_id)
    return ok(_detail(wo))


@bp.patch("/work-orders/<work_order_id>")
@policy.require_permission("work_order.edit")
def update_work_order(work_order_id):
    ctx = policy.current_context()
    wo = work_orders.get_readable(ctx, work_order_id)
    wo = work_orders.update(ctx, wo, json_body())
    return ok(_detail(wo))


# --------------------------------------------------------------------------- transitions


def _register_transition(action: str, permission: str) -> None:
    def view(work_order_id):
        ctx = policy.current_context()
        wo = work_orders.get_readable(ctx, work_order_id)
        wo = work_orders.transition(ctx, wo, action, note=json_body().get("note"))
        return ok(_detail(wo))

    view.__name__ = f"{action}_work_order"
    bp.add_url_rule(
        f"/work-orders/<work_order_id>/{action}",
        endpoint=view.__name__,
        view_func=policy.require_permission(permission)(view),
        methods=["POST"],
    )


for _action, _permission in (
    ("start", "work_order.start"),
    ("hold", "work_order.start"),
    ("resume", "work_order.start"),
    ("cancel", "work_order.cancel"),
    ("reopen", "work_order.edit"),
):
    _register_transition(_action, _permission)


@bp.post("/work-orders/<work_order_id>/complete")
@policy.require_permission("work_order.complete")
def complete_work_order(work_order_id):
    ctx = policy.current_context()
    wo = work_orders.get_readable(ctx, work_order_id)
    body = json_body()
    result = work_orders.complete(
        ctx,
        wo,
        note=body.get("note"),
        time_entries=body.get("time_entries") or (),
        cost_entries=body.get("cost_entries") or (),
        asset_status=body.get("asset_status"),
        follow_up=body.get("follow_up"),
    )
    follow_up = result["follow_up"]
    return ok(
        {
            "work_order": serialize.work_order_detail(result["work_order"]),
            "follow_up": serialize.work_order(follow_up) if follow_up is not None else None,
        }
    )


# --------------------------------------------------------------------------- sub-work orders / duplicate


@bp.post("/work-orders/<work_order_id>/sub-work-orders")
@policy.require_permission("work_order.create")
def create_sub_work_order(work_order_id):
    ctx = policy.current_context()
    parent = work_orders.get_readable(ctx, work_order_id)
    child = work_orders.create(ctx, json_body(), parent=parent)
    return ok(_detail(child), status=201)


@bp.post("/work-orders/<work_order_id>/duplicate")
@policy.require_permission("work_order.create")
def duplicate_work_order(work_order_id):
    ctx = policy.current_context()
    source = work_orders.get_readable(ctx, work_order_id)
    copy = work_orders.duplicate(ctx, source)
    return ok(_detail(copy), status=201)


# --------------------------------------------------------------------------- assignees / watchers


@bp.put("/work-orders/<work_order_id>/assignees")
@policy.require_permission("work_order.assign")
def put_assignees(work_order_id):
    ctx = policy.current_context()
    wo = work_orders.get_readable(ctx, work_order_id)
    body = json_body()
    wo = work_orders.set_assignees(ctx, wo, body.get("user_ids"), body.get("team_ids"))
    return ok(_detail(wo))


@bp.put("/work-orders/<work_order_id>/watchers")
@policy.require_permission("work_order.assign")
def put_watchers(work_order_id):
    ctx = policy.current_context()
    wo = work_orders.get_readable(ctx, work_order_id)
    wo = work_orders.set_watchers(ctx, wo, json_body().get("user_ids"))
    return ok(_detail(wo))


@bp.post("/work-orders/<work_order_id>/watch")
@policy.require_permission(*READ_KEYS, any_of=True)
def watch_work_order(work_order_id):
    ctx = policy.current_context()
    wo = work_orders.get_readable(ctx, work_order_id)
    wo = work_orders.watch(ctx, wo)
    return ok(_detail(wo))


@bp.delete("/work-orders/<work_order_id>/watch")
@policy.require_permission(*READ_KEYS, any_of=True)
def unwatch_work_order(work_order_id):
    ctx = policy.current_context()
    wo = work_orders.get_readable(ctx, work_order_id)
    wo = work_orders.unwatch(ctx, wo)
    return ok(_detail(wo))


# --------------------------------------------------------------------------- time & cost


@bp.post("/work-orders/<work_order_id>/time-entries")
@policy.require_permission("work_order.log_time")
def add_time_entry(work_order_id):
    ctx = policy.current_context()
    wo = work_orders.get_readable(ctx, work_order_id)
    entry = work_orders.add_time_entry(ctx, wo, json_body())
    return ok({"time_entry": serialize.time_entry(entry), "work_order": serialize.work_order_detail(wo)}, status=201)


@bp.delete("/work-orders/<work_order_id>/time-entries/<entry_id>")
@policy.require_permission("work_order.log_time")
def delete_time_entry(work_order_id, entry_id):
    ctx = policy.current_context()
    wo = work_orders.get_readable(ctx, work_order_id)
    wo = work_orders.delete_time_entry(ctx, wo, entry_id)
    return ok(_detail(wo))


@bp.post("/work-orders/<work_order_id>/cost-entries")
@policy.require_permission("work_order.log_time")
def add_cost_entry(work_order_id):
    ctx = policy.current_context()
    wo = work_orders.get_readable(ctx, work_order_id)
    entry = work_orders.add_cost_entry(ctx, wo, json_body())
    return ok({"cost_entry": serialize.cost_entry(entry), "work_order": serialize.work_order_detail(wo)}, status=201)


@bp.delete("/work-orders/<work_order_id>/cost-entries/<entry_id>")
@policy.require_permission("work_order.log_time")
def delete_cost_entry(work_order_id, entry_id):
    ctx = policy.current_context()
    wo = work_orders.get_readable(ctx, work_order_id)
    wo = work_orders.delete_cost_entry(ctx, wo, entry_id)
    return ok(_detail(wo))


# --------------------------------------------------------------------------- dependencies


@bp.post("/work-orders/<work_order_id>/dependencies")
@policy.require_permission("work_order.edit")
def add_dependency(work_order_id):
    ctx = policy.current_context()
    wo = work_orders.get_readable(ctx, work_order_id)
    dep = work_orders.add_dependency(ctx, wo, json_body().get("blocking_work_order_id"))
    return ok(
        {"dependency": serialize.dependency_entry(dep, other=dep.blocking_work_order), "work_order": serialize.work_order_detail(wo)},
        status=201,
    )


@bp.delete("/work-orders/<work_order_id>/dependencies/<dependency_id>")
@policy.require_permission("work_order.edit")
def remove_dependency(work_order_id, dependency_id):
    ctx = policy.current_context()
    wo = work_orders.get_readable(ctx, work_order_id)
    wo = work_orders.remove_dependency(ctx, wo, dependency_id)
    return ok(_detail(wo))
