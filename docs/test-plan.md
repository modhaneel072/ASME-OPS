# Test plan

Updated: 2026-09-14. Applies to ASME Ops Stage 1–2 (foundation, shell, projects, work orders) and the account flows. The repository contains only ASME Ops; the public website, portal, kiosk and legacy HTML sign-in pages were removed deliberately and have no tests.

## Gates per change

| Gate | Command | Scope |
|---|---|---|
| Backend unit + integration | `.\.venv\Scripts\python.exe -m pytest -q` (from the repository root) | `tests/ops/*` (ASME Ops, including `test_account_flows.py`) and the legacy backend-service suite (`tests/test_api_v1.py`, `test_inventory.py`, `test_onboarding.py`, `test_scheduling.py`, `test_identity.py`, `test_roster.py`, `test_outbox.py`, `test_auth_rbac.py`, `test_config.py`, `test_routes_smoke.py`) |
| Migration | `pytest tests/ops/test_migration.py` | Empty DB → head, model/migration agreement, downgrade keeps legacy rows |
| Authorization | `pytest tests/ops/test_policy.py tests/ops/test_work_order_authz.py -q` and every `*_api.py` denial case | Scoped grants, private projects, cross-organization ids |
| Frontend types | `npm run typecheck` (in `apps/ops-web`) | Strict TypeScript, no emit |
| Frontend lint | `npm run lint` | ESLint recommended + React hooks + jsx-a11y |
| Frontend unit | `npm test` | Vitest + Testing Library (API client envelope, sign-in, forgot-password and reset-password pages, RequireSession, Settings profile and change password, invite dialog, UI primitives) |
| Build | `npm run build` | Emits `static/ops`; must succeed before commit |
| End-to-end | `npm run test:e2e` | Playwright against the seeded Flask server (see below) |

Run the backend suite with its output written to a file and read pytest's own exit code (`... > out.txt 2>&1; echo $?`); never judge success from a pipeline such as `pytest | tail`. On Windows machines where `npx` or the npm shims are unreliable, call the frontend binaries through Node: `node ./node_modules/typescript/bin/tsc -b`, `node ./node_modules/eslint/bin/eslint.js .`, `node ./node_modules/vitest/vitest.mjs run`, `node ./node_modules/vite/bin/vite.js build`.

A feature is complete only when every applicable gate passes and its states (loading, empty, no-results, validation, success, failure) are exercised by a test.

## Backend test conventions

- `tests/conftest.py` builds an in-memory SQLite app per test with three legacy users (admin / lead / member, password `correct-horse-battery`).
- `tests/ops/conftest.py` adds `org` (bootstrapped default organization with roles, grants, memberships, default location, seed categories), `ctx_admin` / `ctx_lead` / `ctx_member` / `ctx_requester` policy contexts, `api_login(user)` and `make_user(name, email, legacy_role, ops_role, org)`.
- Every ops API test file covers: happy path, validation (400 with an `errors` map), denial (403 for a role lacking the key), cross-organization id (404), and each business rule from the plan.
- The migration test is the only test that touches a file database; it uses `tmp_path`.
- `tests/test_routes_smoke.py` checks that `/` redirects to `/app`, `/app` serves the shell (or the not-built page), `/healthz` and `/api/v1/health` answer, the removed HTML pages and form posts return 404, unknown `/api` paths keep the JSON envelope, and only the ops, ops-app and JSON API blueprints are registered.

## Account flows (backend and frontend)

`tests/ops/test_account_flows.py` and the Vitest page tests cover the contract in `docs/api.md`:

| Flow | Must be tested |
|---|---|
| Forgot password | `{sent: true}` for known and unknown well-formed addresses alike; 400 `validation` with `errors.email` for a malformed address; `mail.send` enqueued only for an active account; the response never contains the link or token; 429 `rate_limited` with `retry_after` |
| Reset status | valid token → `purpose` `invite` (never signed in) or `reset`, masked e-mail, ISO-8601 `expires_at`; unknown, used or expired token → 404 `invalid_token` |
| Reset password | password under 8 characters → `errors.password`; mismatch → `errors.confirm_password`; success sets the password without starting a session, and the account then signs in with it; the token cannot be reused |
| Invite | `POST /users/invite` returns `invite_url` of the form `<origin>/app/auth/reset-password?token=...`, honouring `ASME_PUBLIC_BASE_URL` |
| Change password | 401 signed out; wrong current password → `errors.current_password`; success changes the credential; rate limited |
| Edit profile | `PATCH /session/profile` validates each field and returns the same payload as `GET /session` |

## End-to-end scenarios (Playwright, `apps/ops-web/e2e`)

Setup: `npm run build`, then `E2E_EMAIL=... E2E_PASSWORD=... npm run test:e2e` against a throwaway database (Playwright starts `manage.py serve` unless `E2E_BASE_URL` is set). Sign-in specs skip when the credentials are not set.

| # | Scenario | Spec file | Status |
|---|---|---|---|
| 1 | Existing user signs in with e-mail or username, wrong password stays on the form, return-to after sign-in, sign-out | `auth.spec.ts` | present |
| – | Sign in, open Locations and create one | `smoke.spec.ts` | present |
| 2 | Admin creates a project and assigns a project lead | `projects.spec.ts` | planned |
| 3 | Team lead creates a work order in the right-side pane | `work-orders.spec.ts` | planned |
| 4 | Member finds the work order through filters and starts it | `work-orders.spec.ts` | planned |
| 5 | Member comments, uploads a permitted file, records time, completes the work order | `work-orders.spec.ts` | planned |
| 6 | Project health and operations report metrics update | `reporting.spec.ts` | planned |
| 11 | Unauthorized member cannot access a private project or perform admin actions | `authz.spec.ts` | planned |
| 12 | ASME Ops only: the legacy HTML routes (public website, `/portal`, kiosk, standalone sign-in pages, `/legacy/app`) were removed deliberately and are not served; `/app` serves the SPA including its signed-out account pages; the ops and legacy JSON APIs keep their envelopes. Legacy route compatibility no longer applies. | `legacy.spec.ts` (HTTP-level) | present |
| 13 | Forgot password → reset link → set password → sign in with the new password; invite link opens the set-password screen | `account.spec.ts` | planned (covered today by backend and Vitest tests) |
| – | Screenshots at 1440×900, 1366×768, 768×1024, 390×844 for Setup Center, Projects, Work Orders (panel, create pane, detail), Categories, Operations dashboard, sign-in and reset-password | `screens.spec.ts` (tag `@responsive`) | planned |
| – | axe accessibility scan on each core page | inside `screens.spec.ts` | planned |

Scenarios 7–10 belong to Stages 3, 5 and 6 and are tracked in `docs/implementation-status.md`.

## Manual checks before a release

1. Sign in as each seeded role and confirm the sidebar only shows permitted modules.
2. Forgot password against a real mailbox (SMTP configured): the e-mail arrives, its link opens `/app/auth/reset-password?token=...` on the public origin, works once and then reports the link as invalid.
3. Invite a new user, open the copied `invite_url` in a private window, set a password and sign in.
4. Settings > Profile: edit name and phone, change the password, sign out and back in with it.
5. Resize to 390 px: sidebar becomes a drawer, list/detail stack, create pane is full-screen with a sticky footer.
6. Turn on "reduce motion" in the OS: no pane/popover animation.
7. Tab through the work-order create pane end to end without a mouse.
8. Kill the network mid-save: the form keeps its values and shows an inline error with retry.
