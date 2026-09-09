"""``run_work_order_scan`` – overdue / due-soon notifications, missed milestones,
and its wiring into the outbox worker."""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

from asme.extensions import db as _db
from asme.jobs import outbox
from asme.models import OutboxJob
from asme.ops.models import (
    AuditEvent,
    Milestone,
    Notification,
    OpsProject,
    Organization,
    Team,
    TeamMember,
    WorkOrder,
    WorkOrderAssignee,
    WorkOrderWatcher,
)
from asme.ops.services import scans
from tests.ops.conftest import make_user

NOW = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
RESULT_KEYS = {"overdue_notified", "due_soon_notified", "milestones_missed", "organizations"}


def _wo(org, number, creator, **kw):
    kw.setdefault("title", f"WO {number}")
    row = WorkOrder(organization_id=org.id, number=number, created_by_user_id=creator.id if creator else None, **kw)
    _db.session.add(row)
    _db.session.flush()
    return row


def _assigned_wo(org, number, creator, user, **kw):
    wo = _wo(org, number, creator, **kw)
    wo.assignees.append(WorkOrderAssignee(user_id=user.id))
    return wo


def test_overdue_notifies_every_stakeholder_once(org, users):
    member2 = make_user("Max Member", "max@uiowa.edu", org=org)
    watcher = make_user("Wendy Watcher", "wendy@uiowa.edu", org=org)
    team = Team(organization_id=org.id, name="Electrical")
    _db.session.add(team)
    _db.session.flush()
    team.members.append(TeamMember(user_id=users["lead"].id, is_lead=True))
    team.members.append(TeamMember(user_id=member2.id))
    wo = _wo(org, 1, users["admin"], title="Replace fuse", due_at=NOW - timedelta(hours=26))
    wo.assignees.append(WorkOrderAssignee(user_id=users["member"].id))
    wo.assignees.append(WorkOrderAssignee(team_id=team.id))
    wo.watchers.append(WorkOrderWatcher(user_id=watcher.id))
    _db.session.commit()

    result = scans.run_work_order_scan(now=NOW)
    assert set(result) == RESULT_KEYS
    assert result == {"overdue_notified": 5, "due_soon_notified": 0, "milestones_missed": 0, "organizations": 1}
    rows = Notification.query.filter_by(type="work_order.overdue").all()
    assert {r.user_id for r in rows} == {users["member"].id, users["lead"].id, member2.id, watcher.id, users["admin"].id}
    assert {r.title for r in rows} == {"#1 Replace fuse is overdue"}
    assert {r.dedupe_key for r in rows} == {f"overdue:{wo.id}:2026-09-07"}
    assert {(r.entity_type, r.entity_id) for r in rows} == {("work_order", str(wo.id))}
    assert all(r.organization_id == org.id and r.read_at is None and r.body for r in rows)

    again = scans.run_work_order_scan(now=NOW + timedelta(hours=3))
    assert again["overdue_notified"] == 0 and again["due_soon_notified"] == 0
    assert Notification.query.count() == 5


def test_dedupe_key_follows_the_due_date(org, users):
    wo = _assigned_wo(org, 1, users["admin"], users["member"], due_at=NOW - timedelta(days=2))
    _db.session.commit()
    assert scans.run_work_order_scan(now=NOW)["overdue_notified"] == 2  # assignee + creator
    assert scans.run_work_order_scan(now=NOW)["overdue_notified"] == 0

    # rescheduled to another (still past) day: the people involved are told again
    wo.due_at = NOW - timedelta(days=1)
    _db.session.commit()
    naive_now = NOW.replace(tzinfo=None)  # naive timestamps are read as UTC
    assert scans.run_work_order_scan(now=naive_now)["overdue_notified"] == 2
    keys = {r.dedupe_key for r in Notification.query.filter_by(user_id=users["member"].id).all()}
    assert keys == {f"overdue:{wo.id}:2026-09-06", f"overdue:{wo.id}:2026-09-07"}


def test_scan_ignores_drafts_closed_and_undated_work_orders(org, users):
    for number, status in enumerate(("draft", "done", "canceled", "skipped"), start=1):
        _assigned_wo(org, number, users["admin"], users["member"], status=status, due_at=NOW - timedelta(days=1))
    _assigned_wo(org, 9, users["admin"], users["member"], status="open")  # no due date
    for number, status in enumerate(("open", "in_progress", "on_hold"), start=20):
        _assigned_wo(org, number, users["admin"], users["member"], status=status, due_at=NOW - timedelta(days=1))
    _db.session.commit()

    result = scans.run_work_order_scan(now=NOW)
    assert result["overdue_notified"] == 6 and result["due_soon_notified"] == 0
    numbers = {int(r.title.split()[0][1:]) for r in Notification.query.all()}
    assert numbers == {20, 21, 22}


def test_due_soon_window_boundaries(org, users):
    cases = {
        1: (NOW - timedelta(seconds=1), {"work_order.overdue"}),
        2: (NOW, {"work_order.due_soon"}),
        3: (NOW + timedelta(hours=1), {"work_order.due_soon"}),
        4: (NOW + timedelta(hours=24), {"work_order.due_soon"}),
        5: (NOW + timedelta(hours=24, seconds=1), set()),
    }
    ids = {}
    for number, (due_at, _expected) in cases.items():
        ids[number] = _assigned_wo(org, number, users["admin"], users["member"], due_at=due_at).id
    _db.session.commit()

    result = scans.run_work_order_scan(now=NOW)
    assert result["overdue_notified"] == 2 and result["due_soon_notified"] == 6  # (assignee + creator) per work order
    for number, (due_at, expected) in cases.items():
        rows = Notification.query.filter_by(user_id=users["member"].id).filter(Notification.title.like(f"#{number} %")).all()
        assert {r.type for r in rows} == expected, number
        if expected == {"work_order.due_soon"}:
            assert rows[0].title == f"#{number} WO {number} is due soon"
            assert rows[0].dedupe_key == f"due_soon:{ids[number]}:{due_at.date()}"

    again = scans.run_work_order_scan(now=NOW)
    assert again["overdue_notified"] == 0 and again["due_soon_notified"] == 0

    # two hours on: #2 and #3 have become overdue (new key), #5 has entered the window, #4 is deduped
    later = scans.run_work_order_scan(now=NOW + timedelta(hours=2))
    assert later["overdue_notified"] == 4 and later["due_soon_notified"] == 2
    types_for_2 = sorted(r.type for r in Notification.query.filter_by(user_id=users["member"].id).filter(Notification.title.like("#2 %")).all())
    assert types_for_2 == ["work_order.due_soon", "work_order.overdue"]


def test_milestones_flip_to_missed_exactly_once(org, users):
    project = OpsProject(organization_id=org.id, name="Rover", code="CCR")
    _db.session.add(project)
    _db.session.flush()
    yesterday = NOW.date() - timedelta(days=1)

    def milestone(name, **kw):
        row = Milestone(organization_id=org.id, project_id=project.id, name=name, **kw)
        _db.session.add(row)
        return row

    late_planned = milestone("PDR", due_date=yesterday, status="planned")
    late_active = milestone("CDR", due_date=yesterday, status="in_progress")
    due_today = milestone("Today", due_date=NOW.date(), status="planned")
    done_late = milestone("Done", due_date=yesterday, status="done")
    already_missed = milestone("Missed", due_date=yesterday - timedelta(days=5), status="missed")
    undated = milestone("Undated", status="planned")
    _db.session.commit()

    result = scans.run_work_order_scan(now=NOW)
    assert result["milestones_missed"] == 2
    _db.session.expire_all()
    assert late_planned.status == "missed" and late_active.status == "missed"
    assert due_today.status == "planned" and done_late.status == "done" and undated.status == "planned"
    assert already_missed.status == "missed"

    events = AuditEvent.query.filter_by(event_type="milestone.missed").all()
    assert {e.entity_id for e in events} == {str(late_planned.id), str(late_active.id)}
    event = next(e for e in events if e.entity_id == str(late_planned.id))
    assert event.entity_type == "milestone" and event.actor_user_id is None and event.organization_id == org.id
    assert event.before_json == {"status": "planned"} and event.after_json == {"status": "missed"}
    assert event.metadata_json["project_id"] == str(project.id)
    assert "PDR" in event.summary

    again = scans.run_work_order_scan(now=NOW)
    assert again["milestones_missed"] == 0
    assert AuditEvent.query.filter_by(event_type="milestone.missed").count() == 2

    # on its due date a milestone is still on time; the next day it is missed
    tomorrow = scans.run_work_order_scan(now=NOW + timedelta(days=1))
    assert tomorrow["milestones_missed"] == 1
    _db.session.expire_all()
    assert due_today.status == "missed"
    assert AuditEvent.query.filter_by(event_type="milestone.missed", entity_id=str(due_today.id)).count() == 1


def test_scan_covers_every_organization_with_a_system_context(org, users):
    other = Organization(name="Other", slug="other")
    _db.session.add(other)
    _db.session.flush()
    _assigned_wo(org, 1, users["admin"], users["member"], due_at=NOW - timedelta(days=1))
    foreign = _wo(other, 1, None, title="Foreign", due_at=NOW - timedelta(days=1))
    foreign.assignees.append(WorkOrderAssignee(user_id=users["member"].id))
    _db.session.commit()

    ctx = scans.system_context(org)
    assert ctx.org is org and ctx.org_id == org.id and ctx.user is None and ctx.user_id is None

    result = scans.run_work_order_scan(now=NOW)
    assert result["organizations"] == 2 and result["overdue_notified"] == 3  # local: assignee + creator; foreign: assignee
    by_org = {(r.organization_id, r.title) for r in Notification.query.all()}
    assert by_org == {(org.id, "#1 WO 1 is overdue"), (other.id, "#1 Foreign is overdue")}
    assert not _db.session.new and not _db.session.dirty  # every organization was committed


def test_handler_is_registered_and_runs_through_the_outbox(app, org, users):
    assert "ops.work_order.scan" in outbox.registered_kinds()
    _assigned_wo(org, 1, users["admin"], users["member"], due_at=datetime.now(timezone.utc) - timedelta(days=1))
    outbox.enqueue("ops.work_order.scan", {})
    _db.session.commit()

    assert outbox.process_pending() == 1
    job = OutboxJob.query.filter_by(kind="ops.work_order.scan").one()
    assert job.status == "done" and job.last_error is None
    assert Notification.query.filter_by(type="work_order.overdue", user_id=users["member"].id).count() == 1


class _OneShot(threading.Event):
    """Trips on the first ``wait`` so ``_loop`` performs exactly one iteration."""

    def wait(self, timeout=None):
        self.set()
        return True


def test_worker_loop_schedules_the_hourly_scan(app, org, users):
    assert OutboxJob.query.filter_by(kind="ops.work_order.scan").count() == 0
    outbox._loop(app, _OneShot())
    jobs = OutboxJob.query.filter_by(kind="ops.work_order.scan").all()
    assert len(jobs) == 1 and jobs[0].status == "done", [(j.status, j.last_error) for j in jobs]
    # a second iteration inside the hourly window does not enqueue another scan
    outbox._loop(app, _OneShot())
    assert OutboxJob.query.filter_by(kind="ops.work_order.scan").count() == 1
