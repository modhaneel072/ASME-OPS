# Test plan

Updated: 2026-09-08. Applies to Stage 1–2 (foundation, shell, projects, work orders).

## Gates per change

| Gate | Command | Scope |
|---|---|---|
| Backend unit + integration | `.\.venv\Scripts\python.exe -m pytest -q` | Legacy suite (155 tests) + `tests/ops/*` |
| Migration | `pytest tests/ops/test_migration.py` | Empty DB → head, model/migration agreement, downgrade keeps legacy rows |
| Authorization | `pytest tests/ops/test_policy.py tests/ops/test_work_order_authz.py -q` and every `*_api.py` denial case | Scoped grants, private projects, cross-organization ids |
| Frontend types | `npm run typecheck` (in `apps/ops-web`) | Strict TypeScript, no emit |
| Frontend lint | `npm run lint` | ESLint recommended + React hooks + jsx-a11y |
| Frontend unit | `npm test` | Vitest + Testing Library (API client envelope, Dialog focus trap, Tabs keyboard, DropdownMenu keyboard, FilterChip) |
| Build | `npm run build` | Emits `static/ops`; must succeed before commit |
| End-to-end | `npm run test:e2e` | Playwright against the seeded Flask server (see below) |

A feature is complete only when every applicable gate passes and its states (loading, empty, no-results, validation, success, failure) are exercised by a test.

## Backend test conventions

- `tests/conftest.py` builds an in-memory SQLite app per test with three legacy users (admin / lead / member, password `correct-horse-battery`).
- `tests/ops/conftest.py` adds `org` (bootstrapped default organization with roles, grants, memberships, default location, seed categories), `ctx_admin` / `ctx_lead` / `ctx_member` / `ctx_requester` policy contexts, `api_login(user)` and `make_user(name, email, legacy_role, ops_role, org)`.
- Every ops API test file covers: happy path, validation (400 with an `errors` map), denial (403 for a role lacking the key), cross-organization id (404), and each business rule from the plan.
- The migration test is the only test that touches a file database; it uses `tmp_path`.

## End-to-end scenarios (Playwright, `apps/ops-web/e2e`)

Setup: `npm run build`, `python manage.py seed-ops`, then `npm run test:e2e` (Playwright starts `manage.py serve` unless `E2E_BASE_URL` is set).

| # | Scenario (from the build prompt) | Spec file |
|---|---|---|
| 1 | Existing user logs in with email or username | `auth.spec.ts` |
| 2 | Admin creates a project and assigns a project lead | `projects.spec.ts` |
| 3 | Team lead creates a work order in the right-side pane | `work-orders.spec.ts` |
| 4 | Member finds the work order through filters and starts it | `work-orders.spec.ts` |
| 5 | Member comments, uploads a permitted file, records time, completes the work order | `work-orders.spec.ts` |
| 6 | Inventory and project/report metrics update (project health + operations report) | `reporting.spec.ts` |
| 11 | Unauthorized member cannot access a private project or perform admin actions | `authz.spec.ts` |
| 12 | Legacy NFC attendance, inventory checkout/return, print requests and calendar routes still work | `legacy.spec.ts` (HTTP-level smoke) |
| – | Screenshots at 1440×900, 1366×768, 768×1024, 390×844 for Setup Center, Projects, Work Orders (panel, create pane, detail), Categories, Operations dashboard | `screens.spec.ts` (tag `@responsive`) |
| – | axe accessibility scan on each core page | inside `screens.spec.ts` |

Scenarios 7–10 belong to Stages 3, 5 and 6 and are tracked in `docs/implementation-status.md`.

## Manual checks before a release

1. Sign in as each seeded role and confirm the sidebar only shows permitted modules.
2. Resize to 390 px: sidebar becomes a drawer, list/detail stack, create pane is full-screen with a sticky footer.
3. Turn on "reduce motion" in the OS: no pane/popover animation.
4. Tab through the work-order create pane end to end without a mouse.
5. Kill the network mid-save: the form keeps its values and shows an inline error with retry.
