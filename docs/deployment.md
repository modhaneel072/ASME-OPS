# Deployment

ASME Ops ships inside the existing Flask application, so the deployment targets do not change (Render, Elastic Beanstalk, or any gunicorn host). Two things are new: the operations frontend must be **built** before deploy, and a few environment variables must be set.

## 1. Build the frontend bundle

The React app in `apps/ops-web` compiles to `static/ops/` (hashed assets plus `index.html`). Flask serves it at `/app`.

```bash
cd apps/ops-web
npm ci
npm run build          # writes ../../static/ops
```

The Python hosts in use (Render, Elastic Beanstalk) do not run Node during deploy, so **commit the built `static/ops/` folder** with the change that produced it, or add a CI job that runs the build before packaging. Never edit files under `static/ops` by hand.

Check the bundle is present before deploying:

```bash
test -f static/ops/index.html && echo ok
```

## 2. Environment variables

All existing variables keep their meaning (see `.env.example`). New or newly important:

| Variable | Required | Notes |
|---|---|---|
| `ASME_APP_BOOT_TOKEN` | **Yes, on any host with more than one worker/process** | Sessions carry this token; when it differs per process users are logged out as requests alternate between workers. Set one long random value per environment (`python -c "import secrets;print(secrets.token_hex(32))"`). |
| `ASME_STORAGE_BACKEND` | No (default `local`) | Only `local` is implemented. Files are written under `ASME_UPLOAD_ROOT` or `instance/uploads/`. On ephemeral hosts (Render free tier) mount a persistent disk at that path or uploads are lost on redeploy. |
| `ASME_UPLOAD_ROOT` | No | Absolute path for private uploads. Must **not** be inside `static/`. |
| `ASME_UPLOAD_MAX_MB` | No (25) | Per-file limit; also raises Flask `MAX_CONTENT_LENGTH`. |
| `ASME_OPS_POLL_SECONDS` | No (15) | How often the SPA polls `/api/v1/changes`. |
| `ASME_OPS_DOWNLOAD_TTL_SECONDS` | No (300) | Lifetime of signed attachment download links. |
| `ASME_SESSION_COOKIE_SECURE` | Yes in production | Must be `1` behind HTTPS. |
| `ASME_SECRET_KEY` | Yes | Also signs download tokens; rotating it invalidates outstanding links and sessions. |

## 3. Database migration

```bash
python manage.py upgrade      # alembic upgrade to head + idempotent seeds (default org, roles, memberships)
```

Migration `0003_ops_foundation` is additive. Take a backup first regardless:

- PostgreSQL: `pg_dump -Fc "$ASME_DATABASE_URL" > backup-$(date +%F).dump`
- SQLite: copy `instance/inventory.db`

Rollback: `python -m flask --app app db downgrade 0002_launchpad` (drops only `ops_*` tables and `outbox_jobs.idempotency_key`).

The migration has been exercised on SQLite. Run it against a PostgreSQL copy of production in staging before the first production release; `tests/ops/test_migration.py` is the automated check and accepts any SQLAlchemy URL through `ASME_DATABASE_URL` when adapted for CI.

## 4. Release steps (Render / EB)

1. Merge with the built `static/ops` bundle.
2. Ensure the variables above are set (especially `ASME_APP_BOOT_TOKEN`).
3. Deploy; the existing release command runs `python manage.py upgrade`.
4. Smoke test: `GET /healthz`, `GET /api/v1/health`, open `/app` and sign in with an admin account, confirm the Setup Center loads and the Work Orders list renders.
5. Never run `python manage.py seed-ops` in production; it refuses when `ASME_ENV=production`, but do not try.

## 5. Background work

The outbox worker still runs as a daemon thread inside the web process (started on the first request). ASME Ops adds an hourly `ops.work_order.scan` job (overdue and due-soon notifications, missed milestones). For higher reliability run a dedicated worker:

```bash
python manage.py worker
```

## 6. Backups and restore

- Database: nightly `pg_dump -Fc`; restore with `pg_restore -d <db> <file>`.
- Uploads: back up the `ASME_UPLOAD_ROOT` directory together with the database dump; attachment rows reference files by `storage_key`.
- After a restore, run `python manage.py upgrade` (no-op when already at head) and re-set `ASME_APP_BOOT_TOKEN` if the environment was rebuilt.

## 7. Local development

```bash
python manage.py upgrade
python manage.py seed-ops            # dev-only demo data, prints credentials
python app.py                        # http://127.0.0.1:5000
cd apps/ops-web && npm run dev       # http://127.0.0.1:5173/app (proxies /api to :5000)
```

Or serve the built bundle from Flask: `npm run build` then open `http://127.0.0.1:5000/app`.
