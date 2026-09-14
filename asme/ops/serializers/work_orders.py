"""JSON shapes for work orders (see the plan's "Serializer shapes").

``work_order`` is the list/item shape; ``work_order_detail`` adds status
history, time and cost entries, dependencies, children and related assets.
``serialize_many`` batches the per-row sub-work-order counts so a list page is
two queries instead of one per row.
"""

from __future__ import annotations

from sqlalchemy import case, func, select

from asme.extensions import db
from asme.ops.models import WorkOrder
from asme.ops.serializers import asset_ref, category_ref, iso, location_ref, money, project_ref, team_ref, uid, user_ref, vendor_ref


def sub_counts_for(work_order_ids) -> dict:
    """``{parent_id: {"total": n, "done": n}}`` for the given parent ids in one query."""
    ids = [i for i in work_order_ids if i is not None]
    if not ids:
        return {}
    rows = db.session.execute(
        select(
            WorkOrder.parent_work_order_id,
            func.count(WorkOrder.id),
            func.sum(case((WorkOrder.status == "done", 1), else_=0)),
        )
        .where(WorkOrder.parent_work_order_id.in_(ids))
        .group_by(WorkOrder.parent_work_order_id)
    ).all()
    return {parent_id: {"total": int(total), "done": int(done or 0)} for parent_id, total, done in rows}


def _sub_counts_from_children(wo: WorkOrder) -> dict:
    children = list(wo.children)
    return {"total": len(children), "done": sum(1 for child in children if child.status == "done")}


def work_order(wo: WorkOrder, *, sub_counts: dict | None = None) -> dict:
    counts = sub_counts.get(wo.id, {"total": 0, "done": 0}) if sub_counts is not None else _sub_counts_from_children(wo)
    parent = wo.parent if wo.parent_work_order_id else None
    return {
        "id": uid(wo.id),
        "number": wo.number,
        "title": wo.title,
        "description": wo.description,
        "status": wo.status,
        "priority": wo.priority,
        "work_type": wo.work_type,
        "project": project_ref(wo.project),
        "location": location_ref(wo.location),
        "asset": asset_ref(wo.primary_asset),
        "team": team_ref(wo.team),
        "assignees": [user_ref(a.user) for a in wo.assignees if a.user_id and a.user is not None],
        "assignee_teams": [team_ref(a.team) for a in wo.assignees if a.team_id and a.team is not None],
        "watchers": [user_ref(w.user) for w in wo.watchers if w.user is not None],
        "categories": [category_ref(link.category) for link in wo.category_links if link.category is not None],
        "vendor": vendor_ref(wo.vendor),
        "parent_id": uid(wo.parent_work_order_id),
        "parent_number": parent.number if parent is not None else None,
        "parent_completion_policy": wo.parent_completion_policy,
        "sub_work_orders": counts,
        "start_at": iso(wo.start_at),
        "due_at": iso(wo.due_at),
        "completed_at": iso(wo.completed_at),
        "canceled_at": iso(wo.canceled_at),
        "estimated_minutes": wo.estimated_minutes,
        "actual_minutes": int(wo.actual_minutes or 0),
        "is_overdue": bool(wo.is_overdue),
        "is_blocked": bool(wo.is_blocked),
        "budget_code": wo.budget_code,
        "completion_note": wo.completion_note,
        "created_by": user_ref(wo.created_by),
        "created_at": iso(wo.created_at),
        "updated_at": iso(wo.updated_at),
    }


def serialize_many(work_orders: list[WorkOrder]) -> list[dict]:
    counts = sub_counts_for([wo.id for wo in work_orders])
    return [work_order(wo, sub_counts=counts) for wo in work_orders]


def status_history_entry(row) -> dict:
    return {
        "id": uid(row.id),
        "from_status": row.from_status,
        "to_status": row.to_status,
        "changed_by": user_ref(row.changed_by),
        "note": row.note,
        "changed_at": iso(row.changed_at),
    }


def time_entry(row) -> dict:
    return {
        "id": uid(row.id),
        "user": user_ref(row.user),
        "minutes": int(row.minutes),
        "started_at": iso(row.started_at),
        "ended_at": iso(row.ended_at),
        "note": row.note,
        "created_at": iso(row.created_at),
    }


def cost_entry(row) -> dict:
    return {
        "id": uid(row.id),
        "type": row.type,
        "amount": money(row.amount),
        "vendor": vendor_ref(row.vendor),
        "description": row.description,
        "created_at": iso(row.created_at),
    }


def _work_order_stub(wo: WorkOrder) -> dict:
    return {"id": uid(wo.id), "number": wo.number, "title": wo.title, "status": wo.status}


def dependency_entry(dep, *, other: WorkOrder) -> dict:
    return {"id": uid(dep.id), "dependency_type": dep.dependency_type, "work_order": _work_order_stub(other)}


def work_order_detail(wo: WorkOrder) -> dict:
    data = work_order(wo)
    children = list(wo.children)
    data.update(
        {
            "status_history": [status_history_entry(row) for row in wo.status_history],
            "time_entries": [time_entry(row) for row in wo.time_entries],
            "cost_entries": [cost_entry(row) for row in wo.cost_entries],
            "dependencies": {
                "blocked_by": [dependency_entry(dep, other=dep.blocking_work_order) for dep in wo.blocked_by],
                "blocking": [dependency_entry(dep, other=dep.blocked) for dep in wo.blocking],
            },
            "children": serialize_many(children),
            "related_assets": [asset_ref(link.asset) for link in wo.asset_links if link.relationship_type == "related" and link.asset is not None],
        }
    )
    return data
