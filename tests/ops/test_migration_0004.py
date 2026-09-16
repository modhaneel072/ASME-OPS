"""Migration 0004 adds the Stage 4 inventory and purchasing tables on top of
0003, matches the ORM models, and downgrades back to 0003 without touching
anything that existed before."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from flask_migrate import downgrade, upgrade
from sqlalchemy import inspect, text

from tests.conftest import make_app

REVISION = "0004_ops_inventory"
PREVIOUS = "0003_ops_foundation"

NEW_TABLES = {
    "ops_part_types",
    "ops_parts",
    "ops_part_vendors",
    "ops_part_assets",
    "ops_inventory_balances",
    "ops_inventory_transactions",
    "ops_work_order_parts",
    "ops_purchase_requests",
    "ops_purchase_request_items",
    "ops_purchase_request_events",
}


@pytest.fixture
def file_app(tmp_path: Path):
    db_file = tmp_path / f"migrate-0004-{uuid.uuid4().hex}.db"
    application = make_app(database_url=f"sqlite:///{db_file.as_posix()}")
    with application.app_context():
        yield application
        from asme.extensions import db

        db.session.remove()
        db.engine.dispose()


def _version(db):
    return db.session.execute(text("SELECT version_num FROM alembic_version")).scalar()


def _tables(db):
    return set(inspect(db.engine).get_table_names())


def test_upgrade_from_0003_matches_the_models(file_app):
    from asme.extensions import db

    migrations_dir = file_app.extensions["migrate"].directory
    upgrade(directory=migrations_dir, revision=PREVIOUS)
    assert _version(db) == PREVIOUS
    assert not (NEW_TABLES & _tables(db))

    upgrade(directory=migrations_dir, revision=REVISION)
    assert _version(db) == REVISION
    assert NEW_TABLES <= _tables(db)

    inspector = inspect(db.engine)
    for table_name in sorted(NEW_TABLES | {"ops_cost_entries"}):
        model_table = db.metadata.tables[table_name]
        migrated = {column["name"]: column["nullable"] for column in inspector.get_columns(table_name)}
        modelled = {column.name: column.nullable for column in model_table.columns}
        assert migrated == modelled, table_name

        migrated_uniques = {u["name"] for u in inspector.get_unique_constraints(table_name)}
        modelled_uniques = {c.name for c in model_table.constraints if c.__class__.__name__ == "UniqueConstraint"}
        assert modelled_uniques <= migrated_uniques, table_name

        migrated_indexes = {i["name"]: tuple(i["column_names"]) for i in inspector.get_indexes(table_name)}
        modelled_indexes = {i.name: tuple(c.name for c in i.columns) for i in model_table.indexes}
        assert migrated_indexes == modelled_indexes, table_name

        migrated_fks = {(tuple(fk["constrained_columns"]), fk["referred_table"]) for fk in inspector.get_foreign_keys(table_name)}
        modelled_fks = {(tuple(c.name for c in fk.columns), fk.referred_table.name) for fk in model_table.foreign_key_constraints}
        assert migrated_fks == modelled_fks, table_name

    checks = {c["name"] for c in inspector.get_check_constraints("ops_inventory_balances")}
    assert {"ck_ops_inventory_balances_on_hand_not_negative", "ck_ops_inventory_balances_reserved_not_negative"} <= checks
    assert {u["name"] for u in inspector.get_unique_constraints("ops_parts")} >= {"uq_ops_parts_org_sku", "uq_ops_parts_org_qr"}
    assert "ix_ops_purchase_requests_status" in {i["name"] for i in inspector.get_indexes("ops_purchase_requests")}

    # The ledger's balance check constraints are enforced by the database too.
    org_id, part_id, location_id = uuid.uuid4().hex, uuid.uuid4().hex, uuid.uuid4().hex
    db.session.execute(
        text(
            "INSERT INTO ops_organizations (id, name, slug, timezone, academic_year_start_month, settings_json, created_at, updated_at) "
            "VALUES (:id, 'Chapter', 'chapter', 'America/Chicago', 8, '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ),
        {"id": org_id},
    )
    db.session.execute(
        text(
            "INSERT INTO ops_locations (id, organization_id, name, is_default, is_active, created_at, updated_at) "
            "VALUES (:id, :org, 'Shelf', 0, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ),
        {"id": location_id, "org": org_id},
    )
    db.session.execute(
        text(
            "INSERT INTO ops_parts (id, organization_id, name, unit, is_critical, is_active, created_at, updated_at) "
            "VALUES (:id, :org, 'Bolt', 'each', 0, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ),
        {"id": part_id, "org": org_id},
    )
    db.session.commit()
    with pytest.raises(Exception):
        db.session.execute(
            text(
                "INSERT INTO ops_inventory_balances (id, organization_id, part_id, location_id, on_hand, reserved, updated_at) "
                "VALUES (:id, :org, :part, :loc, -1, 0, CURRENT_TIMESTAMP)"
            ),
            {"id": uuid.uuid4().hex, "org": org_id, "part": part_id, "loc": location_id},
        )
        db.session.flush()
    db.session.rollback()


def test_downgrade_to_0003_removes_only_stage4_objects(file_app):
    from asme.extensions import db

    migrations_dir = file_app.extensions["migrate"].directory
    upgrade(directory=migrations_dir, revision=PREVIOUS)
    before_tables = _tables(db)
    before_cost_columns = {c["name"] for c in inspect(db.engine).get_columns("ops_cost_entries")}
    db.session.execute(
        text(
            "INSERT INTO users (name, email, username, password_hash, role, is_active, created_at) "
            "VALUES ('Legacy User', 'legacy@uiowa.edu', 'legacy', 'x', 'member', 1, CURRENT_TIMESTAMP)"
        )
    )
    db.session.execute(
        text(
            "INSERT INTO ops_organizations (id, name, slug, timezone, academic_year_start_month, settings_json, created_at, updated_at) "
            "VALUES (:id, 'Chapter', 'chapter', 'America/Chicago', 8, '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ),
        {"id": uuid.uuid4().hex},
    )
    db.session.commit()

    upgrade(directory=migrations_dir, revision=REVISION)
    assert "inventory_transaction_id" in {c["name"] for c in inspect(db.engine).get_columns("ops_cost_entries")}

    downgrade(directory=migrations_dir, revision=PREVIOUS)
    assert _version(db) == PREVIOUS
    assert _tables(db) == before_tables
    assert {c["name"] for c in inspect(db.engine).get_columns("ops_cost_entries")} == before_cost_columns
    assert "ix_ops_cost_entries_inventory_transaction_id" not in {i["name"] for i in inspect(db.engine).get_indexes("ops_cost_entries")}
    assert db.session.execute(text("SELECT count(*) FROM users")).scalar() == 1
    assert db.session.execute(text("SELECT count(*) FROM ops_organizations")).scalar() == 1

    upgrade(directory=migrations_dir, revision=REVISION)
    assert _version(db) == REVISION
    assert NEW_TABLES <= _tables(db)
    assert db.session.execute(text("SELECT count(*) FROM ops_organizations")).scalar() == 1
