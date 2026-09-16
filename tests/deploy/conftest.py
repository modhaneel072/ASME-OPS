"""Helpers for the deployment tests.

These tests reason about what the *hosted* configuration does, so several of
them need a pristine environment: the repository's own ``.env`` is gitignored
and does not exist on a hosting platform or in a fresh clone, and the developer
machine's ``ASME_*`` variables must not leak into a test that is asserting what
a blank Render dashboard field produces.
"""

from __future__ import annotations

import os

import pytest

CONFIG_PREFIXES = ("ASME_", "GOOGLE_", "CALENDAR_", "ANTHROPIC_")
CONFIG_NAMES = ("DATABASE_URL", "RENDER", "FLASK_DEBUG", "PORT")


@pytest.fixture
def hosted_env(monkeypatch):
    """Empty the process environment of every setting the app reads, and stop
    ``create_app`` from loading the developer's ``.env`` (which is gitignored,
    so neither Render nor a fresh clone has one). Returns a setter."""
    import asme

    for name in list(os.environ):
        if name.startswith(CONFIG_PREFIXES) or name in CONFIG_NAMES:
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(asme, "load_dotenv", lambda *args, **kwargs: False)

    def set_env(**values):
        for name, value in values.items():
            monkeypatch.setenv(name, value)

    return set_env
