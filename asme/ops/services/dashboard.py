"""Operations report (``GET /reports/operations``).

Every number here is defined in ``docs/reporting-metrics.md``; keep the two in
step. The base set is ``work_orders.visible_work_orders_query(ctx)`` so a
member never sees figures derived from work they cannot open.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, or_, select

from asme.extensions import db
from asme.ops import policy
from asme.ops.models import CostEntry, OpsProject, Team, TimeEntry, WorkOrder
from asme.ops.models.work import OPEN_STATUSES, PRIORITIES, WORK_ORDER_STATUSES, WORK_TYPES
from asme.ops.serializers import team_ref, user_ref
from asme.ops.types import as_utc, utcnow
from asme.ops.validation import Field, ValidationErrors, validate

log = logging.getLogger("asme.ops.dashboard")

RANGE_KEYS = ("7d", "30d", "90d", "semester", "custom")
ROLLING_DAYS = {"7d": 7, "30d": 30, "90d": 90}
MAX_CUSTOM_DAYS = 366
# Semester anchors (month, day). With ``academic_year_start_month == 8`` the
# year starts Aug 15 and the second semester Jan 10; any other value mirrors
# that (year starts Jan 10, second semester Aug 15). The anchor set is the same
# either way, so the semester window always starts at the most recent anchor.
SEMESTER_ANCHORS = ((1, 10), (8, 15))
PARTS_COST_TYPE = "parts"

SPEC = {
    "range": Field("choice", choices=RANGE_KEYS, default="30d", nullable=False),
    "start": Field("date"),
    "end": Field("date"),
    "project": Field("uuid"),
    "team": Field("uuid"),
}


# --------------------------------------------------------------------------- ranges


def org_timezone(org) -> ZoneInfo:
    name = (getattr(org, "timezone", None) or "").strip() or "UTC"
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        log.warning("organization %s has unknown timezone %r; reporting in UTC", getattr(org, "slug", "?"), name)
        return ZoneInfo("UTC")


def semester_start(today: date, academic_year_start_month: int = 8) -> date:
    """Most recent semester anchor on or before ``today`` (see SEMESTER_ANCHORS)."""
    anchors = [date(year, month, day) for year in (today.year - 1, today.year) for month, day in SEMESTER_ANCHORS]
    if academic_year_start_month != 8:
        anchors = list(reversed(anchors))  # mirrored labelling; same dates
    return max(anchor for anchor in anchors if anchor <= today)


def resolve_range(org, data: dict, *, today: date | None = None) -> dict:
    """Return ``{"key", "start", "end", "tz"}`` (dates in the organization time zone)."""
    tz = org_timezone(org)
    today = today or datetime.now(tz).date()
    key = data.get("range") or "30d"
    if key in ROLLING_DAYS:
        start, end = today - timedelta(days=ROLLING_DAYS[key] - 1), today
    elif key == "semester":
        start, end = semester_start(today, org.academic_year_start_month or 8), today
    else:
        errors: dict[str, str] = {}
        start, end = data.get("start"), data.get("end")
        if start is None:
            errors["start"] = "Enter a start date as YYYY-MM-DD."
        if end is None:
            errors["end"] = "Enter an end date as YYYY-MM-DD."
        if not errors:
            if end < start:
                errors["end"] = "End must be on or after start."
            elif (end - start).days + 1 > MAX_CUSTOM_DAYS:
                errors["end"] = f"Custom ranges may cover at most {MAX_CUSTOM_DAYS} days."
        if errors:
            raise ValidationErrors(errors)
    return {"key": key, "start": start, "end": end, "tz": tz}


def window_bounds(start: date, end: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """UTC ``[start 00:00, day-after-end 00:00)`` — the inclusive local window
    ``[start 00:00, end 23:59:59.999]`` expressed as a half-open interval."""
    start_utc = datetime.combine(start, time.min, tzinfo=tz).astimezone(timezone.utc)
    end_utc = datetime.combine(end + timedelta(days=1), time.min, tzinfo=tz).astimezone(timezone.utc)
    return start_utc, end_utc


def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _local_date(value: datetime, tz: ZoneInfo) -> date:
    return as_utc(value).astimezone(tz).date()


# --------------------------------------------------------------------------- report


def _money(value) -> float:
    return float(value if isinstance(value, Decimal) else Decimal(str(value or 0)))


def operations_report(ctx, params: dict | None = None) -> dict:
    from asme.ops.services.work_orders import visible_work_orders_query

    policy.authorize(ctx, "report.view")
    data = validate(params or {}, SPEC)
    window = resolve_range(ctx.org, data)
    tz, start, end = window["tz"], window["start"], window["end"]
    start_utc, end_utc = window_bounds(start, end, tz)
    now = utcnow()

    base = visible_work_orders_query(ctx)
    if data.get("project") is not None:
        project = policy.get_or_404(ctx, OpsProject, data["project"])
        base = base.filter(WorkOrder.project_id == project.id)
    if data.get("team") is not None:
        team = policy.get_or_404(ctx, Team, data["team"])
        base = base.filter(WorkOrder.team_id == team.id)

    def in_window(column):
        return (column >= start_utc) & (column < end_utc)

    created = base.filter(in_window(WorkOrder.created_at)).all()
    completed = base.filter(in_window(WorkOrder.completed_at)).all()
    open_at_end = base.filter(
        WorkOrder.created_at < end_utc,
        or_(
            WorkOrder.status.in_(OPEN_STATUSES),
            (WorkOrder.status == "done") & (WorkOrder.completed_at >= end_utc),
            (WorkOrder.status == "canceled") & (WorkOrder.canceled_at >= end_utc),
        ),
    ).all()
    currently_open = base.filter(WorkOrder.status.in_(OPEN_STATUSES)).all()

    # weekly created vs completed (weeks start Monday, in the org time zone)
    weeks: dict[date, dict[str, int]] = {}
    cursor = week_start(start)
    while cursor <= end:
        weeks[cursor] = {"created": 0, "completed": 0}
        cursor += timedelta(days=7)
    for row in created:
        weeks[week_start(_local_date(row.created_at, tz))]["created"] += 1
    for row in completed:
        weeks[week_start(_local_date(row.completed_at, tz))]["completed"] += 1

    # distributions over "open at end of window" + "created in window"
    snapshot = {row.id: row for row in created}
    snapshot.update({row.id: row for row in open_at_end})
    by_status = defaultdict(int)
    by_priority = defaultdict(int)
    by_work_type = defaultdict(int)
    repeating = 0
    for row in snapshot.values():
        by_status[row.status] += 1
        by_priority[row.priority] += 1
        by_work_type[row.work_type] += 1
        if row.recurrence_json is not None:
            repeating += 1

    # completion quality
    with_due = [row for row in completed if row.due_at is not None]
    on_time = sum(1 for row in with_due if as_utc(row.completed_at) <= as_utc(row.due_at))
    on_time_rate = round(on_time / len(with_due), 4) if with_due else None
    durations = [(as_utc(row.completed_at) - as_utc(row.created_at)).total_seconds() / 3600 for row in completed]
    avg_hours = round(sum(durations) / len(durations), 2) if durations else None
    overdue_open = sum(1 for row in currently_open if row.due_at is not None and as_utc(row.due_at) < now)

    # workload (current, not windowed)
    team_counts: dict = defaultdict(lambda: {"open": 0, "in_progress": 0})
    user_counts: dict = defaultdict(lambda: {"open": 0, "in_progress": 0})
    users: dict = {}
    for row in currently_open:
        if row.status not in ("open", "in_progress"):
            continue
        team_counts[row.team_id][row.status] += 1
        for assignee in row.assignees:
            if assignee.user_id:
                users[assignee.user_id] = assignee.user
                user_counts[assignee.user_id][row.status] += 1
    team_rows = {t.id: t for t in Team.query.filter(Team.organization_id == ctx.org.id, Team.id.in_([k for k in team_counts if k])).all()} if team_counts else {}

    def _team_sort(item):
        team_id, counts = item
        team = team_rows.get(team_id)
        return (-(counts["open"] + counts["in_progress"]), team is None, (team.name if team else ""))

    def _user_sort(item):
        user_id, counts = item
        return (-(counts["open"] + counts["in_progress"]), (users[user_id].name if users.get(user_id) else ""))

    workload_by_team = [{"team": team_ref(team_rows.get(team_id)), **counts} for team_id, counts in sorted(team_counts.items(), key=_team_sort)]
    workload_by_user = [{"user": user_ref(users[user_id]), **counts} for user_id, counts in sorted(user_counts.items(), key=_user_sort)]

    # time and cost logged in the window against the base set
    base_ids = select(base.with_entities(WorkOrder.id).subquery().c.id)
    minutes = db.session.scalar(
        select(func.coalesce(func.sum(TimeEntry.minutes), 0)).where(TimeEntry.work_order_id.in_(base_ids), in_window(TimeEntry.created_at))
    )
    cost_rows = db.session.execute(
        select(CostEntry.type, func.coalesce(func.sum(CostEntry.amount), 0))
        .where(CostEntry.work_order_id.in_(base_ids), in_window(CostEntry.created_at))
        .group_by(CostEntry.type)
    ).all()
    parts_cost = sum((_money(amount) for cost_type, amount in cost_rows if cost_type == PARTS_COST_TYPE), 0.0)
    other_cost = sum((_money(amount) for cost_type, amount in cost_rows if cost_type != PARTS_COST_TYPE), 0.0)

    return {
        "range": {"key": window["key"], "start": start.isoformat(), "end": end.isoformat(), "timezone": tz.key},
        "created_vs_completed": [{"week_start": day.isoformat(), **counts} for day, counts in weeks.items()],
        "by_work_type": [{"work_type": work_type, "count": by_work_type.get(work_type, 0)} for work_type in WORK_TYPES],
        "repeating_vs_non": {"repeating": repeating, "non_repeating": len(snapshot) - repeating},
        "status_distribution": [{"status": status, "count": by_status.get(status, 0)} for status in WORK_ORDER_STATUSES],
        "priority_distribution": [{"priority": priority, "count": by_priority.get(priority, 0)} for priority in PRIORITIES],
        "on_time_completion_rate": on_time_rate,
        "overdue_open": overdue_open,
        "avg_completion_hours": avg_hours,
        "workload_by_team": workload_by_team,
        "workload_by_user": workload_by_user,
        "hours_logged": round(int(minutes or 0) / 60, 2),
        "parts_cost": round(parts_cost, 2),
        "other_cost": round(other_cost, 2),
        "totals": {"created": len(created), "completed": len(completed), "open": len(currently_open)},
    }
