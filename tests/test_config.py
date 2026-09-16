import dataclasses
import os

from asme.config import PUBLISHED_DEFAULT_PASSWORD, Settings

#: Production refuses to start with the bootstrap passwords left at the value
#: published in this repository (see test_production_refuses_published_bootstrap_passwords),
#: so every "these settings are fine" case has to supply real ones.
BOOTSTRAP_PASSWORDS = {
    "default_admin_password": "a-long-invented-first-password",
    "default_user_password": "another-long-invented-password",
}


def test_defaults_are_sane(monkeypatch):
    for key in list(os.environ):
        if key.startswith("ASME_") or key.startswith("GOOGLE_") or key.startswith("CALENDAR_"):
            monkeypatch.delenv(key, raising=False)
    cfg = Settings.from_env()
    assert cfg.env == "production"
    assert cfg.database_url.startswith("sqlite")
    assert cfg.member_session_idle_minutes == 240
    assert cfg.admin_session_idle_minutes == 30
    assert cfg.calendar_provider == "google"
    assert cfg.onboarding_enforce is False
    assert cfg.auto_migrate is False  # production never auto-migrates


def test_validate_flags_default_secret_in_production(monkeypatch):
    cfg = Settings.from_env(env="production", secret_key="asme-dev-secret")
    problems = cfg.validate()
    assert any("ASME_SECRET_KEY" in p for p in problems)


def test_validate_flags_half_configured_outlook():
    cfg = Settings.from_env(env="development", outlook_tenant_id="abc", outlook_client_id="", outlook_client_secret="", outlook_calendar_user="")
    assert any("Outlook" in p for p in cfg.validate())


def test_env_parsing(monkeypatch):
    monkeypatch.setenv("ASME_ENV", "development")
    monkeypatch.setenv("ASME_SESSION_IDLE_MINUTES", "15")
    monkeypatch.setenv("ASME_ONBOARDING_ENFORCE", "yes")
    monkeypatch.setenv("ASME_SESSION_COOKIE_SAMESITE", "none")
    monkeypatch.setenv("ASME_ADMIN_EMAILS", "A@x.com, b@y.org")
    cfg = Settings.from_env()
    assert cfg.env == "development"
    assert cfg.member_session_idle_minutes == 15
    assert cfg.onboarding_enforce is True
    assert cfg.session_cookie_samesite == "None"
    assert cfg.admin_emails == frozenset({"a@x.com", "b@y.org"})
    assert cfg.auto_migrate is True


def test_public_base_url_and_trusted_proxy_env(monkeypatch):
    monkeypatch.setenv("ASME_PUBLIC_BASE_URL", "https://ops.example.org/")
    monkeypatch.setenv("ASME_TRUSTED_PROXY_COUNT", "1")
    cfg = Settings.from_env(env="production", secret_key="real-secret")
    assert cfg.public_base_url == "https://ops.example.org"
    assert cfg.trusted_proxy_count == 1
    assert not any("ASME_PUBLIC_BASE_URL" in p for p in cfg.validate())
    assert not any("ASME_PUBLIC_BASE_URL" in n for n in cfg.warnings())


def test_public_base_url_must_be_an_origin(monkeypatch):
    for bad in ("ops.example.org", "ftp://ops.example.org", "https://ops.example.org/app"):
        cfg = Settings.from_env(env="development", public_base_url=bad)
        assert any("ASME_PUBLIC_BASE_URL" in p for p in cfg.validate()), bad


def test_missing_public_base_url_is_a_production_warning(monkeypatch):
    monkeypatch.delenv("ASME_PUBLIC_BASE_URL", raising=False)
    cfg = Settings.from_env(env="production", secret_key="real-secret")
    assert any("ASME_PUBLIC_BASE_URL" in n for n in cfg.warnings())


def test_production_mail_requires_a_public_base_url(monkeypatch):
    monkeypatch.delenv("ASME_PUBLIC_BASE_URL", raising=False)
    mailing = Settings.from_env(env="production", secret_key="real-secret", smtp_user="chapter@uiowa.edu", smtp_pass="app-password")
    assert any("ASME_PUBLIC_BASE_URL" in p for p in mailing.validate())
    configured = Settings.from_env(
        env="production", secret_key="real-secret", smtp_user="chapter@uiowa.edu", smtp_pass="app-password", public_base_url="https://ops.example.org"
    )
    assert not any("ASME_PUBLIC_BASE_URL" in p for p in configured.validate())
    no_mail = Settings.from_env(env="production", secret_key="real-secret", smtp_user="", smtp_pass="")
    assert not any("ASME_PUBLIC_BASE_URL" in p for p in no_mail.validate())


def test_database_url_falls_back_to_the_hosting_platforms_variable(monkeypatch):
    monkeypatch.delenv("ASME_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db.internal:5432/asme")
    assert Settings.from_env().database_url == "postgresql://u:p@db.internal:5432/asme"
    # The app's own variable always wins over the platform's.
    monkeypatch.setenv("ASME_DATABASE_URL", "postgresql://u:p@other:5432/asme")
    assert Settings.from_env().database_url == "postgresql://u:p@other:5432/asme"


def test_legacy_postgres_scheme_is_rewritten(monkeypatch):
    # SQLAlchemy 2 removed the postgres:// alias; a pasted connection string
    # using it would otherwise fail with NoSuchModuleError at the first query.
    monkeypatch.setenv("ASME_DATABASE_URL", "postgres://u:p@db.internal:5432/asme?sslmode=require")
    cfg = Settings.from_env()
    assert cfg.database_url == "postgresql://u:p@db.internal:5432/asme?sslmode=require"
    assert not any("ASME_DATABASE_URL" in p for p in cfg.validate())


def test_production_refuses_a_sqlite_database(monkeypatch):
    monkeypatch.delenv("ASME_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    sqlite_prod = Settings.from_env(env="production", secret_key="real-secret", uploads_ephemeral_ok=True, **BOOTSTRAP_PASSWORDS)
    assert any("ASME_DATABASE_URL" in p and "erased" in p for p in sqlite_prod.validate())
    postgres_prod = Settings.from_env(
        env="production",
        secret_key="real-secret",
        database_url="postgresql://u:p@db.internal:5432/asme",
        uploads_ephemeral_ok=True,
        **BOOTSTRAP_PASSWORDS,
    )
    assert postgres_prod.validate() == []
    # Development is unaffected: SQLite stays the default there.
    assert Settings.from_env(env="development").validate() == []


def test_production_refuses_ephemeral_uploads_unless_told_otherwise():
    base = dict(env="production", secret_key="real-secret", database_url="postgresql://u:p@db/asme", **BOOTSTRAP_PASSWORDS)
    unset = Settings.from_env(**base)
    assert any("ASME_UPLOAD_ROOT" in p and "erase" in p for p in unset.validate())
    acknowledged = Settings.from_env(**base, uploads_ephemeral_ok=True)
    assert acknowledged.validate() == []
    assert any("ASME_UPLOADS_EPHEMERAL_OK" in n for n in acknowledged.warnings())
    on_a_disk = Settings.from_env(**base, upload_root="/var/asme-uploads")
    assert on_a_disk.validate() == []
    assert not any("ASME_UPLOADS_EPHEMERAL_OK" in n for n in on_a_disk.warnings())


def test_upload_root_must_be_an_absolute_path():
    cfg = Settings.from_env(env="development", upload_root="uploads")
    assert any("ASME_UPLOAD_ROOT" in p and "absolute" in p for p in cfg.validate())


def test_uploads_ephemeral_flag_is_read_from_the_environment(monkeypatch):
    monkeypatch.setenv("ASME_UPLOADS_EPHEMERAL_OK", "1")
    assert Settings.from_env().uploads_ephemeral_ok is True
    monkeypatch.setenv("ASME_UPLOADS_EPHEMERAL_OK", "0")
    assert Settings.from_env().uploads_ephemeral_ok is False


def test_default_proxy_count_is_a_production_warning():
    cfg = Settings.from_env(env="production", secret_key="real-secret", database_url="postgresql://u:p@db/asme", uploads_ephemeral_ok=True)
    assert cfg.trusted_proxy_count == 0
    assert any("ASME_TRUSTED_PROXY_COUNT" in n for n in cfg.warnings())
    behind_proxies = Settings.from_env(
        env="production", secret_key="real-secret", database_url="postgresql://u:p@db/asme", uploads_ephemeral_ok=True, trusted_proxy_count=2
    )
    assert not any("ASME_TRUSTED_PROXY_COUNT" in n for n in behind_proxies.warnings())


def test_production_refuses_published_bootstrap_passwords(monkeypatch):
    # A developer's own .env (loaded by create_app in other tests) must not decide
    # the answer: this is about what a blank hosting-dashboard field produces.
    monkeypatch.delenv("ASME_DEFAULT_ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("ASME_DEFAULT_USER_PASSWORD", raising=False)
    # render.yaml declares ASME_DEFAULT_ADMIN_PASSWORD as a field the owner types
    # in, so it can be left blank; blank falls back to the value printed in this
    # public repository, and the first administrator would be created with it.
    base = dict(env="production", secret_key="real-secret", database_url="postgresql://u:p@db/asme", uploads_ephemeral_ok=True)
    published = Settings.from_env(**base)
    assert published.default_admin_password == PUBLISHED_DEFAULT_PASSWORD
    problems = published.validate()
    assert any("ASME_DEFAULT_ADMIN_PASSWORD" in p for p in problems)
    assert any("ASME_DEFAULT_USER_PASSWORD" in p for p in problems)
    # It is a refusal, not a warning - the warning was a single log line.
    assert not any("PASSWORD" in n for n in published.warnings())

    blank = Settings.from_env(**base, default_admin_password="", default_user_password="")
    assert any("ASME_DEFAULT_ADMIN_PASSWORD" in p and "empty" in p for p in blank.validate())

    too_short = Settings.from_env(**base, default_admin_password="short1!", default_user_password="short1!")
    assert any("ASME_DEFAULT_ADMIN_PASSWORD" in p and "characters" in p for p in too_short.validate())

    invented = Settings.from_env(**base, **BOOTSTRAP_PASSWORDS)
    assert invented.validate() == []
    # Development is unaffected: a local checkout seeds a throwaway SQLite file.
    assert Settings.from_env(env="development").validate() == []


def test_production_is_declared_by_asme_env_or_by_the_hosting_platform(monkeypatch):
    for name in ("ASME_ENV", "RENDER"):
        monkeypatch.delenv(name, raising=False)
    # A checkout on somebody's own computer: production is assumed, not declared.
    assert Settings.from_env().env == "production"
    assert Settings.from_env().env_declared is False
    # The hosting platform sets its own variable on every process it runs.
    monkeypatch.setenv("RENDER", "true")
    assert Settings.from_env().env_declared is True
    monkeypatch.delenv("RENDER")
    monkeypatch.setenv("ASME_ENV", "production")
    assert Settings.from_env().env_declared is True


def test_session_boot_token_is_stable_unless_set(monkeypatch):
    monkeypatch.delenv("ASME_APP_BOOT_TOKEN", raising=False)
    first = Settings.from_env(env="development", secret_key="one-secret")
    second = Settings.from_env(env="development", secret_key="one-secret")
    assert first.app_boot_token and first.app_boot_token == second.app_boot_token  # restarts and workers agree
    assert Settings.from_env(env="development", secret_key="other-secret").app_boot_token != first.app_boot_token
    assert first.secret_key not in first.app_boot_token
    monkeypatch.setenv("ASME_APP_BOOT_TOKEN", "rotate-to-sign-everyone-out")
    assert Settings.from_env(env="development", secret_key="one-secret").app_boot_token == "rotate-to-sign-everyone-out"


def test_demo_mode_allows_a_throwaway_database_and_says_so(monkeypatch):
    monkeypatch.delenv("ASME_DATABASE_URL", raising=False)
    strict = Settings.from_env(
        env="production", secret_key="a-real-production-secret", database_url="sqlite:///inventory.db",
        default_admin_password="a-real-admin-password", default_user_password="a-real-user-password", uploads_ephemeral_ok=True,
    )
    assert any("SQLite file in production" in p for p in strict.validate())
    assert any("ASME_DEMO_MODE=1" in p for p in strict.validate()), "the refusal must name the way out"

    demo = dataclasses.replace(strict, demo_mode=True)
    assert not any("SQLite" in p for p in demo.validate())
    notes = demo.warnings()
    assert any("ASME_DEMO_MODE is on" in n and "disappears" in n for n in notes), notes

    # A demonstration on a real database still says it is a demonstration.
    hosted = dataclasses.replace(demo, database_url="postgresql://user:pw@host/db")
    assert not any("SQLite" in p for p in hosted.validate())
    assert any("ASME_DEMO_MODE is on" in n for n in hosted.warnings())
    assert not any("disappears" in n for n in hosted.warnings())


def test_a_placeholder_database_url_is_rejected_with_a_readable_message(monkeypatch):
    monkeypatch.setenv("ASME_DATABASE_URL", "REPLACE_WITH_INTERNAL_DATABASE_URL")
    cfg = Settings.from_env(env="development")
    problems = [p for p in cfg.validate() if "ASME_DATABASE_URL is not a database address" in p]
    assert problems, cfg.validate()
    assert "REPLACE_WITH_INTERNAL_DATABASE_URL" in problems[0]
    for good in ("sqlite:///inventory.db", "postgresql://u:p@h/db", "postgresql+psycopg2://u:p@h/db"):
        assert not any("not a database address" in p for p in Settings.from_env(env="development", database_url=good).validate()), good
