"""Typed application settings.

Every ``ASME_*`` / integration environment variable is resolved exactly once here,
at app creation, and validated. Nothing else in the codebase reads ``os.environ``
for configuration - modules take what they need from ``current_app.config["SETTINGS"]``
(see :func:`asme.config.settings`).
"""

from __future__ import annotations

import hashlib
import hmac
import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from flask import current_app

TRUTHY = {"1", "true", "yes", "on", "y"}
FALSY = {"0", "false", "no", "off", "n"}

#: The bootstrap password this file used to fall back to. It is printed in a
#: public repository, so it is a published credential, not a default: production
#: refuses to start with it (see :meth:`Settings.validate`).
PUBLISHED_DEFAULT_PASSWORD = "ChangeMe123!"

#: Shortest bootstrap password production accepts. The same minimum the account
#: API applies to a password a member chooses (asme/blueprints/ops/auth.py).
BOOTSTRAP_PASSWORD_MIN_LENGTH = 8

#: Environment variables that hosting platforms set on every process they run.
#: Their presence means "this is a real deployment" even when nobody remembered
#: to set ``ASME_ENV`` (see ``env_declared``).
HOSTED_PLATFORM_VARS = (
    "RENDER",
    "DYNO",
    "FLY_APP_NAME",
    "K_SERVICE",
    "KUBERNETES_SERVICE_HOST",
    "WEBSITE_SITE_NAME",
    "GAE_ENV",
    "AWS_EXECUTION_ENV",
    "ECS_CONTAINER_METADATA_URI",
    "VERCEL",
)


def _str(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _bool(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return bool(default)
    if raw in TRUTHY:
        return True
    if raw in FALSY:
        return False
    return bool(default)


def _int(name: str, default: int, minimum: int | None = None) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    if minimum is not None and value < minimum:
        return default
    return value


def hosting_platform() -> str:
    """Name of the hosting platform variable found in the environment, if any."""
    for name in HOSTED_PLATFORM_VARS:
        if (os.environ.get(name) or "").strip():
            return name
    return ""


def bootstrap_password_problem(name: str, value: str) -> str | None:
    """Why ``value`` is not usable as a bootstrap account password, or ``None``.

    ``name`` is the environment variable, so the message names the thing the
    reader has to go and change.
    """
    value = value or ""
    if not value.strip():
        return (
            f"{name} is empty, so the account it creates would be given the password "
            f"'{PUBLISHED_DEFAULT_PASSWORD}' that is written in this public repository. "
            f"Set {name} to a long password you invent (16+ characters) in the hosting "
            "dashboard, and change it inside ASME Ops after the first sign-in."
        )
    if value == PUBLISHED_DEFAULT_PASSWORD:
        return (
            f"{name} is still '{PUBLISHED_DEFAULT_PASSWORD}', which is written in this public "
            "repository: anyone who reads it could sign in to the chapter's live platform. "
            f"Set {name} to a long password you invent (16+ characters) in the hosting dashboard."
        )
    if len(value) < BOOTSTRAP_PASSWORD_MIN_LENGTH:
        return (
            f"{name} is shorter than {BOOTSTRAP_PASSWORD_MIN_LENGTH} characters, which is less than "
            "ASME Ops lets a member choose for themselves. Make it 16 or more."
        )
    return None


def _database_url() -> str:
    """The SQLAlchemy URL, normalised.

    ``ASME_DATABASE_URL`` is the name this app owns. Managed hosts (Render,
    Heroku, Neon, Supabase) inject their own ``DATABASE_URL``; accepting it as a
    fallback means a service that was wired up with only the host's variable
    still reaches the real database instead of silently falling back to a
    throwaway SQLite file on an ephemeral container disk.

    Those hosts also still hand out the legacy ``postgres://`` scheme in places.
    SQLAlchemy 2.0 removed that alias and raises ``NoSuchModuleError`` for it, so
    it is rewritten to ``postgresql://`` here rather than at every call site.
    """
    raw = _str("ASME_DATABASE_URL") or _str("DATABASE_URL") or "sqlite:///inventory.db"
    if raw.startswith("postgres://"):
        raw = "postgresql://" + raw[len("postgres://") :]
    return raw


def load_instance_env_file(path: Path) -> None:
    """Load ``KEY=value`` lines from an instance-local env file into ``os.environ``.

    Kept for backward compatibility with ``instance/print_commands.env`` which
    operators used to configure printer commands without touching the host env.
    """
    if not path.exists():
        return
    try:
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                os.environ[key] = value
    except Exception:
        # A malformed local env file must never stop the app from booting.
        pass


@dataclass(frozen=True)
class Settings:
    # -- runtime -------------------------------------------------------------
    env: str = "production"
    # Whether ``env`` was *declared* (``ASME_ENV``, an explicit override, or a
    # hosting platform's own variable) rather than assumed. ``production`` stays
    # the assumed default so an unconfigured deployment still gets production
    # behaviour - but only a declared production refuses to start over the
    # problems in :meth:`validate`, because the same package is also a checkout
    # on a student's laptop running one-shot commands such as
    # ``python manage.py upgrade`` against the hosted database (see
    # docs/deploy-render.md section 9). There the problems are logged in full
    # instead. Defaults to True so a hand-built Settings is never the lenient one.
    env_declared: bool = True
    secret_key: str = ""
    database_url: str = "sqlite:///inventory.db"
    port: int = 5000
    auto_migrate: bool = False
    # Public origin (scheme://host[:port]) used in links that leave the app, such
    # as password reset e-mails. Empty means the request's own host is used.
    public_base_url: str = ""

    # -- sessions / auth -----------------------------------------------------
    session_cookie_secure: bool = True
    session_cookie_samesite: str = "Lax"
    member_session_idle_minutes: int = 240
    admin_session_idle_minutes: int = 30
    app_boot_token: str = ""
    login_rate_window_seconds: int = 900
    login_rate_max_attempts: int = 8
    # Reverse proxies in front of the app that append to X-Forwarded-For. 0 means
    # the socket peer is the client address (see asme.utils.http.request_client_ip).
    trusted_proxy_count: int = 0
    bulk_password_hash_method: str = "pbkdf2:sha256:120000"
    password_reset_hours: int = 2

    # -- bootstrap accounts --------------------------------------------------
    default_admin_email: str = "admin@uiowa.edu"
    default_admin_password: str = "ChangeMe123!"
    default_user_password: str = "ChangeMe123!"
    admin_emails: frozenset[str] = field(default_factory=frozenset)

    # -- feature flags -------------------------------------------------------
    onboarding_enforce: bool = False
    outbox_worker_enabled: bool = True
    outbox_poll_seconds: int = 15

    # -- uploads / limits ----------------------------------------------------
    print_max_upload_bytes: int = 50 * 1024 * 1024
    checkin_soon_window_minutes: int = 20

    # -- calendar ------------------------------------------------------------
    calendar_provider: str = "google"
    google_calendar_embed_url: str = ""
    outlook_calendar_embed_url: str = ""
    google_service_account_json: str = ""
    google_calendar_id_robotics: str = ""
    google_calendar_id_fluids: str = ""
    google_calendar_timezone: str = "America/Chicago"
    calendar_scheduling_days: int = 14
    calendar_work_hours_start: str = "08:00"
    calendar_work_hours_end: str = "22:00"

    outlook_tenant_id: str = ""
    outlook_client_id: str = ""
    outlook_client_secret: str = ""
    outlook_calendar_user: str = ""
    outlook_calendar_id: str = ""
    outlook_calendar_robotics_id: str = ""
    outlook_calendar_fluids_id: str = ""
    outlook_calendar_tz: str = "Central Standard Time"

    # -- mail ----------------------------------------------------------------
    smtp_host: str = "smtp.office365.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_pass: str = ""
    cancel_notify_to: str = ""

    # -- printers ------------------------------------------------------------
    h2s_print_cmd: str = ""
    p1s_print_cmd: str = ""

    # -- assistant -----------------------------------------------------------
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"

    # -- ASME Ops ------------------------------------------------------------
    storage_backend: str = "local"
    upload_root: str = ""
    # Acknowledgement that the local storage root is not a persistent disk. The
    # app refuses to start in production without either a real disk or this flag,
    # because the alternative is attachment rows pointing at files that the host
    # deleted at the last deploy (see :meth:`validate`).
    uploads_ephemeral_ok: bool = False
    upload_max_bytes: int = 25 * 1024 * 1024
    ops_changes_poll_seconds: int = 15
    ops_download_ttl_seconds: int = 300

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    @property
    def is_testing(self) -> bool:
        return self.env == "testing"

    @classmethod
    def from_env(cls, **overrides) -> "Settings":
        env = _str("ASME_ENV", "development" if _bool("FLASK_DEBUG") else "production").lower()
        if env not in {"development", "production", "testing"}:
            env = "production"
        samesite = _str("ASME_SESSION_COOKIE_SAMESITE", "Lax").lower()
        if samesite not in {"lax", "strict", "none"}:
            samesite = "lax"
        admin_emails = frozenset(
            email.strip().lower() for email in _str("ASME_ADMIN_EMAILS").split(",") if email.strip()
        )
        values = dict(
            env=env,
            env_declared=bool(_str("ASME_ENV")) or bool(hosting_platform()) or "env" in overrides,
            secret_key=_str("ASME_SECRET_KEY", "asme-dev-secret"),
            database_url=_database_url(),
            port=_int("PORT", 5000, minimum=1),
            auto_migrate=_bool("ASME_AUTO_MIGRATE", default=(env != "production")),
            public_base_url=_str("ASME_PUBLIC_BASE_URL").rstrip("/"),
            session_cookie_secure=_bool("ASME_SESSION_COOKIE_SECURE", default=bool(os.environ.get("RENDER"))),
            session_cookie_samesite="None" if samesite == "none" else samesite.capitalize(),
            member_session_idle_minutes=_int("ASME_SESSION_IDLE_MINUTES", 240, minimum=0),
            admin_session_idle_minutes=_int("ASME_ADMIN_SESSION_IDLE_MINUTES", 30, minimum=0),
            app_boot_token=_str("ASME_APP_BOOT_TOKEN"),
            login_rate_window_seconds=_int("ASME_LOGIN_RATE_WINDOW_SECONDS", 900, minimum=1),
            login_rate_max_attempts=_int("ASME_LOGIN_RATE_MAX_ATTEMPTS", 8, minimum=1),
            trusted_proxy_count=_int("ASME_TRUSTED_PROXY_COUNT", 0, minimum=0),
            bulk_password_hash_method=_str("ASME_BULK_PASSWORD_HASH_METHOD", "pbkdf2:sha256:120000"),
            default_admin_email=_str("ASME_DEFAULT_ADMIN_EMAIL", "admin@uiowa.edu").lower(),
            default_admin_password=_str("ASME_DEFAULT_ADMIN_PASSWORD", "ChangeMe123!"),
            default_user_password=_str("ASME_DEFAULT_USER_PASSWORD", "ChangeMe123!"),
            admin_emails=admin_emails,
            onboarding_enforce=_bool("ASME_ONBOARDING_ENFORCE", default=False),
            outbox_worker_enabled=_bool("ASME_OUTBOX_WORKER", default=True),
            outbox_poll_seconds=_int("ASME_OUTBOX_POLL_SECONDS", 15, minimum=1),
            print_max_upload_bytes=_int("ASME_PRINT_MAX_UPLOAD_MB", 50, minimum=1) * 1024 * 1024,
            checkin_soon_window_minutes=_int("ASME_CHECKIN_SOON_WINDOW_MINUTES", 20, minimum=0),
            calendar_provider=(_str("ASME_CALENDAR_PROVIDER", "google").lower() or "google"),
            google_calendar_embed_url=_str("ASME_GOOGLE_CALENDAR_EMBED_URL"),
            outlook_calendar_embed_url=_str("ASME_OUTLOOK_CALENDAR_EMBED_URL"),
            google_service_account_json=_str("GOOGLE_SERVICE_ACCOUNT_JSON"),
            google_calendar_id_robotics=_str("GOOGLE_CALENDAR_ID_ROBOTICS"),
            google_calendar_id_fluids=_str("GOOGLE_CALENDAR_ID_FLUIDS"),
            google_calendar_timezone=_str("GOOGLE_CALENDAR_TIMEZONE", "America/Chicago"),
            calendar_scheduling_days=_int("CALENDAR_SCHEDULING_DAYS", 14, minimum=1),
            calendar_work_hours_start=_str("CALENDAR_WORK_HOURS_START", "08:00"),
            calendar_work_hours_end=_str("CALENDAR_WORK_HOURS_END", "22:00"),
            outlook_tenant_id=_str("ASME_OUTLOOK_TENANT_ID"),
            outlook_client_id=_str("ASME_OUTLOOK_CLIENT_ID"),
            outlook_client_secret=_str("ASME_OUTLOOK_CLIENT_SECRET"),
            outlook_calendar_user=_str("ASME_OUTLOOK_CALENDAR_USER"),
            outlook_calendar_id=_str("ASME_OUTLOOK_CALENDAR_ID"),
            outlook_calendar_robotics_id=_str("ASME_OUTLOOK_CALENDAR_ROBOTICS_ID"),
            outlook_calendar_fluids_id=_str("ASME_OUTLOOK_CALENDAR_FLUIDS_ID"),
            outlook_calendar_tz=_str("ASME_OUTLOOK_CALENDAR_TZ", "Central Standard Time"),
            smtp_host=_str("ASME_SMTP_HOST", "smtp.office365.com"),
            smtp_port=_int("ASME_SMTP_PORT", 587, minimum=1),
            smtp_user=_str("ASME_SMTP_USER"),
            smtp_pass=_str("ASME_SMTP_PASS"),
            cancel_notify_to=_str("ASME_CANCEL_NOTIFY_TO"),
            h2s_print_cmd=_str("ASME_H2S_PRINT_CMD"),
            p1s_print_cmd=_str("ASME_P1S_PRINT_CMD"),
            anthropic_api_key=_str("ANTHROPIC_API_KEY"),
            anthropic_model=_str("ASME_ASSISTANT_MODEL", "claude-sonnet-5"),
            storage_backend=(_str("ASME_STORAGE_BACKEND", "local").lower() or "local"),
            upload_root=_str("ASME_UPLOAD_ROOT"),
            uploads_ephemeral_ok=_bool("ASME_UPLOADS_EPHEMERAL_OK", default=False),
            upload_max_bytes=_int("ASME_UPLOAD_MAX_MB", 25, minimum=1) * 1024 * 1024,
            ops_changes_poll_seconds=_int("ASME_OPS_POLL_SECONDS", 15, minimum=3),
            ops_download_ttl_seconds=_int("ASME_OPS_DOWNLOAD_TTL_SECONDS", 300, minimum=30),
        )
        if values["calendar_provider"] not in {"google", "outlook"}:
            values["calendar_provider"] = "google"
        values.update(overrides)
        if not values.get("app_boot_token"):
            values["app_boot_token"] = derived_boot_token(values["secret_key"])
        return cls(**values)

    def validate(self) -> list[str]:
        """Problems that make the app unsafe to run. In production these refuse startup."""
        problems: list[str] = []
        if self.is_production and self.secret_key in {"", "asme-dev-secret", "change-this-secret"}:
            problems.append("ASME_SECRET_KEY must be set to a real secret in production.")
        if self.session_cookie_samesite == "None" and not self.session_cookie_secure:
            problems.append("SameSite=None cookies require ASME_SESSION_COOKIE_SECURE=1.")
        outlook_inputs = (
            self.outlook_tenant_id,
            self.outlook_client_id,
            self.outlook_client_secret,
            self.outlook_calendar_user,
        )
        if any(outlook_inputs) and not all(outlook_inputs):
            problems.append(
                "Outlook sync is half-configured: set ASME_OUTLOOK_TENANT_ID, ASME_OUTLOOK_CLIENT_ID, "
                "ASME_OUTLOOK_CLIENT_SECRET and ASME_OUTLOOK_CALENDAR_USER together."
            )
        if bool(self.smtp_user) != bool(self.smtp_pass):
            problems.append("ASME_SMTP_USER and ASME_SMTP_PASS must be set together.")
        if self.public_base_url and not _is_origin(self.public_base_url):
            problems.append("ASME_PUBLIC_BASE_URL must be an origin such as https://ops.example.org (no path).")
        if self.is_production and self.smtp_user and self.smtp_pass and not self.public_base_url:
            problems.append(
                "ASME_PUBLIC_BASE_URL is required in production when SMTP is configured: password reset e-mails "
                "link to it, and the request Host header cannot be trusted for that."
            )
        if self.is_production and self.database_url.startswith("sqlite"):
            problems.append(
                "ASME_DATABASE_URL is a SQLite file in production. Hosted containers get a fresh, empty filesystem "
                "on every deploy and restart, so every member, work order and purchase request would be erased "
                "without any error. Set ASME_DATABASE_URL to the PostgreSQL connection string of a managed database "
                "(it starts with postgresql:// and ends with ?sslmode=require)."
            )
        if self.is_production:
            # The bootstrap passwords create real accounts on a public address:
            # asme/services/bootstrap.py gives the first administrator
            # ``default_admin_password`` and every roster-imported account
            # ``default_user_password``. Both fall back to a value printed in this
            # public repository, and ASME_DEFAULT_ADMIN_EMAIL is published in
            # render.yaml, so a blank dashboard field publishes an administrator
            # login for the chapter's live data. That is a refusal, not a warning:
            # the warning was one log line during a ten-minute first build.
            for name, value in (
                ("ASME_DEFAULT_ADMIN_PASSWORD", self.default_admin_password),
                ("ASME_DEFAULT_USER_PASSWORD", self.default_user_password),
            ):
                problem = bootstrap_password_problem(name, value)
                if problem:
                    problems.append(problem)
        if self.storage_backend not in {"local", "s3"}:
            problems.append("ASME_STORAGE_BACKEND must be 'local' or 's3'.")
        if self.storage_backend == "s3":
            problems.append("ASME_STORAGE_BACKEND=s3 is not implemented yet; use 'local' (see docs/deployment.md).")
        # A leading "/" is absolute on the Linux hosts this deploys to, which is
        # not how Windows (where development happens) reads it.
        if self.upload_root and not (self.upload_root.startswith("/") or Path(self.upload_root).is_absolute()):
            problems.append(
                "ASME_UPLOAD_ROOT must be an absolute path to the mount point of a persistent disk, "
                "for example /var/asme-uploads."
            )
        if self.is_production and self.storage_backend == "local" and not self.upload_root and not self.uploads_ephemeral_ok:
            problems.append(
                "Attachments would be written inside the container, which hosted platforms erase on every deploy "
                "and restart: the database rows survive and their downloads break. Either set ASME_UPLOAD_ROOT to a "
                "persistent disk mounted on this service (for example /var/asme-uploads), or set "
                "ASME_UPLOADS_EPHEMERAL_OK=1 to accept that uploaded files are lost on every deploy."
            )
        return problems

    def warnings(self) -> list[str]:
        """Things worth fixing that never block startup."""
        notes: list[str] = []
        # The bootstrap passwords are not here: they refuse startup (validate()).
        if self.is_production and not self.session_cookie_secure:
            notes.append("ASME_SESSION_COOKIE_SECURE is off; set it to 1 when serving over HTTPS.")
        if self.is_production and not self.public_base_url:
            notes.append(
                "ASME_PUBLIC_BASE_URL is not set; password reset e-mails are not sent in production until it is, "
                "and invite links use the inviting administrator's own request host."
            )
        if self.is_production and self.storage_backend == "local" and not self.upload_root and self.uploads_ephemeral_ok:
            notes.append(
                "ASME_UPLOADS_EPHEMERAL_OK is on: uploaded attachments live in the container and are deleted on "
                "every deploy and restart. Tell officers not to rely on attachments until a persistent disk is "
                "mounted and ASME_UPLOAD_ROOT points at it."
            )
        if self.is_production and self.trusted_proxy_count == 0:
            notes.append(
                "ASME_TRUSTED_PROXY_COUNT is 0, so every visitor behind the hosting platform's router shares one "
                "address: login rate limiting and audit records cannot tell them apart. Set it to the number of "
                "proxies that append to X-Forwarded-For in front of this service."
            )
        if self.calendar_provider == "google" and not self.google_service_account_json and not self.google_calendar_embed_url:
            notes.append("No Google calendar credentials or embed URL; room scheduling is disabled until configured.")
        return notes


def derived_boot_token(secret_key: str) -> str:
    """Default session boot token: stable for a given secret key, so every
    worker process and every restart accepts the same sessions. Set
    ``ASME_APP_BOOT_TOKEN`` to a new value to sign everyone out on purpose."""
    return hmac.new((secret_key or "").encode("utf-8"), b"asme-app-boot-token", hashlib.sha256).hexdigest()[:32]


def _is_origin(value: str) -> bool:
    parsed = urlsplit(value)
    return (
        parsed.scheme in {"http", "https"}
        and bool(parsed.netloc)
        and parsed.path in {"", "/"}
        and not parsed.query
        and not parsed.fragment
    )


def settings() -> Settings:
    """The active :class:`Settings` for the current app context."""
    return current_app.config["SETTINGS"]
