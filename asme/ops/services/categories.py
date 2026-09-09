"""Categories service (``ops_categories``).

Names are unique per organization, compared case-insensitively. Deleting is a
hard delete and is refused while any work order is tagged with the category.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, or_, select

from asme.extensions import db
from asme.models import User
from asme.ops import policy
from asme.ops.models import Category, WorkOrderCategory
from asme.ops.services import audit_events
from asme.ops.validation import Field, ValidationErrors, validate
from asme.services.errors import Conflict

AUDIT_FIELDS = ("name", "color", "icon", "description", "is_active")
SORTS = ("name", "usage", "created_at")
DEFAULT_COLOR = "#0878d1"
DEFAULT_ICON = "tag"
DUPLICATE_NAME = "A category with this name already exists."

SPEC = {
    "name": Field("str", required=True, max_len=120, nullable=False),
    "color": Field("color", default=DEFAULT_COLOR, nullable=False),
    "icon": Field("str", max_len=60, default=DEFAULT_ICON, nullable=False),
    "description": Field("text"),
}


# --------------------------------------------------------------------------- reads


def base_query(ctx):
    return Category.query.filter(Category.organization_id == ctx.org.id)


def get(ctx, category_id) -> Category:
    return policy.get_or_404(ctx, Category, category_id)


def _like(term: str) -> str:
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _usage_column():
    return select(func.count(WorkOrderCategory.id)).where(WorkOrderCategory.category_id == Category.id).correlate(Category).scalar_subquery()


def list_query(ctx, *, q: str = "", sort: str = "name"):
    query = base_query(ctx)
    if q:
        pattern = _like(q)
        query = query.filter(or_(Category.name.ilike(pattern, escape="\\"), Category.description.ilike(pattern, escape="\\")))
    descending = sort.startswith("-")
    key = sort[1:] if descending else sort
    if key not in SORTS:
        raise ValueError(f"unknown category sort {sort!r}")
    if key == "name":
        column = func.lower(Category.name)
    elif key == "usage":
        column = _usage_column()
    else:
        column = Category.created_at
    return query.order_by(column.desc() if descending else column.asc(), func.lower(Category.name).asc(), Category.id.asc())


def usage_for(ctx, rows) -> dict[UUID, int]:
    """Work-order count per category id for ``rows`` (one query)."""
    ids = [row.id for row in rows if row.organization_id == ctx.org.id]
    if not ids:
        return {}
    counts = db.session.execute(
        select(WorkOrderCategory.category_id, func.count(WorkOrderCategory.id))
        .where(WorkOrderCategory.category_id.in_(ids))
        .group_by(WorkOrderCategory.category_id)
    ).all()
    return {category_id: int(count) for category_id, count in counts}


def creators_for(rows) -> dict[int, User]:
    ids = {row.created_by_user_id for row in rows if row.created_by_user_id}
    if not ids:
        return {}
    return {user.id: user for user in User.query.filter(User.id.in_(ids)).all()}


def usage_count(ctx, category: Category) -> int:
    return usage_for(ctx, [category]).get(category.id, 0)


# --------------------------------------------------------------------------- writes


def _name_taken(ctx, name: str, *, exclude: UUID | None = None) -> bool:
    query = base_query(ctx).filter(func.lower(Category.name) == name.lower())
    if exclude is not None:
        query = query.filter(Category.id != exclude)
    return db.session.scalar(select(query.exists())) is True


def create(ctx, payload: dict) -> Category:
    policy.authorize(ctx, "category.manage")
    data = validate(payload, SPEC)
    if _name_taken(ctx, data["name"]):
        raise ValidationErrors({"name": DUPLICATE_NAME})
    category = Category(
        organization_id=ctx.org.id,
        name=data["name"],
        color=data["color"],
        icon=data["icon"],
        description=data.get("description"),
        is_active=True,
        created_by_user_id=ctx.user_id,
        updated_by_user_id=ctx.user_id,
    )
    db.session.add(category)
    db.session.flush()
    audit_events.record(
        ctx,
        "category.created",
        category,
        after=audit_events.snapshot(category, AUDIT_FIELDS),
        summary=f"Created category {category.name}",
    )
    db.session.commit()
    return category


def update(ctx, category: Category, payload: dict) -> Category:
    policy.authorize(ctx, "category.manage", category)
    data = validate(payload, SPEC, partial=True)
    if "name" in data and _name_taken(ctx, data["name"], exclude=category.id):
        raise ValidationErrors({"name": DUPLICATE_NAME})
    before = audit_events.snapshot(category, AUDIT_FIELDS)
    for key in ("name", "color", "icon", "description"):
        if key in data:
            setattr(category, key, data[key])
    after = audit_events.snapshot(category, AUDIT_FIELDS)
    if after == before:
        return category
    category.updated_by_user_id = ctx.user_id
    audit_events.record(ctx, "category.updated", category, before=before, after=after, summary=f"Updated category {category.name}")
    db.session.commit()
    return category


def delete(ctx, category: Category) -> None:
    policy.authorize(ctx, "category.manage", category)
    used_by = usage_count(ctx, category)
    if used_by:
        raise Conflict("This category is still used by work orders.", code="category_in_use", usage={"work_orders": used_by})
    audit_events.record(
        ctx,
        "category.deleted",
        category,
        before=audit_events.snapshot(category, AUDIT_FIELDS),
        summary=f"Deleted category {category.name}",
    )
    db.session.delete(category)
    db.session.commit()
