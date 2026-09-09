# ASME Ops seed data

Updated: 2026-09-09. Implemented in `asme/ops/seeds.py`; command `python manage.py seed-ops`.

> **Development only.** The dataset ships well-known passwords and refuses to run when
> `ASME_ENV=production` (`Settings.is_production` / `Settings.ops_seed_allowed`). Never point it at a
> production database, and never reuse these accounts anywhere public.

## Running it

```bash
python manage.py upgrade            # schema to head + default org, roles, admin, legacy projects
python manage.py seed-ops           # build the demo dataset and print the credentials table
python manage.py seed-ops --reset   # wipe the organization's ops data and build it again
```

`seed-ops` is idempotent: the organization counts as seeded once it has an ops project with code `CCR`,
and a second run prints the table again with `skipped` and changes nothing. If a run fails half-way
(the database is left with a partial dataset) use `--reset`.

`--reset` deletes the organization's ops rows in dependency order - work-order satellites (dependencies,
time and cost entries, status history, assignees, categories, asset links, watchers), work orders,
milestones, project members, projects, asset status history, assets, asset types, vendors, team members,
teams, comments, attachments (and their stored files), audit events, notifications, saved filters and the
non-default locations - then restarts work-order numbering at 1. It keeps the organization, roles,
memberships (and therefore every user account), user preferences, the default `General` location and the
fourteen seed categories.

From Python: `from asme.ops import seeds; seeds.seed_ops(reset=False)` returns the counts dict
(`echo=None` suppresses the printed report).

## Accounts

Every account signs in at `/app` (or `/login`) with its e-mail or username. Passwords come from the
settings: `ASME_DEFAULT_USER_PASSWORD` for the seeded people and `ASME_DEFAULT_ADMIN_PASSWORD` for the
bootstrap admin (both default to `ChangeMe123!`). An account that already existed before the seed ran is
reused as-is and keeps whatever password it had.

| Name | E-mail | Ops role | Legacy role | Teams |
|---|---|---|---|---|
| ASME Admin (bootstrap) | `ASME_DEFAULT_ADMIN_EMAIL` (default `admin@uiowa.edu`) | Chapter Administrator | admin | - |
| Priya Natarajan (President) | pnatarajan@uiowa.edu | Executive Officer | member | Executive Board (lead), Events and Outreach (lead) |
| Marcus Bell | mbell@uiowa.edu | Project Lead | member | Crater Cruncher Rover (lead), Software and Autonomy (lead) |
| Elena Ortiz | eortiz@uiowa.edu | Team Lead | team_leader | Wheels and Mobility (lead) |
| Jordan Kim | jkim@uiowa.edu | Team Lead | team_leader | Robotic Arm (lead) |
| Sam Okafor | sokafor@uiowa.edu | Team Lead | team_leader | Electrical (lead) |
| Ava Chen | achen@uiowa.edu | Full Member | member | Wheels and Mobility |
| Liam Patel | lpatel@uiowa.edu | Full Member | member | Wheels and Mobility |
| Noah Garcia | ngarcia@uiowa.edu | Full Member | member | Robotic Arm |
| Mia Johnson | mjohnson@uiowa.edu | Full Member | member | Robotic Arm, Events and Outreach |
| Ethan Nguyen | enguyen@uiowa.edu | Full Member | member | Electrical |
| Zoe Williams | zwilliams@uiowa.edu | Full Member | member | Software and Autonomy |
| Dana Reyes (Safety Officer) | dreyes@uiowa.edu | Safety Officer | member | Executive Board |
| Owen Brooks (Inventory Manager) | obrooks@uiowa.edu | Inventory Manager | member | Fabrication (lead), Inventory and Procurement (lead) |
| Grace Lee (Treasurer) | glee@uiowa.edu | Treasurer | member | Executive Board, Inventory and Procurement |
| Alan Whitfield (Faculty Advisor) | awhitfield@uiowa.edu | Faculty Advisor | member | - |
| Riley Park | rpark@uiowa.edu | Requester | member | - |
| Casey Morgan | cmorgan@uiowa.edu | Shop Operator | member | Fabrication |

Usernames are first initial + last name (`identity.make_unique_username`, so a clash gets a numeric
suffix). Good accounts to demo with: `mbell` (project lead of the rover), `eortiz` (team lead), `achen`
(member with assigned work), `dreyes` (critical safety work), `cmorgan` (sees only assigned work),
`rpark` (sees almost nothing), `awhitfield` (read-only including the private project).

## What the dataset contains

Everything is created through the services (`asme/ops/services/*`) acting as the person who would do it
in real life, so every row has its audit event, status history, notifications and legacy mirrors.

- **Organization**: the default `uiowa` chapter from `manage.py upgrade`.
- **Teams (9)**: Executive Board, Crater Cruncher Rover, Wheels and Mobility, Robotic Arm, Electrical,
  Software and Autonomy, Fabrication, Events and Outreach, Inventory and Procurement. Rover sub-teams are
  attached to the CCR project.
- **Locations**: `General` (default) plus Engineering Student Center > Robotics Lab > Bench 1 / Bench 2 /
  Electronics Bench, Machine Shop, ASME Storage; Test Field and Trailer at the root.
- **Categories**: the fourteen seeded by the bootstrap (reused, none added).
- **Asset types (7)**: Vehicle, Subsystem, 3D Printer, Test Equipment, Tool, Power, Compute.
- **Vendors (4)**: McMaster-Carr, DigiKey, Amazon Business, Bambu Lab (created by the inventory manager).
- **Assets (22)**: Crater Cruncher Rover (`CCR-ROVER`) > Chassis, Mobility System > four wheel modules,
  Robotic Arm > Shoulder Assembly / Elbow Assembly / End Effector, Electrical System, Compute and Control;
  3D Printer 01 and 02 (02 is `offline_unplanned`, reason "Nozzle clog"), Soldering Station 01, Battery
  Charger 01, Oscilloscope 01, Bench Power Supply 01, Tool Kit A, Camera Kit, Test Rig 01 (taken offline
  for calibration and brought back online by a completed work order).
- **Projects (3)**: Crater Cruncher Rover (`CCR`, lead Marcus, advisor Whitfield, Lunabotics 2027, target
  the next 15 May, budget 18,500, medium risk, linked to the public-site `rover` project so
  `project_memberships` mirrors the members), General Chapter Operations (`OPS`, lead Priya) and the
  private Fall Engineering Showcase (`FES`, members Priya, Mia and the admin). Nine milestones across them.
- **Work orders (~50)** with realistic titles ("Inspect wheel hub fasteners", "Validate robotic arm current
  limits", "Update telemetry packet parser", "Print spare sensor mount", "Run pre-drive safety inspection",
  "Inventory M4 fasteners", "Replace 3D Printer 02 nozzle", "Torque check before test day", "Calibrate
  bench power supply", "Wire harness continuity test", "Pack competition crates" ...):
  - every status - open, in progress, on hold, done, canceled, draft - reached through the transition and
    completion services, so status history, notifications and audit trails are real;
  - eight overdue (past `due_at`, still open) and three critical-priority safety work orders created by the
    safety officer;
  - five parents with sub-work orders, one of them (`Rebuild shoulder assembly with new bushings`) with
    `parent_completion_policy = auto` whose children were completed so the parent auto-completed;
  - three dependencies, one currently blocked (`Stage rover for mobility test day` waits on the torque
    check);
  - time entries and parts / vendor cost entries (McMaster-Carr, Bambu Lab) on completed work, assignees
    mixing people and teams, watchers, categories, primary and related assets, a follow-up work order
    created from a completion, one completion that changed an asset's status;
  - `recurrence_json = {"every": "month"}` on the two preventive inspections. There is no service path
    for recurrence until the maintenance-plans stage, so this one field is written directly on the model.
- **Comments**: on work orders (including a reply thread and two `@[Name](user:id)` mentions), on the CCR
  project and on the rover asset.
- **Notifications and audit events**: whatever the services produced (roughly 200 audit events).

Timestamps are not backdated: everything was created "now", and overdue work is overdue because its due
date is in the past. Dashboards therefore show all activity on the day the seed ran.

## Tests

`tests/ops/test_seeds.py` runs the seed against the in-memory test database and asserts the counts above,
that every work order has status history, that a second run is skipped without duplicating rows, that
`reset=True` rebuilds cleanly, and that the seed raises `RuntimeError` when the settings say production.
