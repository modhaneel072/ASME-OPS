"""The development seed dataset (``asme.ops.seeds``): builds through the
services, is idempotent, resets cleanly and refuses to run in production."""

from __future__ import annotations

from dataclasses import replace

import pytest
from sqlalchemy import func, select

from asme.config import settings
from asme.extensions import db as _db
from asme.models import Project as LegacyProject
from asme.models import ProjectMembership as LegacyProjectMembership
from asme.models import User
from asme.ops import bootstrap
from asme.ops.models import (
    Asset,
    AssetStatusHistory,
    AuditEvent,
    Category,
    Comment,
    Location,
    Membership,
    Notification,
    OpsProject,
    Team,
    WorkOrder,
    WorkOrderDependency,
    WorkOrderStatusHistory,
)
from asme.ops.services import comments as comments_service
from asme.ops.services import work_orders
from asme.ops import seeds

REQUIRED_STATUSES = {"open", "in_progress", "on_hold", "done", "canceled", "draft"}


def _org():
    return bootstrap.default_organization()


def _count(model, org, **filters):
    return model.query.filter_by(organization_id=org.id, **filters).count()


@pytest.fixture
def seeded(app, users):
    return seeds.seed_ops(echo=None)


# --------------------------------------------------------------------------- happy path


def test_seed_counts(seeded):
    org = _org()
    assert seeded["skipped"] is False
    assert seeded["projects"] == 3 == _count(OpsProject, org)
    assert seeded["teams"] == 9 == _count(Team, org)
    assert seeded["assets"] >= 18
    assert seeded["work_orders"] >= 40
    assert set(seeded["work_order_statuses"]) >= REQUIRED_STATUSES
    assert seeded["overdue_work_orders"] >= 6
    assert seeded["critical_work_orders"] >= 3
    assert seeded["audit_events"] > 100
    assert seeded["comments"] >= 4
    assert seeded["notifications"] > 0


def test_statuses_reached_through_services(seeded):
    org = _org()
    rows = WorkOrder.query.filter_by(organization_id=org.id).all()
    assert {row.status for row in rows} >= REQUIRED_STATUSES
    for row in rows:
        assert len(row.status_history) >= 1, row.title
        assert row.status_history[0].from_status is None
        assert row.status_history[-1].to_status == row.status
    done = [row for row in rows if row.status == "done"]
    assert all(row.completed_at is not None for row in done)
    assert any(row.time_entries for row in done)
    assert any(entry.type == "parts" and entry.vendor_id for row in done for entry in row.cost_entries)
    assert any(entry.type == "vendor" for row in done for entry in row.cost_entries)
    canceled = [row for row in rows if row.status == "canceled"]
    assert all(row.canceled_at is not None and row.status_history[-1].note for row in canceled)


def test_overdue_critical_and_safety(seeded):
    org = _org()
    rows = WorkOrder.query.filter_by(organization_id=org.id).all()
    overdue = [row for row in rows if row.is_overdue]
    assert len(overdue) >= 6
    critical = [row for row in rows if row.priority == "critical"]
    assert len(critical) >= 3
    safety = Category.query.filter_by(organization_id=org.id, name="Safety").one()
    dana = User.query.filter_by(email="dreyes@uiowa.edu").one()
    assert all(safety.id in row.category_ids and row.created_by_user_id == dana.id for row in critical)


def test_hierarchy_dependencies_and_auto_complete(seeded):
    org = _org()
    rows = WorkOrder.query.filter_by(organization_id=org.id).all()
    parents = {row.parent_work_order_id for row in rows if row.parent_work_order_id}
    assert len(parents) >= 5
    auto_parents = [row for row in rows if row.parent_completion_policy == "auto" and row.children]
    assert auto_parents
    for parent in auto_parents:
        assert parent.status == "done"
        assert parent.completion_note == work_orders.AUTO_COMPLETE_NOTE
        assert all(child.status == "done" for child in parent.children)
    deps = WorkOrderDependency.query.join(WorkOrder, WorkOrder.id == WorkOrderDependency.blocked_work_order_id).filter(
        WorkOrder.organization_id == org.id
    ).all()
    assert len(deps) >= 3
    assert any(dep.blocked.is_blocked for dep in deps)
    assert any(not dep.blocked.is_blocked for dep in deps)
    recurring = [row for row in rows if row.recurrence_json == {"every": "month"}]
    assert len(recurring) == 2 and all(row.work_type == "preventive" for row in recurring)


def test_assignees_watchers_and_related_assets(seeded):
    org = _org()
    rows = WorkOrder.query.filter_by(organization_id=org.id).all()
    assert any(row.assignee_user_ids for row in rows)
    assert any(row.assignee_team_ids for row in rows)
    assert any(row.watcher_user_ids for row in rows)
    assert any(link.relationship_type == "related" for row in rows for link in row.asset_links)
    # every top-level work order the seed authored is categorised; the follow-up
    # created through ``complete(follow_up=...)`` inherits none, by design
    top_level = [row for row in rows if row.parent_work_order_id is None and not (row.description or "").startswith("Follow-up to #")]
    assert top_level and all(row.category_links for row in top_level)


def test_people_teams_and_projects(seeded):
    org = _org()
    cfg = settings()
    by_email = {user.email: user for user in User.query.all()}
    priya = by_email["pnatarajan@uiowa.edu"]
    assert priya.username == "pnatarajan" and priya.role == "member"
    elena = by_email["eortiz@uiowa.edu"]
    assert elena.role == "team_leader"
    memberships = {m.user_id: m for m in Membership.query.filter_by(organization_id=org.id).all()}
    assert memberships[priya.id].role.system_key == "executive_officer"
    assert memberships[priya.id].title == "President"
    assert memberships[by_email["awhitfield@uiowa.edu"].id].role.system_key == "faculty_advisor"
    assert memberships[by_email["cmorgan@uiowa.edu"].id].role.system_key == "shop_operator"
    admin = by_email[cfg.default_admin_email]
    assert memberships[admin.id].role.system_key == "chapter_admin"
    accounts = {row["email"]: row for row in seeded["accounts"]}
    assert accounts["pnatarajan@uiowa.edu"]["password"] == cfg.default_user_password
    assert accounts[cfg.default_admin_email]["password"] == cfg.default_admin_password

    teams = {team.name: team for team in Team.query.filter_by(organization_id=org.id).all()}
    assert teams["Wheels and Mobility"].lead_user_ids == {elena.id}
    assert {by_email["achen@uiowa.edu"].id, by_email["lpatel@uiowa.edu"].id} <= teams["Wheels and Mobility"].member_user_ids

    projects = {project.code: project for project in OpsProject.query.filter_by(organization_id=org.id).all()}
    assert set(projects) == {"CCR", "OPS", "FES"}
    ccr = projects["CCR"]
    assert ccr.lead_user_id == by_email["mbell@uiowa.edu"].id
    assert ccr.faculty_advisor_user_id == by_email["awhitfield@uiowa.edu"].id
    assert ccr.competition == "Lunabotics 2027" and float(ccr.budget_amount) == 18500.0
    assert ccr.target_date.month == 5 and ccr.target_date.day == 15
    assert ccr.public_project_id == LegacyProject.query.filter_by(slug="rover").one().id
    assert LegacyProjectMembership.query.filter_by(project_id=ccr.public_project_id, left_at=None).count() >= 3
    assert len(ccr.milestones) == 6
    fes = projects["FES"]
    assert fes.visibility == "private"
    assert fes.member_user_ids == {priya.id, by_email["mjohnson@uiowa.edu"].id, admin.id}


def test_structure(seeded):
    org = _org()
    names = {row.name for row in Location.query.filter_by(organization_id=org.id).all()}
    assert {"General", "Engineering Student Center", "Robotics Lab", "Bench 1", "Bench 2", "Machine Shop", "Electronics Bench", "ASME Storage", "Test Field", "Trailer"} <= names
    assert Location.query.filter_by(organization_id=org.id, is_default=True).count() == 1
    assert _count(Category, org) == 14
    rover = Asset.query.filter_by(organization_id=org.id, code="CCR-ROVER").one()
    children = Asset.query.filter_by(parent_asset_id=rover.id).all()
    assert {child.name for child in children} == {"Chassis", "Mobility System", "Robotic Arm", "Electrical System", "Compute and Control"}
    mobility = next(child for child in children if child.name == "Mobility System")
    assert Asset.query.filter_by(parent_asset_id=mobility.id).count() == 4
    printer = Asset.query.filter_by(organization_id=org.id, name="3D Printer 02").one()
    assert printer.status == "offline_unplanned"
    history = AssetStatusHistory.query.filter_by(asset_id=printer.id).order_by(AssetStatusHistory.started_at).all()
    assert history[-1].downtime_reason == "Nozzle clog"


def test_comments_include_a_mention(seeded):
    org = _org()
    rows = Comment.query.filter_by(organization_id=org.id).all()
    mentioned = [row for row in rows if comments_service.mentioned_user_ids(row.body)]
    assert mentioned
    assert {row.entity_type for row in rows} >= {"work_order", "project"}
    assert Notification.query.filter_by(organization_id=org.id, type="work_order.mentioned").count() >= 1


# --------------------------------------------------------------------------- idempotency / reset


def _snapshot(org):
    return {
        "projects": _count(OpsProject, org),
        "teams": _count(Team, org),
        "assets": _count(Asset, org),
        "work_orders": _count(WorkOrder, org),
        "comments": _count(Comment, org),
        "audit": AuditEvent.query.filter_by(organization_id=org.id).count(),
        "users": User.query.count(),
        "memberships": _count(Membership, org),
    }


def test_second_run_is_skipped(seeded):
    org = _org()
    before = _snapshot(org)
    again = seeds.seed_ops(echo=None)
    assert again["skipped"] is True
    assert again["work_orders"] == before["work_orders"]
    assert _snapshot(org) == before


def test_reset_then_reseed(seeded):
    org = _org()
    before = _snapshot(org)
    first_numbers = sorted(row.number for row in WorkOrder.query.filter_by(organization_id=org.id).all())
    result = seeds.seed_ops(reset=True, echo=None)
    assert result["skipped"] is False
    after = _snapshot(org)
    assert after == before  # same shape, no duplicates
    assert sorted(row.number for row in WorkOrder.query.filter_by(organization_id=org.id).all()) == first_numbers
    # every work order still has real history after the second build
    counts = dict(
        _db.session.execute(
            select(WorkOrderStatusHistory.work_order_id, func.count(WorkOrderStatusHistory.id))
            .join(WorkOrder, WorkOrder.id == WorkOrderStatusHistory.work_order_id)
            .where(WorkOrder.organization_id == org.id)
            .group_by(WorkOrderStatusHistory.work_order_id)
        ).all()
    )
    assert len(counts) == after["work_orders"] and min(counts.values()) >= 1


def test_reset_keeps_org_roles_memberships_default_location_and_categories(seeded):
    org = _org()
    memberships = _count(Membership, org)
    seed_categories = len(bootstrap.SEED_CATEGORIES)
    seeds.reset_ops(org)
    assert _org().id == org.id
    assert _count(Membership, org) == memberships
    assert _count(Category, org) == seed_categories
    assert _count(Location, org) == 1 and Location.query.filter_by(organization_id=org.id).one().is_default
    assert _count(WorkOrder, org) == 0 == _count(Asset, org) == _count(Team, org) == _count(OpsProject, org)
    assert AuditEvent.query.filter_by(organization_id=org.id).count() == 0
    assert Notification.query.filter_by(organization_id=org.id).count() == 0
    assert bootstrap.role_by_key(org, "chapter_admin") is not None


# --------------------------------------------------------------------------- production guard


def test_refuses_in_production(app, users, monkeypatch):
    monkeypatch.setitem(app.config, "SETTINGS", replace(settings(), env="production"))
    with pytest.raises(RuntimeError):
        seeds.seed_ops(echo=None)
    assert OpsProject.query.count() == 0


def test_refuses_when_seed_not_allowed(app, users, monkeypatch):
    monkeypatch.setitem(app.config, "SETTINGS", replace(settings(), ops_seed_allowed=False))
    with pytest.raises(RuntimeError):
        seeds.seed_ops(reset=True, echo=None)
