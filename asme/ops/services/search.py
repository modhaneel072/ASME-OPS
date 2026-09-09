"""Global search across work orders, projects, assets, locations, categories
and members.

Every group is filtered by the caller's visibility:

* work orders through ``work_orders.visible_work_orders_query`` (title match;
  a numeric query also matches the work-order number);
* projects through the project visibility rule (chapter projects need
  ``project.read``; private ones need membership or ``project.read_private``);
* assets need ``asset.read`` and go through ``policy.visible_project_filter``;
* locations need ``location.read``; categories need ``category.read``;
* members (active memberships) appear only for holders of ``team.read`` or
  ``user.read``.

Groups the caller may not read come back as empty lists so the response shape
is stable.
"""

from __future__ import annotations

from sqlalchemy import or_, select

from asme.extensions import db
from asme.models import User
from asme.ops import policy
from asme.ops.models import Asset, Category, Location, Membership, OpsProject, WorkOrder
from asme.ops.validation import ValidationErrors

MIN_QUERY_LENGTH = 2
DEFAULT_LIMIT = 8
MAX_LIMIT = 20
GROUPS = ("work_orders", "projects", "assets", "locations", "categories", "users")


def clamp_limit(value) -> int:
    try:
        limit = int(value)
    except (TypeError, ValueError):
        return DEFAULT_LIMIT
    return max(1, min(limit, MAX_LIMIT))


def _like(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _number_of(text: str) -> int | None:
    digits = text.lstrip("#").strip()
    return int(digits) if digits.isdigit() else None


def search(ctx, q: str, limit: int = DEFAULT_LIMIT) -> dict:
    """Return ``{"query", "results": {group: [rows]}}`` with ORM rows per group."""
    text = (q or "").strip()
    if len(text) < MIN_QUERY_LENGTH:
        raise ValidationErrors({"q": f"Type at least {MIN_QUERY_LENGTH} characters."})
    limit = clamp_limit(limit)
    pattern = _like(text)
    return {
        "query": text,
        "results": {
            "work_orders": _work_orders(ctx, text, pattern, limit),
            "projects": _projects(ctx, pattern, limit),
            "assets": _assets(ctx, pattern, limit),
            "locations": _locations(ctx, pattern, limit),
            "categories": _categories(ctx, pattern, limit),
            "users": _users(ctx, pattern, limit),
        },
    }


def _work_orders(ctx, text: str, pattern: str, limit: int) -> list[WorkOrder]:
    from asme.ops.services.work_orders import visible_work_orders_query

    criteria = [WorkOrder.title.ilike(pattern, escape="\\")]
    number = _number_of(text)
    if number is not None:
        criteria.append(WorkOrder.number == number)
    return visible_work_orders_query(ctx).filter(or_(*criteria)).order_by(WorkOrder.number.desc()).limit(limit).all()


def _projects(ctx, pattern: str, limit: int) -> list[OpsProject]:
    stmt = select(OpsProject).where(
        OpsProject.organization_id == ctx.org.id,
        or_(OpsProject.name.ilike(pattern, escape="\\"), OpsProject.code.ilike(pattern, escape="\\")),
    )
    visible = []
    if ctx.has("project.read"):
        visible.append(OpsProject.visibility != "private")
    if ctx.has("project.read_private"):
        visible.append(OpsProject.visibility == "private")
    elif ctx.project_ids:
        visible.append(OpsProject.id.in_(list(ctx.project_ids)))
    if not visible:
        return []
    return list(db.session.scalars(stmt.where(or_(*visible)).order_by(OpsProject.archived_at.is_not(None), OpsProject.name.asc()).limit(limit)))


def _assets(ctx, pattern: str, limit: int) -> list[Asset]:
    if not ctx.has("asset.read"):
        return []
    stmt = (
        select(Asset)
        .where(
            Asset.organization_id == ctx.org.id,
            Asset.is_active.is_(True),
            or_(Asset.name.ilike(pattern, escape="\\"), Asset.code.ilike(pattern, escape="\\"), Asset.serial_number.ilike(pattern, escape="\\")),
            policy.visible_project_filter(ctx, Asset.project_id),
        )
        .order_by(Asset.name.asc())
        .limit(limit)
    )
    return list(db.session.scalars(stmt))


def _locations(ctx, pattern: str, limit: int) -> list[Location]:
    if not ctx.has("location.read"):
        return []
    stmt = (
        select(Location)
        .where(Location.organization_id == ctx.org.id, Location.is_active.is_(True), Location.name.ilike(pattern, escape="\\"))
        .order_by(Location.name.asc())
        .limit(limit)
    )
    return list(db.session.scalars(stmt))


def _categories(ctx, pattern: str, limit: int) -> list[Category]:
    if not ctx.has("category.read"):
        return []
    stmt = (
        select(Category)
        .where(Category.organization_id == ctx.org.id, Category.is_active.is_(True), Category.name.ilike(pattern, escape="\\"))
        .order_by(Category.name.asc())
        .limit(limit)
    )
    return list(db.session.scalars(stmt))


def _users(ctx, pattern: str, limit: int) -> list[User]:
    if not (ctx.has("team.read") or ctx.has("user.read")):
        return []
    stmt = (
        select(User)
        .join(Membership, Membership.user_id == User.id)
        .where(
            Membership.organization_id == ctx.org.id,
            Membership.member_status == "active",
            or_(User.name.ilike(pattern, escape="\\"), User.email.ilike(pattern, escape="\\")),
        )
        .order_by(User.name.asc())
        .limit(limit)
    )
    return list(db.session.scalars(stmt))
