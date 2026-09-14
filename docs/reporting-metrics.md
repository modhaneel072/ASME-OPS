# Reporting metrics

Definitions for `GET /api/v1/reports/operations` (implemented in
`asme/ops/services/dashboard.py`). The code and this document must agree; when
a formula changes, change both in the same commit.

Requires `report.view`.

## Base set

The report is computed over the **base set**: the work orders returned by
`asme.ops.services.work_orders.visible_work_orders_query(ctx)` - every work
order in the chapter the caller may read (private projects only when the caller
is a member or holds `project.read_private`; `work_order.read_assigned` holders
only see work they created, watch or are assigned to). Two optional filters
narrow it further:

| Query parameter    | Effect                                                    |
|--------------------|-----------------------------------------------------------|
| `filter[project]`  | `work_order.project_id == :id` (404 for an unknown or foreign-organization id) |
| `filter[team]`     | `work_order.team_id == :id` - the responsible team, not assignee teams (404 as above) |

Unknown filter names are rejected with `400 bad_filter`; a value that is not a
UUID is a validation error on that field.

## Time zone and date ranges

All dates are interpreted in the **organization time zone**
(`ops_organizations.timezone`, IANA name; an unknown name falls back to UTC and
is logged). `today` is today's date in that zone.

| `range`    | Window (inclusive local dates)                                   |
|------------|------------------------------------------------------------------|
| `7d`       | `today - 6 days` ... `today` (7 calendar days)                   |
| `30d`      | `today - 29 days` ... `today`                                    |
| `90d`      | `today - 89 days` ... `today`                                    |
| `semester` | most recent semester anchor on or before `today` ... `today`     |
| `custom`   | `start` ... `end` (both `YYYY-MM-DD`, both required)             |

The default range is `30d`.

**Semester anchors.** When `academic_year_start_month == 8` the academic year
starts on **Aug 15** and the second semester on **Jan 10**. Any other value
uses the mirrored calendar (year starts Jan 10, second semester Aug 15). The
anchor dates are the same either way, so the semester window always starts at
the most recent of Jan 10 / Aug 15 that is on or before `today`.

**Custom ranges** must satisfy `start <= end` and cover at most **366 days**
(`(end - start).days + 1 <= 366`). Violations return `400 validation` with
`errors.start` / `errors.end`.

**Window conversion.** The local window `[start 00:00:00, end 23:59:59.999]`
is converted to UTC and applied as the half-open interval
`[start_utc, day_after_end_utc)` to every timestamp column (all `ops_*`
timestamps are stored in UTC). Example: for `America/Chicago` in August,
`2026-08-03 ... 2026-08-16` becomes `2026-08-03T05:00Z <= t < 2026-08-17T05:00Z`,
so a work order created at `2026-08-16 23:30` local is inside the window and one
created at `2026-08-17 00:30` local is not.

The response echoes the resolved window as
`{"range": {"key", "start", "end", "timezone"}}`.

## Populations

| Name                   | Definition                                                                   |
|------------------------|------------------------------------------------------------------------------|
| created in window      | base set with `created_at` in the window                                     |
| completed in window    | base set with `completed_at` in the window                                   |
| open at end of window  | base set created before the window end that is currently open (`draft`, `open`, `in_progress`, `on_hold`) **or** was completed / canceled after the window end (`completed_at >= end` or `canceled_at >= end`) |
| snapshot               | union of *open at end of window* and *created in window*                     |
| currently open         | base set with status in `draft, open, in_progress, on_hold` (evaluated now, ignores the window) |

## Metrics

| Field                       | Definition                                                                                          |
|-----------------------------|-----------------------------------------------------------------------------------------------------|
| `created_vs_completed`      | One row per week (weeks start **Monday**) from the week containing `start` through the week containing `end`: `created` = created in window whose local `created_at` date falls in that week; `completed` = completed in window whose local `completed_at` date falls in that week. Empty weeks are included with zeros. |
| `by_work_type`              | Count of the **snapshot** by current `work_type`; every value of `WORK_TYPES` is listed (zeros included). |
| `repeating_vs_non`          | Over the **snapshot**: `repeating` = `recurrence_json IS NOT NULL`, `non_repeating` = the rest.       |
| `status_distribution`       | Count of the **snapshot** by current `status`; every value of `WORK_ORDER_STATUSES` is listed, canonical order. |
| `priority_distribution`     | Count of the **snapshot** by current `priority`; every value of `PRIORITIES` is listed, canonical order. |
| `on_time_completion_rate`   | Over *completed in window* with `due_at` not null: `count(completed_at <= due_at) / count(*)`, a fraction 0-1 rounded to 4 places. `null` when the denominator is 0. |
| `overdue_open`              | *Currently open* with `due_at < now` (not windowed).                                                 |
| `avg_completion_hours`      | Mean of `(completed_at - created_at)` in hours over *completed in window*, rounded to 2 places; `null` when nothing was completed. |
| `workload_by_team`          | Over *currently open* rows with status `open` or `in_progress` (`on_hold`/`draft` are not workload), grouped by `team_id`: `{"team": team_ref|null, "open", "in_progress"}`. Sorted by total desc, then team name; the no-team group last among ties. |
| `workload_by_user`          | Same population, grouped by direct user assignees (`ops_work_order_assignees.user_id`); team assignees are not expanded. Sorted by total desc, then name. |
| `hours_logged`              | `sum(ops_time_entries.minutes) / 60` for entries whose `created_at` is in the window and whose work order is in the base set; rounded to 2 places. |
| `parts_cost`                | `sum(ops_cost_entries.amount)` where `type = 'parts'`, entry `created_at` in window, work order in base set. |
| `other_cost`                | Same for every other cost type (`labor`, `vendor`, `other`).                                         |
| `totals.created`            | Size of *created in window*.                                                                         |
| `totals.completed`          | Size of *completed in window*.                                                                       |
| `totals.open`               | Size of *currently open*.                                                                            |

Distributions use each work order's **current** field values (status, priority,
work type, recurrence), not the values it had at the window end; the report
does not replay status history.

Money is returned as floats rounded to 2 decimals; `0.0` when nothing was
logged.
