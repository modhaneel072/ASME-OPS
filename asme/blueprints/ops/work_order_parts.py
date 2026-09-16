"""Work-order parts (``/work-orders/:id/parts``).

Every route resolves the work order through ``work_orders.get_readable`` first,
so a foreign-organization id, a malformed id or a work order the caller may not
read all answer 404. Who may plan, reserve, kit, issue or return is decided
inside ``asme.ops.services.work_order_parts``; the decorators here only keep out
callers with none of the relevant keys.
"""

from __future__ import annotations

from asme.blueprints.ops import bp, json_body, ok
from asme.ops import policy
from asme.ops.serializers import work_order_parts as serialize
from asme.ops.services import work_order_parts, work_orders

READ_KEYS = ("work_order.read_all", "work_order.read_assigned")
RESERVE_KEYS = ("inventory.manage", "work_order.edit")
ISSUE_KEYS = ("inventory.manage", "work_order.log_time")


def _payload(ctx, wo, line=None) -> dict:
    rows = work_order_parts.list_for_work_order(ctx, wo)
    items = serialize.serialize_many(rows)
    payload = {
        "items": items,
        "work_order_parts": items,  # legacy-friendly alias, as in list_payload
        "readiness_summary": work_order_parts.readiness_summary(rows),
        "parts_outstanding": work_order_parts.outstanding_count(wo),
    }
    if line is not None:
        payload["work_order_part"] = next(
            (item for item in items if item["id"] == str(line.id)), serialize.work_order_part(line)
        )
    return payload


# --------------------------------------------------------------------------- list / plan


@bp.get("/work-orders/<work_order_id>/parts")
@policy.require_permission(*READ_KEYS, any_of=True)
def list_work_order_parts(work_order_id):
    ctx = policy.current_context()
    wo = work_orders.get_readable(ctx, work_order_id)
    return ok(_payload(ctx, wo))


@bp.post("/work-orders/<work_order_id>/parts")
@policy.require_permission("work_order.edit")
def add_work_order_part(work_order_id):
    ctx = policy.current_context()
    wo = work_orders.get_readable(ctx, work_order_id)
    line = work_order_parts.add(ctx, wo, json_body())
    return ok(_payload(ctx, wo, line), status=201)


@bp.patch("/work-orders/<work_order_id>/parts/<part_line_id>")
@policy.require_permission("work_order.edit")
def update_work_order_part(work_order_id, part_line_id):
    ctx = policy.current_context()
    wo = work_orders.get_readable(ctx, work_order_id)
    line = work_order_parts.get_line(ctx, wo, part_line_id)
    line = work_order_parts.update(ctx, wo, line, json_body())
    return ok(_payload(ctx, wo, line))


@bp.delete("/work-orders/<work_order_id>/parts/<part_line_id>")
@policy.require_permission("work_order.edit")
def delete_work_order_part(work_order_id, part_line_id):
    ctx = policy.current_context()
    wo = work_orders.get_readable(ctx, work_order_id)
    line = work_order_parts.get_line(ctx, wo, part_line_id)
    work_order_parts.remove(ctx, wo, line)
    return ok(_payload(ctx, wo))


# --------------------------------------------------------------------------- reserve / release


@bp.post("/work-orders/<work_order_id>/parts/<part_line_id>/reserve")
@policy.require_permission(*RESERVE_KEYS, any_of=True)
def reserve_work_order_part(work_order_id, part_line_id):
    ctx = policy.current_context()
    wo = work_orders.get_readable(ctx, work_order_id)
    line = work_order_parts.get_line(ctx, wo, part_line_id)
    line = work_order_parts.reserve(ctx, wo, line, json_body())
    return ok(_payload(ctx, wo, line))


@bp.post("/work-orders/<work_order_id>/parts/<part_line_id>/release")
@policy.require_permission(*RESERVE_KEYS, any_of=True)
def release_work_order_part(work_order_id, part_line_id):
    ctx = policy.current_context()
    wo = work_orders.get_readable(ctx, work_order_id)
    line = work_order_parts.get_line(ctx, wo, part_line_id)
    line = work_order_parts.release(ctx, wo, line, json_body())
    return ok(_payload(ctx, wo, line))


@bp.post("/work-orders/<work_order_id>/parts/release-all")
@policy.require_permission(*RESERVE_KEYS, any_of=True)
def release_all_work_order_parts(work_order_id):
    ctx = policy.current_context()
    wo = work_orders.get_readable(ctx, work_order_id)
    work_order_parts.release_all(ctx, wo)
    return ok(_payload(ctx, wo))


# --------------------------------------------------------------------------- kit / stage


def _register_readiness(action: str, readiness: str) -> None:
    def view(work_order_id, part_line_id):
        ctx = policy.current_context()
        wo = work_orders.get_readable(ctx, work_order_id)
        line = work_order_parts.get_line(ctx, wo, part_line_id)
        line = work_order_parts.set_readiness(ctx, wo, line, readiness, json_body())
        return ok(_payload(ctx, wo, line))

    view.__name__ = f"{action}_work_order_part"
    bp.add_url_rule(
        f"/work-orders/<work_order_id>/parts/<part_line_id>/{action}",
        endpoint=view.__name__,
        view_func=policy.require_permission("inventory.manage")(view),
        methods=["POST"],
    )


for _action, _readiness in (("kit", "kitted"), ("stage", "staged")):
    _register_readiness(_action, _readiness)


# --------------------------------------------------------------------------- issue / return


@bp.post("/work-orders/<work_order_id>/parts/<part_line_id>/issue")
@policy.require_permission(*ISSUE_KEYS, any_of=True)
def issue_work_order_part(work_order_id, part_line_id):
    ctx = policy.current_context()
    wo = work_orders.get_readable(ctx, work_order_id)
    line = work_order_parts.get_line(ctx, wo, part_line_id)
    line = work_order_parts.issue(ctx, wo, line, json_body())
    return ok(_payload(ctx, wo, line))


@bp.post("/work-orders/<work_order_id>/parts/<part_line_id>/return")
@policy.require_permission(*ISSUE_KEYS, any_of=True)
def return_work_order_part(work_order_id, part_line_id):
    ctx = policy.current_context()
    wo = work_orders.get_readable(ctx, work_order_id)
    line = work_order_parts.get_line(ctx, wo, part_line_id)
    line = work_order_parts.return_parts(ctx, wo, line, json_body())
    return ok(_payload(ctx, wo, line))
