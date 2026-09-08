from datetime import timedelta

from asme.ops.models import (
    Asset,
    Category,
    Location,
    OpsProject,
    Organization,
    Team,
    TeamMember,
    WorkOrder,
    WorkOrderAssignee,
    WorkOrderCategory,
    WorkOrderStatusHistory,
)
from asme.ops.types import utcnow


def test_ops_tables_are_part_of_metadata(app, db):
    names = set(db.metadata.tables)
    for expected in (
        "ops_organizations",
        "ops_memberships",
        "ops_roles",
        "ops_permissions",
        "ops_role_permissions",
        "ops_teams",
        "ops_locations",
        "ops_categories",
        "ops_assets",
        "ops_projects",
        "ops_milestones",
        "ops_work_orders",
        "ops_work_order_assignees",
        "ops_work_order_status_history",
        "ops_time_entries",
        "ops_cost_entries",
        "ops_comments",
        "ops_attachments",
        "ops_audit_events",
        "ops_saved_filters",
        "ops_notifications",
        "ops_sequences",
    ):
        assert expected in names, expected
    assert all(name.startswith("ops_") for name in names if name.startswith("ops_"))


def test_work_order_graph_round_trips(app, db, users):
    org = Organization(name="ASME Iowa", slug="uiowa-test")
    db.session.add(org)
    db.session.flush()

    lab = Location(organization_id=org.id, name="Robotics Lab")
    mech = Category(organization_id=org.id, name="Mechanical", color="#0878d1", icon="wrench")
    team = Team(organization_id=org.id, name="Wheels and Mobility")
    db.session.add_all([lab, mech, team])
    db.session.flush()
    team.members.append(TeamMember(user_id=users["lead"].id, is_lead=True))
    team.members.append(TeamMember(user_id=users["member"].id, is_lead=False))

    project = OpsProject(organization_id=org.id, name="Crater Cruncher Rover", code="CCR", lead_user_id=users["lead"].id)
    db.session.add(project)
    db.session.flush()
    rover = Asset(organization_id=org.id, name="Crater Cruncher Rover", code="CCR-ROVER", location_id=lab.id, project_id=project.id)
    db.session.add(rover)
    db.session.flush()
    wheel = Asset(organization_id=org.id, name="Front Left Wheel Module", parent_asset_id=rover.id, location_id=lab.id)
    db.session.add(wheel)
    db.session.flush()

    wo = WorkOrder(
        organization_id=org.id,
        number=1,
        title="Inspect wheel hub fasteners",
        priority="high",
        work_type="inspection",
        project_id=project.id,
        location_id=lab.id,
        primary_asset_id=wheel.id,
        team_id=team.id,
        due_at=utcnow() - timedelta(days=1),
        created_by_user_id=users["lead"].id,
    )
    db.session.add(wo)
    db.session.flush()
    wo.assignees.append(WorkOrderAssignee(user_id=users["member"].id))
    wo.assignees.append(WorkOrderAssignee(team_id=team.id))
    wo.category_links.append(WorkOrderCategory(category_id=mech.id))
    wo.status_history.append(WorkOrderStatusHistory(from_status=None, to_status="open", changed_by_user_id=users["lead"].id))
    db.session.commit()
    db.session.expire_all()

    loaded = db.session.get(WorkOrder, wo.id)
    assert loaded.assignee_user_ids == {users["member"].id}
    assert loaded.assignee_team_ids == {team.id}
    assert loaded.category_ids == [mech.id]
    assert loaded.is_open and loaded.is_overdue
    assert loaded.primary_asset.parent.id == rover.id
    assert loaded.team.lead_user_ids == {users["lead"].id}
    assert loaded.project.lead.id == users["lead"].id
    assert [h.to_status for h in loaded.status_history] == ["open"]
    assert loaded.created_by.id == users["lead"].id
