# Deployment

ASME Ops is a single Flask application (gunicorn `app:app`) with a React frontend served from `static/ops` at `/app`. It deploys to Render, Elastic Beanstalk or any gunicorn host. The repository contains nothing else: there is no public website, portal or kiosk to deploy, and `/` redirects to `/app`.

## 1. Build the frontend bundle

The React app in `apps/ops-web` compiles to `static/ops/` (hashed assets plus `index.html`). Flask serves it at `/app`; without it `/app` answers `503` with an "ASME Ops frontend is not built" page.

```bash
cd apps/ops-web
npm ci
npm run build          # tsc -b && vite build, writes ../../static/ops
```

On Windows machines where `npx` or the npm shims misbehave, run the binaries through Node: `node ./node_modules/typescript/bin/tsc -b` then `node ./node_modules/vite/bin/vite.js build`.

The Python hosts in use (Render, Elastic Beanstalk) do not run Node during deploy, so **commit the built `static/ops/` folder** with the change that produced it, or add a CI job that runs the build before packaging. Never edit files under `static/ops` by hand.

Check the bundle is present before deploying:

```bash
test -f static/ops/index.html && echo ok
```

## 2. Environment variables

`.env.example` documents every variable. The ones a production deploy must get right:

| Variable | Required | Notes |
|---|---|---|
| `ASME_ENV` | Yes | `production`. Disables auto-migration and refuses the default secret key. |
| `ASME_SECRET_KEY` | Yes | Also signs download tokens; rotating it invalidates outstanding links and sessions. |
| `ASME_DATABASE_URL` | Yes | PostgreSQL URL. |
| `ASME_APP_BOOT_TOKEN` | No | Defaults to a value derived from `ASME_SECRET_KEY`, identical in every worker and across restarts. Set a new value only to sign every user out (for example after a suspected session leak). |
| `ASME_SESSION_COOKIE_SECURE` | Yes in production | Must be `1` behind HTTPS. |
| `ASME_PUBLIC_BASE_URL` | Yes in production | Public origin such as `https://ops.example.org`, used for password reset and invite links (`<origin>/app/auth/reset-password?token=...`). Without it links are built from the request `Host` header and startup logs a warning. |
| `ASME_SMTP_HOST` / `ASME_SMTP_PORT` / `ASME_SMTP_USER` / `ASME_SMTP_PASS` | **Yes for forgot password** | Forgot-password mail is queued in the outbox (`mail.send`); without `ASME_SMTP_USER` and `ASME_SMTP_PASS` the jobs fail and nobody receives a link. Invitations are not e-mailed: the inviting admin copies `invite_url` from the invite dialog on the Users screen. |
| `ASME_TRUSTED_PROXY_COUNT` | Behind a proxy or load balancer | Number of proxies in front of the app that append to `X-Forwarded-For`; check your platform's proxy chain before setting it, because a value that is too high lets clients choose their own address. With `0` every client shares the proxy address for rate limiting. |
| `ASME_STORAGE_BACKEND` | No (default `local`) | Only `local` is implemented. Files are written under `ASME_UPLOAD_ROOT` or `instance/uploads/`. On ephemeral hosts (Render free tier) mount a persistent disk at that path or uploads are lost on redeploy. |
| `ASME_UPLOAD_ROOT` | No | Absolute path for private uploads. Must **not** be inside `static/`. |
| `ASME_UPLOAD_MAX_MB` | No (25) | Per-file limit; also raises Flask `MAX_CONTENT_LENGTH`. |
| `ASME_OPS_POLL_SECONDS` | No (15) | How often the SPA polls `/api/v1/changes`. |
| `ASME_OPS_DOWNLOAD_TTL_SECONDS` | No (300) | Lifetime of signed attachment download links. |

The calendar, printer and assistant variables in `.env.example` only affect the legacy backend services that remain in `asme/services` without a UI.

## 3. Database migration

```bash
python manage.py upgrade      # alembic upgrade to head + idempotent seeds (default org, roles, memberships)
```

Migration `0003_ops_foundation` is additive. Take a backup first regardless:

- PostgreSQL: `pg_dump -Fc "$ASME_DATABASE_URL" > backup-$(date +%F).dump`
- SQLite: copy `instance/inventory.db`

Rollback: `python -m flask --app app db downgrade 0002_launchpad` (drops only `ops_*` tables and `outbox_jobs.idempotency_key`).

The migration has been exercised on SQLite. Run it against a PostgreSQL copy of production in staging before the first production release; `tests/ops/test_migration.py` is the automated check and accepts any SQLAlchemy URL through `ASME_DATABASE_URL` when adapted for CI.

Removing the legacy HTML pages did not change the schema: legacy tables (members, items, checkouts, attendance and so on) keep their data.

## 4. Release steps (Render / EB)

1. Merge with the built `static/ops` bundle (or let CI build it).
2. Ensure the variables above are set (especially `ASME_SECRET_KEY`, `ASME_PUBLIC_BASE_URL` and the SMTP credentials).
3. Deploy; the release command runs `python manage.py upgrade` (`Procfile` `release:`, `render.yaml` `startCommand`, `.ebextensions/03_migrate.config`).
4. Smoke test:
   - `GET /healthz` and `GET /api/v1/health` return 200.
   - `GET /` redirects to `/app`.
   - Open `/app`; it shows the sign-in screen at `/app/auth/login`. Sign in with an admin account and confirm the Setup Center loads and the Work Orders list renders.
   - On `/app/auth/forgot-password`, request a reset for a real account and confirm the e-mail arrives with a link to `/app/auth/reset-password?token=...` on the public origin.
5. Platform health checks must target `/healthz` (configured in `render.yaml` and `.ebextensions/01_python.config`) because `/` is a redirect.

## 5. Background work

The outbox worker runs as a daemon thread inside the web process (started on the first request). ASME Ops uses it for password reset e-mail and an hourly `ops.work_order.scan` job (overdue and due-soon notifications, missed milestones). For higher reliability run a dedicated worker:

```bash
python manage.py worker
```

## 6. Backups and restore

- Database: nightly `pg_dump -Fc`; restore with `pg_restore -d <db> <file>`.
- Uploads: back up the `ASME_UPLOAD_ROOT` directory together with the database dump; attachment rows reference files by `storage_key`.
- After a restore, run `python manage.py upgrade` (no-op when already at head) and keep the same `ASME_SECRET_KEY` so existing sessions and download links stay valid.

## 7. Local development

```bash
python manage.py upgrade
python app.py                        # http://127.0.0.1:5000 (redirects to /app)
cd apps/ops-web && npm run dev       # http://127.0.0.1:5173/app (proxies /api to :5000)
```

Or serve the built bundle from Flask: `npm run build` then open `http://127.0.0.1:5000/app`. Without SMTP in development, the outbox worker logs the reset link as a warning (keep `ASME_OUTBOX_WORKER` on, or run `python manage.py worker`).
