import pytest

from asme.extensions import db as _db
from asme.ops import policy
from asme.ops.models import Asset, Category, Location, Membership, OpsProject, Organization, ProjectMember, WorkOrder, WorkOrderAssignee
from asme.ops.services import search
from asme.ops.validation import ValidationErrors
from tests.ops.conftest import make_user

URL = "/api/v1/search"


def _project(org, name, code, visibility="chapter"):
    row = OpsProject(organization_id=org.id, name=name, code=code, visibility=visibility)
    _db.session.add(row)
    _db.session.flush()
    return row


def _wo(org, number, creator, title, **kw):
    row = WorkOrder(organization_id=org.id, number=number, title=title, created_by_user_id=creator.id, **kw)
    _db.session.add(row)
    _db.session.flush()
    return row


@pytest.fixture
def dataset(org, users):
    rover = _project(org, "Crater Cruncher Rover", "CCR")
    secret = _project(org, "Rover Sponsor Bid", "BID", visibility="private")
    _wo(org, 12, users["lead"], "Replace rover wheel bearing", project_id=rover.id, status="in_progress", priority="high")
    _wo(org, 13, users["lead"], "Rover sponsor deck", project_id=secret.id)
    _wo(org, 120, users["lead"], "Calibrate printer")
    _wo(org, 7, users["lead"], "Unrelated task")
    _db.session.add_all(
        [
            Asset(organization_id=org.id, name="Rover Chassis", code="CCR-CH", status="online"),
            Asset(organization_id=org.id, name="Sponsor Rover Mockup", code="BID-1", project_id=secret.id),
            Asset(organization_id=org.id, name="Old Rover Frame", code="OLD", is_active=False),
            Asset(organization_id=org.id, name="Oscilloscope", serial_number="ROVER-SN-9"),
            Location(organization_id=org.id, name="Rover Bay"),
            Location(organization_id=org.id, name="Closed Rover Bay", is_active=False),
            Category(organization_id=org.id, name="Rover Systems", color="#123456", icon="rocket"),
        ]
    )
    _db.session.commit()
    return {"rover": rover, "secret": secret}


def test_search_returns_every_group_with_visibility_applied(client, org, users, dataset, api_login):
    api_login(users["member"])
    response = client.get(URL + "?q=rover")
    assert response.status_code == 200, response.get_json()
    payload = response.get_json()["payload"]
    assert payload["query"] == "rover"
    results = payload["results"]
    assert set(results) == {"work_orders", "projects", "assets", "locations", "categories", "users"}
    assert results["work_orders"] == [
        {"id": results["work_orders"][0]["id"], "number": 12, "title": "Replace rover wheel bearing", "status": "in_progress", "priority": "high"}
    ]
    assert [p["code"] for p in results["projects"]] == ["CCR"]
    assert results["projects"][0] == {"id": str(dataset["rover"].id), "name": "Crater Cruncher Rover", "code": "CCR", "visibility": "chapter"}
    assert [a["name"] for a in results["assets"]] == ["Oscilloscope", "Rover Chassis"]
    assert results["assets"][1]["code"] == "CCR-CH" and results["assets"][1]["status"] == "online"
    assert results["locations"] == [{"id": results["locations"][0]["id"], "name": "Rover Bay"}]
    assert results["categories"] == [{"id": results["categories"][0]["id"], "name": "Rover Systems", "color": "#123456", "icon": "rocket"}]
    assert results["users"] == []


def test_private_project_content_appears_for_members_and_read_private_holders(client, org, users, dataset, api_login):
    dataset["secret"].members.append(ProjectMember(user_id=users["member"].id))
    _db.session.commit()
    api_login(users["member"])
    results = client.get(URL + "?q=rover").get_json()["payload"]["results"]
    assert sorted(p["code"] for p in results["projects"]) == ["BID", "CCR"]
    assert sorted(w["number"] for w in results["work_orders"]) == [12, 13]
    assert "Sponsor Rover Mockup" in [a["name"] for a in results["assets"]]

    advisor = make_user("Dr. Rover Advisor", "advisor@uiowa.edu", ops_role="faculty_advisor", org=org)
    api_login(advisor)
    results = client.get(URL + "?q=rover").get_json()["payload"]["results"]
    assert sorted(p["code"] for p in results["projects"]) == ["BID", "CCR"]
    assert sorted(w["number"] for w in results["work_orders"]) == [12, 13]


def test_numeric_query_matches_work_order_number(client, org, users, dataset, api_login):
    api_login(users["member"])
    results = client.get(URL + "?q=12").get_json()["payload"]["results"]
    assert [w["number"] for w in results["work_orders"]] == [12]
    results = client.get(URL + "?q=%2312").get_json()["payload"]["results"]
    assert [w["number"] for w in results["work_orders"]] == [12]
    results = client.get(URL + "?q=120").get_json()["payload"]["results"]
    assert [w["number"] for w in results["work_orders"]] == [120]


def test_users_group_needs_team_or_user_read(client, org, users, dataset, api_login):
    make_user("Rover Fan", "fan@uiowa.edu", ops_role="full_member", org=org)
    suspended = make_user("Rover Ghost", "ghost@uiowa.edu", ops_role="full_member", org=org)
    Membership.query.filter_by(user_id=suspended.id).one().member_status = "suspended"
    _db.session.commit()

    api_login(users["member"])  # full_member holds team.read
    results = client.get(URL + "?q=rover").get_json()["payload"]["results"]
    assert [u["email"] for u in results["users"]] == ["fan@uiowa.edu"]
    assert results["users"][0] == {"id": results["users"][0]["id"], "name": "Rover Fan", "email": "fan@uiowa.edu", "avatar_url": None}

    operator = make_user("Op Erator", "op@uiowa.edu", ops_role="shop_operator", org=org)
    api_login(operator)
    results = client.get(URL + "?q=rover").get_json()["payload"]["results"]
    assert results["users"] == [] and results["categories"] == []
    assert [a["name"] for a in results["assets"]] == ["Oscilloscope", "Rover Chassis"]
    assert results["work_orders"] == []  # read_assigned only, nothing assigned


def test_read_assigned_role_sees_only_assigned_work(client, org, users, dataset, api_login):
    operator = make_user("Op Erator", "op@uiowa.edu", ops_role="shop_operator", org=org)
    wo = WorkOrder.query.filter_by(number=12).one()
    wo.assignees.append(WorkOrderAssignee(user_id=operator.id))
    _db.session.commit()
    api_login(operator)
    results = client.get(URL + "?q=rover").get_json()["payload"]["results"]
    assert [w["number"] for w in results["work_orders"]] == [12]


def test_requester_sees_projects_only(client, org, requester, dataset, api_login):
    api_login(requester)
    results = client.get(URL + "?q=rover").get_json()["payload"]["results"]
    assert [p["code"] for p in results["projects"]] == ["CCR"]
    assert results["work_orders"] == [] and results["assets"] == [] and results["locations"] == []
    assert results["categories"] == [] and results["users"] == []


def test_query_validation_and_limit(client, org, users, dataset, api_login):
    api_login(users["member"])
    short = client.get(URL + "?q=r")
    assert short.status_code == 400 and set(short.get_json()["errors"]) == {"q"}
    blank = client.get(URL)
    assert blank.status_code == 400 and set(blank.get_json()["errors"]) == {"q"}

    for number in range(200, 230):
        _wo(org, number, users["lead"], f"Rover chore {number}")
    _db.session.commit()
    default = client.get(URL + "?q=rover").get_json()["payload"]["results"]["work_orders"]
    assert len(default) == 8 and default[0]["number"] == 229
    capped = client.get(URL + "?q=rover&limit=500").get_json()["payload"]["results"]["work_orders"]
    assert len(capped) == 20
    small = client.get(URL + "?q=rover&limit=2").get_json()["payload"]["results"]["work_orders"]
    assert [w["number"] for w in small] == [229, 228]
    nonsense = client.get(URL + "?q=rover&limit=abc").get_json()["payload"]["results"]["work_orders"]
    assert len(nonsense) == 8

    ctx = policy.load_context(users["member"], org)
    with pytest.raises(ValidationErrors) as excinfo:
        search.search(ctx, " ")
    assert set(excinfo.value.errors) == {"q"}


def test_like_wildcards_are_escaped_and_other_orgs_are_hidden(client, org, users, dataset, api_login):
    other = Organization(name="Other", slug="other")
    _db.session.add(other)
    _db.session.flush()
    _db.session.add_all(
        [
            OpsProject(organization_id=other.id, name="Rover Elsewhere", code="ELSE"),
            Location(organization_id=other.id, name="Rover Garage"),
            WorkOrder(organization_id=other.id, number=12, title="Rover foreign", created_by_user_id=users["admin"].id),
        ]
    )
    _db.session.commit()
    api_login(users["admin"])
    results = client.get(URL + "?q=rover").get_json()["payload"]["results"]
    assert "ELSE" not in [p["code"] for p in results["projects"]]
    assert "Rover Garage" not in [l["name"] for l in results["locations"]]
    assert all(w["title"] != "Rover foreign" for w in results["work_orders"])

    wildcard = client.get(URL + "?q=%25%25").get_json()["payload"]["results"]
    assert all(len(group) == 0 for group in wildcard.values())
