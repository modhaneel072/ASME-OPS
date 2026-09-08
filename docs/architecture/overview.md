# ASME Ops – architecture overview

See [ADR-0001](../decisions/ADR-0001-transitional-architecture.md) for the decision record. This page is the working map of the system as it is being built.

## Process view

```
browser ─┬─ /            public site (Jinja, unchanged)
         ├─ /portal/*    legacy portal (Jinja, unchanged)
         ├─ /app/*       ASME Ops SPA (React bundle from static/ops)
         └─ /api/v1/*    JSON API (legacy api_v1 + new ops blueprints)
                │
        Flask app (gunicorn, 2 sync workers)
                │
        ┌───────┴────────┐
   PostgreSQL        outbox worker thread (or `manage.py worker`)
   (SQLite in dev)   ├─ calendar.*, mail.send, stock.reconcile   (legacy)
                     └─ ops.notify, ops.work_order.scan          (new)
```

## Package layout (backend)

```
asme/
  ops/
    __init__.py
    types.py            UUID / UTCDateTime / JSON column helpers, OpsBase mixin
    models/
      identity.py       ops_organizations, ops_memberships, ops_roles, ops_permissions,
                        ops_role_permissions, ops_user_preferences, ops_sequences
      structure.py      ops_teams, ops_team_members, ops_locations, ops_categories,
                        ops_asset_types, ops_assets, ops_asset_type_links,
                        ops_asset_status_history, ops_vendors
      projects.py       ops_projects, ops_project_members, ops_milestones
      work.py           ops_work_orders + assignees/categories/assets/watchers/
                        status_history/dependencies, ops_time_entries, ops_cost_entries
      shared.py         ops_comments, ops_attachments, ops_audit_events,
                        ops_saved_filters, ops_notifications
    permissions.py      PERMISSIONS registry, SYSTEM_ROLES, DEFAULT_GRANTS
    policy.py           PolicyContext, load_context(user, org), can(), authorize(),
                        require_permission() decorator
    storage.py          StorageAdapter, LocalStorage, signed download tokens
    numbering.py        next_number(org_id, key)  (ops_sequences)
    bootstrap.py        ensure_default_organization(), ensure_membership(user)
    seeds.py            development/demo dataset (Crater Cruncher Rover, ...)
    services/
      audit_events.py   record(ctx, event_type, entity, before, after, **meta)
      notifications.py  notify(ctx, user_ids, type, title, body, entity)
      changes.py        change feed for polling clients
      setup_center.py   derived setup progress
      teams.py users.py locations.py categories.py assets.py projects.py
      work_orders.py    create/update/transitions/assign/time/cost/sub-work-orders
      comments.py attachments.py saved_filters.py dashboard.py search.py
  blueprints/
    ops/                one module per resource, all registering on `ops_api` bp
      __init__.py       bp, error handlers, JSON-content-type guard, helpers
      session.py auth.py organization.py setup.py teams.py users.py locations.py
      categories.py assets.py projects.py work_orders.py comments.py attachments.py
      saved_filters.py notifications.py changes.py reports.py search.py
    ops_app.py          serves the SPA shell for /app and /app/<path>
```

## Request lifecycle (ops API)

1. `current_auth_user()` resolves the session (unchanged).
2. `require_permission("work_order.create")` loads a `PolicyContext` for the user's membership in the active organization (`g.ops_ctx`), denies with `401 login_required`, `403 no_membership` or `403 forbidden` in the shared envelope.
3. The route parses and validates input (`asme/ops/validation.py` helpers produce `{"ok": false, "code": "validation", "errors": {field: message}}`).
4. The service performs object-level checks (`authorize(ctx, key, obj)`), mutates, writes `ops_audit_events`, enqueues outbox jobs, commits, then emits domain events.
5. The route serializes (`asme/ops/serializers.py`) and returns `{"ok": true, "payload": ...}`.

## Rules inherited from the legacy code (verified during the baseline read)

- **Time.** Legacy tables store naive `datetime.utcnow()` (and a few local `datetime.now()` comparisons in scheduling/attendance). Ops tables use `UTCDateTime`, which always returns timezone-aware UTC. Never compare the two directly: convert at the service edge with `asme.ops.types.as_utc()` when reading legacy rows, and strip `tzinfo` only when writing legacy columns.
- **Transactions.** Services commit themselves. `audit.record`, `audit_events.record` and `outbox.enqueue` only add to the session and rely on the caller's commit. `events.emit` is synchronous and the Launchpad subscriber commits the shared session, so emit **after** your own commit, never before.
- **Outbox.** Handlers must be idempotent (stale "running" rows are released after 10 minutes and admins can retry). Recurring jobs are scheduled only by the in-process worker loop; use `enqueue_once` with an idempotency key for anything that must not double-run.
- **Errors.** Blueprint-level `ServiceError` handlers only fire for matched routes; the app now also returns JSON 404/405 for any `/api/` path.
- **Sessions.** `Settings.app_boot_token` defaults to a per-process random value; multi-worker deployments must set `ASME_APP_BOOT_TOKEN` or users are logged out when a request lands on the other worker. This predates ASME Ops and is called out in `docs/deployment.md`.
- **Legacy `/app`.** The kiosk-era front portal moved from `/app` to `/legacy/app` so `/app` can serve ASME Ops. Shared devices should use `/kiosk` directly (unchanged).

## Data ownership and compatibility

| Legacy table | Ops counterpart | Relationship |
|---|---|---|
| `users` | `ops_memberships` | 1:1 per organization; ops role derived from legacy role at first sight |
| `projects` (public showcase) | `ops_projects` | `ops_projects.public_project_id` → `projects.id`; public site keeps reading `projects` |
| `project_memberships` | `ops_project_members` | writes to an ops project linked to a public project also upsert the legacy row and emit `team.joined` |
| `items`, `transactions`, `stock_ledger` | Parts inventory (Stage 4) | mapped in Stage 4; not touched before |
| `events`, `attendance_records` | Events module (Stage 3) | mapped in Stage 3 |
| `audit_logs` | `ops_audit_events` | both kept; legacy routes keep writing `audit_logs` |
| `outbox_jobs` | same table | gains `idempotency_key` |

## Frontend layout

```
apps/ops-web/
  vite.config.ts        base /static/ops/, outDir ../../static/ops, dev proxy /api -> :5000
  playwright.config.ts  screenshots + e2e against a seeded Flask server
  src/
    main.tsx            providers (QueryClient, Router, Session)
    app/                routes.tsx, AppShell, Sidebar, SetupBanner, ErrorBoundary
    ui/                 tokens.css, primitives (Button, IconButton, SplitButton, SearchField,
                        FilterChip, Tabs, MasterDetailLayout, DataTable, DetailPanel, SideSheet,
                        FormField/Input/Textarea/Select/Combobox/DatePicker, StatusBadge,
                        PriorityBadge, EmptyState, Skeleton, Toast, InlineAlert, Dialog,
                        Popover, DropdownMenu, Tooltip, ActivityTimeline, CommentComposer,
                        AttachmentUploader, ReportCard)
    api/                client.ts (fetch wrapper, envelope, errors), contracts/*.ts (zod),
                        queries/*.ts (TanStack Query hooks per resource)
    features/           setup/, projects/, work-orders/, teams-users/, locations/,
                        categories/, assets/, reporting/, settings/
    lib/                formatting, dates, permissions hook
```

## Environments

| Concern | Development | Production |
|---|---|---|
| Database | SQLite `instance/inventory.db` | PostgreSQL (`ASME_DATABASE_URL`) |
| Migrations | auto at boot (`ASME_AUTO_MIGRATE=1`) | `python manage.py upgrade` release step |
| Ops seed data | `python manage.py seed-ops` (dev only, refuses in production) | never |
| Uploads | `instance/uploads/` | `ASME_STORAGE_BACKEND=s3` + bucket vars (adapter documented, optional) |
| SPA | `npm run dev` on :5173 with proxy, or built bundle | built bundle in `static/ops` |
