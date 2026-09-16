"""Migration 0003 must upgrade an empty database and a legacy-shaped database to
head, agree with the ORM models, and downgrade cleanly without touching legacy
tables."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from flask_migrate import downgrade, upgrade
from sqlalchemy import inspect, text

from tests.conftest import make_app

HEAD = "0004_ops_inventory"
PREVIOUS = "0002_launchpad"

EXPECTED_OPS_TABLES = {
    "ops_organizations",
    "ops_permissions",
    "ops_roles",
    "ops_role_permissions",
    "ops_memberships",
    "ops_user_preferences",
    "ops_sequences",
    "ops_teams",
    "ops_team_members",
    "ops_locations",
    "ops_categories",
    "ops_asset_types",
    "ops_assets",
    "ops_asset_type_links",
    "ops_asset_status_history",
    "ops_vendors",
    "ops_projects",
    "ops_project_members",
    "ops_milestones",
    "ops_work_orders",
    "ops_work_order_assignees",
    "ops_work_order_categories",
    "ops_work_order_assets",
    "ops_work_order_watchers",
    "ops_work_order_status_history",
    "ops_work_order_dependencies",
    "ops_time_entries",
    "ops_cost_entries",
    "ops_comments",
    "ops_attachments",
    "ops_audit_events",
    "ops_saved_filters",
    "ops_notifications",
}


@pytest.fixture
def file_app(tmp_path: Path):
    db_file = tmp_path / f"migrate-{uuid.uuid4().hex}.db"
    application = make_app(database_url=f"sqlite:///{db_file.as_posix()}")
    with application.app_context():
        yield application
        from asme.extensions import db

        db.session.remove()
        db.engine.dispose()


def _tables(db):
    return set(inspect(db.engine).get_table_names())


def _version(db):
    return db.session.execute(text("SELECT version_num FROM alembic_version")).scalar()


def test_upgrade_from_empty_reaches_head_and_matches_models(file_app):
    from asme.extensions import db

    migrations_dir = file_app.extensions["migrate"].directory
    upgrade(directory=migrations_dir)

    assert _version(db) == HEAD
    tables = _tables(db)
    assert EXPECTED_OPS_TABLES <= tables, EXPECTED_OPS_TABLES - tables
    assert {"users", "items", "transactions", "projects", "outbox_jobs"} <= tables

    outbox_columns = {c["name"] for c in inspect(db.engine).get_columns("outbox_jobs")}
    assert "idempotency_key" in outbox_columns
    unique_names = {u["name"] for u in inspect(db.engine).get_unique_constraints("outbox_jobs")}
    assert "uq_outbox_jobs_idempotency_key" in unique_names

    # Models and migration agree on the ops tables (structure only; SQLite type
    # rendering differences are ignored on purpose).
    with db.engine.connect() as conn:
        context = MigrationContext.configure(conn, opts={"compare_type": False})
        diffs = compare_metadata(context, db.metadata)
    structural = []
    for diff in diffs:
        entries = diff if isinstance(diff, list) else [diff]
        for entry in entries:
            kind = entry[0]
            target = repr(entry)
            if "ops_" in target and kind in {"add_table", "remove_table", "add_column", "remove_column", "add_constraint", "remove_constraint"}:
                structural.append(target)
    assert structural == [], structural


def test_downgrade_removes_ops_tables_and_keeps_legacy_data(file_app):
    from asme.extensions import db

    migrations_dir = file_app.extensions["migrate"].directory
    upgrade(directory=migrations_dir)
    db.session.execute(
        text(
            "INSERT INTO users (name, email, username, password_hash, role, is_active, created_at) "
            "VALUES ('Legacy User', 'legacy@uiowa.edu', 'legacy', 'x', 'member', 1, CURRENT_TIMESTAMP)"
        )
    )
    db.session.commit()

    downgrade(directory=migrations_dir, revision=PREVIOUS)
    assert _version(db) == PREVIOUS
    tables = _tables(db)
    assert not (EXPECTED_OPS_TABLES & tables), EXPECTED_OPS_TABLES & tables
    assert "idempotency_key" not in {c["name"] for c in inspect(db.engine).get_columns("outbox_jobs")}
    assert db.session.execute(text("SELECT count(*) FROM users")).scalar() == 1

    upgrade(directory=migrations_dir)
    assert _version(db) == HEAD
    assert db.session.execute(text("SELECT count(*) FROM users")).scalar() == 1
