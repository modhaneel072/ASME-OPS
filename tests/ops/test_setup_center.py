import pytest

from asme.extensions import db as _db
from asme.ops import policy
from asme.ops.models import Asset, AuditEvent, Category, Location, Membership, OpsProject, Organization, Team, UserPreference
from asme.ops.services import setup_center
from asme.services.errors import Forbidden

URL = "/api/v1/setup"

EXPECTED_LAYOUT = {
    "Build the Foundation": ["chapter_profile", "locations", "assets", "teams_users", "officer_guide"],
    "Organize Project Work": ["first_project", "categories", "parts", "procedure"],
    "Standardize Operations": ["maintenance_plan", "request_portal", "automation", "dashboard"],
}
UNAVAILABLE_STAGES = {"parts": 4, "procedure": 5, "maintenance_plan": 5, "request_portal": 3, "automation": 6, "dashboard": 7}
HREFS = {
    "chapter_profile": "/app/settings/chapter",
    "locations": "/app/locations",
    "assets": "/app/assets",
    "teams_users": "/app/teams-users",
    "officer_guide": "/app/setup",
    "first_project": "/app/projects",
    "categories": "/app/categories",
    "parts": "/app/parts",
}


def _tasks(payload) -> dict:
    return {task["key"]: task for phase in payload["phases"] for task in phase["tasks"]}


def test_fresh_chapter_progress_layout_and_percent(client, org, users, api_login):
    api_login(users["member"])  # any member may read
    response = client.get(URL)
    assert response.status_code == 200
    payload = response.get_json()["payload"]
    assert {phase["title"]: [t["key"] for t in phase["tasks"]] for phase in payload["phases"]} == EXPECTED_LAYOUT
    assert [phase["key"] for phase in payload["phases"]] == ["foundation", "project_work", "standardize"]
    tasks = _tasks(payload)
    for key, task in tasks.items():
        assert set(task) == {"key", "title", "description", "estimated_minutes", "status", "stage", "href", "count", "optional"}
        assert task["title"] and task["description"] and task["estimated_minutes"] > 0
    for key, stage in UNAVAILABLE_STAGES.items():
        assert tasks[key]["status"] == "unavailable" and tasks[key]["stage"] == stage and tasks[key]["count"] is None
    for key, href in HREFS.items():
        assert tasks[key]["href"] == href
    assert tasks["chapter_profile"] == {**tasks["chapter_profile"], "status": "incomplete", "stage": None, "count": None, "optional": False}
    assert tasks["locations"]["status"] == "incomplete" and tasks["locations"]["count"] == 0  # bootstrap "General" is the default
    assert tasks["assets"]["status"] == "incomplete" and tasks["assets"]["count"] == 0
    assert tasks["teams_users"]["status"] == "incomplete" and tasks["teams_users"]["count"] == 3  # 3 members but no team yet
    assert tasks["officer_guide"]["status"] == "incomplete" and tasks["officer_guide"]["optional"] is True
    assert tasks["first_project"]["status"] == "incomplete" and tasks["first_project"]["count"] == 0
    assert tasks["categories"]["status"] == "complete" and tasks["categories"]["count"] == 14  # seeded categories
    assert [k for k, t in tasks.items() if t["optional"]] == ["officer_guide"]
    assert payload["progress"] == {"completed": 1, "available": 6, "percent": 17}
    assert payload["banner_dismissed"] is False and payload["completed_at"] is None


def test_each_task_completes_from_live_data(client, org, users, api_login):
    api_login(users["admin"])

    def status(key):
        return _tasks(client.get(URL).get_json()["payload"])[key]

    # chapter profile needs timezone AND profile_completed
    org.settings_json = {"profile_completed": False}
    _db.session.commit()
    assert status("chapter_profile")["status"] == "incomplete"
    org.settings_json = {"profile_completed": True}
    org.timezone = ""
    _db.session.commit()
    assert status("chapter_profile")["status"] == "incomplete"
    org.timezone = "America/Chicago"
    _db.session.commit()
    assert status("chapter_profile")["status"] == "complete"

    # locations: default and inactive ones do not count
    _db.session.add(Location(organization_id=org.id, name="Closed", is_active=False))
    _db.session.commit()
    assert status("locations") == {**status("locations"), "status": "incomplete", "count": 0}
    _db.session.add(Location(organization_id=org.id, name="Robotics Lab"))
    _db.session.commit()
    assert status("locations") == {**status("locations"), "status": "complete", "count": 1}

    # assets: five active assets
    for index in range(4):
        _db.session.add(Asset(organization_id=org.id, name=f"Asset {index}"))
    _db.session.add(Asset(organization_id=org.id, name="Retired", is_active=False))
    _db.session.commit()
    assert status("assets") == {**status("assets"), "status": "incomplete", "count": 4}
    _db.session.add(Asset(organization_id=org.id, name="Asset 5"))
    _db.session.commit()
    assert status("assets") == {**status("assets"), "status": "complete", "count": 5}

    # teams_users: one active team and three active memberships
    inactive = Team(organization_id=org.id, name="Disbanded", is_active=False)
    _db.session.add(inactive)
    _db.session.commit()
    assert status("teams_users")["status"] == "incomplete"
    team = Team(organization_id=org.id, name="Electrical")
    _db.session.add(team)
    _db.session.commit()
    assert status("teams_users") == {**status("teams_users"), "status": "complete", "count": 3}
    membership = Membership.query.filter_by(organization_id=org.id, user_id=users["member"].id).one()
    membership.member_status = "suspended"
    _db.session.commit()
    assert status("teams_users") == {**status("teams_users"), "status": "incomplete", "count": 2}
    membership.member_status = "active"
    _db.session.commit()

    # first_project: archived projects do not count
    archived = OpsProject(organization_id=org.id, name="Old", code="OLD", status="archived")
    _db.session.add(archived)
    _db.session.commit()
    assert status("first_project") == {**status("first_project"), "status": "incomplete", "count": 0}
    _db.session.add(OpsProject(organization_id=org.id, name="Rover", code="CCR"))
    _db.session.commit()
    assert status("first_project") == {**status("first_project"), "status": "complete", "count": 1}

    # categories: only active ones count
    for category in Category.query.filter_by(organization_id=org.id).all():
        category.is_active = False
    _db.session.commit()
    assert status("categories") == {**status("categories"), "status": "incomplete", "count": 0}
    Category.query.filter_by(organization_id=org.id).first().is_active = True
    _db.session.commit()
    assert status("categories") == {**status("categories"), "status": "complete", "count": 1}

    payload = client.get(URL).get_json()["payload"]
    assert payload["progress"] == {"completed": 6, "available": 6, "percent": 100}
    assert _tasks(payload)["officer_guide"]["status"] == "incomplete"  # optional, not in the percentage


def test_banner_dismiss_and_reopen_are_per_user(client, org, users, api_login):
    api_login(users["member"])
    dismissed = client.post(URL + "/dismiss-banner", json={})
    assert dismissed.status_code == 200 and dismissed.get_json()["payload"]["banner_dismissed"] is True
    assert client.get(URL).get_json()["payload"]["banner_dismissed"] is True
    assert client.get("/api/v1/session").get_json()["payload"]["setup"]["banner_dismissed"] is True
    row = UserPreference.query.filter_by(organization_id=org.id, user_id=users["member"].id, key="setup_banner_dismissed").one()
    assert row.value_json is True

    api_login(users["lead"])
    assert client.get(URL).get_json()["payload"]["banner_dismissed"] is False

    api_login(users["member"])
    reopened = client.post(URL + "/reopen-banner", json={})
    assert reopened.status_code == 200 and reopened.get_json()["payload"]["banner_dismissed"] is False
    assert client.get(URL).get_json()["payload"]["banner_dismissed"] is False


def test_complete_requires_chapter_setup_manage_and_audits(client, org, users, requester, api_login):
    api_login(users["member"])
    denied = client.post(URL + "/complete", json={})
    assert denied.status_code == 403 and denied.get_json()["permission"] == ["chapter.setup.manage"]
    api_login(requester)
    assert client.post(URL + "/complete", json={}).status_code == 403
    with pytest.raises(Forbidden):
        setup_center.complete(policy.load_context(requester, org))

    api_login(users["admin"])
    done = client.post(URL + "/complete", json={})
    assert done.status_code == 200
    completed_at = done.get_json()["payload"]["completed_at"]
    assert completed_at is not None and completed_at.endswith("Z")
    assert org.setup_completed_at is not None
    assert client.get("/api/v1/session").get_json()["payload"]["setup"]["completed"] is True
    event = AuditEvent.query.filter_by(event_type="organization.setup_completed").one()
    assert event.entity_type == "organization" and event.entity_id == str(org.id) and event.actor_user_id == users["admin"].id
    assert event.before_json["setup_completed_at"] is None and event.after_json["setup_completed_at"] is not None
    assert event.metadata_json["progress"]["available"] == 6

    # idempotent: the timestamp is kept and no second audit row is written
    again = client.post(URL + "/complete", json={})
    assert again.status_code == 200 and again.get_json()["payload"]["completed_at"] == completed_at
    assert AuditEvent.query.filter_by(event_type="organization.setup_completed").count() == 1


def test_mark_guide_read_is_an_org_setting(client, org, users, api_login):
    api_login(users["member"])
    assert client.post(URL + "/mark-guide-read", json={}).status_code == 403

    api_login(users["admin"])
    response = client.post(URL + "/mark-guide-read", json={})
    assert response.status_code == 200
    assert _tasks(response.get_json()["payload"])["officer_guide"]["status"] == "complete"
    assert org.settings_json["officer_guide_read"] is True
    assert AuditEvent.query.filter_by(event_type="organization.updated").count() == 1
    # every member sees the org-wide flag
    api_login(users["lead"])
    assert _tasks(client.get(URL).get_json()["payload"])["officer_guide"]["status"] == "complete"
    # repeat calls are no-ops
    api_login(users["admin"])
    client.post(URL + "/mark-guide-read", json={})
    assert AuditEvent.query.filter_by(event_type="organization.updated").count() == 1


def test_counts_are_scoped_to_the_organization(client, org, users, api_login):
    other = Organization(name="Other", slug="other", settings_json={"profile_completed": True})
    _db.session.add(other)
    _db.session.flush()
    _db.session.add_all(
        [
            Location(organization_id=other.id, name="Elsewhere"),
            Team(organization_id=other.id, name="Foreign Team"),
            OpsProject(organization_id=other.id, name="Foreign", code="FRN"),
            *[Asset(organization_id=other.id, name=f"Foreign asset {i}") for i in range(5)],
        ]
    )
    _db.session.commit()
    api_login(users["admin"])
    tasks = _tasks(client.get(URL).get_json()["payload"])
    assert tasks["locations"]["count"] == 0 and tasks["assets"]["count"] == 0 and tasks["first_project"]["count"] == 0
    assert tasks["teams_users"]["status"] == "incomplete" and tasks["chapter_profile"]["status"] == "incomplete"
