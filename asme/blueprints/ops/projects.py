"""Projects, members, milestones, health, activity.

Routes are registered on the shared ``ops_api`` blueprint. Object-level checks
(project visibility, ``project.manage`` at project scope) live in the services;
the decorators here only require the key at any scope.
"""

from __future__ import annotations

from flask import request

from asme.blueprints.ops import bp, json_body, list_payload, ok, paginate, parse_filters, parse_sort, query_text
from asme.ops import policy
from asme.ops.serializers import audit_event as serialize_audit_event
from asme.ops.serializers.projects import milestone as serialize_milestone
from asme.ops.serializers.projects import project as serialize_project
from asme.ops.serializers.projects import project_member as serialize_member
from asme.ops.services import milestones, projects


def _project_payload(ctx, project) -> dict:
    return serialize_project(project, projects.stats_for(ctx, [project]).get(project.id))


# --------------------------------------------------------------------------- projects


@bp.get("/projects")
@policy.require_permission("project.read")
def list_projects():
    ctx = policy.current_context()
    view = (request.args.get("view") or "active").strip().lower()
    filters = parse_filters(projects.LIST_FILTERS)
    sort = parse_sort(projects.SORTS, projects.DEFAULT_SORT)
    query = projects.list_query(ctx, view=view, q=query_text(), filters=filters, sort=sort)
    rows, next_cursor, total = paginate(query)
    stats = projects.stats_for(ctx, rows)
    items = [serialize_project(row, stats.get(row.id)) for row in rows]
    return ok(list_payload("projects", items, next_cursor, total))


@bp.post("/projects")
@policy.require_permission("project.create")
def create_project():
    ctx = policy.current_context()
    project = projects.create(ctx, json_body())
    return ok({"project": _project_payload(ctx, project)}, status=201)


@bp.get("/projects/<project_id>")
@policy.require_permission("project.read")
def get_project(project_id):
    ctx = policy.current_context()
    project = projects.get_visible_project(ctx, project_id)
    return ok({"project": _project_payload(ctx, project), "members": [serialize_member(m) for m in project.members]})


@bp.patch("/projects/<project_id>")
@policy.require_permission("project.manage")
def patch_project(project_id):
    ctx = policy.current_context()
    project = projects.get_visible_project(ctx, project_id)
    project = projects.update(ctx, project, json_body())
    return ok({"project": _project_payload(ctx, project)})


@bp.post("/projects/<project_id>/archive")
@policy.require_permission("project.archive")
def archive_project(project_id):
    ctx = policy.current_context()
    project = projects.get_visible_project(ctx, project_id)
    project = projects.archive(ctx, project)
    return ok({"project": _project_payload(ctx, project)})


@bp.post("/projects/<project_id>/restore")
@policy.require_permission("project.archive")
def restore_project(project_id):
    ctx = policy.current_context()
    project = projects.get_visible_project(ctx, project_id)
    project = projects.restore(ctx, project)
    return ok({"project": _project_payload(ctx, project)})


@bp.put("/projects/<project_id>/members")
@policy.require_permission("project.manage")
def put_project_members(project_id):
    ctx = policy.current_context()
    project = projects.get_visible_project(ctx, project_id)
    project = projects.replace_members(ctx, project, json_body())
    return ok({"project": _project_payload(ctx, project), "members": [serialize_member(m) for m in project.members]})


@bp.get("/projects/<project_id>/health")
@policy.require_permission("project.read")
def project_health(project_id):
    ctx = policy.current_context()
    project = projects.get_visible_project(ctx, project_id)
    return ok(projects.health(ctx, project))


@bp.get("/projects/<project_id>/activity")
@policy.require_permission("project.read")
def project_activity(project_id):
    ctx = policy.current_context()
    project = projects.get_visible_project(ctx, project_id)
    rows, next_cursor, total = paginate(projects.activity_query(ctx, project))
    return ok(list_payload("events", [serialize_audit_event(row) for row in rows], next_cursor, total))


# --------------------------------------------------------------------------- milestones


@bp.get("/projects/<project_id>/milestones")
@policy.require_permission("project.read")
def list_milestones(project_id):
    ctx = policy.current_context()
    project = projects.get_visible_project(ctx, project_id)
    rows = milestones.list_for_project(ctx, project)
    return ok(list_payload("milestones", [serialize_milestone(row) for row in rows], None, len(rows)))


@bp.post("/projects/<project_id>/milestones")
@policy.require_permission("milestone.manage")
def create_milestone(project_id):
    ctx = policy.current_context()
    project = projects.get_visible_project(ctx, project_id)
    milestone = milestones.create(ctx, project, json_body())
    return ok({"milestone": serialize_milestone(milestone)}, status=201)


@bp.patch("/projects/<project_id>/milestones/<milestone_id>")
@policy.require_permission("milestone.manage")
def patch_milestone(project_id, milestone_id):
    ctx = policy.current_context()
    project = projects.get_visible_project(ctx, project_id)
    milestone = milestones.get_or_404(ctx, project, milestone_id)
    milestone = milestones.update(ctx, project, milestone, json_body())
    return ok({"milestone": serialize_milestone(milestone)})


@bp.delete("/projects/<project_id>/milestones/<milestone_id>")
@policy.require_permission("milestone.manage")
def delete_milestone(project_id, milestone_id):
    ctx = policy.current_context()
    project = projects.get_visible_project(ctx, project_id)
    milestone = milestones.get_or_404(ctx, project, milestone_id)
    milestones.delete(ctx, project, milestone)
    return ok({"deleted": milestone_id})
