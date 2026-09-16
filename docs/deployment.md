# Deployment

ASME Ops is a single Flask application (gunicorn `app:app`) plus a React frontend.
There is no public website, portal or kiosk to deploy; `/` redirects to `/app`.

**If you are the chapter officer doing this for the first time, do not read this
file.** Follow the click-by-click guides instead and come back here only when you
need to know what a setting does:

- [`deploy-render.md`](deploy-render.md) — the backend and database on Render.
- [`deploy-netlify.md`](deploy-netlify.md) — the screens on Netlify.

This file is the reference: the hosted layout, every environment variable, the
migration, background work, backups and local development.

## 1. How the hosted deployment is laid out

```
browser ──► Netlify (static screens, netlify-dist/)
              │  /api/*   forwarded ──► Render web service (Flask, gunicorn app:app)
              │  /healthz forwarded ──►        │
              └─ /app/*   served locally       └──► Render PostgreSQL
```

Two halves, two hosts, and **one address as far as the browser is concerned**.
That last part matters: `apps/ops-web/src/api/client.ts` fetches relative
`/api/v1` paths with `credentials: 'same-origin'`, and there is no CORS layer in
the application. A browser calling the Render host directly from a page served by
Netlify would send no session cookie. The Netlify proxy is what makes the cookie
first-party, which in turn is why `SESSION_COOKIE_SAMESITE=Lax` (the default) is
correct and `None` must not be set.

Two settings tie the halves together, each naming the *other* host:

| Set on | Name | Value |
|---|---|---|
| Netlify | `ASME_API_ORIGIN` | the Render origin, e.g. `https://asme-ops-api.onrender.com` |
| Render | `ASME_PUBLIC_BASE_URL` | the Netlify origin, e.g. `https://asme-ops.netlify.app` |

Both must be bare origins: scheme and host only, no path, no trailing slash. The
app refuses to start if `ASME_PUBLIC_BASE_URL` has a path; the Netlify build
fails if `ASME_API_ORIGIN` does.

### `render.yaml` is the Blueprint

Render reads `render.yaml` at the repository root and creates the services it
declares. Before the first deploy, confirm it declares **both**:

- a `databases:` entry (the PostgreSQL instance), and
- a web-service `envVars` entry `key: ASME_DATABASE_URL` with
  `fromDatabase: {name: <that database>, property: connectionString}`.

Without them the service starts happily on `sqlite:///inventory.db` inside the
container, people enter real data, and the next deploy erases it with no error
anywhere. `asme/config.py` reads `ASME_DATABASE_URL` only — Render's
auto-injected `DATABASE_URL` is ignored.

Free instances have no pre-deploy command, so `python manage.py upgrade` runs at
the front of the start command. On a paid instance, move it to the **Pre-Deploy
Command** field instead and leave the start command as the `gunicorn` line alone;
a failed migration then fails the deploy cleanly rather than taking the running
service down.

The database is created with `ipAllowList: []`, which means *no public internet
access*. Render's default for a new database is the opposite — it accepts
connections from every address, with only the generated password in the way — and
the web service never needs that route, because `ASME_DATABASE_URL` is wired with
`property: connectionString`, the private-network URL. Opening it is a deliberate
act: the database's **Access Control** page, one address, removed again
afterwards (the free-plan migration in `deploy-render.md` section 9 and backup
exports are the only two reasons).

### Files that must actually be committed

Render and Netlify build from a **clone**, so anything that is only in somebody's
working tree does not exist as far as they are concerned. Before a first deploy,
and after anyone adds deployment files, check them in one command:

```bash
git ls-files --error-unmatch render.yaml netlify.toml .python-version \
  requirements-render.txt docs/deploy-render.md docs/deploy-netlify.md
```

Every path must print. In particular:

- **`.python-version`** is what pins the interpreter to 3.13, the version every
  pin in `requirements-render.txt` publishes a wheel for. Untracked, Render uses
  its own default instead and the repository's stated guarantee is false — see
  the `PYTHON_VERSION` row in section 3 for what to set meanwhile.
- **The two guides** are what the officer doing the deploy is reading, and
  `deploy-render.md` section 9 tells them to `git clone` this repository on their
  own machine during an outage. A clone that does not contain the guide is a
  fifteen-minute recovery turned into an evening.

`Procfile` is a leftover from Heroku/Elastic Beanstalk. Render does not read it.
It is kept correct anyway — `web:` binds `0.0.0.0:${PORT:-8000}` and `release:`
runs the migration — so a host that *does* read it behaves the same way.

## 2. Build the frontend bundle

There are **two** builds of the same React app, and both are wanted:

| Build | Output | Built by | Served at |
|---|---|---|---|
| Netlify | `netlify-dist/` (assets under `/assets/`) | Netlify, on every push | the Netlify site root — this is what members use |
| Flask | `static/ops/` (assets under `/static/ops/`) | a person, and **committed** | `https://<render-host>/app` |

Keep the committed `static/ops` copy. `/` → `/app` on the Render host depends on
it, so does the invite-link fallback in `asme/blueprints/ops/auth.py` when
`ASME_PUBLIC_BASE_URL` is unset, and it is the only front door if Netlify is
down. Nothing keeps the two in step automatically, so **rebuild `static/ops` in
the same commit whenever anything under `apps/ops-web/src` changes**.

```bash
cd apps/ops-web
npm ci
npm run build          # tsc -b && vite build, writes ../../static/ops
```

On Windows machines where `npx` or the npm shims misbehave, run the binaries
through Node: `node ./node_modules/typescript/bin/tsc -b` then
`node ./node_modules/vite/bin/vite.js build`.

Without `static/ops/index.html`, `/app` on the Render host answers `503` with an
"ASME Ops frontend is not built" page. Check before deploying:

```bash
test -f static/ops/index.html && echo ok
```

Never edit files under `static/ops` by hand.

## 3. Environment variables

`.env.example` documents every variable. These are the ones a hosted deploy must
get right. [`deploy-render.md` section 13](deploy-render.md#13-every-environment-variable-explained)
has the same list written for a non-specialist, with example values.

| Variable | Required | Notes |
|---|---|---|
| `ASME_ENV` | Yes | `production`. Disables auto-migration and refuses the default secret key. |
| `ASME_SECRET_KEY` | Yes | Signs session cookies, the derived app boot token, credential fingerprints and attachment download links. Rotating it signs everyone out **and** breaks every outstanding download link. On Render use `generateValue: true` and never touch it again. |
| `ASME_DATABASE_URL` | Yes | PostgreSQL URL. SQLAlchemy 2.0 removed the `postgres://` alias, but `_database_url()` in `asme/config.py` rewrites that prefix to `postgresql://` before SQLAlchemy sees it, so a hand-copied legacy URL is accepted. Append `?sslmode=require`; without it libpq defaults to `prefer` and will silently accept an unencrypted connection. On Render, prefer the **Internal Database URL** and keep the database in the same region as the web service. A host-supplied `DATABASE_URL` is used as a fallback when this is unset — deliberately, so a service wired up with only the platform's own variable reaches the real database instead of falling back to a throwaway SQLite file. Setting a SQLite URL in production is refused outright. |
| `ASME_PUBLIC_BASE_URL` | Yes in production | The **Netlify** origin, e.g. `https://asme-ops.netlify.app`. Bare origin only. Used for password-reset and invitation links. Becomes a hard startup requirement as soon as both `ASME_SMTP_USER` and `ASME_SMTP_PASS` are set. |
| `ASME_SESSION_COOKIE_SECURE` | Yes in production | Set `1`. The default is `bool(os.environ.get("RENDER"))`, i.e. it depends on a platform variable this repository does not control — pin it explicitly. |
| `ASME_DEFAULT_ADMIN_PASSWORD` | **Yes, always, in production** | Read **only** when the bootstrap administrator row is created. The fallback is the literal `ChangeMe123!` printed in `asme/config.py` in a public repository, and `ASME_DEFAULT_ADMIN_EMAIL` is published in `render.yaml`, so `validate()` **refuses startup** when it is empty, equal to that fallback, or shorter than 8 characters. Change the password inside the app after first sign-in, then rotate this variable to a different value. |
| `ASME_DEFAULT_USER_PASSWORD` | **Yes, always, in production** | Given to every account created by a roster import (`seed_defaults`). Refused on exactly the same three conditions as the admin one. `render.yaml` sets it with `generateValue: true`: roster-imported people get in through an invite link or forgot-password, so nobody needs to know the value. |
| `ASME_DEFAULT_ADMIN_EMAIL` | No (`admin@uiowa.edu`) | **Do not change it after the first deploy.** `seed_defaults()` runs on every deploy and re-creates the bootstrap administrator whenever no user holds exactly this address, using whatever `ASME_DEFAULT_ADMIN_PASSWORD` currently is. |
| `ASME_SMTP_HOST` / `ASME_SMTP_PORT` / `ASME_SMTP_USER` / `ASME_SMTP_PASS` | **Yes for forgot-password** | Reset mail is queued in the outbox (`mail.send`). Without user+pass nobody receives a link, and the HTTP endpoint still answers as though one was sent (deliberate — it must not reveal which addresses exist). User and pass must be set together or startup refuses. Invitations are **not** e-mailed: the inviting admin copies `invite_url` from the invite dialog on the Users screen. |
| `ASME_TRUSTED_PROXY_COUNT` | Behind a proxy | Number of proxies in front of the app that append to `X-Forwarded-For`; `request_client_ip()` takes the *n*-th entry from the right. `2` is correct for browser → Netlify → Render, but Render does not document its hop count — confirm it by logging a raw `X-Forwarded-For` from a known address before relying on per-IP rate limiting. With `0` every visitor shares the proxy's address. Residual risk at any value: a request sent straight to the `.onrender.com` host skips Netlify, so its chain is one entry short and the caller's own forged value is returned. That can pick a rate-limit bucket and poison an audit row; it cannot defeat the identifier-only counter. |
| `ASME_AUTO_MIGRATE` | No | `0` in production. Otherwise `create_app` runs Alembic inside every gunicorn worker concurrently. Defaults to `env != "production"`, so production is safe even if unset. |
| `ASME_APP_BOOT_TOKEN` | No | Defaults to a value derived from `ASME_SECRET_KEY`, identical in every worker and across restarts. Set a new value only to sign every user out (for example after a suspected session leak); unlike rotating the secret key, this does not break download links. |
| `ASME_STORAGE_BACKEND` | No (default `local`) | Only `local` is implemented; `s3` is declared but raises, and startup refuses it. |
| `ASME_UPLOAD_ROOT` | One of these two, in production | Absolute path for private uploads; defaults to `<instance_path>/uploads`. Must **not** be inside `static/`, and a relative value is refused. Point it at a mounted disk. |
| `ASME_UPLOADS_EPHEMERAL_OK` | One of these two, in production | `1` is the written acknowledgement that there is no persistent disk and attachments are erased on every deploy and restart while their database rows survive. With neither this nor `ASME_UPLOAD_ROOT`, `validate()` refuses startup — see section 6. |
| `ASME_UPLOAD_MAX_MB` | No (25) | Per-file limit; also raises Flask `MAX_CONTENT_LENGTH`. |
| `ASME_OPS_POLL_SECONDS` | No (15) | How often the SPA polls `/api/v1/changes`. This is a short poll, not a long poll. |
| `ASME_OPS_DOWNLOAD_TTL_SECONDS` | No (300) | Lifetime of signed attachment download links. |
| `ASME_OUTBOX_WORKER` | No (on) | Runs the outbox thread inside the web process. Do not turn it off without reading section 5. |
| `PYTHON_VERSION` | **Only while `.python-version` is untracked** | The interpreter version is meant to come from `.python-version` at the repository root, which says `3.13`. Every pin in `requirements-render.txt` publishes a `cp313` Linux wheel (verified by resolving the file against `--platform manylinux2014_x86_64 --python-version 3.13 --abi cp313`), so the build never compiles from source. Render builds a **clone**, so that file only reaches it if it is committed on the deploy branch — check with `git ls-files --error-unmatch .python-version`. While it is not, Render falls back to its own default (newer than 3.13 and rising over time) and the honest fix is to set `PYTHON_VERSION=3.13` in the dashboard until the file is committed. Never point it at an interpreter *older* than 3.13: that reintroduces the source-build failure the pins avoid. Render ignores `runtime.txt`. |

The remaining variables in `.env.example` (calendar, printing, and the other
legacy integrations) only affect the backend services that remain in
`asme/services` without a UI, and can be left unset on a first deploy.

### Configuration failures

`Settings.validate()` returns a list of problems and `create_app` raises
`RuntimeError("Refusing to start with invalid configuration:")`, listing each
one. The ones that realistically stop a deploy: a blank or published
`ASME_DEFAULT_ADMIN_PASSWORD` / `ASME_DEFAULT_USER_PASSWORD`; an unset or default
`ASME_SECRET_KEY`; `ASME_PUBLIC_BASE_URL` with a path, query or fragment;
`ASME_PUBLIC_BASE_URL` missing while SMTP is configured; a SQLite
`ASME_DATABASE_URL`; neither `ASME_UPLOAD_ROOT` nor `ASME_UPLOADS_EPHEMERAL_OK`;
and `ASME_STORAGE_BACKEND=s3`.

**Declared vs assumed production.** `Settings.env` still defaults to
`production` when `ASME_ENV` is unset, so an unconfigured deployment gets
production behaviour. The *refusal*, though, needs production to have been
**declared** — `ASME_ENV`, an explicit override, or a hosting platform's own
variable (`RENDER`, `DYNO`, `FLY_APP_NAME`, `K_SERVICE`, … see
`HOSTED_PLATFORM_VARS`). Everywhere else — a checkout on a student's laptop
running `python manage.py upgrade` against the hosted database, which is the
documented free-plan recovery path — the same problems are logged in full, led by
a line saying they would be fatal on a host. Without that split, cookie and
upload settings that a migration never touches would block the one command that
repairs a broken schema. The accounts themselves are not left to that leniency:
`manage.py`'s `seed_guard` re-checks the bootstrap passwords on any non-SQLite
database before `seed_defaults` can create a user with one.

`Settings.warnings()` only logs: `ASME_SESSION_COOKIE_SECURE` off in production,
`ASME_PUBLIC_BASE_URL` unset, ephemeral uploads acknowledged,
`ASME_TRUSTED_PROXY_COUNT` at 0, no calendar credentials. None of these block
startup, so a silent misconfiguration is possible — check the log lines prefixed
`config:` after the first deploy.

## 4. Database migration

```bash
python manage.py upgrade      # alembic upgrade to head + idempotent seeds
```

It prints two lines, and they are the acceptance test for a hosted deploy:

```
schema: upgraded
seed: {'users': 1}
```

`schema: upgraded` (or `stamped-baseline+upgraded` on a legacy SQLite database)
means Alembic reached head. `seed:` reports how many users were created — `1` on
a first run against an empty database (the bootstrap administrator), `0` on every
subsequent deploy.

Take a backup first regardless:

- PostgreSQL: `pg_dump -Fc "$ASME_DATABASE_URL" > backup-$(date +%F).dump`
- SQLite: copy `instance/inventory.db`

Rollback: `python -m flask --app app db downgrade 0002_launchpad`.

### Known PostgreSQL issues

- **No migration in this repository has ever been run against a real PostgreSQL
  server.** The DDL has been rendered and checked against the PostgreSQL dialect
  (native `UUID`, `JSONB` via `asme/ops/types.py`, `SERIAL` primary keys,
  `render_as_batch` emitting plain `ALTER TABLE` rather than table copies,
  constraint names truncating consistently at PostgreSQL's 63-character limit),
  but the data-backfill statements have not been executed. `tests/ops/test_migration.py`
  and `tests/ops/test_migration_0004.py` both hard-code a SQLite file.
- **`0002_launchpad` used to write integers into boolean columns** in
  `_backfill_data()` — `UPDATE projects SET is_joinable = 1`, and
  `COALESCE(is_consumable, 0)` / `COALESCE(active, 1)`. PostgreSQL type-checks
  those at parse time and rejects them even against an empty table (`column
  "is_joinable" is of type boolean but expression is of type integer`), while
  SQLite accepts them, which is why it never surfaced in the test suite. **Fixed:**
  the file now writes `true` / `false`. Anyone deploying an older commit still
  hits it; the fix is those three literals and nothing else.
- **Offline SQL generation is unavailable.** `flask db upgrade --sql` fails,
  because `0002` reads rows (`bind.execute(...).fetchall()`). Migrations must run
  against a live connection.

### Engine settings

`_engine_options()` in `asme/__init__.py` sets `SQLALCHEMY_ENGINE_OPTIONS` from
the database URL:

- **PostgreSQL:** `pool_pre_ping=True, pool_size=5, max_overflow=5,
  pool_recycle=280`. The ping is the one that matters on a managed database — a
  connection dropped during an idle period (a restart, maintenance, a free web
  instance spinning down) is discovered and replaced instead of being handed to
  the next visitor as a 500. `pool_recycle=280` retires connections before the
  usual five-minute idle timeout upstream. Ten connections at most per process;
  a Render Basic-256mb instance allows far more.
- **SQLite:** `pool_pre_ping=True` only. Its pool implementation takes no size
  arguments and raises at engine creation if they are passed, so development and
  the test suite must not get them.

Both shapes are checked against `sqlalchemy.create_engine` without opening a
socket, so a mistake here fails locally rather than on the first deploy.

## 5. Background work

The outbox worker runs as a **daemon thread inside the web process**, started
from a `before_request` hook on the first request. ASME Ops uses it for
password-reset e-mail, an hourly `ops.work_order.scan` (overdue and due-soon
notifications, missed milestones) and a daily `stock.reconcile`.

Three things follow from that, all of which matter on a hosted deploy:

- **It sleeps when the web service sleeps.** On a free instance that spins down
  after 15 minutes of inactivity, a queued reset e-mail waits for the next
  visitor. Any request revives it, including `GET /healthz`, so a 10-minute
  uptime ping keeps it running — at the cost of the free monthly instance-hour
  budget.
- **More than one worker is safe, but one is still the right number.** `_claim`
  in `asme/jobs/outbox.py` is a conditional `UPDATE ... WHERE status='pending'`
  committed before the handler runs, so a job never executes twice.
  `ensure_recurring` now goes through `enqueue_once` with a fixed-window
  idempotency key (`recurring:<kind>:<window>`), which every process computes
  identically for the same moment, so the `uq_outbox_jobs_idempotency_key` index
  lets exactly one of them win the insert. Verified by running two app processes
  against one database: one job enqueued, one execution recorded, and exactly one
  row per recurring kind despite two schedulers. **Run a single gunicorn worker
  anyway** (`--workers 1 --threads 4`): it halves memory on a 512 MB instance and
  stops the in-memory login rate limiter's allowance being multiplied by the
  worker count, which is per-process and not shared.
- **A dedicated worker process is now a complete replacement.** `python manage.py
  worker` calls `schedule_recurring()` as well as `process_pending()`, so setting
  `ASME_OUTBOX_WORKER=0` on the web service and running a separate worker keeps
  the hourly scan and the daily reconcile. Render has no free background worker,
  so on the free plan keep `ASME_OUTBOX_WORKER=1`; the split is a two-variable
  change on the day a paid worker service exists. The older Flask CLI variant
  (`flask run-jobs --loop`) still only processes and does not schedule.

```bash
python manage.py worker      # processes queued jobs AND schedules recurring ones
```

### When a job gives up

`outbox.RETRY_POLICY` sets how long a kind keeps trying: `(attempts, longest gap
between attempts)`, defaulting to `(5, 3600)`. Five attempts with the default
backoff are all spent inside about eight minutes, which is shorter than any real
mail outage, so `auth.password_reset` and `mail.send` use `(10, 6h)` — roughly
four hours of retrying, which rides out a blocked SMTP port, a throttle, or an
app password rotated at officer handover.

When the attempts do run out, `_run_one` marks the job `failed` and then calls the
kind's `@failure_handler`. For the two mail kinds that hook writes a `job.failed`
audit event on the chapter (`entity_type="outbox_job"`, so it is in
`ops_audit_events` for anyone investigating, and *not* in the members' `/changes`
feed — `changes._readable_ids` deliberately drops entity types nobody has written
a visibility rule for) and notifies every active `chapter_admin` membership, which
is the part a person actually sees. That is the whole point: a member who asked
for a password reset is told "check your e-mail" before anything is sent —
correctly, since the response must not reveal which addresses are members — so
without this the failure existed only as one log line on a plan that keeps logs
for seven days, and the officer had nowhere to look. The hook is committed
separately and anything it raises is logged, never re-failing the job.

`outbox.stats()` and `outbox.recent_failures()` are the read side; no blueprint
exposes them yet, so for now a failed job is read from the change feed, the
notification, or the log.

## 6. Uploads

`build_storage` writes attachments under `ASME_UPLOAD_ROOT`, or
`<instance_path>/uploads` when it is unset — on Render, inside the container at
`/opt/render/project/src/instance`.

**A free Render web service has no persistent disk.** Every deploy, restart and
wake-from-sleep gives a fresh filesystem. Attachment rows survive in PostgreSQL
and keep pointing at storage keys whose bytes are gone; `storage.open()` then
raises `FileNotFoundError` on download. Pick one, and write the choice into the
chapter's runbook:

1. **Free.** Tell officers not to attach files yet. Leave `ASME_UPLOAD_ROOT`
   unset. No code change.
2. **Paid.** Move the web service to the smallest paid instance, attach a Render
   disk (about $0.25 per GB per month) mounted at `/var/asme-uploads`, and set
   `ASME_UPLOAD_ROOT=/var/asme-uploads`. No code change. Note that disks are
   incompatible with more than one instance.
3. **Object storage.** Implement the S3 adapter that `asme/ops/storage.py` and
   `Settings.validate()` are already stubbed for. This is a feature, not a deploy
   setting.

## 7. Backups and restore

- **Database.** On a paid Render PostgreSQL instance, point-in-time recovery
  covers roughly the last 3 days on a Hobby workspace and is driven from the
  database's recovery page in the dashboard, alongside a downloadable logical
  export retained about 7 days. That is not a backup policy on its own: a mistake
  nobody notices until the following week is already out of range. Take a
  downloadable export at least once a semester and keep it off Render.
  **Free Render PostgreSQL supports no backups of any kind**, and Render deletes
  the database 30 days after creation plus a 14-day grace period — so real
  chapter data should not live on it.
- From your own machine: `pg_dump -Fc "$ASME_DATABASE_URL" > backup-$(date +%F).dump`,
  restore with `pg_restore -d <db> <file>`. Use the **External Database URL** for
  this; the internal one only resolves from inside Render. `render.yaml` declares
  `ipAllowList: []`, so that external route is closed until you add your own
  address under the database's **Access Control** — add it for the export,
  remove it afterwards.
- **A Render point-in-time restore creates a NEW database instance with a NEW
  connection string.** It does not rewind the existing one, and the Blueprint's
  `fromDatabase: {name: asme-ops-db}` link keeps pointing at the old instance.
  After restoring, set `ASME_DATABASE_URL` on the web service by hand to the new
  instance's Internal Database URL (plus `?sslmode=require`), redeploy, confirm
  the data is there, set the new instance's Access Control to empty, and only
  then delete the old one.
- **Uploads.** Back up the `ASME_UPLOAD_ROOT` directory together with the
  database dump. Attachment rows reference files by `storage_key`, so a database
  restored on its own leaves every download broken.
- After a restore, run `python manage.py upgrade` (a no-op when already at head)
  and keep the same `ASME_SECRET_KEY`, so existing sessions and outstanding
  download links stay valid.

## 8. Release steps

1. Merge with the rebuilt `static/ops` bundle if anything under
   `apps/ops-web/src` changed.
2. Confirm the variables in section 3 are set on the Render service — especially
   `ASME_DATABASE_URL`, `ASME_SECRET_KEY` and `ASME_PUBLIC_BASE_URL`.
3. Push. Render redeploys on every push to the linked branch by default; Netlify
   rebuilds the screens independently. A commit message containing
   `[skip render]` skips the backend deploy.
4. Watch the Render log for `schema: upgraded` followed by `seed:`. If a command
   fails or times out the whole deploy fails and the previous version keeps
   serving, with no downtime.
5. Smoke test:
   - `https://<render-host>/healthz` returns `{"ok": true, "status": "ok",
     "service": "asme-web"}`.
   - `https://<netlify-host>/healthz` returns the same thing — this is what
     proves the Netlify proxy rule was built and points at the right backend.
   - `https://<netlify-host>/` shows the sign-in screen at `/app/auth/login`.
     Sign in, confirm the Setup Center loads and the Work Orders list renders.
   - On `/app/auth/forgot-password`, request a reset for a real account and
     confirm the e-mail arrives with a link to
     `<ASME_PUBLIC_BASE_URL>/app/auth/reset-password#token=...`. The token is
     after a `#` on purpose: a URL fragment is never sent to the server, so it
     cannot appear in Netlify's, Render's or any other proxy's access logs.
   - Create a record, redeploy, and confirm it is still there. This is the only
     check that catches a service running on ephemeral SQLite.
6. Platform health checks must target `/healthz`, not `/`, because `/` is a
   redirect. `/healthz` is unauthenticated, excluded from the request log, and
   returns a static JSON 200 with no database access — so it passes even while the
   database is unreachable. It proves the process is up, not that the app works.

## 9. Observability

`asme/logging_setup.py` attaches one JSON handler on stdout, which is exactly
what Render captures. Each request logs one structured line with `request_id`,
method, path, status, `duration_ms`, `user_id` and endpoint; `/static/` and
`/healthz` are excluded so health checks do not flood the log, and
token-bearing path variables are redacted. The same `request_id` is returned in
the `X-Request-Id` response header, which gives a string to search the log for
when someone reports a problem.

JSON error handlers are registered for 404, 405 and unhandled exceptions, so an
`/api/` route that fails unexpectedly answers with
`{"ok": false, "code": "server_error", …, "request_id": …}` rather than Flask's
HTML 500 page, and the SPA shows a message instead of a blank breakage. The
`request_id` in the body is the same one in `X-Request-Id` and in the log line.
Outside `/api/` Flask's own behaviour is untouched, and `PROPAGATE_EXCEPTIONS`
(on in testing and debug) still re-raises so tracebacks are not swallowed.

## 10. Dependency drift

`requirements-render.txt` pins exact versions while `requirements.txt` allows
ranges (`Flask>=3.0,<4.0`, `pandas>=2.2,<3.1`). The two are currently in
agreement: every pin in `requirements-render.txt` is the version installed in the
development virtualenv the test suite runs in, so the deployed stack is the stack
the tests exercise. Keep it that way — after upgrading a package locally and
re-running the suite, copy the new version into the pinned file.

Two properties to preserve when changing a pin:

- Every pin must publish a Linux `cp313` wheel, matching `.python-version`.
  Check without installing anything:
  `pip download --only-binary=:all: --no-deps --platform manylinux2014_x86_64
  --python-version 3.13 --implementation cp --abi cp313 --abi abi3 --abi none
  -d /tmp/wheels -r requirements-render.txt`. A pin with no wheel makes Render
  compile from source, and `psycopg2-binary` in particular then fails for want of
  `pg_config`.
- `psycopg2-binary` must stay at 2.9.12 or newer: 2.9.9 publishes nothing for
  Python 3.13.

## 11. Known defects, not yet fixed

Both are in code this deployment work is not allowed to touch (Stage 4 owns those
paths); both are one-line fixes, and both are written up for the officer in
[`deploy-render.md` section 17](deploy-render.md#17-two-known-quirks-to-tell-officers-about).

- **Milestones flip to `missed` on the server's UTC date.**
  `asme/ops/services/scans.py::_mark_missed_milestones` takes `today =
  now.date()` from a UTC instant while the chapter is in Iowa, so a milestone due
  the 16th is marked missed at 19:00 local on the 16th (18:00 in winter) and an
  audit event goes out. `Organization.timezone` already holds `America/Chicago`
  and `asme.ops.services.dashboard.resolve_range` already uses it. Fix:
  `today = now.astimezone(org_timezone(ctx.org)).date()`.
- **Password reset is rate-limited per address only, and the whole campus shares
  one address.** `asme/blueprints/ops/auth.py::reset_password` passes the client
  IP as both key components (`counter = ip`), so `LoginRateLimiter`'s two
  counters describe the same bucket and the identifier counter — whose comment
  says it exists so "a shared campus NAT does not lock a real member out" — buys
  nothing. Eight stale links clicked from campus wifi inside
  `ASME_LOGIN_RATE_WINDOW_SECONDS` block every other member, including one
  holding a valid link. Fix: key the second counter on the token or the account
  (`change_password` in the same file does this), and resolve the token before
  applying an address block, since a 32-byte `secrets.token_urlsafe` is not what
  the limiter is protecting against. `tests/deploy/test_deploy_operations_2.py`
  and `_3.py` fail until these land.

## 12. Local development

```bash
python manage.py upgrade
python app.py                        # http://127.0.0.1:5000 (redirects to /app)
cd apps/ops-web && npm run dev       # http://127.0.0.1:5173/app (proxies /api to :5000)
```

Or serve the built bundle from Flask: `npm run build` then open
`http://127.0.0.1:5000/app`. Without SMTP in development, the outbox worker logs
the reset link as a warning (keep `ASME_OUTBOX_WORKER` on, or run
`python manage.py worker`).
