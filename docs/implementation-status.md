# Implementation status

Updated: 2026-09-08

## Current stage

**Stage 1 – Foundation and app shell** (in progress). Stage 0 baseline is complete.

## Baseline (Stage 0) – facts recorded before any change

- Branch: `feat/asme-ops-foundation`, created from `codex/landing-webgl` @ `b9774ee` (two commits ahead of `origin/main`; the package rebuild lives only on that branch).
- App: Flask 3.1 / SQLAlchemy 2.0 / Flask-Migrate 4.1 / Alembic 1.19 on Python 3.13; package `asme/` v2.0.0; migrations at head `0002_launchpad`.
- Tests: `python -m pytest` → **155 passed** (in-memory SQLite). `node --test tests/landing/*.test.mjs` covers the landing page.
- Local DB: SQLite `instance/inventory.db`, 33 tables, 1 user, 3 projects, Launchpad seeds; everything else empty.
- Tooling present: Node 24.12, npm 11.6, ffmpeg 8. Absent: PostgreSQL server, Docker.
- Reference recording (MP4): **not available** in workspace or Downloads. See `docs/reference/video-observations.md`.
- Secrets: `.env` exists locally, is git-ignored and was not read beyond confirming `ASME_ENV=development` and a SQLite URL.

## Completed

| Item | Evidence |
|---|---|
| Repository inspection and subsystem map | `docs/migration-plan.md` (schema inventory), this file |
| Architecture decision | `docs/decisions/ADR-0001-transitional-architecture.md`, `docs/architecture/overview.md` |
| Reference documentation with evidence labels | `docs/reference/*.md` |
| Implementation plan | `docs/plans/2026-09-08-asme-ops-stage1-stage2.md` |

## In progress

- Stage 1: `asme/ops` package (models, permissions, policy, audit, storage), migration `0003_ops_foundation`, ops API skeleton, SPA scaffold and design tokens, Setup Center, teams/users/locations/categories.

## Not started

- Stage 2: projects + work orders vertical slice, operations dashboard, seeds, Playwright screenshots.
- Stages 3–8 (requests, messaging, events, assets/inventory/purchasing beyond selectors, procedures, plans, meters, automations, reporting suite, public-site projection).

## Blockers

- None that stop local implementation. PostgreSQL verification of migrations must happen in CI/staging (no local server).
- Recording MP4 missing → visual fidelity is spec-driven until frames are available.

## Known defects (pre-existing, found during the baseline read; not fixed by Stage 1)

- `Settings.app_boot_token` is random per process unless `ASME_APP_BOOT_TOKEN` is set; with gunicorn `--workers 2` users get logged out when requests alternate between workers. Deployment docs now require the variable.
- "Low stock" has three different definitions (API serializer, `inventory.low_stock_items`, legacy dashboard). Tracked for Stage 4 (parts inventory).
- `POST /api/v1/checkouts` replays `Idempotency-Key` globally (not per user); a colliding key returns another user's loan. Tracked for Stage 4.
- Several legacy API views cast query ids with bare `int()` and return 500 instead of 400 on bad input. Tracked for Stage 8 hardening.
- Migration `0002` backfills booleans with integer literals; it has not been verified on PostgreSQL. Migration `0003` (ops) uses portable types; both must be exercised against PostgreSQL in CI before a production upgrade.
- **Security (legacy, scheduled for Stage 8 hardening, listed here so they are not forgotten):** several legacy-ops and legacy-API write routes (`/transact`, `/attendance/scan`, `/print/submit`, `/api/inventory/transact`, `/api/attendance/scan`, kiosk `/pair/*`) and the `/export` and `/api/bootstrap` dumps do not check `ASME_ENABLE_LEGACY_OPS` or a login; `/forgot-password` flashes the live reset link to the requester; roster import returns plaintext passwords; the login rate limiter is per-process and trusts `X-Forwarded-For`. The route-count smoke test pins these URLs, so gating them needs coordinated test changes. None of these are reachable through the new `/api/v1` ops endpoints.

## Commands

```bash
# backend
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe manage.py upgrade
.\.venv\Scripts\python.exe manage.py routes
# frontend (apps/ops-web)
npm run dev | npm run build | npm run typecheck | npm test | npm run test:e2e
```
