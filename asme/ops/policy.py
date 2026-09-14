"""Permission checks for ASME Ops.

``PolicyContext`` is built once per request (``g.ops_ctx``) from the user's
membership in the active organization. Routes gate on ``require_permission``;
services call ``authorize(ctx, key, obj)`` before mutating and use
``visible_project_filter`` / ``get_or_404`` so cross-organization ids and
private projects are never leaked.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from functools import wraps
from uuid import UUID

from flask import g, has_request_context, jsonify
from sqlalchemy import or_, select, true

from asme.auth.session import current_auth_user
from asme.extensions import db
from asme.ops import permissions as registry
from asme.ops.models import Membership, OpsProject, Organization, ProjectMember, Role, Team, TeamMember
from asme.services.errors import Forbidden, NotFound

log = logging.getLogger("asme.ops.policy")

NO_MEMBERSHIP_MESSAGE = "Your account is not a member of this chapter's ASME Ops workspace."


@dataclass
class PolicyContext:
    user: object
    org: Organization
    membership: Membership
    role: Role
    grants: dict[str, set[str]] = field(default_factory=dict)
    project_ids: set[UUID] = field(default_factory=set)
    team_ids: set[UUID] = field(default_factory=set)
    lead_team_ids: set[UUID] = field(default_factory=set)

    @property
    def user_id(self) -> int:
        return self.user.id

    @property
    def org_id(self) -> UUID:
        return self.org.id

    def has(self, key: str) -> bool:
        return bool(self.grants.get(key))

    def scopes(self, key: str) -> set[str]:
        return set(self.grants.get(key, ()))

    @property
    def is_chapter_admin(self) -> bool:
        return self.role.system_key == "chapter_admin"

    def permission_map(self) -> dict[str, list[str]]:
        return {key: sorted(scopes, key=registry.SCOPE_RANK.get) for key, scopes in sorted(self.grants.items())}


# --------------------------------------------------------------------------- loading


def load_context(user, org: Organization | None = None) -> PolicyContext | None:
    if user is None:
        return None
    if org is None:
        from asme.ops.bootstrap import default_organization

        org = default_organization()
    if org is None:
        return None
    membership = Membership.query.filter_by(organization_id=org.id, user_id=user.id).first()
    if membership is None or membership.member_status != "active" or membership.role is None:
        return None
    grants: dict[str, set[str]] = {}
    for grant in membership.role.grants:
        if grant.permission:
            grants.setdefault(grant.permission.key, set()).add(grant.scope_type)
    project_ids = {
        row[0]
        for row in db.session.execute(
            select(ProjectMember.project_id).join(OpsProject, OpsProject.id == ProjectMember.project_id).where(
                ProjectMember.user_id == user.id, OpsProject.organization_id == org.id
            )
        )
    }
    team_rows = db.session.execute(
        select(TeamMember.team_id, TeamMember.is_lead).join(Team, Team.id == TeamMember.team_id).where(
            TeamMember.user_id == user.id, Team.organization_id == org.id
        )
    ).all()
    return PolicyContext(
        user=user,
        org=org,
        membership=membership,
        role=membership.role,
        grants=grants,
        project_ids=project_ids,
        team_ids={row[0] for row in team_rows},
        lead_team_ids={row[0] for row in team_rows if row[1]},
    )


def current_context() -> PolicyContext:
    """The context for the logged-in user, cached per request. Raises ``Forbidden``
    (403 ``no_membership``) when the user has no active membership."""
    user = current_auth_user()
    if user is None:
        raise Forbidden("Login required.", code="login_required")
    cached = _cached_context(user)
    if cached is not None:
        return cached
    ctx = load_context(user)
    if ctx is None:
        raise Forbidden(NO_MEMBERSHIP_MESSAGE, code="no_membership")
    _cache_context(ctx)
    return ctx


def _cached_context(user) -> PolicyContext | None:
    if not has_request_context():
        return None
    ctx = getattr(g, "ops_ctx", None)
    if ctx is not None and ctx.user.id == user.id:
        return ctx
    return None


def _cache_context(ctx: PolicyContext) -> None:
    if has_request_context():
        g.ops_ctx = ctx


def clear_cached_context() -> None:
    if has_request_context():
        g.ops_ctx = None


# --------------------------------------------------------------------------- checks


def _project_id_of(obj):
    if isinstance(obj, OpsProject):
        return obj.id
    return getattr(obj, "project_id", None)


def _team_ids_of(obj) -> set:
    ids = set()
    if isinstance(obj, Team):
        ids.add(obj.id)
    team_id = getattr(obj, "team_id", None)
    if team_id:
        ids.add(team_id)
    responsible = getattr(obj, "responsible_team_id", None)
    if responsible:
        ids.add(responsible)
    ids |= set(getattr(obj, "assignee_team_ids", ()) or ())
    return ids


def can(ctx: PolicyContext, key: str, obj=None) -> bool:
    scopes = ctx.scopes(key)
    if not scopes:
        return False
    if "chapter" in scopes or obj is None:
        return True
    if "project" in scopes:
        project_id = _project_id_of(obj)
        if project_id and project_id in ctx.project_ids:
            return True
    if "team" in scopes:
        allowed = ctx.team_ids if registry.is_read_key(key) else ctx.lead_team_ids
        if _team_ids_of(obj) & allowed:
            return True
    if "assigned" in scopes:
        if ctx.user.id in set(getattr(obj, "assignee_user_ids", ()) or ()):
            return True
        if set(getattr(obj, "assignee_team_ids", ()) or ()) & ctx.team_ids:
            return True
    if "own" in scopes:
        if getattr(obj, "created_by_user_id", None) == ctx.user.id:
            return True
        if getattr(obj, "owner_user_id", None) == ctx.user.id:
            return True
        if getattr(obj, "author_user_id", None) == ctx.user.id:
            return True
    return False


def authorize(ctx: PolicyContext, key: str, obj=None, message: str | None = None) -> None:
    if obj is not None and getattr(obj, "organization_id", ctx.org.id) != ctx.org.id:
        raise NotFound()
    if not can(ctx, key, obj):
        raise Forbidden(message or "You do not have permission to do that.", permission=key)


def can_read_project(ctx: PolicyContext, project: OpsProject) -> bool:
    if project.organization_id != ctx.org.id:
        return False
    if project.visibility != "private":
        return ctx.has("project.read")
    return project.id in ctx.project_ids or ctx.has("project.read_private")


def visible_project_filter(ctx: PolicyContext, column, *, include_null: bool = True):
    """SQL criterion restricting ``column`` (a project id column) to projects the
    user may read. ``include_null`` keeps rows that belong to no project."""
    if ctx.has("project.read_private"):
        return true()
    hidden = select(OpsProject.id).where(OpsProject.organization_id == ctx.org.id, OpsProject.visibility == "private")
    if ctx.project_ids:
        hidden = hidden.where(OpsProject.id.notin_(list(ctx.project_ids)))
    criterion = column.notin_(hidden)
    if include_null:
        return or_(column.is_(None), criterion)
    return criterion


def get_or_404(ctx: PolicyContext, model, object_id, message: str = "Not found."):
    """Load a tenant-owned row by id, treating other organizations' rows as missing."""
    if object_id is None:
        raise NotFound(message)
    row = db.session.get(model, object_id)
    if row is None or getattr(row, "organization_id", ctx.org.id) != ctx.org.id:
        raise NotFound(message)
    return row


# --------------------------------------------------------------------------- decorator


def _deny(status: int, code: str, message: str, **extra):
    body = {"ok": False, "code": code, "error": message}
    body.update(extra)
    return jsonify(body), status


def require_permission(*keys: str, any_of: bool = False):
    """Route decorator: login, active membership, and the permission key(s) at
    any scope. Object-level scope is enforced inside services."""

    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            user = current_auth_user()
            if user is None:
                return _deny(401, "login_required", "Login required.")
            ctx = _cached_context(user)
            if ctx is None:
                ctx = load_context(user)
                if ctx is None:
                    return _deny(403, "no_membership", NO_MEMBERSHIP_MESSAGE)
                _cache_context(ctx)
            if keys:
                checks = [ctx.has(key) for key in keys]
                allowed = any(checks) if any_of else all(checks)
                if not allowed:
                    return _deny(403, "forbidden", "You do not have permission to do that.", permission=list(keys))
            return view_func(*args, **kwargs)

        wrapped.ops_permissions = tuple(keys)  # introspected by docs generators
        wrapped.ops_permissions_any_of = any_of
        return wrapped

    return decorator
