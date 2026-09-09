"""Setup Center: derived onboarding progress for a chapter.

Progress is never stored; every task is evaluated from live data so it stays
correct when records are deleted. Tasks that belong to later stages are
reported as ``unavailable`` with their ``stage`` number and are excluded from
the percentage, as are optional tasks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from sqlalchemy import func, select

from asme.extensions import db
from asme.ops import policy
from asme.ops.models import Asset, Category, Location, Membership, OpsProject, Team
from asme.ops.serializers import iso
from asme.ops.services import audit_events, preferences
from asme.ops.types import utcnow

MIN_ASSETS = 5
MIN_ACTIVE_MEMBERSHIPS = 3
ORG_SNAPSHOT = ("settings_json", "setup_completed_at")
GUIDE_READ_KEY = "officer_guide_read"
PROFILE_COMPLETED_KEY = "profile_completed"


@dataclass(frozen=True)
class TaskSpec:
    key: str
    title: str
    description: str
    estimated_minutes: int
    href: str
    check: Callable | None = None  # (ctx) -> (complete: bool, count: int | None)
    optional: bool = False
    stage: int | None = None  # set when the task is unavailable in this stage


@dataclass(frozen=True)
class PhaseSpec:
    key: str
    title: str
    description: str
    tasks: tuple[TaskSpec, ...]


# --------------------------------------------------------------------------- checks


def _count(stmt) -> int:
    return int(db.session.scalar(stmt) or 0)


def _chapter_profile(ctx):
    settings = ctx.org.settings
    complete = bool((ctx.org.timezone or "").strip()) and settings.get(PROFILE_COMPLETED_KEY) is True
    return complete, None


def _locations(ctx):
    count = _count(
        select(func.count(Location.id)).where(Location.organization_id == ctx.org.id, Location.is_default.is_(False), Location.is_active.is_(True))
    )
    return count >= 1, count


def _assets(ctx):
    count = _count(select(func.count(Asset.id)).where(Asset.organization_id == ctx.org.id, Asset.is_active.is_(True)))
    return count >= MIN_ASSETS, count


def _teams_users(ctx):
    teams = _count(select(func.count(Team.id)).where(Team.organization_id == ctx.org.id, Team.is_active.is_(True)))
    members = _count(select(func.count(Membership.id)).where(Membership.organization_id == ctx.org.id, Membership.member_status == "active"))
    return teams >= 1 and members >= MIN_ACTIVE_MEMBERSHIPS, members


def _officer_guide(ctx):
    return bool(ctx.org.settings.get(GUIDE_READ_KEY)), None


def _first_project(ctx):
    count = _count(
        select(func.count(OpsProject.id)).where(
            OpsProject.organization_id == ctx.org.id, OpsProject.archived_at.is_(None), OpsProject.status != "archived"
        )
    )
    return count >= 1, count


def _categories(ctx):
    count = _count(select(func.count(Category.id)).where(Category.organization_id == ctx.org.id, Category.is_active.is_(True)))
    return count >= 1, count


PHASES: tuple[PhaseSpec, ...] = (
    PhaseSpec(
        key="foundation",
        title="Build the Foundation",
        description="Describe the chapter, where work happens, what you own and who does it.",
        tasks=(
            TaskSpec("chapter_profile", "Complete the chapter profile", "Set the chapter name, time zone and contact details.", 5, "/app/settings/chapter", _chapter_profile),
            TaskSpec("locations", "Add your first location", "Add at least one lab, shop, storage or field location beyond General.", 5, "/app/locations", _locations),
            TaskSpec("assets", "Register your assets", f"Add at least {MIN_ASSETS} assets: vehicles, subsystems, tools and equipment.", 15, "/app/assets", _assets),
            TaskSpec(
                "teams_users",
                "Set up teams and members",
                f"Create at least one team and have at least {MIN_ACTIVE_MEMBERSHIPS} active members.",
                10,
                "/app/teams-users",
                _teams_users,
            ),
            TaskSpec("officer_guide", "Read the officer guide", "A short tour of roles, work orders and reporting for chapter officers.", 10, "/app/setup", _officer_guide, optional=True),
        ),
    ),
    PhaseSpec(
        key="project_work",
        title="Organize Project Work",
        description="Create a project, label work with categories and prepare parts and procedures.",
        tasks=(
            TaskSpec("first_project", "Create your first project", "Projects group work orders, milestones, members and budget.", 5, "/app/projects", _first_project),
            TaskSpec("categories", "Review categories", "Keep at least one category so work orders can be labelled.", 5, "/app/categories", _categories),
            TaskSpec("parts", "Stock your parts inventory", "Parts and inventory arrive in Stage 4.", 15, "/app/parts", stage=4),
            TaskSpec("procedure", "Write a procedure", "Procedures and checklists arrive in Stage 5.", 20, "/app/procedures", stage=5),
        ),
    ),
    PhaseSpec(
        key="standardize",
        title="Standardize Operations",
        description="Automate recurring work, open a request portal and build dashboards.",
        tasks=(
            TaskSpec("maintenance_plan", "Create a maintenance plan", "Recurring maintenance plans arrive in Stage 5.", 15, "/app/maintenance-plans", stage=5),
            TaskSpec("request_portal", "Open the request portal", "The request portal arrives in Stage 3.", 10, "/app/requests", stage=3),
            TaskSpec("automation", "Add an automation", "Automations arrive in Stage 6.", 10, "/app/automations", stage=6),
            TaskSpec("dashboard", "Build a dashboard", "Custom dashboards arrive in Stage 7.", 10, "/app/dashboards", stage=7),
        ),
    ),
)

TASKS_BY_KEY = {task.key: task for phase in PHASES for task in phase.tasks}


# --------------------------------------------------------------------------- reads


def _task_payload(ctx, task: TaskSpec) -> dict:
    if task.stage is not None:
        status, count = "unavailable", None
    else:
        complete, count = task.check(ctx)
        status = "complete" if complete else "incomplete"
    return {
        "key": task.key,
        "title": task.title,
        "description": task.description,
        "estimated_minutes": task.estimated_minutes,
        "status": status,
        "stage": task.stage,
        "href": task.href,
        "count": count,
        "optional": task.optional,
    }


def progress(ctx) -> dict:
    phases = []
    completed = available = 0
    for phase in PHASES:
        tasks = [_task_payload(ctx, task) for task in phase.tasks]
        for spec, payload in zip(phase.tasks, tasks):
            if payload["status"] == "unavailable" or spec.optional:
                continue
            available += 1
            if payload["status"] == "complete":
                completed += 1
        phases.append({"key": phase.key, "title": phase.title, "description": phase.description, "tasks": tasks})
    percent = round(completed / available * 100) if available else 0
    return {
        "phases": phases,
        "progress": {"completed": completed, "available": available, "percent": percent},
        "banner_dismissed": bool(preferences.get_preference(ctx, preferences.SETUP_BANNER_DISMISSED, False)),
        "completed_at": iso(ctx.org.setup_completed_at),
    }


# --------------------------------------------------------------------------- writes


def set_banner_dismissed(ctx, dismissed: bool) -> bool:
    """Per-user banner state; ``dismiss`` and ``reopen`` both go through here."""
    preferences.set_preference(ctx, preferences.SETUP_BANNER_DISMISSED, bool(dismissed))
    return bool(dismissed)


def complete(ctx):
    """Mark setup complete for the whole chapter. Idempotent: a second call
    leaves the original timestamp and writes no audit row."""
    policy.authorize(ctx, "chapter.setup.manage")
    org = ctx.org
    if org.setup_completed_at is not None:
        return org
    before = audit_events.snapshot(org, ORG_SNAPSHOT)
    org.setup_completed_at = utcnow()
    audit_events.record(
        ctx,
        "organization.setup_completed",
        org,
        before=before,
        after=audit_events.snapshot(org, ORG_SNAPSHOT),
        summary="Marked Setup Center complete",
        progress=progress(ctx)["progress"],
    )
    db.session.commit()
    return org


def mark_guide_read(ctx):
    """Record that the officer guide was read (a chapter-wide setting)."""
    policy.authorize(ctx, "chapter.setup.manage")
    org = ctx.org
    if org.settings.get(GUIDE_READ_KEY) is True:
        return org
    before = audit_events.snapshot(org, ORG_SNAPSHOT)
    merged = dict(org.settings_json or {})
    merged[GUIDE_READ_KEY] = True
    org.settings_json = merged
    audit_events.record(
        ctx,
        "organization.updated",
        org,
        before=before,
        after=audit_events.snapshot(org, ORG_SNAPSHOT),
        summary="Marked the officer guide as read",
    )
    db.session.commit()
    return org
