"""JSON shapes for projects, project members and milestones.

Field names follow the plan's "Serializer shapes" section. The milestone status
is the *effective* status: a milestone whose ``due_date`` has passed and that is
not done is reported as ``missed`` without persisting the change (the nightly
scan job persists it).
"""

from __future__ import annotations

from datetime import date

from asme.ops.serializers import iso, money, team_ref, uid, user_ref
from asme.ops.types import utcnow


def today_utc() -> date:
    return utcnow().date()


def effective_milestone_status(m, today: date | None = None) -> str:
    if m.status == "done":
        return "done"
    today = today or today_utc()
    if m.due_date is not None and m.due_date < today:
        return "missed"
    return m.status


def milestone(m, today: date | None = None) -> dict:
    return {
        "id": uid(m.id),
        "project_id": uid(m.project_id),
        "name": m.name,
        "description": m.description,
        "due_date": iso(m.due_date),
        "status": effective_milestone_status(m, today),
        "owner": user_ref(m.owner),
        "weight": int(m.weight or 1),
        "completed_at": iso(m.completed_at),
        "order_index": int(m.order_index or 0),
    }


EMPTY_STATS = {
    "open_work_orders": 0,
    "overdue_work_orders": 0,
    "completion_percent": 0,
    "next_milestone": None,
    "member_count": 0,
}


def project(p, stats: dict | None = None) -> dict:
    return {
        "id": uid(p.id),
        "name": p.name,
        "code": p.code,
        "description": p.description,
        "status": p.status,
        "visibility": p.visibility,
        "risk_level": p.risk_level,
        "lead": user_ref(p.lead),
        "faculty_advisor": user_ref(p.faculty_advisor),
        "start_date": iso(p.start_date),
        "target_date": iso(p.target_date),
        "budget_amount": money(p.budget_amount),
        "repository_url": p.repository_url,
        "cad_url": p.cad_url,
        "requirements_url": p.requirements_url,
        "competition": p.competition,
        "academic_year": p.academic_year,
        "public_project_id": p.public_project_id,
        "archived_at": iso(p.archived_at),
        "stats": dict(stats) if stats is not None else dict(EMPTY_STATS),
        "created_at": iso(p.created_at),
        "updated_at": iso(p.updated_at),
    }


def project_member(pm) -> dict:
    return {
        "user": user_ref(pm.user),
        "project_role": pm.project_role,
        "team": team_ref(pm.team),
        "joined_at": iso(pm.joined_at),
    }
