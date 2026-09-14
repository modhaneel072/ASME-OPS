# ADR-0001: Transitional architecture for ASME Ops

- **Status:** Accepted
- **Date:** 2026-09-08
- **Deciders:** platform maintainers
- **Supersedes:** none
- **Update 2026-09-14:** the transitional coexistence described here has ended. The public site, the member/leader/admin portal, the kiosk and the standalone HTML sign-in pages were removed; the repository now contains only ASME Ops, and account flows (sign-in, forgot/reset password, invitations, change password, profile) live in `/app`. The legacy backend services, models, migrations and JSON APIs remain without a UI pending a separate decision. The context below is kept as written at the time of the decision.

## Context

The ASME-WEB repository is a working Flask application (package `asme/`, version 2.0.0) that already ships the public site, the member/leader/admin portal, inventory checkout with an append-only stock ledger, print requests, NFC attendance, room scheduling and the Launchpad onboarding engine. It has:

- a services layer that owns every transaction (`asme/services/*`),
- Alembic migrations with a naming convention and SQLite batch mode (`0001_baseline`, `0002_launchpad`),
- a transactional outbox with an in-process worker (`asme/jobs/outbox.py`),
- an in-process domain event bus (`asme/events`),
- session auth with email-or-username login, role ladder `member < team_leader < admin`, and entitlement gates,
- a versioned JSON API at `/api/v1` with a single error envelope, cursor pagination and `Idempotency-Key` support,
- 155 passing pytest tests on an in-memory SQLite database.

The ASME Ops specification asks for a much larger operations platform (projects, work orders, requests, messaging, assets, parts, procedures, plans, meters, automations, reporting) with organization scoping, fine-grained RBAC, immutable audit history, durable jobs, private files and a dense React operations UI. The specification's *preferred* shape is a TypeScript monorepo (Next.js + NestJS + Prisma). The master build prompt allows a transitional architecture when a full rewrite would endanger existing behaviour, and forbids rewriting working systems for fashion.

Local development constraints observed on 2026-09-08: Python 3.13, Node 24, ffmpeg available; no PostgreSQL server or Docker on the workstation, so the local database is SQLite and migrations must run on both SQLite (batch mode) and PostgreSQL (production).

## Decision

Build ASME Ops as a **modular monolith inside the existing Flask application**, with a **React + TypeScript single-page operations frontend** served by Flask, and a **versioned JSON API** shared by both.

1. **Backend stays Flask + SQLAlchemy + Alembic + PostgreSQL.** The new domain lives in a new package `asme/ops/` (models, permissions, policies, services, seeds, storage) and follows the existing layering rule: blueprints parse, authorize and render; services own transactions; integrations are adapters. Existing modules are not rewritten.
2. **Every new table is prefixed `ops_`** and carries the tenant columns from the specification (`id` UUID, `organization_id`, `created_at`, `updated_at`, `created_by`, `updated_by`). Prefixing avoids collisions with populated legacy tables (`projects`, `events`, `transactions`) and makes the compatibility boundary visible. UUIDs use SQLAlchemy's portable `Uuid` type (native on PostgreSQL, CHAR(32) on SQLite). Timestamps are UTC through a `UTCDateTime` type decorator so both backends return timezone-aware values.
3. **Tenancy is additive.** An `ops_organizations` row ("ASME at the University of Iowa") is seeded, and every existing user receives an `ops_memberships` row. Legacy `users.role` keeps driving the existing portal; the ops role lives on the membership and is derived once from the legacy role (`admin -> chapter_admin`, `team_leader -> team_lead`, `member -> full_member`). Memberships are never downgraded automatically.
4. **Authorization is permission-based.** A registry of action keys (`work_order.create`, `asset.manage`, ...) and twelve system roles with default grants and scopes (`chapter`, `project`, `team`, `assigned`, `own`) are seeded into `ops_roles`, `ops_permissions`, `ops_role_permissions`. Routes are gated with `require_permission(key)`; services perform object-level checks through a per-request `PolicyContext`. Hiding UI is never the control.
5. **Audit is immutable and separate.** `ops_audit_events` stores before/after JSON per important action, written inside the same transaction by `asme/ops/services/audit_events.py`. The legacy `audit_logs` table and `audit.record` API stay untouched for legacy routes.
6. **Background work reuses the outbox.** `outbox_jobs` gains a nullable unique `idempotency_key` so recurring and event-driven jobs can be enqueued exactly once. Handlers are registered with the existing `@handler(kind)` decorator. The registry remains the seam for moving to a dedicated queue later.
7. **Files are private by default.** `ops_attachments` plus a storage adapter interface (`LocalStorage` under `instance/uploads/`, an S3 adapter documented but optional). Downloads go through short-lived signed URLs produced with the app secret.
8. **Realtime is polling first, push later.** Stage 1–2 ship `GET /api/v1/changes?since=` so the SPA revalidates on a 15 s cadence; a Server-Sent-Events endpoint is added in Stage 3 (messaging) behind a feature flag. Gunicorn sync workers make long-lived connections the exception, not the default.
9. **Frontend is a Vite React 19 + TypeScript app at `apps/ops-web/`.** State: TanStack Query for server state, React Hook Form + Zod for forms, TanStack Table for tables, React Router for `/app/*` routes. The design system is original (`src/ui/tokens.css` + primitives); icons come from the MIT-licensed `lucide-react` set. The production build is emitted to `static/ops/` and served by a Flask blueprint at `/app` and `/app/<path>`; the Vite dev server proxies `/api` to Flask so the session cookie is shared.
10. **Authentication reuses the session.** The SPA calls `POST /api/v1/auth/login` (same identity service, same rate limiter) and `GET /api/v1/session` (user, organization, role, permissions, setup state). Mutating JSON endpoints require `Content-Type: application/json`, which together with `SameSite=Lax` cookies blocks cross-site form posts; multipart uploads require the `X-Requested-With: ASME-Ops` header.

## Alternatives considered

| Alternative | Why not now |
|---|---|
| Full TypeScript monorepo (Next.js + NestJS + Prisma) as the spec prefers | Would fork identity, inventory, NFC, scheduling and Launchpad into a second source of truth or require porting ~10k lines of tested Python before any ops value ships. Violates "do not rewrite working systems merely for fashion" and the preservation rules. Can still be reached later by extracting services behind the same `/api/v1` contracts. |
| Server-rendered Jinja + htmx for the ops UI | Lower tooling cost, but the specification explicitly requires a React/TypeScript frontend, master-detail panes, optimistic updates and typed contracts; the interaction density is easier to achieve and test with a component system. |
| Django or FastAPI rewrite of the backend | Same second-source-of-truth problem; no benefit that justifies discarding the existing services, migrations and tests. |
| Flask-SocketIO WebSockets from day one | Requires eventlet/gevent workers or an ASGI gateway that the current gunicorn/Elastic Beanstalk/Render deployments do not run. Polling with cache revalidation meets the "reliable fallback" requirement; SSE is the incremental step. |
| Unprefixed table names matching the spec | Collides with populated `projects`, `events`, `transactions`; prefixing is the reversible, low-risk choice. |

## Consequences

**Positive**

- Existing routes, data, password hashes, tests and deployments keep working untouched.
- One database, one migration chain, one auth session, one API style.
- New modules can be developed and tested in parallel because each is its own service + blueprint module + test file with pre-agreed contracts.

**Negative / accepted costs**

- Two frontends coexist (Jinja portal for legacy flows, React SPA for ops) until legacy screens are migrated in later stages. (Superseded 2026-09-14: the Jinja frontend was removed; only the React SPA remains.)
- Python services and TypeScript contracts must be kept in sync by hand (Zod schemas mirror serializer output); an OpenAPI export is planned in Stage 8.
- SQLite in local development cannot exercise PostgreSQL-only behaviour (row locks, JSONB indexes). Migration tests run on SQLite here and must be re-run against PostgreSQL in CI or staging before a production release.

## Migration impact

- Migration `0003_ops_foundation` is additive only: new `ops_*` tables, one nullable unique column on `outbox_jobs`, no drops or renames.
- Backfill (`seed_defaults` → `ops.bootstrap.ensure_default_organization()`) is idempotent and safe to re-run.
- Legacy `projects`, `project_memberships`, `items`, `transactions`, `events` are mapped, not migrated: `ops_projects.public_project_id` links to legacy `projects`; membership changes on a linked ops project also upsert legacy `project_memberships` so Launchpad rules keep evaluating.

## Rollback

- `alembic downgrade 0002_launchpad` drops the `ops_*` tables and the `outbox_jobs.idempotency_key` column. No legacy data is touched by the upgrade, so downgrade is loss-free for legacy modules.
- The SPA is a static bundle plus one blueprint; unregistering `ops_app`/`ops_api` in `asme/blueprints/__init__.py` removes the surface.
