"""Member directory, invitations, roles.

``GET /users`` and ``GET /users/:id`` (``team.read`` or ``user.read``),
``POST /users/invite`` and ``PATCH /users/:id`` (``user.manage``),
``GET /roles`` (any member). ``:id`` is the legacy ``users.id`` integer.
"""

from __future__ import annotations

from asme.blueprints.ops import bp, json_body, list_payload, ok, paginate, parse_filters, parse_sort, query_text
from asme.blueprints.ops.auth import invite_link
from asme.ops import policy
from asme.ops.serializers.users import member as serialize_member, roles as serialize_roles
from asme.ops.services import users


def _member_with_teams(ctx, membership) -> dict:
    teams = users.teams_for_users(ctx, [membership.user_id]).get(membership.user_id, [])
    return serialize_member(membership, teams)


@bp.get("/users")
@policy.require_permission(*users.DIRECTORY_PERMISSIONS, any_of=True)
def list_users():
    ctx = policy.current_context()
    filters = parse_filters(users.FILTERS)
    sort = parse_sort(users.SORTS, users.DEFAULT_SORT)
    query = users.directory_query(
        ctx,
        q=query_text(),
        role_keys=filters.get("role"),
        statuses=filters.get("status"),
        team_ids=filters.get("team"),
        sort=sort,
    )
    rows, next_cursor, total = paginate(query)
    teams_by_user = users.teams_for_users(ctx, [row.user_id for row in rows])
    items = [serialize_member(row, teams_by_user.get(row.user_id, [])) for row in rows]
    return ok(list_payload("users", items, next_cursor, total))


@bp.get("/users/<int:user_id>")
@policy.require_permission(*users.DIRECTORY_PERMISSIONS, any_of=True)
def get_user(user_id):
    ctx = policy.current_context()
    return ok({"member": _member_with_teams(ctx, users.get(ctx, user_id))})


@bp.post("/users/invite")
@policy.require_permission("user.manage")
def invite_user():
    ctx = policy.current_context()
    membership, token = users.invite(ctx, json_body())
    # A link is only minted for an account this request created; an existing
    # account keeps its own credentials (see asme.ops.services.users).
    # The link opens the SPA's set-password screen: /app/auth/reset-password?token=...
    invite_url = invite_link(token) if token else None
    return ok({"member": _member_with_teams(ctx, membership), "invite_url": invite_url}, status=201)


@bp.patch("/users/<int:user_id>")
@policy.require_permission("user.manage")
def patch_user(user_id):
    ctx = policy.current_context()
    membership = users.update(ctx, user_id, json_body())
    return ok({"member": _member_with_teams(ctx, membership)})


@bp.get("/roles")
@policy.require_permission()
def list_roles():
    ctx = policy.current_context()
    items = serialize_roles(users.list_roles(ctx))
    return ok(list_payload("roles", items, None, len(items)))
