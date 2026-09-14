import os

from asme.config import Settings


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


def test_session_boot_token_is_stable_unless_set(monkeypatch):
    monkeypatch.delenv("ASME_APP_BOOT_TOKEN", raising=False)
    first = Settings.from_env(env="development", secret_key="one-secret")
    second = Settings.from_env(env="development", secret_key="one-secret")
    assert first.app_boot_token and first.app_boot_token == second.app_boot_token  # restarts and workers agree
    assert Settings.from_env(env="development", secret_key="other-secret").app_boot_token != first.app_boot_token
    assert first.secret_key not in first.app_boot_token
    monkeypatch.setenv("ASME_APP_BOOT_TOKEN", "rotate-to-sign-everyone-out")
    assert Settings.from_env(env="development", secret_key="one-secret").app_boot_token == "rotate-to-sign-everyone-out"
