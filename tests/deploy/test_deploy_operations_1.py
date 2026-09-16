"""A blank ASME_DEFAULT_ADMIN_PASSWORD must not be allowed to boot production.

``render.yaml`` declares ``ASME_DEFAULT_ADMIN_PASSWORD`` as ``sync: false``,
which on the Render Blueprint screen is a field the owner may leave empty, and
``docs/deploy-render.md`` step 5 presents it as one of four prompts. If it is
left empty the app starts anyway: ``Settings.validate()`` reports no problems
and only ``warnings()`` mentions it, so the only trace is one line in a log the
free plan keeps for seven days.

What that means for the semester: ``asme/services/bootstrap.seed_defaults`` then
creates the first administrator with ``Settings.default_admin_password``, whose
fallback ``ChangeMe123!`` is written in ``asme/config.py``, for the address
``admin@uiowa.edu`` that ``render.yaml`` pins in plain sight. The repository is
public, so anyone who reads it holds administrator credentials for the chapter's
live platform - every member record, work order, purchase request and the audit
trail.

This must be a *startup refusal*, like the SQLite-in-production check right
above it, not a warning: a warning is exactly what nobody reads.
"""

from __future__ import annotations

import pytest

RENDER_YAML_ENV = {
    "ASME_ENV": "production",
    "ASME_SECRET_KEY": "a-real-generated-secret-value-0123456789",
    "ASME_DATABASE_URL": "postgresql://asme_ops:pw@dpg-abc/asme_ops",
    "ASME_AUTO_MIGRATE": "0",
    "ASME_PUBLIC_BASE_URL": "https://asme-ops.netlify.app",
    "ASME_SESSION_COOKIE_SECURE": "1",
    "ASME_SESSION_COOKIE_SAMESITE": "Lax",
    "ASME_TRUSTED_PROXY_COUNT": "2",
    "ASME_DEFAULT_ADMIN_EMAIL": "admin@uiowa.edu",
    "ASME_ADMIN_EMAILS": "admin@uiowa.edu",
    "ASME_STORAGE_BACKEND": "local",
    "ASME_UPLOADS_EPHEMERAL_OK": "1",
    # ASME_DEFAULT_ADMIN_PASSWORD: the owner left the Blueprint field empty.
}


def test_blank_admin_password_is_refused_not_merely_warned(hosted_env):
    from asme.config import Settings

    hosted_env(**RENDER_YAML_ENV)
    cfg = Settings.from_env()

    # The published fallback is what the first administrator would be created with.
    assert cfg.default_admin_password == "ChangeMe123!"

    problems = cfg.validate()
    assert any("ADMIN_PASSWORD" in problem for problem in problems), (
        "production accepted the published default administrator password "
        f"{cfg.default_admin_password!r} for {cfg.default_admin_email!r}; "
        f"validate() returned {problems!r}"
    )


def test_production_app_refuses_to_start_with_the_published_admin_password(hosted_env):
    import asme

    hosted_env(**RENDER_YAML_ENV)
    with pytest.raises(RuntimeError, match="ADMIN_PASSWORD"):
        asme.create_app()
