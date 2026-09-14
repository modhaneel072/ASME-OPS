# ASME Ops – architecture overview

See [ADR-0001](../decisions/ADR-0001-transitional-architecture.md) for the decision record. This page is the working map of the system. The repository contains only ASME Ops: the public website, member/admin portal, kiosk and NFC check-in screens and the standalone HTML sign-in pages were removed deliberately, and there are no Jinja templates.

## Process view

```
browser ─┬─ /            302 -> /app
         ├─ /app/*       ASME Ops SPA (React bundle from static/ops), including sign-in and account flows
         ├─ /api/v1/*    JSON API (ops blueprint + legacy api_v1 endpoints)
         ├─ /api/*       legacy JSON endpoints (api_legacy); unknown paths get the JSON error envelope
         └─ /healthz     health check
                │
        Flask app (gunicorn, 2 sync workers)
                │
        ┌───────┴────────┐
   PostgreSQL        outbox worker thread (or `manage.py worker`)
   (SQLite in dev)   ├─ calendar.*, stock.reconcile, onboarding.*  (legacy backend services)
                     ├─ mail.send                                  (password reset e-mail)
                     └─ ops.work_order.scan                        (ASME Ops)
                │
        SMTP (ASME_SMTP_*) for forgot-password mail
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
    validation.py       Field specs, validate() -> {"code": "validation", "errors": {...}}
    serializers/        JSON shapes for every resource, session payload
    storage.py          StorageAdapter, LocalStorage, signed download tokens
    numbering.py        next_number(org_id, key)  (ops_sequences)
    bootstrap.py        ensure_default_organization(), ensure_membership(user)
    services/
      audit_events.py   record(ctx, event_type, entity, before, after, **meta)
      notifications.py  notify(ctx, user_ids, type, title, body, entity)
      changes.py        change feed for polling clients
      setup_center.py   derived setup progress
      teams.py users.py locations.py categories.py assets.py vendors.py
      projects.py milestones.py organizations.py preferences.py entities.py
      work_orders.py    create/update/transitions/assign/time/cost/sub-work-orders
      scans.py          hourly overdue / due-soon / missed-milestone scan
      comments.py attachments.py saved_filters.py dashboard.py search.py
      users.py          directory, invitations (invite_url), role/status changes
  blueprints/
    ops/                one module per resource, all registering on `ops_api` bp
      __init__.py       bp, error handlers, JSON-content-type guard, helpers
      session.py        GET /session, PATCH /session/profile
      auth.py           login, logout, forgot-password, reset-password (status + set),
                        change-password
      organization.py setup.py teams.py users.py locations.py categories.py assets.py
      vendors.py projects.py work_orders.py comments.py attachments.py
      saved_filters.py notifications.py changes.py reports.py search.py
    ops_app.py          / -> /app redirect, SPA shell for /app and /app/<path>, /healthz
    api_v1.py           legacy JSON API (items, checkouts, print requests, events, bookings,
                        onboarding, roster import, health)
    api_legacy.py       legacy /api endpoints
  auth/                 session.py (sign_in_user, current_auth_user), rate_limit.py
  models/ services/     legacy domain models and services: inventory, fabrication, attendance,
                        scheduling, identity, onboarding (Launchpad), roster, audit
  integrations/         mail, calendar adapters, assistant
  events/ jobs/         domain event bus, transactional outbox + handlers
```

The legacy backend services under `asme/services` and their JSON blueprints have no user interface. They stay because production data (members, items, checkouts, attendance) may depend on them; whether to keep, migrate or retire them is a pending decision recorded in `docs/implementation-status.md`.

## Account flows

All account flows are JSON endpoints on the `ops_api` blueprint consumed by signed-out SPA screens (`/app/auth/*`) and Settings > Profile. Tokens are rows in the legacy `password_reset_tokens` table, created by `asme/services/identity.py`.

| Flow | SPA | API | Notes |
|---|---|---|---|
| Sign in / out | `/app/auth/login` | `POST /auth/login`, `POST /auth/logout` | e-mail or username; login rate limiter; `ensure_membership` at first sign-in |
| Forgot password | `/app/auth/forgot-password` | `POST /auth/forgot-password` | always `{sent: true}` for a well-formed e-mail; for an active account enqueues `mail.send` with `<ASME_PUBLIC_BASE_URL or request host>/app/auth/reset-password?token=...`; never returns the token; rate limited per address and client IP |
| Reset password / accept invite | `/app/auth/reset-password?token=...` | `GET /auth/reset-password/<token>`, `POST /auth/reset-password` | status reports `purpose` `invite` (never signed in) or `reset`, masked e-mail, `expires_at`; unknown, used or expired tokens are `404 invalid_token`; tokens are single-use and other outstanding tokens for the account are retired |
| Invite | Users > Invite dialog | `POST /users/invite` | creates the account and membership `invited` and returns `invite_url` (same reset link); existing accounts get `invite_url = null` |
| Change password | Settings > Profile | `POST /auth/change-password` | requires the current password |
| Edit profile | Settings > Profile | `PATCH /session/profile` | `name`, `major`, `graduation_year`, `phone`; returns the session payload |


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
- **Sessions.** `Settings.app_boot_token` defaults to an HMAC of the secret key, so every worker and every restart accepts the same sessions; setting `ASME_APP_BOOT_TOKEN` to a new value signs everyone out. Each session also stores a keyed fingerprint of the account's password hash, so a password change ends that account's other sessions. Admins are signed out after `ASME_ADMIN_SESSION_IDLE_MINUTES` (30) of inactivity, other members after `ASME_SESSION_IDLE_MINUTES` (240).
- **Removed HTML surfaces.** The public website, the member/admin portal, the kiosk and NFC check-in screens, the short-lived `/legacy/app` alias and the standalone sign-in, sign-up, admin sign-in, sign-out, forgot-password and reset-password HTML pages were removed deliberately; those paths return 404. Sign-in, forgot/reset password, invitations, change password and profile editing live in `/app` on `/api/v1/auth/*` and `/api/v1/session/profile`. Legacy models, services and the JSON blueprints `api_v1` / `api_legacy` remain.

## Data ownership and compatibility

| Legacy table | Ops counterpart | Relationship |
|---|---|---|
| `users` | `ops_memberships` | 1:1 per organization; ops role derived from legacy role at first sight |
| `projects` (former public showcase) | `ops_projects` | `ops_projects.public_project_id` → `projects.id`; the legacy `projects` table is kept for existing data |
| `project_memberships` | `ops_project_members` | writes to an ops project linked to a public project also upsert the legacy row and emit `team.joined` |
| `items`, `transactions`, `stock_ledger` | Parts inventory (Stage 4) | mapped in Stage 4; not touched before |
| `events`, `attendance_records` | Events module (Stage 3) | mapped in Stage 3 |
| `audit_logs` | `ops_audit_events` | both kept; legacy services and JSON endpoints keep writing `audit_logs` |
| `outbox_jobs` | same table | gains `idempotency_key` |

## Frontend layout

```
apps/ops-web/
  vite.config.ts        base /static/ops/, outDir ../../static/ops, dev proxy /api -> :5000
  playwright.config.ts  screenshots + e2e against a seeded Flask server
  src/
    main.tsx            providers (QueryClient, Router, Session)
    app/                routes.tsx, AppShell, Sidebar, ErrorBoundary, RequireSession,
                        AuthLayout, LoginPage, ForgotPasswordPage, ResetPasswordPage
    ui/                 tokens.css, primitives (Button, IconButton, SplitButton, SearchField,
                        FilterChip, Tabs, MasterDetailLayout, DataTable, DetailPanel, SideSheet,
                        FormField/Input/Textarea/Select/Combobox/DatePicker, StatusBadge,
                        PriorityBadge, EmptyState, Skeleton, Toast, InlineAlert, Dialog,
                        Popover, DropdownMenu, Tooltip, ActivityTimeline, CommentComposer,
                        AttachmentUploader, ReportCard)
    api/                client.ts (fetch wrapper, envelope, errors), contracts/*.ts (zod),
                        queries/*.ts (TanStack Query hooks per resource)
    features/           setup/, projects/, work-orders/, teams-users/, locations/,
                        categories/, assets/, vendors/, reporting/, settings/ (profile,
                        change password), and later-stage modules
    lib/                cn, dates, permissions hook, realtime (change-feed polling)
```

## Environments

| Concern | Development | Production |
|---|---|---|
| Database | SQLite `instance/inventory.db` | PostgreSQL (`ASME_DATABASE_URL`) |
| Migrations | auto at boot (`ASME_AUTO_MIGRATE=1`) | `python manage.py upgrade` release step |
| Example data | none; the chapter enters its own data | none |
| Uploads | `instance/uploads/` | `ASME_STORAGE_BACKEND=s3` + bucket vars (adapter documented, optional) |
| SPA | `npm run dev` on :5173 with proxy, or built bundle | built bundle in `static/ops` |
