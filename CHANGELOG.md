# Changelog

All notable changes to ASME Ops (formerly the ASME @ UIowa web platform) are recorded here. Dates are ISO 8601.

## Unreleased

### Added – Stage 4: parts inventory and purchase requests

- **Parts inventory.** A parts catalogue (`/app/parts`) with part types, vendor links and "spare part for this asset" links, per-location stock, QR/SKU lookup and a full transaction history. Screens for receive, issue, adjust, scrap, return, transfer and cycle count; All / Low stock / Out of stock tabs with live counts.
- **One ledger.** Every quantity change goes through `inventory_ledger.post(...)`. `ops_inventory_transactions` is append-only (updates and deletes, including bulk ORM ones, raise), `ops_inventory_balances` is a cached projection of it, and a movement that would drive stock negative is refused with `409 insufficient_stock` having written nothing. Priced receipts re-weight the part's average unit cost.
- **One definition of "low stock."** `inventory_ledger.stock_state` decides `ok` / `low` / `out` / `untracked`, and the SQL used by `GET /parts?filter[stock]=` mirrors it branch for branch. Moving into `low` or `out` notifies holders of `inventory.manage` once per part per day, plus the leads of the chapter's critical-parts team for a critical part.
- **Work-order parts.** A Parts section on the work-order detail: plan a line, reserve, kit, stage, issue and return, with a readiness chip per line and a readiness summary in the header. Issuing consumes the reservation and writes a system parts cost entry linked to its ledger row, so the operations report `parts_cost` and project health `budget.used` include it; a return writes the matching credit. Completing a work order reports `parts_outstanding` and leaves reservations alone; `release-all` clears them.
- **Purchase requests.** `/app/purchase-requests` with Mine / Needs review / Open / Closed tabs, line items with a part picker, live totals, an approval timeline and an action bar driven by the server's `available_actions`. Workflow: draft → submit → optional project-lead step → treasurer review → optional advisor review above a chapter threshold → approved → ordered → partially received → received, plus decline, request changes, cancel and reopen. Nobody approves their own request (`409 self_approval`). Receiving posts stock receipts and records what the vendor actually charged.
- **Reorder from low stock.** `POST /purchase-requests/from-low-stock` turns selected low parts into one draft per preferred vendor, with the suggested quantity and last known price filled in.
- **Chapter purchasing settings.** `GET|PUT /api/v1/purchasing/settings`: advisor review threshold, whether a project lead must approve first, and the critical-parts team.
- **Permission** `purchase.advisor_review` ("Give faculty-advisor sign-off on purchase requests"). Members, project leads and team leads gain `inventory.read` and `purchase.submit`; shop operators gain `inventory.read`; faculty advisors gain `inventory.read`, `vendor.read` and `purchase.advisor_review`; inventory managers no longer hold `purchase.review` by default (ordering and receiving is theirs, spending approval is the treasurer's). Existing chapters keep any manual grants.
- **Shared integration.** Comments and files work on parts and purchase requests; the change feed, global search and notification deep links cover both; the Setup Center "Add your parts" task is live; new events `ops.inventory.low_stock` and `ops.purchase_request.status_changed`.
- **Migration** `0004_ops_inventory` (additive; adds `ops_cost_entries.inventory_transaction_id`) and the command `python manage.py reconcile-ops-inventory`, which compares every chapter's balances with its ledger, prints the mismatches and never corrects them.

### Security – Stage 4

- Two approval steps now need two people: nobody may record a second `approve` on a purchase request they already approved in the current round of review (`409 already_approved`), so a faculty advisor holding both `purchase.review` and `purchase.advisor_review` can no longer clear the treasurer and advisor steps alone. A request sent back to `draft` starts a fresh round.
- The inventory ledger no longer names purchase requests the caller may not read. `GET /inventory/transactions`, `GET /parts/:id/transactions`, the `recent_transactions` on `GET /parts/:id` and the part's `open_purchase_requests` all apply the purchase-request read rule, the way the linked work order already was hidden.
- A purchase request's computed `estimated_total` is bounded by the money column: a line, or a whole request, that comes to more than 9999999999.99 is a field error instead of a row `Numeric(12, 2)` cannot hold (a `numeric field overflow` 500 on PostgreSQL).
- Returning parts credits only what the issues charged. A return is split across the line's issues newest first and each piece is priced at the unit cost of the issue it reverses, so a receipt that re-weighted the part between two issues can no longer leave a work order — or a project's `budget.used` — with a negative parts cost.
- `POST /parts/:id/transactions` with `type=return` and a work order now reverses issues that work order actually made, capped at what is still out (`409 return_exceeds_issued`) and referenced to the issue it reverses. Previously anyone who could log time on a work order could hand it an arbitrary negative parts cost.
- Moving stock between locations is judged as one movement, so a transfer no longer raises a false "out of stock" alert whose per-day dedupe key then swallowed the real stock-out.
- A location that still holds or is referenced by inventory (balances, ledger rows, work-order part lines, parts defaulting to it, purchase-request receive lines) is refused with `409 location_in_use` instead of being hard-deleted into orphaned rows.
- `request-changes` clears the abandoned `approved_total` and `approved_at`, so the final approval records the amount it actually approved rather than an earlier, smaller one — the number `GET /projects/:id/health` reports as `budget.committed`.
- The purchase-request form sends a line's unit price at the four decimals the field accepts and the `Numeric(12, 4)` column stores, and its live totals use the server's exact half-up rule, so what is approved on screen is what is stored.

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
