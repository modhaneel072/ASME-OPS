# Changelog

All notable changes to ASME Ops (formerly the ASME @ UIowa web platform) are recorded here. Dates are ISO 8601.

## Unreleased

### Added – ASME Ops (Stage 1–2)

- **Operations platform** served at `/app`: React + TypeScript single-page app (`apps/ops-web`) built into `static/ops`, with an original design system (tokens, sidebar shell, master-detail layouts, right-side create pane, filter chips, dialogs, toasts) and a JSON API under `/api/v1`.
- **Tenancy and access control**: `ops_organizations`, `ops_memberships`, `ops_roles`, `ops_permissions`, `ops_role_permissions`; twelve system roles with scoped grants (chapter / project / team / assigned / own); legacy roles map to ops roles at seed and first sign-in.
- **Audit**: immutable `ops_audit_events` written inside every mutating transaction.
- **Modules**: Setup Center, teams and users, locations, categories, assets and asset types, vendors, projects and milestones, work orders (list, filters, saved views, create pane, detail, transitions, sub-work orders, dependencies, time and cost, watchers), comments, private attachments with signed downloads, notifications, change feed, global search, operations report.
- **Background jobs**: `enqueue_once` idempotency for the outbox and an hourly `ops.work_order.scan` (overdue / due-soon notifications, missed milestones).
- **Migration** `0003_ops_foundation` (additive; adds `outbox_jobs.idempotency_key`).
- **Docs**: architecture overview, ADR-0001, migration plan, reference/baseline documents, implementation status, test plan, deployment guide, reporting metrics.
- **Dev tooling**: Vitest and Playwright suites for the frontend.

### Security – account flows

- Reset and invite tokens are stored as SHA-256 digests; a database read or backup no longer yields working links. Links issued before this change stop working.
- Reset links carry the token in the URL fragment (`#token=`), and the SPA checks it with `POST /auth/reset-password/status`, so tokens never reach web-server, proxy or application logs. The request logger also redacts `token` URL variables.
- Setting a password (reset link, change password, administrator reset) ends every other session for that account; the session stores a keyed fingerprint of the password hash.
- Forgot-password does identical work for every address: it queues an `auth.password_reset` job and the worker looks the account up, so response time no longer reveals membership.
- Production refuses to start with SMTP configured but no `ASME_PUBLIC_BASE_URL`, and e-mailed links never use the request `Host` header in production.
- Rate-limiter counters are namespaced per flow, so failed sign-ins cannot lock someone out of changing or resetting their password.

### Removed – example data

- `python manage.py seed-ops`, `asme/ops/seeds.py`, `docs/seed-data.md` and `db_init.py`. `seed_defaults` no longer creates placeholder public projects or a welcome announcement. The system starts empty apart from the admin account, roles, the default location and the default categories.

### Added – account flows in ASME Ops

- Signed-out screens `/app/auth/login`, `/app/auth/forgot-password` and `/app/auth/reset-password#token=...` (the reset screen also accepts invitations), plus change password and profile editing under Settings > Profile.
- API: `POST /api/v1/auth/forgot-password` (always `{sent: true}` for a well-formed address; the outbox worker e-mails a single-use link), `POST /api/v1/auth/reset-password/status` with `{token}` (`valid`, `purpose` `invite`/`reset`, masked e-mail, `expires_at`; `404 invalid_token` otherwise), `POST /api/v1/auth/reset-password`, `POST /api/v1/auth/change-password` and `PATCH /api/v1/session/profile` (name, major, graduation year, phone). These endpoints answer `429 rate_limited` with `retry_after` when limited.
- `POST /api/v1/users/invite` returns `invite_url` in the form `<origin>/app/auth/reset-password#token=<token>`.
- `ASME_PUBLIC_BASE_URL` fixes the origin of e-mailed reset and invite links; `ASME_TRUSTED_PROXY_COUNT` tells rate limiting how many proxies append to `X-Forwarded-For`. Forgot-password e-mail requires `ASME_SMTP_USER` / `ASME_SMTP_PASS` in production.

### Removed – everything that was not ASME Ops

- The public website (home, who we are, executive team, projects, events, gallery, join, contact, sponsors, and the landing page with its 3D models and arm simulator).
- The member and admin portal (everything under `/portal`).
- The kiosk and NFC check-in screens.
- The standalone `/login`, `/signup`, `/admin-login`, `/logout`, `/forgot-password` and `/reset-password` HTML pages; their account flows now live in `/app` (see above).
- The Jinja templates, static assets, blueprints and tests that only those pages used. `/` now redirects to `/app`, the removed paths return 404, and deploy health checks use `/healthz`.
- Settings that only those pages used: `ASME_ENABLE_LEGACY_OPS`, `ASME_SHARED_ADMIN_EMAIL` / `ASME_SHARED_ADMIN_PASSWORD` / `ASME_ADMIN_EMAIL` / `ASME_ADMIN_PASSWORD` (the shared admin login), `ASME_TEMPLATES_AUTO_RELOAD`.
- Kept deliberately: the legacy backend services (tool checkout inventory, 3D print requests, attendance, room scheduling, Launchpad), their models and migrations, and the JSON blueprints `api_v1` and `api_legacy`. They have no user interface; their future is a pending decision.

### Changed

- Unknown `/api/*` paths and disallowed methods now return the JSON error envelope instead of HTML.
- Correction to an earlier note in this section: the kiosk-era front portal was briefly moved from `/app` to `/legacy/app` so `/app` could serve ASME Ops. That `/legacy/app` route, and `/kiosk`, no longer exist; they were removed with the rest of the legacy HTML surfaces.

### Security

- Mutating `/api/v1` ops requests must be JSON (or multipart with `X-Requested-With: ASME-Ops`), which together with `SameSite=Lax` cookies blocks cross-site form posts.
- Attachment downloads require short-lived signed tokens; files live outside `static/`.
- `ASME_APP_BOOT_TOKEN` is now documented as required for multi-worker deployments (pre-existing behaviour logged users out when requests alternated between gunicorn workers).
- The removed `/forgot-password` page flashed the live reset link to the requester; the replacement API never returns the link or token and does not reveal whether an account exists.
