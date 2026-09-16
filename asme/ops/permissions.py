"""Permission registry and default role grants.

This module is the single source of truth for action keys, scopes and the
twelve system roles. ``bootstrap.ensure_default_organization`` seeds it into
``ops_permissions`` / ``ops_roles`` / ``ops_role_permissions``; the policy
engine reads the seeded rows, so a chapter may later customise grants without
code changes.

Scope semantics (see ``asme/ops/policy.py``):

* ``chapter``  – anywhere in the organization
* ``project``  – only on records belonging to a project the user is a member of
* ``team``     – only on records owned by a team the user leads (read keys: is a member of)
* ``assigned`` – only on records the user (or one of their teams) is assigned to
* ``own``      – only on records the user created
"""

from __future__ import annotations

SCOPES = ("chapter", "project", "team", "assigned", "own")
SCOPE_RANK = {scope: index for index, scope in enumerate(SCOPES)}

PERMISSIONS: dict[str, str] = {
    # chapter
    "chapter.settings.manage": "Edit chapter profile, branding and security settings",
    "chapter.setup.manage": "Complete or reopen Setup Center tasks for everyone",
    # people
    "user.read": "View the member directory",
    "user.manage": "Invite members, change their role or status",
    "role.manage": "Edit roles and permission grants",
    "team.read": "View teams and their members",
    "team.manage": "Create teams and edit their membership",
    # structure
    "location.read": "View locations",
    "location.manage": "Create, edit and delete locations",
    "category.read": "View categories",
    "category.manage": "Create, edit and delete categories",
    "asset.read": "View assets and their history",
    "asset.manage": "Create and edit assets",
    "asset.status.update": "Change asset status and record downtime",
    "vendor.read": "View vendors",
    "vendor.manage": "Create and edit vendors",
    # projects
    "project.read": "View chapter-visible projects",
    "project.read_private": "View private projects without being a member",
    "project.create": "Create projects",
    "project.manage": "Edit project details, members and settings",
    "project.archive": "Archive and restore projects",
    "milestone.manage": "Create and edit milestones",
    # work
    "work_order.read_all": "View all work orders in visible projects",
    "work_order.read_assigned": "View work orders assigned to you or your teams",
    "work_order.create": "Create work orders",
    "work_order.edit": "Edit work-order fields",
    "work_order.assign": "Change assignees, team and watchers",
    "work_order.start": "Start, hold and resume work",
    "work_order.complete": "Complete work orders",
    "work_order.cancel": "Cancel work orders",
    "work_order.comment": "Comment on work orders",
    "work_order.log_time": "Record time and cost entries",
    "work_order.attach": "Upload files to work orders, projects, assets, parts and purchase requests",
    # ui / reporting
    "saved_filter.share": "Share saved filters with a team or the chapter",
    "report.view": "View reports and dashboards",
    "report.export": "Export report data",
    "audit.read": "View the audit history",
    "notification.read": "Receive in-app notifications",
    # seeded now, enforced by later stages
    "request.submit": "Submit requests",
    "request.review": "Review, approve, decline and convert requests",
    "inventory.read": "View parts inventory",
    "inventory.manage": "Receive, issue, transfer and count parts",
    "purchase.submit": "Submit purchase requests",
    "purchase.review": "Approve purchase requests",
    "purchase.advisor_review": "Give faculty-advisor sign-off on purchase requests",
    "procedure.read": "View procedures",
    "procedure.manage": "Author procedure drafts",
    "procedure.publish": "Publish procedure versions",
    "plan.manage": "Create and edit maintenance plans",
    "meter.read": "View meters and readings",
    "meter.record": "Record meter readings",
    "automation.manage": "Create and edit automations",
    "dashboard.manage": "Create and share dashboards",
    "message.read": "Read conversations",
    "message.send": "Send messages",
    "sponsor.manage": "Manage sponsors",
}

READ_SUFFIXES = (".read", ".read_all", ".read_assigned", ".read_private", ".view")


def is_read_key(key: str) -> bool:
    return key.endswith(READ_SUFFIXES)


SYSTEM_ROLES: list[dict[str, str]] = [
    {"key": "chapter_admin", "name": "Chapter Administrator", "description": "All chapter settings, users, data, reporting and audit."},
    {"key": "executive_officer", "name": "Executive Officer", "description": "Broad operational access; limited security configuration."},
    {"key": "project_lead", "name": "Project Lead", "description": "Manages own projects, their teams, work, assets and reports."},
    {"key": "team_lead", "name": "Team Lead", "description": "Creates, assigns and manages work for own team."},
    {"key": "full_member", "name": "Full Member", "description": "Executes work, creates permitted work, uses messages and procedures."},
    {"key": "shop_operator", "name": "Shop Operator", "description": "Views and completes assigned work; reports issues."},
    {"key": "requester", "name": "Requester", "description": "Submits and tracks requests."},
    {"key": "inventory_manager", "name": "Inventory Manager", "description": "Parts, transactions, cycle counts and purchase receiving."},
    {"key": "safety_officer", "name": "Safety Officer", "description": "Procedures, inspections, corrective actions and safety reporting."},
    {"key": "treasurer", "name": "Treasurer", "description": "Purchase approvals, budgets and cost reports."},
    {"key": "faculty_advisor", "name": "Faculty Advisor", "description": "Reads everything plus approvals configured by the chapter."},
    {"key": "sponsor_guest", "name": "Sponsor / Guest", "description": "Explicitly shared read-only dashboards or reports."},
]
SYSTEM_ROLE_KEYS = tuple(role["key"] for role in SYSTEM_ROLES)

LEGACY_ROLE_MAP = {"admin": "chapter_admin", "team_leader": "team_lead", "member": "full_member"}
# Ops roles that should also hold the legacy admin role so the legacy portal agrees.
OPS_ROLES_IMPLYING_LEGACY_ADMIN = ("chapter_admin",)


def _grants(*, chapter=(), project=(), team=(), assigned=(), own=()) -> dict[str, str]:
    out: dict[str, str] = {}
    for scope, keys in (("own", own), ("assigned", assigned), ("team", team), ("project", project), ("chapter", chapter)):
        for key in keys:
            out[key] = scope  # broader scope listed later wins
    return out


_ALL = tuple(PERMISSIONS)

_FULL_MEMBER_CHAPTER = (
    "project.read",
    "work_order.read_all",
    "work_order.create",
    "work_order.comment",
    "work_order.attach",
    "team.read",
    "asset.read",
    "location.read",
    "category.read",
    "vendor.read",
    "report.view",
    "request.submit",
    "notification.read",
    "inventory.read",
    "purchase.submit",
)
_FULL_MEMBER = _grants(
    chapter=_FULL_MEMBER_CHAPTER,
    own=("work_order.edit",),
    assigned=("work_order.start", "work_order.complete", "work_order.log_time"),
)


def _extend(base: dict[str, str], **scoped) -> dict[str, str]:
    merged = dict(base)
    merged.update(_grants(**scoped))
    return merged


DEFAULT_GRANTS: dict[str, dict[str, str]] = {
    "chapter_admin": _grants(chapter=_ALL),
    "executive_officer": _grants(chapter=tuple(k for k in _ALL if k not in ("role.manage", "chapter.settings.manage"))),
    "project_lead": _grants(
        chapter=(
            "project.read",
            "project.create",
            "work_order.create",
            "work_order.read_all",
            "work_order.comment",
            "work_order.attach",
            "work_order.log_time",
            "team.read",
            "asset.read",
            "location.read",
            "category.read",
            "vendor.read",
            "report.view",
            "notification.read",
            "inventory.read",
            "purchase.submit",
        ),
        project=(
            "project.read_private",
            "project.manage",
            "milestone.manage",
            "work_order.edit",
            "work_order.assign",
            "work_order.start",
            "work_order.complete",
            "work_order.cancel",
            "asset.manage",
            "team.manage",
            "report.export",
        ),
    ),
    "team_lead": _grants(
        chapter=(
            "project.read",
            "work_order.create",
            "work_order.read_all",
            "work_order.comment",
            "work_order.attach",
            "work_order.log_time",
            "team.read",
            "asset.read",
            "location.read",
            "category.read",
            "vendor.read",
            "report.view",
            "notification.read",
            "inventory.read",
            "purchase.submit",
        ),
        team=(
            "team.manage",
            "work_order.edit",
            "work_order.assign",
            "work_order.start",
            "work_order.complete",
            "work_order.cancel",
        ),
    ),
    "full_member": dict(_FULL_MEMBER),
    "shop_operator": _grants(
        chapter=(
            "project.read",
            "work_order.read_assigned",
            "work_order.comment",
            "work_order.attach",
            "asset.read",
            "location.read",
            "request.submit",
            "notification.read",
            "inventory.read",
        ),
        assigned=("work_order.start", "work_order.complete", "work_order.log_time"),
    ),
    "requester": _grants(chapter=("project.read", "request.submit", "notification.read")),
    "inventory_manager": _extend(
        _FULL_MEMBER,
        chapter=(
            "inventory.read",
            "inventory.manage",
            "purchase.submit",
            "asset.manage",
            "vendor.manage",
            "work_order.edit",
            "work_order.assign",
        ),
    ),
    "safety_officer": _extend(
        _FULL_MEMBER,
        chapter=(
            "procedure.read",
            "procedure.manage",
            "procedure.publish",
            "asset.status.update",
            "work_order.edit",
            "work_order.assign",
            "work_order.cancel",
            "audit.read",
        ),
    ),
    "treasurer": _extend(_FULL_MEMBER, chapter=("purchase.review", "vendor.read", "report.export", "audit.read")),
    "faculty_advisor": _grants(
        chapter=(
            "project.read",
            "project.read_private",
            "work_order.read_all",
            "asset.read",
            "team.read",
            "user.read",
            "location.read",
            "category.read",
            "report.view",
            "report.export",
            "audit.read",
            "purchase.review",
            "notification.read",
            "inventory.read",
            "vendor.read",
            "purchase.advisor_review",
        )
    ),
    "sponsor_guest": _grants(chapter=("report.view",)),
}


def validate_registry() -> list[str]:
    """Return a list of problems; empty when the registry is consistent."""
    problems: list[str] = []
    for role_key, grants in DEFAULT_GRANTS.items():
        if role_key not in SYSTEM_ROLE_KEYS:
            problems.append(f"grants for unknown role {role_key}")
        for key, scope in grants.items():
            if key not in PERMISSIONS:
                problems.append(f"{role_key}: unknown permission {key}")
            if scope not in SCOPES:
                problems.append(f"{role_key}: unknown scope {scope} for {key}")
    for role_key in SYSTEM_ROLE_KEYS:
        if role_key not in DEFAULT_GRANTS:
            problems.append(f"no grants defined for {role_key}")
    return problems
