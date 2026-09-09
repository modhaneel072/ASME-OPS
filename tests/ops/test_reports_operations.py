from datetime import date, datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from asme.extensions import db as _db
from asme.ops import policy
from asme.ops.models import CostEntry, OpsProject, Organization, Team, TimeEntry, WorkOrder, WorkOrderAssignee
from asme.ops.services import dashboard
from asme.ops.validation import ValidationErrors
from asme.services.errors import Forbidden, NotFound
from tests.ops.conftest import make_user

URL = "/api/v1/reports/operations"
WINDOW = "range=custom&start=2026-08-03&end=2026-08-16"


def _utc(year, month, day, hour=0, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def _chicago(year, month, day, hour=0, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=ZoneInfo("America/Chicago"))


def _wo(org, number, creator, created, **kw):
    kw.setdefault("title", f"WO {number}")
    row = WorkOrder(organization_id=org.id, number=number, created_by_user_id=creator.id, created_at=created, updated_at=created, **kw)
    _db.session.add(row)
    _db.session.flush()
    return row


@pytest.fixture
def dataset(org, users):
    admin, lead, member = users["admin"], users["lead"], users["member"]
    rover = OpsProject(organization_id=org.id, name="Rover", code="CCR")
    secret = OpsProject(organization_id=org.id, name="Sponsor Bid", code="BID", visibility="private")
    team_a = Team(organization_id=org.id, name="Arm")
    team_b = Team(organization_id=org.id, name="Wheels")
    _db.session.add_all([rover, secret, team_a, team_b])
    _db.session.flush()

    wo1 = _wo(org, 1, lead, _utc(2026, 8, 4, 10), status="done", completed_at=_utc(2026, 8, 5, 10), due_at=_utc(2026, 8, 6), priority="high", work_type="reactive", team_id=team_a.id, project_id=rover.id)
    wo2 = _wo(org, 2, lead, _utc(2026, 8, 10, 10), status="done", completed_at=_utc(2026, 8, 12, 22), due_at=_utc(2026, 8, 11), priority="medium", work_type="preventive", team_id=team_b.id, recurrence_json={"freq": "weekly"})
    _wo(org, 3, lead, _utc(2026, 8, 1, 10), status="done", completed_at=_utc(2026, 8, 14, 10), priority="none", work_type="reactive")
    wo4 = _wo(org, 4, lead, _utc(2026, 8, 8, 10), status="open", due_at=_utc(2026, 8, 9), priority="critical", work_type="project", team_id=team_a.id, project_id=rover.id)
    wo5 = _wo(org, 5, lead, _utc(2026, 7, 1, 10), status="in_progress", priority="low", work_type="reactive", team_id=team_b.id)
    _wo(org, 6, lead, _utc(2026, 8, 15, 10), status="canceled", canceled_at=_utc(2026, 8, 15, 12), priority="none", work_type="event")
    _wo(org, 7, lead, _utc(2026, 6, 1, 10), status="done", completed_at=_utc(2026, 7, 1, 10), due_at=_utc(2026, 7, 2), priority="high", work_type="safety")
    _wo(org, 8, lead, _chicago(2026, 8, 16, 23, 30), status="on_hold", priority="medium", work_type="inspection")
    _wo(org, 9, lead, _chicago(2026, 8, 17, 0, 30), status="open", due_at=_utc(2026, 8, 18), priority="none", work_type="reactive", team_id=team_a.id)
    wo10 = _wo(org, 10, admin, _utc(2026, 8, 5, 10), status="open", priority="high", work_type="safety", project_id=secret.id)
    _wo(org, 11, lead, _utc(2026, 8, 6, 10), status="done", completed_at=_utc(2026, 8, 20, 10), due_at=_utc(2026, 8, 19), priority="low", work_type="documentation")

    wo4.assignees.append(WorkOrderAssignee(user_id=member.id))
    wo5.assignees.append(WorkOrderAssignee(user_id=lead.id))
    wo5.assignees.append(WorkOrderAssignee(user_id=member.id))
    wo5.assignees.append(WorkOrderAssignee(team_id=team_b.id))

    _db.session.add_all(
        [
            TimeEntry(organization_id=org.id, work_order_id=wo1.id, user_id=lead.id, minutes=90, created_at=_utc(2026, 8, 5, 9)),
            TimeEntry(organization_id=org.id, work_order_id=wo5.id, user_id=member.id, minutes=30, created_at=_utc(2026, 8, 11, 9)),
            TimeEntry(organization_id=org.id, work_order_id=wo1.id, user_id=lead.id, minutes=600, created_at=_utc(2026, 8, 20, 9)),
            TimeEntry(organization_id=org.id, work_order_id=wo10.id, user_id=admin.id, minutes=60, created_at=_utc(2026, 8, 6, 9)),
            CostEntry(organization_id=org.id, work_order_id=wo1.id, type="parts", amount=Decimal("25.50"), created_at=_utc(2026, 8, 5, 9)),
            CostEntry(organization_id=org.id, work_order_id=wo2.id, type="labor", amount=Decimal("10.00"), created_at=_utc(2026, 8, 12, 9)),
            CostEntry(organization_id=org.id, work_order_id=wo4.id, type="other", amount=Decimal("4.25"), created_at=_utc(2026, 8, 9, 9)),
            CostEntry(organization_id=org.id, work_order_id=wo1.id, type="parts", amount=Decimal("100.00"), created_at=_utc(2026, 8, 20, 9)),
        ]
    )

    other = Organization(name="Other", slug="other")
    _db.session.add(other)
    _db.session.flush()
    _db.session.add(WorkOrder(organization_id=other.id, number=1, title="Foreign", created_by_user_id=admin.id, created_at=_utc(2026, 8, 4, 10), status="open", due_at=_utc(2026, 8, 5)))
    _db.session.commit()
    return {"rover": rover, "secret": secret, "team_a": team_a, "team_b": team_b, "other": other}


def _counts(rows, key):
    return {row[key]: row["count"] for row in rows}


def test_member_report_numbers_for_a_custom_window(client, org, users, dataset, api_login):
    api_login(users["member"])
    response = client.get(f"{URL}?{WINDOW}")
    assert response.status_code == 200, response.get_json()
    report = response.get_json()["payload"]
    assert set(report) == {
        "range", "created_vs_completed", "by_work_type", "repeating_vs_non", "status_distribution", "priority_distribution",
        "on_time_completion_rate", "overdue_open", "avg_completion_hours", "workload_by_team", "workload_by_user",
        "hours_logged", "parts_cost", "other_cost", "totals",
    }
    assert report["range"] == {"key": "custom", "start": "2026-08-03", "end": "2026-08-16", "timezone": "America/Chicago"}
    assert report["created_vs_completed"] == [
        {"week_start": "2026-08-03", "created": 3, "completed": 1},
        {"week_start": "2026-08-10", "created": 3, "completed": 2},
    ]
    assert report["totals"] == {"created": 6, "completed": 3, "open": 4}
    assert _counts(report["status_distribution"], "status") == {"draft": 0, "open": 1, "in_progress": 1, "on_hold": 1, "done": 3, "canceled": 1, "skipped": 0}
    assert _counts(report["priority_distribution"], "priority") == {"none": 1, "low": 2, "medium": 2, "high": 1, "critical": 1}
    assert _counts(report["by_work_type"], "work_type") == {
        "reactive": 2, "preventive": 1, "project": 1, "event": 1, "inspection": 1, "safety": 0, "procurement": 0, "documentation": 1,
    }
    assert [row["status"] for row in report["status_distribution"]] == ["draft", "open", "in_progress", "on_hold", "done", "canceled", "skipped"]
    assert report["repeating_vs_non"] == {"repeating": 1, "non_repeating": 6}
    assert report["on_time_completion_rate"] == 0.5
    assert report["overdue_open"] == 2
    assert report["avg_completion_hours"] == 132.0
    assert report["hours_logged"] == 2.0
    assert report["parts_cost"] == 25.5 and report["other_cost"] == 14.25
    assert report["workload_by_team"] == [
        {"team": {"id": str(dataset["team_a"].id), "name": "Arm"}, "open": 2, "in_progress": 0},
        {"team": {"id": str(dataset["team_b"].id), "name": "Wheels"}, "open": 0, "in_progress": 1},
    ]
    assert [(row["user"]["id"], row["open"], row["in_progress"]) for row in report["workload_by_user"]] == [
        (users["member"].id, 1, 1),
        (users["lead"].id, 0, 1),
    ]
    assert report["workload_by_user"][0]["user"]["name"] == "Mo Member"


def test_private_project_work_counts_only_for_those_who_can_read_it(client, org, users, dataset, api_login):
    api_login(users["admin"])
    report = client.get(f"{URL}?{WINDOW}").get_json()["payload"]
    assert report["totals"] == {"created": 7, "completed": 3, "open": 5}
    assert _counts(report["status_distribution"], "status")["open"] == 2
    assert _counts(report["by_work_type"], "work_type")["safety"] == 1
    assert report["hours_logged"] == 3.0
    assert report["repeating_vs_non"] == {"repeating": 1, "non_repeating": 7}
    assert report["workload_by_team"][-1] == {"team": None, "open": 1, "in_progress": 0}  # WO 10 has no team


def test_project_and_team_filters_narrow_the_base_set(client, org, users, dataset, api_login):
    api_login(users["member"])
    by_project = client.get(f"{URL}?{WINDOW}&filter[project]={dataset['rover'].id}").get_json()["payload"]
    assert by_project["totals"] == {"created": 2, "completed": 1, "open": 1}
    assert by_project["on_time_completion_rate"] == 1.0 and by_project["avg_completion_hours"] == 24.0
    assert by_project["parts_cost"] == 25.5 and by_project["other_cost"] == 4.25 and by_project["hours_logged"] == 1.5
    assert by_project["overdue_open"] == 1

    by_team = client.get(f"{URL}?{WINDOW}&filter[team]={dataset['team_a'].id}").get_json()["payload"]
    assert by_team["totals"] == {"created": 2, "completed": 1, "open": 2}
    assert by_team["workload_by_team"] == [{"team": {"id": str(dataset["team_a"].id), "name": "Arm"}, "open": 2, "in_progress": 0}]

    empty = client.get(f"{URL}?{WINDOW}&filter[team]={dataset['team_b'].id}&filter[project]={dataset['rover'].id}").get_json()["payload"]
    assert empty["totals"] == {"created": 0, "completed": 0, "open": 0}
    assert empty["on_time_completion_rate"] is None and empty["avg_completion_hours"] is None
    assert empty["hours_logged"] == 0.0 and empty["parts_cost"] == 0.0 and empty["other_cost"] == 0.0
    assert empty["workload_by_team"] == [] and empty["workload_by_user"] == []
    assert empty["created_vs_completed"] == [
        {"week_start": "2026-08-03", "created": 0, "completed": 0},
        {"week_start": "2026-08-10", "created": 0, "completed": 0},
    ]

    unknown = client.get(f"{URL}?{WINDOW}&filter[location]=x")
    assert unknown.status_code == 400 and unknown.get_json()["code"] == "bad_filter"
    bad_id = client.get(f"{URL}?{WINDOW}&filter[project]=nope")
    assert bad_id.status_code == 400 and set(bad_id.get_json()["errors"]) == {"project"}


def test_cross_organization_ids_are_404(client, org, users, dataset, api_login):
    foreign_project = OpsProject(organization_id=dataset["other"].id, name="Foreign", code="FRN")
    foreign_team = Team(organization_id=dataset["other"].id, name="Foreign Team")
    _db.session.add_all([foreign_project, foreign_team])
    _db.session.commit()
    api_login(users["admin"])
    assert client.get(f"{URL}?{WINDOW}&filter[project]={foreign_project.id}").status_code == 404
    assert client.get(f"{URL}?{WINDOW}&filter[team]={foreign_team.id}").status_code == 404
    ctx = policy.load_context(users["admin"], org)
    with pytest.raises(NotFound):
        dashboard.operations_report(ctx, {"range": "custom", "start": "2026-08-03", "end": "2026-08-16", "project": str(foreign_project.id)})
    # foreign-organization work orders never leak into the totals
    report = client.get(f"{URL}?range=custom&start=2026-08-04&end=2026-08-04").get_json()["payload"]
    assert report["totals"]["created"] == 1  # WO 1 only


def test_report_requires_report_view(client, org, users, requester, dataset, api_login):
    api_login(requester)
    denied = client.get(f"{URL}?{WINDOW}")
    assert denied.status_code == 403 and denied.get_json()["permission"] == ["report.view"]
    with pytest.raises(Forbidden):
        dashboard.operations_report(policy.load_context(requester, org), {"range": "7d"})

    guest = make_user("Gus Guest", "gus@uiowa.edu", ops_role="sponsor_guest", org=org)
    api_login(guest)  # report.view without work_order.read_* -> empty base set, still 200
    report = client.get(f"{URL}?{WINDOW}").get_json()["payload"]
    assert report["totals"] == {"created": 0, "completed": 0, "open": 0}


def test_range_validation(client, org, users, dataset, api_login):
    api_login(users["member"])
    bad_key = client.get(f"{URL}?range=fortnight")
    assert bad_key.status_code == 400 and set(bad_key.get_json()["errors"]) == {"range"}
    missing = client.get(f"{URL}?range=custom")
    assert missing.status_code == 400 and set(missing.get_json()["errors"]) == {"start", "end"}
    malformed = client.get(f"{URL}?range=custom&start=08/03/2026&end=soon")
    assert malformed.status_code == 400 and set(malformed.get_json()["errors"]) == {"start", "end"}
    reversed_ = client.get(f"{URL}?range=custom&start=2026-08-16&end=2026-08-03")
    assert reversed_.status_code == 400 and set(reversed_.get_json()["errors"]) == {"end"}
    too_long = client.get(f"{URL}?range=custom&start=2025-01-01&end=2026-01-02")
    assert too_long.status_code == 400 and set(too_long.get_json()["errors"]) == {"end"}
    longest = client.get(f"{URL}?range=custom&start=2025-01-01&end=2026-01-01")  # exactly 366 days
    assert longest.status_code == 200 and longest.get_json()["payload"]["range"]["start"] == "2025-01-01"
    with pytest.raises(ValidationErrors) as excinfo:
        dashboard.resolve_range(org, {"range": "custom", "start": date(2026, 8, 3)})
    assert set(excinfo.value.errors) == {"end"}


def test_rolling_and_semester_windows(client, org, users, dataset, api_login):
    tz = ZoneInfo("America/Chicago")
    today = date(2026, 9, 8)
    assert dashboard.resolve_range(org, {"range": "7d"}, today=today)["start"] == date(2026, 9, 2)
    assert dashboard.resolve_range(org, {"range": "30d"}, today=today)["start"] == date(2026, 8, 10)
    assert dashboard.resolve_range(org, {"range": "90d"}, today=today)["start"] == date(2026, 6, 11)
    assert dashboard.resolve_range(org, {}, today=today)["key"] == "30d"
    assert dashboard.resolve_range(org, {"range": "semester"}, today=today) == {"key": "semester", "start": date(2026, 8, 15), "end": today, "tz": tz}

    assert dashboard.semester_start(date(2026, 8, 15)) == date(2026, 8, 15)
    assert dashboard.semester_start(date(2026, 8, 14)) == date(2026, 1, 10)
    assert dashboard.semester_start(date(2026, 1, 10)) == date(2026, 1, 10)
    assert dashboard.semester_start(date(2026, 1, 9)) == date(2025, 8, 15)
    assert dashboard.semester_start(date(2026, 1, 9), academic_year_start_month=1) == date(2025, 8, 15)
    assert dashboard.semester_start(date(2026, 9, 8), academic_year_start_month=1) == date(2026, 8, 15)

    api_login(users["member"])
    live_today = datetime.now(tz).date()
    for key in ("7d", "30d", "90d", "semester"):
        payload = client.get(f"{URL}?range={key}").get_json()["payload"]
        expected = dashboard.resolve_range(org, {"range": key}, today=live_today)
        assert payload["range"] == {"key": key, "start": expected["start"].isoformat(), "end": live_today.isoformat(), "timezone": "America/Chicago"}
        assert payload["created_vs_completed"][0]["week_start"] == dashboard.week_start(expected["start"]).isoformat()
        assert all(date.fromisoformat(row["week_start"]).weekday() == 0 for row in payload["created_vs_completed"])
    default = client.get(URL).get_json()["payload"]
    assert default["range"]["key"] == "30d"


def test_window_edges_follow_the_organization_timezone(client, org, users, dataset, api_login):
    start_utc, end_utc = dashboard.window_bounds(date(2026, 8, 3), date(2026, 8, 16), ZoneInfo("America/Chicago"))
    assert start_utc == _utc(2026, 8, 3, 5) and end_utc == _utc(2026, 8, 17, 5)

    api_login(users["member"])
    last_day = client.get(f"{URL}?range=custom&start=2026-08-16&end=2026-08-16").get_json()["payload"]
    assert last_day["totals"]["created"] == 1  # WO 8 at 23:30 local; WO 9 at 00:30 the next day is excluded
    assert _counts(last_day["status_distribution"], "status")["on_hold"] == 1
    next_day = client.get(f"{URL}?range=custom&start=2026-08-17&end=2026-08-17").get_json()["payload"]
    assert next_day["totals"]["created"] == 1  # WO 9

    org.timezone = "UTC"
    _db.session.commit()
    utc_last_day = client.get(f"{URL}?range=custom&start=2026-08-16&end=2026-08-16").get_json()["payload"]
    assert utc_last_day["range"]["timezone"] == "UTC" and utc_last_day["totals"]["created"] == 0
    utc_next_day = client.get(f"{URL}?range=custom&start=2026-08-17&end=2026-08-17").get_json()["payload"]
    assert utc_next_day["totals"]["created"] == 2  # WO 8 (04:30Z) and WO 9 (05:30Z)


def test_open_at_end_of_window_counts_later_completions(client, org, users, dataset, api_login):
    api_login(users["member"])
    # window ending 2026-08-05: WO 1 completed later that day 10:00Z -> at 05:00Z on the 6th it is done
    early = client.get(f"{URL}?range=custom&start=2026-08-01&end=2026-08-05").get_json()["payload"]
    assert early["totals"] == {"created": 2, "completed": 1, "open": 4}  # WO 3 and WO 1 created; WO 1 completed
    # snapshot = created {WO1, WO3} + open at end {WO5 (in progress), WO1? no (done on the 5th)} -> WO1, WO3, WO5
    assert _counts(early["status_distribution"], "status") == {"draft": 0, "open": 0, "in_progress": 1, "on_hold": 0, "done": 2, "canceled": 0, "skipped": 0}
    # window ending 2026-08-04: WO 1 created that day and completed after the window -> open at end, counted as done today
    edge = client.get(f"{URL}?range=custom&start=2026-08-04&end=2026-08-04").get_json()["payload"]
    assert edge["totals"] == {"created": 1, "completed": 0, "open": 4}
    assert _counts(edge["status_distribution"], "status")["done"] == 2  # WO 1 (created) and WO 3 (open at end, completed on the 14th)
    assert edge["repeating_vs_non"] == {"repeating": 0, "non_repeating": 3}  # WO 1, WO 3, WO 5
    assert edge["on_time_completion_rate"] is None and edge["avg_completion_hours"] is None
    assert edge["overdue_open"] == 2  # overdue is evaluated now regardless of the window
