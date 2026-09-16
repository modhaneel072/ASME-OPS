# ASME Ops – shop focus: groups, tool checkout and the kiosk

Decided with the chapter on 2026-09-16. This plan replaces the generic CMMS shape with the way ASME at Iowa actually runs: officers manage the system on the web, members meet it at a kiosk in the shop.

## Decisions

1. **Groups over projects.** The chapter runs programs (IAM3D, SDC) with a project manager; teams sit under a program. "Project" disappears from the interface: the top level is a **Group** with a PM, and **Teams** belong to a group. Nothing is pre-created — officers enter every group, team and person themselves.
2. **Tool checkout only.** Members check out tools and equipment at the kiosk, with a due date and a return. Consumable parts (filament, fasteners) are stock that officers adjust in the web app; members do not draw them at the kiosk.
3. **3D-printed NFC badges.** The chapter prints badges with an NFC tag and hands them out. A badge carries an identifier only: the person, their role and their teams are looked up in the database, never read from the badge (a tag can be cloned or rewritten; a database row cannot be, and it can be revoked).
4. **Roles stay as they are** for now. Admin goes to people the chapter trusts; a trimmed role list can come later.
5. **No seeded data, ever.** The system ships empty apart from the administrator account, roles, one default location and the default work categories.

## Removed

Deleted outright, backend and screens: Requests, Messages, Events, Maintenance Plans, Library (templates, procedures, documents), Meters, Automations, Sponsors, and the reporting pages beyond the operations report (Project Health, Asset Health, Details, Recent Activity, Export Data, Dashboards).

Also deleted: the unused legacy backend kept from the old platform – tool-checkout ledger (`asme/services/inventory.py`), 3D-print queue (`fabrication.py`), attendance (`attendance.py`), room scheduling (`scheduling.py`) with the Google/Outlook calendar adapters, the Launchpad onboarding engine (`asme/services/onboarding/`), the JSON blueprints `api_v1.py` and `api_legacy.py`, their models, their outbox handlers and their tests. Their tables are dropped in the same migration that adds the new ones; nothing in the chapter's data depends on them.

Kept but not advertised: **Purchase Requests**, because the low-stock list feeds it and the treasurer will want it. It stays out of the sidebar until asked for.

## Groups and teams

- A **Group** is the unit a program is run as: name, code, PM (a member), academic year, description, optional budget. It is the existing `ops_projects` row, renamed everywhere a person can see it, with `lead_user_id` presented as "Project manager".
- A **Team** belongs to a group (`ops_teams.project_id`), has leads and members, and owns work.
- Work orders, assets and tool loans hang off a **team**; the group is derived from the team, so nobody picks two things.
- Screens: **Groups** (list, detail with its teams, members and work), **Teams / Members** (create a team under a group, add members, set leads and roles, bulk-add from a pasted roster).

## Parts inventory

- Edit opens fully populated and every field is editable straight away; each section saves on its own.
- **Autofill while typing**: name, SKU, manufacturer part number and vendor suggest values already in the chapter's catalogue; picking a suggestion fills the rest of that part's details.
- **Duplicate part** copies everything except the identifiers, for the M4×16 → M4×20 case.
- Manufacturer, vendor and unit fields offer what the chapter has used before rather than a blank box.
- Stock stays as built in Stage 4: immutable transactions, per-location balances, low-stock state, and a low-stock list that can become a purchase request.

## Work orders: nothing gates anything

- Every section of a work order (details, assignment, parts, time and cost, files, comments) is editable at any time, independently, each saving on its own.
- No required order of operations: a work order can be completed without being started, parts can be attached before anyone is assigned, and a due date can be set on a draft.
- The only rules that remain are the ones that protect data: a closed work order must be reopened before it changes, and quantities cannot go negative.

## Badges, tool loans and the kiosk

### New tables (migration `0005_ops_shop`)

- `ops_badges` – `tag_uid` (unique per organization), `user_id`, `label`, `is_active`, `issued_at`, `issued_by_user_id`, `revoked_at`, `last_seen_at`.
- `ops_tool_loans` – `asset_id`, `user_id`, `team_id` (the team the member was acting for), `checked_out_at`, `due_at`, `returned_at`, `returned_to_condition`, `note`, `checked_out_via` (`kiosk` | `web`), `kiosk_device_id`, `checkout_badge_id`.
- `ops_kiosk_devices` – `name`, `location_id`, `token_hash`, `is_active`, `created_by_user_id`, `last_seen_at`. The token is shown once when the device is registered and stored only as a hash.

### Rules

- A tool is loanable when it is an active asset whose status is `online`; checking it out sets it `offline_planned` with the loan as the reason, and returning it restores `online`.
- One open loan per asset. A second checkout attempt says who has it.
- Default loan length is a chapter setting (default 7 days); leads may override at the kiosk.
- A member with an overdue tool is warned and, if the chapter turns that setting on, blocked from taking another.
- Every checkout and return writes an audit event and appears in the asset's history and on the member's record.

### Kiosk API (`/api/v1/kiosk/*`, device token in `X-Kiosk-Token`, no session cookie)

- `POST /kiosk/scan` `{tag_uid}` → the member's name, role, teams, open loans (with overdue flags) and the actions they may take. Unknown tag → a neutral "badge not recognised" with nothing else disclosed.
- `POST /kiosk/checkout` `{tag_uid, asset_code, team_id?, due_at?}` → the loan, or the reason it was refused.
- `POST /kiosk/return` `{tag_uid, asset_code, condition?, note?}` → the closed loan.
- `POST /kiosk/heartbeat` → device status, so an unplugged kiosk is visible to officers.
- Every call is rate limited per device, carries an `Idempotency-Key` so a flaky network cannot double-book a tool, and is audited with the device and badge that made it.

### Officer screens

- **Badges**: assign a badge to a member (scan or type the tag id), revoke, see last use.
- **Tools out**: everything currently checked out, who has it, since when, overdue first; return on behalf of a member.
- **Kiosks**: register a device, see when it last checked in, revoke its token.

## Order of work

1. Land the parts inventory and purchase requests already built, plus the Render deployment configuration.
2. Remove the modules listed above, including the legacy backend, with the migration that drops their tables.
3. Groups and teams: rename and restructure, with the teams screen doing group assignment and bulk member add.
4. Parts editing: autofill, duplicate, per-section saving.
5. Work orders: make every section independent.
6. Badges, tool loans and the kiosk API, with the three officer screens.
7. The kiosk application itself, once the hardware is chosen: it is a thin screen over the API above.
