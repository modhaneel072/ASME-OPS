# Changelog

All notable changes to the ASME @ UIowa platform are recorded here. Dates are ISO 8601.

## Unreleased

### Added – ASME Ops (Stage 1–2)

- **Operations platform** served at `/app`: React + TypeScript single-page app (`apps/ops-web`) built into `static/ops`, with an original design system (tokens, sidebar shell, master-detail layouts, right-side create pane, filter chips, dialogs, toasts) and a JSON API under `/api/v1`.
- **Tenancy and access control**: `ops_organizations`, `ops_memberships`, `ops_roles`, `ops_permissions`, `ops_role_permissions`; twelve system roles with scoped grants (chapter / project / team / assigned / own); legacy roles map to ops roles at seed and first sign-in.
- **Audit**: immutable `ops_audit_events` written inside every mutating transaction.
- **Modules**: Setup Center, teams and users, locations, categories, assets and asset types, vendors, projects and milestones, work orders (list, filters, saved views, create pane, detail, transitions, sub-work orders, dependencies, time and cost, watchers), comments, private attachments with signed downloads, notifications, change feed, global search, operations report.
- **Background jobs**: `enqueue_once` idempotency for the outbox and an hourly `ops.work_order.scan` (overdue / due-soon notifications, missed milestones).
- **Migration** `0003_ops_foundation` (additive; adds `outbox_jobs.idempotency_key`).
- **Docs**: architecture overview, ADR-0001, migration plan, reference/baseline documents, implementation status, test plan, deployment guide, reporting metrics, seed data.
- **Dev tooling**: `python manage.py seed-ops` demo dataset (refuses in production); Vitest and Playwright suites for the frontend.

### Changed

- The kiosk-era front portal moved from `/app` to `/legacy/app` so `/app` can serve ASME Ops. Shared devices keep using `/kiosk`.
- Unknown `/api/*` paths and disallowed methods now return the JSON error envelope instead of HTML.

### Security

- Mutating `/api/v1` ops requests must be JSON (or multipart with `X-Requested-With: ASME-Ops`), which together with `SameSite=Lax` cookies blocks cross-site form posts.
- Attachment downloads require short-lived signed tokens; files live outside `static/`.
- `ASME_APP_BOOT_TOKEN` is now documented as required for multi-worker deployments (pre-existing behaviour logged users out when requests alternated between gunicorn workers).
