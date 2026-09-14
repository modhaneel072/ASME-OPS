"""Teams and team membership.

``GET|POST /teams``, ``GET|PATCH|DELETE /teams/:id``, ``PUT /teams/:id/members``.
Reads need ``team.read``; writes need ``team.manage`` (object scope is checked
in the service, so a team lead can only touch teams they lead).
"""

from __future__ import annotations

from asme.blueprints.ops import bp, json_body, list_payload, ok, paginate, parse_filters, parse_sort, query_text
from asme.ops import policy
from asme.ops.serializers.teams import team as serialize_team, team_detail
from asme.ops.services import teams


@bp.get("/teams")
@policy.require_permission("team.read")
def list_teams():
    ctx = policy.current_context()
    filters = parse_filters(teams.FILTERS)
    sort = parse_sort(teams.SORTS, teams.DEFAULT_SORT)
    query = teams.list_query(
        ctx,
        q=query_text(),
        project_ids=filters.get("project"),
        active=filters.get("active", ["true"])[0],
        sort=sort,
    )
    rows, next_cursor, total = paginate(query)
    return ok(list_payload("teams", [serialize_team(row) for row in rows], next_cursor, total))


@bp.post("/teams")
@policy.require_permission("team.manage")
def create_team():
    ctx = policy.current_context()
    team = teams.create(ctx, json_body())
    return ok({"team": team_detail(team)}, status=201)


@bp.get("/teams/<team_id>")
@policy.require_permission("team.read")
def get_team(team_id):
    ctx = policy.current_context()
    return ok({"team": team_detail(teams.get(ctx, team_id))})


@bp.patch("/teams/<team_id>")
@policy.require_permission("team.manage")
def patch_team(team_id):
    ctx = policy.current_context()
    team = teams.update(ctx, team_id, json_body())
    return ok({"team": team_detail(team)})


@bp.delete("/teams/<team_id>")
@policy.require_permission("team.manage")
def delete_team(team_id):
    ctx = policy.current_context()
    team = teams.delete(ctx, team_id)
    return ok({"deleted": True, "id": str(team.id)})


@bp.put("/teams/<team_id>/members")
@policy.require_permission("team.manage")
def put_team_members(team_id):
    ctx = policy.current_context()
    team = teams.set_members(ctx, team_id, json_body())
    return ok({"team": team_detail(team)})
