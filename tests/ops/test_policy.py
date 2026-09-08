import pytest
from flask import Blueprint, jsonify

from asme.extensions import db as _db
from asme.ops import bootstrap, policy
from asme.ops.models import OpsProject, ProjectMember, Team, TeamMember, WorkOrder, WorkOrderAssignee
from asme.services.errors import Forbidden, NotFound
from tests.ops.conftest import make_user


def _project(org, name, code, visibility="chapter", **kw):
    row = OpsProject(organization_id=org.id, name=name, code=code, visibility=visibility, **kw)
    _db.session.add(row)
    _db.session.flush()
    return row


def _team(org, name, lead=None, members=()):
    team = Team(organization_id=org.id, name=name)
    _db.session.add(team)
    _db.session.flush()
    if lead:
        team.members.append(TeamMember(user_id=lead.id, is_lead=True))
    for user in members:
        team.members.append(TeamMember(user_id=user.id, is_lead=False))
    _db.session.flush()
    return team


def _wo(org, number, creator, **kw):
    row = WorkOrder(organization_id=org.id, number=number, title=f"WO {number}", created_by_user_id=creator.id, **kw)
    _db.session.add(row)
    _db.session.flush()
    return row


def test_chapter_scope_allows_everything_for_admin(ctx_admin, org, users):
    project = _project(org, "Private", "PRV", visibility="private")
    assert policy.can(ctx_admin, "project.manage", project)
    assert policy.can(ctx_admin, "role.manage")
    assert ctx_admin.is_chapter_admin


def test_member_edit_own_only(ctx_member, ctx_lead, org, users):
    mine = _wo(org, 1, users["member"])
    theirs = _wo(org, 2, users["lead"])
    assert policy.can(ctx_member, "work_order.edit", mine)
    assert not policy.can(ctx_member, "work_order.edit", theirs)
    with pytest.raises(Forbidden):
        policy.authorize(ctx_member, "work_order.edit", theirs)


def test_assigned_scope_via_user_and_team(org, users):
    team = _team(org, "Electrical", lead=users["lead"], members=[users["member"]])
    direct = _wo(org, 1, users["lead"])
    direct.assignees.append(WorkOrderAssignee(user_id=users["member"].id))
    via_team = _wo(org, 2, users["lead"])
    via_team.assignees.append(WorkOrderAssignee(team_id=team.id))
    unrelated = _wo(org, 3, users["lead"])
    _db.session.flush()

    ctx = policy.load_context(users["member"], org)
    assert policy.can(ctx, "work_order.complete", direct)
    assert policy.can(ctx, "work_order.complete", via_team)
    assert not policy.can(ctx, "work_order.complete", unrelated)


def test_team_scope_requires_lead_for_manage_but_member_for_read(org, users):
    led = _team(org, "Arm", lead=users["lead"])
    member_of = _team(org, "Wheels", members=[users["lead"]])
    other = _team(org, "Software")
    ctx = policy.load_context(users["lead"], org)
    assert ctx.lead_team_ids == {led.id} and ctx.team_ids == {led.id, member_of.id}

    wo_led = _wo(org, 1, users["member"], team_id=led.id)
    wo_member = _wo(org, 2, users["member"], team_id=member_of.id)
    wo_other = _wo(org, 3, users["member"], team_id=other.id)
    assert policy.can(ctx, "work_order.assign", wo_led)
    assert not policy.can(ctx, "work_order.assign", wo_member)
    assert not policy.can(ctx, "work_order.assign", wo_other)
    assert policy.can(ctx, "team.manage", led)
    assert not policy.can(ctx, "team.manage", member_of)
    # team_lead holds team.read at chapter scope anyway
    assert policy.can(ctx, "team.read", other)


def test_project_scope_for_project_lead(org, users):
    lead = make_user("Pat Lead", "pat@uiowa.edu", ops_role="project_lead", org=org)
    mine = _project(org, "Rover", "CCR", lead_user_id=lead.id)
    mine.members.append(ProjectMember(user_id=lead.id, project_role="lead"))
    other = _project(org, "Showcase", "FES")
    _db.session.flush()
    ctx = policy.load_context(lead, org)
    assert policy.can(ctx, "project.manage", mine)
    assert not policy.can(ctx, "project.manage", other)
    wo_mine = _wo(org, 1, users["member"], project_id=mine.id)
    wo_other = _wo(org, 2, users["member"], project_id=other.id)
    assert policy.can(ctx, "work_order.assign", wo_mine)
    assert not policy.can(ctx, "work_order.assign", wo_other)


def test_private_project_visibility(org, users):
    public = _project(org, "Rover", "CCR")
    secret = _project(org, "Sponsor Bid", "BID", visibility="private")
    joined = _project(org, "Showcase", "FES", visibility="private")
    joined.members.append(ProjectMember(user_id=users["member"].id))
    _db.session.flush()
    for number, project in enumerate((public, secret, joined), start=1):
        _wo(org, number, users["lead"], project_id=project.id)
    _wo(org, 9, users["lead"])  # no project

    ctx = policy.load_context(users["member"], org)
    assert policy.can_read_project(ctx, public)
    assert not policy.can_read_project(ctx, secret)
    assert policy.can_read_project(ctx, joined)

    visible = _db.session.query(WorkOrder.number).filter(policy.visible_project_filter(ctx, WorkOrder.project_id)).all()
    assert sorted(n for (n,) in visible) == [1, 3, 9]

    advisor = make_user("Dr. Advisor", "advisor@uiowa.edu", ops_role="faculty_advisor", org=org)
    ctx_adv = policy.load_context(advisor, org)
    assert policy.can_read_project(ctx_adv, secret)
    visible = _db.session.query(WorkOrder.number).filter(policy.visible_project_filter(ctx_adv, WorkOrder.project_id)).all()
    assert sorted(n for (n,) in visible) == [1, 2, 3, 9]


def test_get_or_404_hides_other_organizations(ctx_admin, org, users, db):
    from asme.ops.models import Organization

    other = Organization(name="Other", slug="other")
    db.session.add(other)
    db.session.flush()
    foreign = OpsProject(organization_id=other.id, name="Foreign", code="FRN")
    db.session.add(foreign)
    db.session.flush()
    with pytest.raises(NotFound):
        policy.get_or_404(ctx_admin, OpsProject, foreign.id)
    with pytest.raises(NotFound):
        policy.authorize(ctx_admin, "project.manage", foreign)
    local = _project(org, "Local", "LOC")
    assert policy.get_or_404(ctx_admin, OpsProject, local.id) is local


def test_requester_lacks_work_order_keys(ctx_requester):
    assert ctx_requester.has("request.submit")
    assert not ctx_requester.has("work_order.create")
    assert not policy.can(ctx_requester, "work_order.read_all")
    assert ctx_requester.permission_map()["request.submit"] == ["chapter"]


def test_require_permission_decorator(app, client, org, users, requester, login_as):
    bp = Blueprint("policy_probe", __name__)

    @bp.get("/api/v1/_probe")
    @policy.require_permission("work_order.create")
    def probe():
        return jsonify({"ok": True, "user": policy.current_context().user.id})

    app.register_blueprint(bp)

    anonymous = client.get("/api/v1/_probe")
    assert anonymous.status_code == 401 and anonymous.get_json()["code"] == "login_required"

    login_as(users["member"])
    allowed = client.get("/api/v1/_probe")
    assert allowed.status_code == 200 and allowed.get_json()["user"] == users["member"].id
    client.post("/logout")

    login_as(requester)
    denied = client.get("/api/v1/_probe")
    assert denied.status_code == 403 and denied.get_json()["code"] == "forbidden"
    assert denied.get_json()["permission"] == ["work_order.create"]
    client.post("/logout")

    outsider = make_user("Out Sider", "out@uiowa.edu")  # legacy user, no membership yet
    assert bootstrap.membership_for(outsider, org) is None
    login_as(outsider)
    # sign-in creates a membership automatically, so the user is now a full member
    joined = client.get("/api/v1/_probe")
    assert joined.status_code == 200


def test_sign_in_creates_membership(app, client, org, login_as):
    user = make_user("New Person", "new@uiowa.edu", legacy_role="team_leader")
    assert bootstrap.membership_for(user, org) is None
    login_as(user)
    membership = bootstrap.membership_for(user, org)
    assert membership is not None and membership.role.system_key == "team_lead"
