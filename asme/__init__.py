"""ASME @ UIowa web platform - application factory."""

from __future__ import annotations

import logging
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, g, request, session

from asme.auth.rate_limit import LoginRateLimiter
from asme.config import Settings, load_instance_env_file
from asme.extensions import db, migrate

ROOT = Path(__file__).resolve().parent.parent
log = logging.getLogger("asme")

__version__ = "2.0.0"


def _engine_options(database_url: str) -> dict:
    """Connection-pool settings for the database behind ``database_url``.

    ``pool_pre_ping`` is the one that matters on hosted PostgreSQL: the database
    closes idle connections (maintenance, restarts, an instance that spun down
    overnight), and without a ping the first click after a quiet period hands the
    member a 500 instead of quietly reconnecting.

    The size limits are deliberately small. A chapter of a couple of hundred
    people never needs more, and a small managed database counts every open
    connection against a fixed ceiling shared with the migration command and any
    worker process.

    SQLite gets only the ping: its pool implementation takes no size arguments,
    and passing them raises at engine creation.
    """
    options: dict = {"pool_pre_ping": True}
    if not database_url.startswith("sqlite"):
        options.update(pool_size=5, max_overflow=5, pool_recycle=280)
    return options


def create_app(settings: Settings | None = None, **overrides) -> Flask:
    """Build the Flask app.

    ``overrides`` are applied on top of the environment-derived settings, which
    is how tests get an in-memory database and no background worker.
    """
    load_dotenv(ROOT / ".env")
    instance_path = ROOT / "instance"
    instance_path.mkdir(parents=True, exist_ok=True)
    load_instance_env_file(instance_path / "print_commands.env")

    cfg = settings or Settings.from_env(**overrides)

    app = Flask(
        __name__,
        static_folder=str(ROOT / "static"),
        instance_path=str(instance_path),
    )
    app.config.update(
        SETTINGS=cfg,
        SECRET_KEY=cfg.secret_key,
        SQLALCHEMY_DATABASE_URI=cfg.database_url,
        SQLALCHEMY_ENGINE_OPTIONS=_engine_options(cfg.database_url),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SESSION_COOKIE_SAMESITE=cfg.session_cookie_samesite,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=cfg.session_cookie_secure,
        SESSION_PERMANENT=False,
        TESTING=cfg.is_testing,
        MAX_CONTENT_LENGTH=max(cfg.print_max_upload_bytes, cfg.upload_max_bytes, 64 * 1024 * 1024),
    )

    problems = cfg.validate()
    if problems:
        if cfg.is_production and cfg.env_declared:
            raise RuntimeError("Refusing to start with invalid configuration:\n- " + "\n- ".join(problems))
        if cfg.is_production:
            # Production was assumed, not declared: no ASME_ENV and no hosting
            # platform variable, which is a checkout on somebody's own computer
            # running a one-shot command (``python manage.py upgrade`` against
            # the hosted database is the documented recovery path). Refusing over
            # cookie and upload settings that command never uses would leave the
            # owner with no way to repair the schema, so the problems are logged
            # in full instead - with the sentence that says they are fatal on a
            # host, so this can never be mistaken for a clean start.
            log.warning(
                "config: ASME_ENV is not set and no hosting platform was detected, so these "
                "settings are being reported instead of refused. On a hosting platform (with "
                "ASME_ENV=production) the app would refuse to start until they are fixed:"
            )
        for problem in problems:
            log.warning("config: %s", problem)
    for note in cfg.warnings():
        log.warning("config: %s", note)

    if cfg.trusted_proxy_count:
        # Behind a CDN and a platform router the socket is plain HTTP, so
        # ``request.host_url`` comes out as http:// and any link built from it
        # (the invite-link fallback) is wrong. Trust only the scheme header, and
        # only when the deployment has declared that proxies are in front of it.
        # remote_addr is deliberately left alone: asme.utils.http.request_client_ip
        # does its own counted read of X-Forwarded-For and must stay the single
        # place that decides what a client address is.
        from werkzeug.middleware.proxy_fix import ProxyFix

        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=0, x_proto=1, x_host=0, x_port=0, x_prefix=0)

    # -- extensions ------------------------------------------------------------
    db.init_app(app)
    migrate.init_app(app, db, directory=str(ROOT / "migrations"), render_as_batch=True)
    app.extensions["asme_login_rate_limiter"] = LoginRateLimiter(cfg.login_rate_window_seconds, cfg.login_rate_max_attempts)

    from asme.integrations.calendar import build_provider

    app.extensions["asme_calendar_provider"] = build_provider(cfg)

    # -- wiring ----------------------------------------------------------------
    from asme.blueprints import register_blueprints
    from asme.logging_setup import configure_logging
    from asme.services.onboarding import register_event_handlers
    import asme.jobs  # noqa: F401  (registers outbox handlers)

    configure_logging(app)
    register_blueprints(app)
    register_event_handlers()
    _register_request_hooks(app, cfg)
    _register_cli(app)

    # -- schema / seeds / worker ----------------------------------------------
    if cfg.auto_migrate and not cfg.is_testing:
        from asme.services import bootstrap

        with app.app_context():
            try:
                outcome = bootstrap.sync_schema()
                bootstrap.seed_defaults()
                log.info("schema sync: %s", outcome)
            except Exception:
                log.exception("automatic schema sync failed; run `python manage.py upgrade`")

    return app


def _register_request_hooks(app: Flask, cfg: Settings):
    from asme.auth.session import current_auth_user

    skip_prefixes = ("/static/",)

    @app.before_request
    def _start_worker_once():
        if cfg.outbox_worker_enabled and not cfg.is_testing and not app.extensions.get("asme_worker_started"):
            from asme.jobs import start_worker

            start_worker(app)
            app.extensions["asme_worker_started"] = True

    @app.before_request
    def _enforce_auth_session_guardrails():
        # Per-request caches. ``g`` belongs to the app context, which a request
        # reuses when one is already pushed (tests, CLI), so reset them here.
        g.ops_ctx = None  # policy cache (see asme.ops.policy)
        g._current_auth_user_resolved = False  # auth cache (see asme.auth.session)
        g._current_auth_user_cached = None
        if request.path.startswith(skip_prefixes) or request.path == "/healthz":
            return None
        current_auth_user()
        return None

    @app.after_request
    def _no_cache_for_authenticated(response):
        if session.get("auth_user_id"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0, private"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            existing_vary = response.headers.get("Vary", "")
            if "Cookie" not in existing_vary:
                response.headers["Vary"] = f"{existing_vary}, Cookie".strip(", ")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return response

    @app.errorhandler(404)
    def _not_found(exc):
        if request.path.startswith("/api/"):
            from flask import jsonify

            return jsonify({"ok": False, "code": "not_found", "error": "Not found."}), 404
        return exc

    @app.errorhandler(405)
    def _method_not_allowed(exc):
        if request.path.startswith("/api/"):
            from flask import jsonify

            return jsonify({"ok": False, "code": "method_not_allowed", "error": "Method not allowed."}), 405
        return exc

    @app.errorhandler(Exception)
    def _unhandled(exc):
        """Unexpected failures on an API route must still be JSON.

        The screens parse every ``/api/`` response as JSON; Flask's HTML 500 page
        makes them show a blank breakage instead of a message. The request id is
        echoed so the owner has one string to search the platform logs for.
        HTTP errors keep their own handlers, and outside ``/api/`` Flask's normal
        behaviour (including the debugger in development) is untouched.
        """
        from werkzeug.exceptions import HTTPException

        if isinstance(exc, HTTPException):
            return exc
        propagate = app.config.get("PROPAGATE_EXCEPTIONS")
        if propagate is None:
            propagate = app.testing or app.debug
        if propagate:
            # Tests and the development debugger want the traceback, not a
            # tidy error body. Set PROPAGATE_EXCEPTIONS=False to exercise this.
            raise exc
        log.exception("unhandled error on %s %s", request.method, request.path)
        if request.path.startswith("/api/"):
            from flask import jsonify

            return (
                jsonify(
                    {
                        "ok": False,
                        "code": "server_error",
                        "error": "Something went wrong. Try again, and quote the request id if it keeps happening.",
                        "request_id": getattr(g, "request_id", None),
                    }
                ),
                500,
            )
        raise exc

    @app.teardown_appcontext
    def _shutdown_session(_exc):
        db.session.remove()


def _register_cli(app: Flask):
    import click

    @app.cli.command("upgrade-db")
    def upgrade_db():
        """Bring the schema to head (stamps legacy databases first) and seed defaults."""
        from asme.services import bootstrap

        click.echo(f"schema: {bootstrap.sync_schema()}")
        click.echo(f"seed: {bootstrap.seed_defaults()}")

    @app.cli.command("seed")
    def seed():
        """Seed default projects, announcement, admin and Launchpad tracks."""
        from asme.services import bootstrap

        click.echo(bootstrap.seed_defaults())

    @app.cli.command("evaluate-launchpad")
    def evaluate_launchpad():
        """Re-run the onboarding engine for every active user and the chapter."""
        from asme.models import User
        from asme.services.onboarding import engine

        count = 0
        for user in User.query.filter(User.is_active.is_(True)).all():
            engine.evaluate_user(user)
            count += 1
        engine.evaluate_chapter()
        click.echo(f"evaluated {count} users + chapter")

    @app.cli.command("reconcile-stock")
    def reconcile_stock():
        from asme.services import inventory

        filed = inventory.reconcile_stock()
        click.echo(f"discrepancies filed: {len(filed)}")

    @app.cli.command("run-jobs")
    @click.option("--loop/--once", default=False)
    def run_jobs(loop):
        """Process outbox jobs once, or loop forever (use for a dedicated worker process)."""
        import time

        from asme.jobs import process_pending

        while True:
            done = process_pending()
            click.echo(f"processed {done}")
            if not loop:
                break
            time.sleep(app.config["SETTINGS"].outbox_poll_seconds)
