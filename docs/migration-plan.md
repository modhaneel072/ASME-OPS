# Migration plan

Updated: 2026-09-08. Complements [ADR-0001](decisions/ADR-0001-transitional-architecture.md).

## 1. Current schema inventory (head `0002_launchpad`)

Row counts are from the local development SQLite database on 2026-09-08; production counts must be captured with the queries in §5 before the first production upgrade.

| Table | Domain | Local rows | Notes |
|---|---|---|---|
| `alembic_version` | infra | 1 | `0002_launchpad` |
| `users` | identity | 1 | canonical identity; `role` in member/team_leader/admin; `username` nullable unique; `member_id` → `members` |
| `members` | identity (legacy) | 0 | kiosk-era roster; kept one release |
| `nfc_tags` | identity | 0 | user ↔ tag |
| `password_reset_tokens` | identity | 0 | |
| `items` | inventory | 0 | `available_qty` counter + `stock_ledger` audit |
| `transactions` | inventory | 0 | loans (`Loan` alias); `idempotency_key` unique |
| `item_tags` | inventory | 0 | |
| `stock_ledger` | inventory | 0 | append-only |
| `stock_discrepancies` | inventory | 0 | nightly reconcile output |
| `print_requests`, `print_runs` | fabrication | 0 | portal print queue |
| `print_jobs` | fabrication (legacy) | 0 | legacy ops only |
| `events` | scheduling/attendance | 0 | meetings, bookings, open shop |
| `attendance_records` | attendance | 0 | user ↔ event |
| `attendance_scans` | attendance (legacy) | 0 | day-based kiosk scans |
| `meetings` | scheduling (legacy) | 0 | legacy ops calendar |
| `calendar_syncs` | scheduling | 0 | provider mirror |
| `projects` | public content | 3 | public showcase (`slug`, `title`, `gallery_json`, `is_joinable`) |
| `project_memberships` | public/launchpad | 0 | feeds Launchpad `team.joined` |
| `work_logs` | launchpad | 0 | hours logged |
| `contact_messages` | public | 0 | |
| `announcements` | content | 1 | |
| `audit_logs` | audit (legacy) | 0 | `admin_user_id`, `action`, `details`, `ip_address` |
| `outbox_jobs` | jobs | 1 | transactional outbox |
| `onboarding_tracks/phases/tasks/task_states/phase_states` | launchpad | 2/6/25/10/2 | seeded engine data |
| `entitlements` | launchpad | 0 | grants/overrides |
| `training_modules`, `training_completions` | launchpad | 3/0 | |

Conventions that new migrations must keep: constraint naming convention from `asme/extensions.py`, `render_as_batch=True` for SQLite, revision ids `NNNN_slug`, additive changes with explicit `downgrade()`.

## 2. New schema (migration `0003_ops_foundation`)

All new tables are prefixed `ops_`, use UUID primary keys, and carry `organization_id`, `created_at`, `updated_at`, `created_by_user_id`, `updated_by_user_id` unless stated.

| Table | Purpose |
|---|---|
| `ops_organizations` | chapter/tenant (no `organization_id` on itself) |
| `ops_memberships` | user ↔ organization ↔ role; unique (organization_id, user_id) |
| `ops_roles`, `ops_permissions`, `ops_role_permissions` | permission model; `ops_permissions` is global (no organization_id) |
| `ops_user_preferences` | per-user per-org key/value (setup banner, column layouts) |
| `ops_sequences` | per-org counters (work-order numbers) |
| `ops_teams`, `ops_team_members` | teams, leads |
| `ops_locations` | nested locations, `is_default` |
| `ops_categories` | colour + icon |
| `ops_asset_types`, `ops_assets`, `ops_asset_type_links`, `ops_asset_status_history` | assets and hierarchy |
| `ops_vendors` | selector for work orders (full module in Stage 4) |
| `ops_projects`, `ops_project_members`, `ops_milestones` | projects; `ops_projects.public_project_id` → legacy `projects.id` |
| `ops_work_orders` + `_assignees`, `_categories`, `_assets`, `_watchers`, `_status_history`, `_dependencies` | work |
| `ops_time_entries`, `ops_cost_entries` | time and cost |
| `ops_comments`, `ops_attachments` | polymorphic by (`entity_type`, `entity_id`) |
| `ops_audit_events` | immutable audit |
| `ops_saved_filters`, `ops_notifications` | UI state and notifications |
| `outbox_jobs.idempotency_key` | new nullable unique column |

## 3. Backfill

Executed by `asme.ops.bootstrap.ensure_default_organization()` from `seed_defaults()` (idempotent, additive):

1. Insert `ops_organizations` `slug='uiowa'` if missing.
2. Insert the twelve system roles for that organization with default grants (`asme/ops/permissions.py`).
3. For every `users` row without a membership, insert `ops_memberships` with role derived from `users.role`: `admin → chapter_admin`, `team_leader → team_lead`, else `full_member`. Never change an existing membership.
4. Insert the default `General` location (`is_default=True`) and the fourteen seed categories if the organization has none.
5. Ensure an `ops_sequences` row `work_order` starting at 1.

`ensure_membership(user)` also runs at sign-in so users created by legacy flows (signup, roster import) get a membership on first login.

## 4. Mapping rules for later stages

| Legacy | Stage | Rule |
|---|---|---|
| `project_memberships` | 2 | adding a member to an ops project with `public_project_id` upserts the legacy row and emits `team.joined` |
| `items`/`transactions`/`stock_ledger` | 4 | parts are created from items with a `legacy_item_id`; loans stay in `transactions`; quantities reconcile against `stock_ledger` |
| `events`/`attendance_records` | 3 | ops events reference `legacy_event_id`; attendance keeps writing `attendance_records` |
| `audit_logs` | – | never migrated; read-only in Recent Activity alongside `ops_audit_events` |

## 5. Verification queries

Run before and after the production upgrade:

```sql
SELECT count(*) FROM users;                                   -- unchanged
SELECT count(*) FROM ops_memberships;                         -- == active + inactive users after backfill
SELECT u.role, m.role_id, r.system_key FROM users u
  JOIN ops_memberships m ON m.user_id = u.id
  JOIN ops_roles r ON r.id = m.role_id;                        -- mapping matches §3
SELECT count(*) FROM ops_locations WHERE is_default;          -- == 1 per organization
SELECT version_num FROM alembic_version;                      -- 0003_ops_foundation
```

Migration test: `tests/test_ops_migration.py` upgrades a SQLite database from `0001_baseline` fixture → head and asserts the tables, the backfilled membership and the unchanged legacy row counts.

## 6. Rollback

```bash
python -m flask --app app db downgrade 0002_launchpad
```

Drops `ops_*` tables and `outbox_jobs.idempotency_key`; legacy tables untouched. Take a database backup before the upgrade regardless (`pg_dump -Fc` on PostgreSQL; copy `instance/inventory.db` on SQLite).
