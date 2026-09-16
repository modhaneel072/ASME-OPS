"""The documented emergency recovery command refuses to run.

``docs/deploy-render.md`` section 9, "If the database migration did not run",
is the owner's only way to create or repair the schema on the free instance -
Render gives free services no Shell tab, so the section says to run the
migration from their own computer. It prescribes, verbatim, a fresh clone and
exactly one environment variable::

    git clone https://github.com/modhaneel072/ASME-OPS.git
    cd ASME-OPS
    python -m venv .venv
    .venv/Scripts/activate
    pip install -r requirements-render.txt

    $env:ASME_DATABASE_URL="postgresql://...?sslmode=require"

    python manage.py upgrade

``manage.py`` calls ``create_app`` before it touches the database, and
``create_app`` runs ``Settings.validate()`` in production - which a fresh clone
is, because ``ASME_ENV`` is unset and ``Settings.from_env`` defaults to
``production``. A clone has no ``.env`` (it is gitignored), so two unrelated
checks fire and the command dies before it opens a connection::

    RuntimeError: Refusing to start with invalid configuration:
    - ASME_SECRET_KEY must be set to a real secret in production.
    - Attachments would be written inside the container, ...

Neither variable is mentioned anywhere in section 9, and neither has anything to
do with running a migration: the secret key signs cookies this process never
issues, and the uploads acknowledgement is about a disk this process never
writes to. The owner meets this at the worst possible moment - the site is
already broken, which is why they are in section 9 - and the error text points
them at attachments and secrets rather than at the missing two lines.

Section 15's once-a-semester backup export has the same shape: the restore that
export exists for ends at this same command.

Either section 9 must set the variables it needs (``ASME_ENV=development`` is
the honest one for a laptop, or the two names spelled out), or ``manage.py``'s
one-shot commands must not demand production settings they do not use.
"""

from __future__ import annotations

import pytest

# Exactly what section 9 tells the owner to set, and nothing else.
SECTION_9_ENV = {"ASME_DATABASE_URL": "postgresql://asme_ops:pw@dpg-abc.ohio-postgres.render.com/asme_ops?sslmode=require"}


def test_section_9_recovery_command_can_build_the_app(hosted_env):
    """``python manage.py upgrade`` must get as far as the database."""
    import asme

    hosted_env(**SECTION_9_ENV)
    try:
        # The same call manage.py makes for its one-shot commands.
        asme.create_app(outbox_worker_enabled=False, auto_migrate=False)
    except RuntimeError as exc:
        pytest.fail(
            "the documented free-instance recovery procedure cannot start:\n"
            f"{exc}\n"
            "docs/deploy-render.md section 9 sets only ASME_DATABASE_URL."
        )
