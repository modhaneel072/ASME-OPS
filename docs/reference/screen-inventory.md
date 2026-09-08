# Screen inventory

Evidence levels follow `video-observations.md` (OBSERVED / REPORTED / PROPOSED). Frame references will be added once the recording is available.

## Stage 1–2 screens (being built now)

| Route | Screen | Regions | Evidence |
|---|---|---|---|
| `/app/setup` | Setup Center | heading, phase cards (3 phases), right progress panel | REPORTED layout, PROPOSED copy |
| `/app/projects` | Projects list + overview | header (view selector Active/All/Archived, search, New Project), filter chips, 42/58 split | REPORTED pattern (work orders), PROPOSED for projects |
| `/app/projects/:id/(overview\|work\|milestones\|teams\|assets\|documents\|budget\|activity)` | Project detail tabs | tab strip under header; per-tab cards or lists | PROPOSED |
| `/app/work-orders` | Work-order list | header (view selector, search, split button), filter chips, To Do/Done tabs, sort menu, panel or table view | REPORTED |
| `/app/work-orders/new` | Create pane | right pane ≈58 %, 22 fields in spec order, sticky footer Cancel / Create | REPORTED |
| `/app/work-orders/:id` | Work-order detail | header (number, title, status selector, priority badge, Edit, More), body cards, comments, files, activity | REPORTED header, PROPOSED card order |
| `/app/teams-users` | Teams / Users | tabs Teams · Users; list/detail split; invite dialog | REPORTED (nav entry), PROPOSED layout |
| `/app/locations` | Locations | list/detail split, nested locations | REPORTED |
| `/app/categories` | Categories | list with coloured circle icons left; detail right with "Use in New Work Order" | REPORTED |
| `/app/assets` | Assets | header (Panel/Table/Hierarchy selector), filters, split | REPORTED |
| `/app/reporting/operations` | Operations dashboard | date range header, two-column report cards | REPORTED |
| `/app/settings/profile` | Profile | form | PROPOSED |

## States each screen must implement

Every list screen: loading skeleton shaped like rows, empty state, no-results (filters active) state, inline fetch error with retry, selected row highlight, deep-link restore of the selected record.

Every form: field-level validation messages from the server envelope, disabled submit while pending, success toast, failure alert that preserves entered data.

## Later-stage screens (tracked, not built yet)

Requests, Messages, Events, Parts Inventory, Purchase Requests, Maintenance Plans, Library (templates, procedures, documents), Vendors, Sponsors, Meters, Automations, Reporting Details / Activity / Exports / Dashboards, Settings (chapter, roles, notifications, integrations, audit).
