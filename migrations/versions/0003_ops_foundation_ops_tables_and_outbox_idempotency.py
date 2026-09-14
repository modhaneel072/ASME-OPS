"""ASME Ops foundation: tenancy, permissions, structure, projects, work orders,
comments/attachments/audit/saved filters/notifications, plus an idempotency key on
the outbox. Additive only; every ops table is prefixed ``ops_``.

Revision ID: 0003_ops_foundation
Revises: 0002_launchpad
Create Date: 2026-09-08 15:51:10.107832

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

import asme.ops.types

# revision identifiers, used by Alembic.
revision = '0003_ops_foundation'
down_revision = '0002_launchpad'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('ops_organizations',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('slug', sa.String(length=80), nullable=False),
    sa.Column('logo_url', sa.String(length=500), nullable=True),
    sa.Column('timezone', sa.String(length=64), nullable=False),
    sa.Column('academic_year_start_month', sa.Integer(), nullable=False),
    sa.Column('settings_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('setup_completed_at', asme.ops.types.UTCDateTime(), nullable=True),
    sa.Column('created_at', asme.ops.types.UTCDateTime(), nullable=False),
    sa.Column('updated_at', asme.ops.types.UTCDateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ops_organizations'))
    )
    with op.batch_alter_table('ops_organizations', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ops_organizations_slug'), ['slug'], unique=True)

    op.create_table('ops_permissions',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('key', sa.String(length=80), nullable=False),
    sa.Column('description', sa.String(length=300), nullable=False),
    sa.Column('created_at', asme.ops.types.UTCDateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ops_permissions'))
    )
    with op.batch_alter_table('ops_permissions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ops_permissions_key'), ['key'], unique=True)

    op.create_table('ops_sequences',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('key', sa.String(length=40), nullable=False),
    sa.Column('next_value', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['organization_id'], ['ops_organizations.id'], name=op.f('fk_ops_sequences_organization_id_ops_organizations')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ops_sequences')),
    sa.UniqueConstraint('organization_id', 'key', name='uq_ops_sequences_org_key')
    )
    with op.batch_alter_table('ops_sequences', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ops_sequences_organization_id'), ['organization_id'], unique=False)

    op.create_table('ops_asset_types',
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('color', sa.String(length=20), nullable=False),
    sa.Column('icon', sa.String(length=60), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('created_by_user_id', sa.Integer(), nullable=True),
    sa.Column('updated_by_user_id', sa.Integer(), nullable=True),
    sa.Column('created_at', asme.ops.types.UTCDateTime(), nullable=False),
    sa.Column('updated_at', asme.ops.types.UTCDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], name=op.f('fk_ops_asset_types_created_by_user_id_users')),
    sa.ForeignKeyConstraint(['organization_id'], ['ops_organizations.id'], name=op.f('fk_ops_asset_types_organization_id_ops_organizations')),
    sa.ForeignKeyConstraint(['updated_by_user_id'], ['users.id'], name=op.f('fk_ops_asset_types_updated_by_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ops_asset_types')),
    sa.UniqueConstraint('organization_id', 'name', name='uq_ops_asset_types_org_name')
    )
    with op.batch_alter_table('ops_asset_types', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ops_asset_types_organization_id'), ['organization_id'], unique=False)

    op.create_table('ops_attachments',
    sa.Column('entity_type', sa.String(length=30), nullable=False),
    sa.Column('entity_id', sa.Uuid(), nullable=False),
    sa.Column('storage_key', sa.String(length=400), nullable=False),
    sa.Column('original_name', sa.String(length=260), nullable=False),
    sa.Column('content_type', sa.String(length=120), nullable=False),
    sa.Column('size_bytes', sa.Integer(), nullable=False),
    sa.Column('checksum_sha256', sa.String(length=64), nullable=True),
    sa.Column('uploaded_by_user_id', sa.Integer(), nullable=False),
    sa.Column('is_image', sa.Boolean(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('created_by_user_id', sa.Integer(), nullable=True),
    sa.Column('updated_by_user_id', sa.Integer(), nullable=True),
    sa.Column('created_at', asme.ops.types.UTCDateTime(), nullable=False),
    sa.Column('updated_at', asme.ops.types.UTCDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], name=op.f('fk_ops_attachments_created_by_user_id_users')),
    sa.ForeignKeyConstraint(['organization_id'], ['ops_organizations.id'], name=op.f('fk_ops_attachments_organization_id_ops_organizations')),
    sa.ForeignKeyConstraint(['updated_by_user_id'], ['users.id'], name=op.f('fk_ops_attachments_updated_by_user_id_users')),
    sa.ForeignKeyConstraint(['uploaded_by_user_id'], ['users.id'], name=op.f('fk_ops_attachments_uploaded_by_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ops_attachments')),
    sa.UniqueConstraint('storage_key', name=op.f('uq_ops_attachments_storage_key'))
    )
    with op.batch_alter_table('ops_attachments', schema=None) as batch_op:
        batch_op.create_index('ix_ops_attachments_entity', ['entity_type', 'entity_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_attachments_organization_id'), ['organization_id'], unique=False)

    op.create_table('ops_audit_events',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('actor_user_id', sa.Integer(), nullable=True),
    sa.Column('event_type', sa.String(length=80), nullable=False),
    sa.Column('entity_type', sa.String(length=40), nullable=False),
    sa.Column('entity_id', sa.String(length=40), nullable=False),
    sa.Column('summary', sa.String(length=400), nullable=True),
    sa.Column('before_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True),
    sa.Column('after_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True),
    sa.Column('metadata_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True),
    sa.Column('occurred_at', asme.ops.types.UTCDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], name=op.f('fk_ops_audit_events_actor_user_id_users')),
    sa.ForeignKeyConstraint(['organization_id'], ['ops_organizations.id'], name=op.f('fk_ops_audit_events_organization_id_ops_organizations')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ops_audit_events'))
    )
    with op.batch_alter_table('ops_audit_events', schema=None) as batch_op:
        batch_op.create_index('ix_ops_audit_events_entity', ['entity_type', 'entity_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_audit_events_event_type'), ['event_type'], unique=False)
        batch_op.create_index('ix_ops_audit_events_org_occurred', ['organization_id', 'occurred_at'], unique=False)

    op.create_table('ops_categories',
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('color', sa.String(length=20), nullable=False),
    sa.Column('icon', sa.String(length=60), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('created_by_user_id', sa.Integer(), nullable=True),
    sa.Column('updated_by_user_id', sa.Integer(), nullable=True),
    sa.Column('created_at', asme.ops.types.UTCDateTime(), nullable=False),
    sa.Column('updated_at', asme.ops.types.UTCDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], name=op.f('fk_ops_categories_created_by_user_id_users')),
    sa.ForeignKeyConstraint(['organization_id'], ['ops_organizations.id'], name=op.f('fk_ops_categories_organization_id_ops_organizations')),
    sa.ForeignKeyConstraint(['updated_by_user_id'], ['users.id'], name=op.f('fk_ops_categories_updated_by_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ops_categories')),
    sa.UniqueConstraint('organization_id', 'name', name='uq_ops_categories_org_name')
    )
    with op.batch_alter_table('ops_categories', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ops_categories_organization_id'), ['organization_id'], unique=False)

    op.create_table('ops_comments',
    sa.Column('entity_type', sa.String(length=30), nullable=False),
    sa.Column('entity_id', sa.Uuid(), nullable=False),
    sa.Column('author_user_id', sa.Integer(), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('parent_comment_id', sa.Uuid(), nullable=True),
    sa.Column('edited_at', asme.ops.types.UTCDateTime(), nullable=True),
    sa.Column('deleted_at', asme.ops.types.UTCDateTime(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('created_by_user_id', sa.Integer(), nullable=True),
    sa.Column('updated_by_user_id', sa.Integer(), nullable=True),
    sa.Column('created_at', asme.ops.types.UTCDateTime(), nullable=False),
    sa.Column('updated_at', asme.ops.types.UTCDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['author_user_id'], ['users.id'], name=op.f('fk_ops_comments_author_user_id_users')),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], name=op.f('fk_ops_comments_created_by_user_id_users')),
    sa.ForeignKeyConstraint(['organization_id'], ['ops_organizations.id'], name=op.f('fk_ops_comments_organization_id_ops_organizations')),
    sa.ForeignKeyConstraint(['parent_comment_id'], ['ops_comments.id'], name=op.f('fk_ops_comments_parent_comment_id_ops_comments')),
    sa.ForeignKeyConstraint(['updated_by_user_id'], ['users.id'], name=op.f('fk_ops_comments_updated_by_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ops_comments'))
    )
    with op.batch_alter_table('ops_comments', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ops_comments_author_user_id'), ['author_user_id'], unique=False)
        batch_op.create_index('ix_ops_comments_entity', ['entity_type', 'entity_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_comments_organization_id'), ['organization_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_comments_parent_comment_id'), ['parent_comment_id'], unique=False)

    op.create_table('ops_locations',
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('parent_location_id', sa.Uuid(), nullable=True),
    sa.Column('building', sa.String(length=160), nullable=True),
    sa.Column('room', sa.String(length=80), nullable=True),
    sa.Column('address_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True),
    sa.Column('is_default', sa.Boolean(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('created_by_user_id', sa.Integer(), nullable=True),
    sa.Column('updated_by_user_id', sa.Integer(), nullable=True),
    sa.Column('created_at', asme.ops.types.UTCDateTime(), nullable=False),
    sa.Column('updated_at', asme.ops.types.UTCDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], name=op.f('fk_ops_locations_created_by_user_id_users')),
    sa.ForeignKeyConstraint(['organization_id'], ['ops_organizations.id'], name=op.f('fk_ops_locations_organization_id_ops_organizations')),
    sa.ForeignKeyConstraint(['parent_location_id'], ['ops_locations.id'], name=op.f('fk_ops_locations_parent_location_id_ops_locations')),
    sa.ForeignKeyConstraint(['updated_by_user_id'], ['users.id'], name=op.f('fk_ops_locations_updated_by_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ops_locations'))
    )
    with op.batch_alter_table('ops_locations', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ops_locations_organization_id'), ['organization_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_locations_parent_location_id'), ['parent_location_id'], unique=False)

    op.create_table('ops_notifications',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('type', sa.String(length=60), nullable=False),
    sa.Column('title', sa.String(length=240), nullable=False),
    sa.Column('body', sa.Text(), nullable=True),
    sa.Column('entity_type', sa.String(length=40), nullable=True),
    sa.Column('entity_id', sa.String(length=40), nullable=True),
    sa.Column('dedupe_key', sa.String(length=160), nullable=True),
    sa.Column('read_at', asme.ops.types.UTCDateTime(), nullable=True),
    sa.Column('created_at', asme.ops.types.UTCDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['organization_id'], ['ops_organizations.id'], name=op.f('fk_ops_notifications_organization_id_ops_organizations')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_ops_notifications_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ops_notifications')),
    sa.UniqueConstraint('organization_id', 'user_id', 'dedupe_key', name='uq_ops_notifications_org_user_dedupe')
    )
    with op.batch_alter_table('ops_notifications', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ops_notifications_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_notifications_organization_id'), ['organization_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_notifications_user_id'), ['user_id'], unique=False)
        batch_op.create_index('ix_ops_notifications_user_unread', ['user_id', 'read_at'], unique=False)

    op.create_table('ops_projects',
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('code', sa.String(length=20), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('visibility', sa.String(length=20), nullable=False),
    sa.Column('risk_level', sa.String(length=20), nullable=False),
    sa.Column('lead_user_id', sa.Integer(), nullable=True),
    sa.Column('faculty_advisor_user_id', sa.Integer(), nullable=True),
    sa.Column('start_date', sa.Date(), nullable=True),
    sa.Column('target_date', sa.Date(), nullable=True),
    sa.Column('budget_amount', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('repository_url', sa.String(length=500), nullable=True),
    sa.Column('cad_url', sa.String(length=500), nullable=True),
    sa.Column('requirements_url', sa.String(length=500), nullable=True),
    sa.Column('competition', sa.String(length=200), nullable=True),
    sa.Column('academic_year', sa.String(length=12), nullable=True),
    sa.Column('public_project_id', sa.Integer(), nullable=True),
    sa.Column('archived_at', asme.ops.types.UTCDateTime(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('created_by_user_id', sa.Integer(), nullable=True),
    sa.Column('updated_by_user_id', sa.Integer(), nullable=True),
    sa.Column('created_at', asme.ops.types.UTCDateTime(), nullable=False),
    sa.Column('updated_at', asme.ops.types.UTCDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], name=op.f('fk_ops_projects_created_by_user_id_users')),
    sa.ForeignKeyConstraint(['faculty_advisor_user_id'], ['users.id'], name=op.f('fk_ops_projects_faculty_advisor_user_id_users')),
    sa.ForeignKeyConstraint(['lead_user_id'], ['users.id'], name=op.f('fk_ops_projects_lead_user_id_users')),
    sa.ForeignKeyConstraint(['organization_id'], ['ops_organizations.id'], name=op.f('fk_ops_projects_organization_id_ops_organizations')),
    sa.ForeignKeyConstraint(['public_project_id'], ['projects.id'], name=op.f('fk_ops_projects_public_project_id_projects')),
    sa.ForeignKeyConstraint(['updated_by_user_id'], ['users.id'], name=op.f('fk_ops_projects_updated_by_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ops_projects')),
    sa.UniqueConstraint('organization_id', 'code', name='uq_ops_projects_org_code')
    )
    with op.batch_alter_table('ops_projects', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ops_projects_lead_user_id'), ['lead_user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_projects_organization_id'), ['organization_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_projects_public_project_id'), ['public_project_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_projects_status'), ['status'], unique=False)

    op.create_table('ops_roles',
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('system_key', sa.String(length=40), nullable=True),
    sa.Column('is_custom', sa.Boolean(), nullable=False),
    sa.Column('description', sa.String(length=300), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('created_by_user_id', sa.Integer(), nullable=True),
    sa.Column('updated_by_user_id', sa.Integer(), nullable=True),
    sa.Column('created_at', asme.ops.types.UTCDateTime(), nullable=False),
    sa.Column('updated_at', asme.ops.types.UTCDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], name=op.f('fk_ops_roles_created_by_user_id_users')),
    sa.ForeignKeyConstraint(['organization_id'], ['ops_organizations.id'], name=op.f('fk_ops_roles_organization_id_ops_organizations')),
    sa.ForeignKeyConstraint(['updated_by_user_id'], ['users.id'], name=op.f('fk_ops_roles_updated_by_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ops_roles')),
    sa.UniqueConstraint('organization_id', 'system_key', name='uq_ops_roles_org_system_key')
    )
    with op.batch_alter_table('ops_roles', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ops_roles_organization_id'), ['organization_id'], unique=False)

    op.create_table('ops_user_preferences',
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('key', sa.String(length=80), nullable=False),
    sa.Column('value_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('created_by_user_id', sa.Integer(), nullable=True),
    sa.Column('updated_by_user_id', sa.Integer(), nullable=True),
    sa.Column('created_at', asme.ops.types.UTCDateTime(), nullable=False),
    sa.Column('updated_at', asme.ops.types.UTCDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], name=op.f('fk_ops_user_preferences_created_by_user_id_users')),
    sa.ForeignKeyConstraint(['organization_id'], ['ops_organizations.id'], name=op.f('fk_ops_user_preferences_organization_id_ops_organizations')),
    sa.ForeignKeyConstraint(['updated_by_user_id'], ['users.id'], name=op.f('fk_ops_user_preferences_updated_by_user_id_users')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_ops_user_preferences_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ops_user_preferences')),
    sa.UniqueConstraint('organization_id', 'user_id', 'key', name='uq_ops_user_preferences_org_user_key')
    )
    with op.batch_alter_table('ops_user_preferences', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ops_user_preferences_organization_id'), ['organization_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_user_preferences_user_id'), ['user_id'], unique=False)

    op.create_table('ops_vendors',
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('contact_name', sa.String(length=160), nullable=True),
    sa.Column('email', sa.String(length=160), nullable=True),
    sa.Column('phone', sa.String(length=40), nullable=True),
    sa.Column('website', sa.String(length=300), nullable=True),
    sa.Column('address_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('created_by_user_id', sa.Integer(), nullable=True),
    sa.Column('updated_by_user_id', sa.Integer(), nullable=True),
    sa.Column('created_at', asme.ops.types.UTCDateTime(), nullable=False),
    sa.Column('updated_at', asme.ops.types.UTCDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], name=op.f('fk_ops_vendors_created_by_user_id_users')),
    sa.ForeignKeyConstraint(['organization_id'], ['ops_organizations.id'], name=op.f('fk_ops_vendors_organization_id_ops_organizations')),
    sa.ForeignKeyConstraint(['updated_by_user_id'], ['users.id'], name=op.f('fk_ops_vendors_updated_by_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ops_vendors')),
    sa.UniqueConstraint('organization_id', 'name', name='uq_ops_vendors_org_name')
    )
    with op.batch_alter_table('ops_vendors', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ops_vendors_organization_id'), ['organization_id'], unique=False)

    op.create_table('ops_memberships',
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('role_id', sa.Uuid(), nullable=False),
    sa.Column('member_status', sa.String(length=20), nullable=False),
    sa.Column('title', sa.String(length=120), nullable=True),
    sa.Column('joined_at', asme.ops.types.UTCDateTime(), nullable=False),
    sa.Column('last_seen_at', asme.ops.types.UTCDateTime(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('created_by_user_id', sa.Integer(), nullable=True),
    sa.Column('updated_by_user_id', sa.Integer(), nullable=True),
    sa.Column('created_at', asme.ops.types.UTCDateTime(), nullable=False),
    sa.Column('updated_at', asme.ops.types.UTCDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], name=op.f('fk_ops_memberships_created_by_user_id_users')),
    sa.ForeignKeyConstraint(['organization_id'], ['ops_organizations.id'], name=op.f('fk_ops_memberships_organization_id_ops_organizations')),
    sa.ForeignKeyConstraint(['role_id'], ['ops_roles.id'], name=op.f('fk_ops_memberships_role_id_ops_roles')),
    sa.ForeignKeyConstraint(['updated_by_user_id'], ['users.id'], name=op.f('fk_ops_memberships_updated_by_user_id_users')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_ops_memberships_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ops_memberships')),
    sa.UniqueConstraint('organization_id', 'user_id', name='uq_ops_memberships_org_user')
    )
    with op.batch_alter_table('ops_memberships', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ops_memberships_member_status'), ['member_status'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_memberships_organization_id'), ['organization_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_memberships_role_id'), ['role_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_memberships_user_id'), ['user_id'], unique=False)

    op.create_table('ops_milestones',
    sa.Column('project_id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('due_date', sa.Date(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('owner_user_id', sa.Integer(), nullable=True),
    sa.Column('weight', sa.Integer(), nullable=False),
    sa.Column('order_index', sa.Integer(), nullable=False),
    sa.Column('completed_at', asme.ops.types.UTCDateTime(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('created_by_user_id', sa.Integer(), nullable=True),
    sa.Column('updated_by_user_id', sa.Integer(), nullable=True),
    sa.Column('created_at', asme.ops.types.UTCDateTime(), nullable=False),
    sa.Column('updated_at', asme.ops.types.UTCDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], name=op.f('fk_ops_milestones_created_by_user_id_users')),
    sa.ForeignKeyConstraint(['organization_id'], ['ops_organizations.id'], name=op.f('fk_ops_milestones_organization_id_ops_organizations')),
    sa.ForeignKeyConstraint(['owner_user_id'], ['users.id'], name=op.f('fk_ops_milestones_owner_user_id_users')),
    sa.ForeignKeyConstraint(['project_id'], ['ops_projects.id'], name=op.f('fk_ops_milestones_project_id_ops_projects'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['updated_by_user_id'], ['users.id'], name=op.f('fk_ops_milestones_updated_by_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ops_milestones'))
    )
    with op.batch_alter_table('ops_milestones', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ops_milestones_organization_id'), ['organization_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_milestones_project_id'), ['project_id'], unique=False)

    op.create_table('ops_role_permissions',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('role_id', sa.Uuid(), nullable=False),
    sa.Column('permission_id', sa.Uuid(), nullable=False),
    sa.Column('scope_type', sa.String(length=20), nullable=False),
    sa.Column('created_at', asme.ops.types.UTCDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['permission_id'], ['ops_permissions.id'], name=op.f('fk_ops_role_permissions_permission_id_ops_permissions')),
    sa.ForeignKeyConstraint(['role_id'], ['ops_roles.id'], name=op.f('fk_ops_role_permissions_role_id_ops_roles'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ops_role_permissions')),
    sa.UniqueConstraint('role_id', 'permission_id', name='uq_ops_role_permissions_role_permission')
    )
    with op.batch_alter_table('ops_role_permissions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ops_role_permissions_permission_id'), ['permission_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_role_permissions_role_id'), ['role_id'], unique=False)

    op.create_table('ops_teams',
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('parent_team_id', sa.Uuid(), nullable=True),
    sa.Column('project_id', sa.Uuid(), nullable=True),
    sa.Column('conversation_id', sa.Uuid(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('created_by_user_id', sa.Integer(), nullable=True),
    sa.Column('updated_by_user_id', sa.Integer(), nullable=True),
    sa.Column('created_at', asme.ops.types.UTCDateTime(), nullable=False),
    sa.Column('updated_at', asme.ops.types.UTCDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], name=op.f('fk_ops_teams_created_by_user_id_users')),
    sa.ForeignKeyConstraint(['organization_id'], ['ops_organizations.id'], name=op.f('fk_ops_teams_organization_id_ops_organizations')),
    sa.ForeignKeyConstraint(['parent_team_id'], ['ops_teams.id'], name=op.f('fk_ops_teams_parent_team_id_ops_teams')),
    sa.ForeignKeyConstraint(['project_id'], ['ops_projects.id'], name=op.f('fk_ops_teams_project_id_ops_projects')),
    sa.ForeignKeyConstraint(['updated_by_user_id'], ['users.id'], name=op.f('fk_ops_teams_updated_by_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ops_teams')),
    sa.UniqueConstraint('organization_id', 'name', name='uq_ops_teams_org_name')
    )
    with op.batch_alter_table('ops_teams', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ops_teams_organization_id'), ['organization_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_teams_parent_team_id'), ['parent_team_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_teams_project_id'), ['project_id'], unique=False)

    op.create_table('ops_assets',
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('code', sa.String(length=60), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('parent_asset_id', sa.Uuid(), nullable=True),
    sa.Column('project_id', sa.Uuid(), nullable=True),
    sa.Column('location_id', sa.Uuid(), nullable=True),
    sa.Column('responsible_team_id', sa.Uuid(), nullable=True),
    sa.Column('owner_user_id', sa.Integer(), nullable=True),
    sa.Column('manufacturer', sa.String(length=160), nullable=True),
    sa.Column('model', sa.String(length=160), nullable=True),
    sa.Column('serial_number', sa.String(length=160), nullable=True),
    sa.Column('purchase_date', sa.Date(), nullable=True),
    sa.Column('purchase_cost', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('warranty_end', sa.Date(), nullable=True),
    sa.Column('criticality', sa.String(length=20), nullable=False),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('qr_code', sa.String(length=160), nullable=True),
    sa.Column('custom_fields_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('created_by_user_id', sa.Integer(), nullable=True),
    sa.Column('updated_by_user_id', sa.Integer(), nullable=True),
    sa.Column('created_at', asme.ops.types.UTCDateTime(), nullable=False),
    sa.Column('updated_at', asme.ops.types.UTCDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], name=op.f('fk_ops_assets_created_by_user_id_users')),
    sa.ForeignKeyConstraint(['location_id'], ['ops_locations.id'], name=op.f('fk_ops_assets_location_id_ops_locations')),
    sa.ForeignKeyConstraint(['organization_id'], ['ops_organizations.id'], name=op.f('fk_ops_assets_organization_id_ops_organizations')),
    sa.ForeignKeyConstraint(['owner_user_id'], ['users.id'], name=op.f('fk_ops_assets_owner_user_id_users')),
    sa.ForeignKeyConstraint(['parent_asset_id'], ['ops_assets.id'], name=op.f('fk_ops_assets_parent_asset_id_ops_assets')),
    sa.ForeignKeyConstraint(['project_id'], ['ops_projects.id'], name=op.f('fk_ops_assets_project_id_ops_projects')),
    sa.ForeignKeyConstraint(['responsible_team_id'], ['ops_teams.id'], name=op.f('fk_ops_assets_responsible_team_id_ops_teams')),
    sa.ForeignKeyConstraint(['updated_by_user_id'], ['users.id'], name=op.f('fk_ops_assets_updated_by_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ops_assets')),
    sa.UniqueConstraint('organization_id', 'code', name='uq_ops_assets_org_code')
    )
    with op.batch_alter_table('ops_assets', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ops_assets_location_id'), ['location_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_assets_organization_id'), ['organization_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_assets_parent_asset_id'), ['parent_asset_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_assets_project_id'), ['project_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_assets_responsible_team_id'), ['responsible_team_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_assets_status'), ['status'], unique=False)

    op.create_table('ops_project_members',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('project_id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('team_id', sa.Uuid(), nullable=True),
    sa.Column('project_role', sa.String(length=20), nullable=False),
    sa.Column('joined_at', asme.ops.types.UTCDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['ops_projects.id'], name=op.f('fk_ops_project_members_project_id_ops_projects'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['team_id'], ['ops_teams.id'], name=op.f('fk_ops_project_members_team_id_ops_teams')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_ops_project_members_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ops_project_members')),
    sa.UniqueConstraint('project_id', 'user_id', name='uq_ops_project_members_project_user')
    )
    with op.batch_alter_table('ops_project_members', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ops_project_members_project_id'), ['project_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_project_members_team_id'), ['team_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_project_members_user_id'), ['user_id'], unique=False)

    op.create_table('ops_saved_filters',
    sa.Column('entity_type', sa.String(length=40), nullable=False),
    sa.Column('owner_user_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('visibility', sa.String(length=20), nullable=False),
    sa.Column('team_id', sa.Uuid(), nullable=True),
    sa.Column('filter_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('sort_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True),
    sa.Column('view_type', sa.String(length=20), nullable=True),
    sa.Column('is_default', sa.Boolean(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('created_by_user_id', sa.Integer(), nullable=True),
    sa.Column('updated_by_user_id', sa.Integer(), nullable=True),
    sa.Column('created_at', asme.ops.types.UTCDateTime(), nullable=False),
    sa.Column('updated_at', asme.ops.types.UTCDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], name=op.f('fk_ops_saved_filters_created_by_user_id_users')),
    sa.ForeignKeyConstraint(['organization_id'], ['ops_organizations.id'], name=op.f('fk_ops_saved_filters_organization_id_ops_organizations')),
    sa.ForeignKeyConstraint(['owner_user_id'], ['users.id'], name=op.f('fk_ops_saved_filters_owner_user_id_users')),
    sa.ForeignKeyConstraint(['team_id'], ['ops_teams.id'], name=op.f('fk_ops_saved_filters_team_id_ops_teams')),
    sa.ForeignKeyConstraint(['updated_by_user_id'], ['users.id'], name=op.f('fk_ops_saved_filters_updated_by_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ops_saved_filters'))
    )
    with op.batch_alter_table('ops_saved_filters', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ops_saved_filters_entity_type'), ['entity_type'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_saved_filters_organization_id'), ['organization_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_saved_filters_owner_user_id'), ['owner_user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_saved_filters_team_id'), ['team_id'], unique=False)

    op.create_table('ops_team_members',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('team_id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('is_lead', sa.Boolean(), nullable=False),
    sa.Column('joined_at', asme.ops.types.UTCDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['team_id'], ['ops_teams.id'], name=op.f('fk_ops_team_members_team_id_ops_teams'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_ops_team_members_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ops_team_members')),
    sa.UniqueConstraint('team_id', 'user_id', name='uq_ops_team_members_team_user')
    )
    with op.batch_alter_table('ops_team_members', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ops_team_members_team_id'), ['team_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_team_members_user_id'), ['user_id'], unique=False)

    op.create_table('ops_asset_type_links',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('asset_id', sa.Uuid(), nullable=False),
    sa.Column('asset_type_id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['asset_id'], ['ops_assets.id'], name=op.f('fk_ops_asset_type_links_asset_id_ops_assets'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['asset_type_id'], ['ops_asset_types.id'], name=op.f('fk_ops_asset_type_links_asset_type_id_ops_asset_types')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ops_asset_type_links')),
    sa.UniqueConstraint('asset_id', 'asset_type_id', name='uq_ops_asset_type_links_asset_type')
    )
    with op.batch_alter_table('ops_asset_type_links', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ops_asset_type_links_asset_id'), ['asset_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_asset_type_links_asset_type_id'), ['asset_type_id'], unique=False)

    op.create_table('ops_work_orders',
    sa.Column('number', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=240), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('priority', sa.String(length=20), nullable=False),
    sa.Column('work_type', sa.String(length=30), nullable=False),
    sa.Column('project_id', sa.Uuid(), nullable=True),
    sa.Column('location_id', sa.Uuid(), nullable=True),
    sa.Column('primary_asset_id', sa.Uuid(), nullable=True),
    sa.Column('team_id', sa.Uuid(), nullable=True),
    sa.Column('vendor_id', sa.Uuid(), nullable=True),
    sa.Column('parent_work_order_id', sa.Uuid(), nullable=True),
    sa.Column('source_request_id', sa.Uuid(), nullable=True),
    sa.Column('maintenance_plan_id', sa.Uuid(), nullable=True),
    sa.Column('start_at', asme.ops.types.UTCDateTime(), nullable=True),
    sa.Column('due_at', asme.ops.types.UTCDateTime(), nullable=True),
    sa.Column('completed_at', asme.ops.types.UTCDateTime(), nullable=True),
    sa.Column('canceled_at', asme.ops.types.UTCDateTime(), nullable=True),
    sa.Column('estimated_minutes', sa.Integer(), nullable=True),
    sa.Column('actual_minutes', sa.Integer(), nullable=False),
    sa.Column('recurrence_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True),
    sa.Column('completion_note', sa.Text(), nullable=True),
    sa.Column('is_blocked', sa.Boolean(), nullable=False),
    sa.Column('budget_code', sa.String(length=60), nullable=True),
    sa.Column('parent_completion_policy', sa.String(length=20), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('created_by_user_id', sa.Integer(), nullable=True),
    sa.Column('updated_by_user_id', sa.Integer(), nullable=True),
    sa.Column('created_at', asme.ops.types.UTCDateTime(), nullable=False),
    sa.Column('updated_at', asme.ops.types.UTCDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], name=op.f('fk_ops_work_orders_created_by_user_id_users')),
    sa.ForeignKeyConstraint(['location_id'], ['ops_locations.id'], name=op.f('fk_ops_work_orders_location_id_ops_locations')),
    sa.ForeignKeyConstraint(['organization_id'], ['ops_organizations.id'], name=op.f('fk_ops_work_orders_organization_id_ops_organizations')),
    sa.ForeignKeyConstraint(['parent_work_order_id'], ['ops_work_orders.id'], name=op.f('fk_ops_work_orders_parent_work_order_id_ops_work_orders')),
    sa.ForeignKeyConstraint(['primary_asset_id'], ['ops_assets.id'], name=op.f('fk_ops_work_orders_primary_asset_id_ops_assets')),
    sa.ForeignKeyConstraint(['project_id'], ['ops_projects.id'], name=op.f('fk_ops_work_orders_project_id_ops_projects')),
    sa.ForeignKeyConstraint(['team_id'], ['ops_teams.id'], name=op.f('fk_ops_work_orders_team_id_ops_teams')),
    sa.ForeignKeyConstraint(['updated_by_user_id'], ['users.id'], name=op.f('fk_ops_work_orders_updated_by_user_id_users')),
    sa.ForeignKeyConstraint(['vendor_id'], ['ops_vendors.id'], name=op.f('fk_ops_work_orders_vendor_id_ops_vendors')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ops_work_orders')),
    sa.UniqueConstraint('organization_id', 'number', name='uq_ops_work_orders_org_number')
    )
    with op.batch_alter_table('ops_work_orders', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ops_work_orders_due_at'), ['due_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_work_orders_location_id'), ['location_id'], unique=False)
        batch_op.create_index('ix_ops_work_orders_org_status_due', ['organization_id', 'status', 'due_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_work_orders_organization_id'), ['organization_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_work_orders_parent_work_order_id'), ['parent_work_order_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_work_orders_primary_asset_id'), ['primary_asset_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_work_orders_project_id'), ['project_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_work_orders_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_work_orders_team_id'), ['team_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_work_orders_vendor_id'), ['vendor_id'], unique=False)

    op.create_table('ops_asset_status_history',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('asset_id', sa.Uuid(), nullable=False),
    sa.Column('from_status', sa.String(length=30), nullable=True),
    sa.Column('to_status', sa.String(length=30), nullable=False),
    sa.Column('downtime_type', sa.String(length=20), nullable=True),
    sa.Column('downtime_reason', sa.String(length=160), nullable=True),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('started_at', asme.ops.types.UTCDateTime(), nullable=False),
    sa.Column('ended_at', asme.ops.types.UTCDateTime(), nullable=True),
    sa.Column('changed_by_user_id', sa.Integer(), nullable=True),
    sa.Column('work_order_id', sa.Uuid(), nullable=True),
    sa.ForeignKeyConstraint(['asset_id'], ['ops_assets.id'], name=op.f('fk_ops_asset_status_history_asset_id_ops_assets'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['changed_by_user_id'], ['users.id'], name=op.f('fk_ops_asset_status_history_changed_by_user_id_users')),
    sa.ForeignKeyConstraint(['organization_id'], ['ops_organizations.id'], name=op.f('fk_ops_asset_status_history_organization_id_ops_organizations')),
    sa.ForeignKeyConstraint(['work_order_id'], ['ops_work_orders.id'], name=op.f('fk_ops_asset_status_history_work_order_id_ops_work_orders')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ops_asset_status_history'))
    )
    with op.batch_alter_table('ops_asset_status_history', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ops_asset_status_history_asset_id'), ['asset_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_asset_status_history_organization_id'), ['organization_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_asset_status_history_work_order_id'), ['work_order_id'], unique=False)

    op.create_table('ops_cost_entries',
    sa.Column('work_order_id', sa.Uuid(), nullable=False),
    sa.Column('type', sa.String(length=20), nullable=False),
    sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('vendor_id', sa.Uuid(), nullable=True),
    sa.Column('description', sa.String(length=400), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('created_by_user_id', sa.Integer(), nullable=True),
    sa.Column('updated_by_user_id', sa.Integer(), nullable=True),
    sa.Column('created_at', asme.ops.types.UTCDateTime(), nullable=False),
    sa.Column('updated_at', asme.ops.types.UTCDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], name=op.f('fk_ops_cost_entries_created_by_user_id_users')),
    sa.ForeignKeyConstraint(['organization_id'], ['ops_organizations.id'], name=op.f('fk_ops_cost_entries_organization_id_ops_organizations')),
    sa.ForeignKeyConstraint(['updated_by_user_id'], ['users.id'], name=op.f('fk_ops_cost_entries_updated_by_user_id_users')),
    sa.ForeignKeyConstraint(['vendor_id'], ['ops_vendors.id'], name=op.f('fk_ops_cost_entries_vendor_id_ops_vendors')),
    sa.ForeignKeyConstraint(['work_order_id'], ['ops_work_orders.id'], name=op.f('fk_ops_cost_entries_work_order_id_ops_work_orders'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ops_cost_entries'))
    )
    with op.batch_alter_table('ops_cost_entries', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ops_cost_entries_organization_id'), ['organization_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_cost_entries_vendor_id'), ['vendor_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_cost_entries_work_order_id'), ['work_order_id'], unique=False)

    op.create_table('ops_time_entries',
    sa.Column('work_order_id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('started_at', asme.ops.types.UTCDateTime(), nullable=True),
    sa.Column('ended_at', asme.ops.types.UTCDateTime(), nullable=True),
    sa.Column('minutes', sa.Integer(), nullable=False),
    sa.Column('note', sa.String(length=400), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('created_by_user_id', sa.Integer(), nullable=True),
    sa.Column('updated_by_user_id', sa.Integer(), nullable=True),
    sa.Column('created_at', asme.ops.types.UTCDateTime(), nullable=False),
    sa.Column('updated_at', asme.ops.types.UTCDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], name=op.f('fk_ops_time_entries_created_by_user_id_users')),
    sa.ForeignKeyConstraint(['organization_id'], ['ops_organizations.id'], name=op.f('fk_ops_time_entries_organization_id_ops_organizations')),
    sa.ForeignKeyConstraint(['updated_by_user_id'], ['users.id'], name=op.f('fk_ops_time_entries_updated_by_user_id_users')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_ops_time_entries_user_id_users')),
    sa.ForeignKeyConstraint(['work_order_id'], ['ops_work_orders.id'], name=op.f('fk_ops_time_entries_work_order_id_ops_work_orders'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ops_time_entries'))
    )
    with op.batch_alter_table('ops_time_entries', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ops_time_entries_organization_id'), ['organization_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_time_entries_user_id'), ['user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_time_entries_work_order_id'), ['work_order_id'], unique=False)

    op.create_table('ops_work_order_assets',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('work_order_id', sa.Uuid(), nullable=False),
    sa.Column('asset_id', sa.Uuid(), nullable=False),
    sa.Column('relationship_type', sa.String(length=20), nullable=False),
    sa.ForeignKeyConstraint(['asset_id'], ['ops_assets.id'], name=op.f('fk_ops_work_order_assets_asset_id_ops_assets')),
    sa.ForeignKeyConstraint(['work_order_id'], ['ops_work_orders.id'], name=op.f('fk_ops_work_order_assets_work_order_id_ops_work_orders'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ops_work_order_assets')),
    sa.UniqueConstraint('work_order_id', 'asset_id', name='uq_ops_work_order_assets_wo_asset')
    )
    with op.batch_alter_table('ops_work_order_assets', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ops_work_order_assets_asset_id'), ['asset_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_work_order_assets_work_order_id'), ['work_order_id'], unique=False)

    op.create_table('ops_work_order_assignees',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('work_order_id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('team_id', sa.Uuid(), nullable=True),
    sa.Column('assigned_at', asme.ops.types.UTCDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['team_id'], ['ops_teams.id'], name=op.f('fk_ops_work_order_assignees_team_id_ops_teams')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_ops_work_order_assignees_user_id_users')),
    sa.ForeignKeyConstraint(['work_order_id'], ['ops_work_orders.id'], name=op.f('fk_ops_work_order_assignees_work_order_id_ops_work_orders'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ops_work_order_assignees')),
    sa.UniqueConstraint('work_order_id', 'team_id', name='uq_ops_work_order_assignees_wo_team'),
    sa.UniqueConstraint('work_order_id', 'user_id', name='uq_ops_work_order_assignees_wo_user')
    )
    with op.batch_alter_table('ops_work_order_assignees', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ops_work_order_assignees_team_id'), ['team_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_work_order_assignees_user_id'), ['user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_work_order_assignees_work_order_id'), ['work_order_id'], unique=False)

    op.create_table('ops_work_order_categories',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('work_order_id', sa.Uuid(), nullable=False),
    sa.Column('category_id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['category_id'], ['ops_categories.id'], name=op.f('fk_ops_work_order_categories_category_id_ops_categories')),
    sa.ForeignKeyConstraint(['work_order_id'], ['ops_work_orders.id'], name=op.f('fk_ops_work_order_categories_work_order_id_ops_work_orders'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ops_work_order_categories')),
    sa.UniqueConstraint('work_order_id', 'category_id', name='uq_ops_work_order_categories_wo_category')
    )
    with op.batch_alter_table('ops_work_order_categories', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ops_work_order_categories_category_id'), ['category_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_work_order_categories_work_order_id'), ['work_order_id'], unique=False)

    op.create_table('ops_work_order_dependencies',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('blocking_work_order_id', sa.Uuid(), nullable=False),
    sa.Column('blocked_work_order_id', sa.Uuid(), nullable=False),
    sa.Column('dependency_type', sa.String(length=30), nullable=False),
    sa.Column('created_at', asme.ops.types.UTCDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['blocked_work_order_id'], ['ops_work_orders.id'], name=op.f('fk_ops_work_order_dependencies_blocked_work_order_id_ops_work_orders'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['blocking_work_order_id'], ['ops_work_orders.id'], name=op.f('fk_ops_work_order_dependencies_blocking_work_order_id_ops_work_orders'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ops_work_order_dependencies')),
    sa.UniqueConstraint('blocking_work_order_id', 'blocked_work_order_id', name='uq_ops_work_order_dependencies_pair')
    )
    with op.batch_alter_table('ops_work_order_dependencies', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ops_work_order_dependencies_blocked_work_order_id'), ['blocked_work_order_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_work_order_dependencies_blocking_work_order_id'), ['blocking_work_order_id'], unique=False)

    op.create_table('ops_work_order_status_history',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('work_order_id', sa.Uuid(), nullable=False),
    sa.Column('from_status', sa.String(length=20), nullable=True),
    sa.Column('to_status', sa.String(length=20), nullable=False),
    sa.Column('changed_by_user_id', sa.Integer(), nullable=True),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('changed_at', asme.ops.types.UTCDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['changed_by_user_id'], ['users.id'], name=op.f('fk_ops_work_order_status_history_changed_by_user_id_users')),
    sa.ForeignKeyConstraint(['work_order_id'], ['ops_work_orders.id'], name=op.f('fk_ops_work_order_status_history_work_order_id_ops_work_orders'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ops_work_order_status_history'))
    )
    with op.batch_alter_table('ops_work_order_status_history', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ops_work_order_status_history_changed_at'), ['changed_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_work_order_status_history_work_order_id'), ['work_order_id'], unique=False)

    op.create_table('ops_work_order_watchers',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('work_order_id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_ops_work_order_watchers_user_id_users')),
    sa.ForeignKeyConstraint(['work_order_id'], ['ops_work_orders.id'], name=op.f('fk_ops_work_order_watchers_work_order_id_ops_work_orders'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ops_work_order_watchers')),
    sa.UniqueConstraint('work_order_id', 'user_id', name='uq_ops_work_order_watchers_wo_user')
    )
    with op.batch_alter_table('ops_work_order_watchers', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ops_work_order_watchers_user_id'), ['user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_work_order_watchers_work_order_id'), ['work_order_id'], unique=False)


    with op.batch_alter_table('outbox_jobs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('idempotency_key', sa.String(length=160), nullable=True))
        batch_op.create_unique_constraint('uq_outbox_jobs_idempotency_key', ['idempotency_key'])


def downgrade():
    with op.batch_alter_table('outbox_jobs', schema=None) as batch_op:
        batch_op.drop_constraint('uq_outbox_jobs_idempotency_key', type_='unique')
        batch_op.drop_column('idempotency_key')

    with op.batch_alter_table('ops_work_order_watchers', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ops_work_order_watchers_work_order_id'))
        batch_op.drop_index(batch_op.f('ix_ops_work_order_watchers_user_id'))

    op.drop_table('ops_work_order_watchers')
    with op.batch_alter_table('ops_work_order_status_history', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ops_work_order_status_history_work_order_id'))
        batch_op.drop_index(batch_op.f('ix_ops_work_order_status_history_changed_at'))

    op.drop_table('ops_work_order_status_history')
    with op.batch_alter_table('ops_work_order_dependencies', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ops_work_order_dependencies_blocking_work_order_id'))
        batch_op.drop_index(batch_op.f('ix_ops_work_order_dependencies_blocked_work_order_id'))

    op.drop_table('ops_work_order_dependencies')
    with op.batch_alter_table('ops_work_order_categories', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ops_work_order_categories_work_order_id'))
        batch_op.drop_index(batch_op.f('ix_ops_work_order_categories_category_id'))

    op.drop_table('ops_work_order_categories')
    with op.batch_alter_table('ops_work_order_assignees', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ops_work_order_assignees_work_order_id'))
        batch_op.drop_index(batch_op.f('ix_ops_work_order_assignees_user_id'))
        batch_op.drop_index(batch_op.f('ix_ops_work_order_assignees_team_id'))

    op.drop_table('ops_work_order_assignees')
    with op.batch_alter_table('ops_work_order_assets', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ops_work_order_assets_work_order_id'))
        batch_op.drop_index(batch_op.f('ix_ops_work_order_assets_asset_id'))

    op.drop_table('ops_work_order_assets')
    with op.batch_alter_table('ops_time_entries', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ops_time_entries_work_order_id'))
        batch_op.drop_index(batch_op.f('ix_ops_time_entries_user_id'))
        batch_op.drop_index(batch_op.f('ix_ops_time_entries_organization_id'))

    op.drop_table('ops_time_entries')
    with op.batch_alter_table('ops_cost_entries', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ops_cost_entries_work_order_id'))
        batch_op.drop_index(batch_op.f('ix_ops_cost_entries_vendor_id'))
        batch_op.drop_index(batch_op.f('ix_ops_cost_entries_organization_id'))

    op.drop_table('ops_cost_entries')
    with op.batch_alter_table('ops_asset_status_history', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ops_asset_status_history_work_order_id'))
        batch_op.drop_index(batch_op.f('ix_ops_asset_status_history_organization_id'))
        batch_op.drop_index(batch_op.f('ix_ops_asset_status_history_asset_id'))

    op.drop_table('ops_asset_status_history')
    with op.batch_alter_table('ops_work_orders', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ops_work_orders_vendor_id'))
        batch_op.drop_index(batch_op.f('ix_ops_work_orders_team_id'))
        batch_op.drop_index(batch_op.f('ix_ops_work_orders_status'))
        batch_op.drop_index(batch_op.f('ix_ops_work_orders_project_id'))
        batch_op.drop_index(batch_op.f('ix_ops_work_orders_primary_asset_id'))
        batch_op.drop_index(batch_op.f('ix_ops_work_orders_parent_work_order_id'))
        batch_op.drop_index(batch_op.f('ix_ops_work_orders_organization_id'))
        batch_op.drop_index('ix_ops_work_orders_org_status_due')
        batch_op.drop_index(batch_op.f('ix_ops_work_orders_location_id'))
        batch_op.drop_index(batch_op.f('ix_ops_work_orders_due_at'))

    op.drop_table('ops_work_orders')
    with op.batch_alter_table('ops_asset_type_links', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ops_asset_type_links_asset_type_id'))
        batch_op.drop_index(batch_op.f('ix_ops_asset_type_links_asset_id'))

    op.drop_table('ops_asset_type_links')
    with op.batch_alter_table('ops_team_members', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ops_team_members_user_id'))
        batch_op.drop_index(batch_op.f('ix_ops_team_members_team_id'))

    op.drop_table('ops_team_members')
    with op.batch_alter_table('ops_saved_filters', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ops_saved_filters_team_id'))
        batch_op.drop_index(batch_op.f('ix_ops_saved_filters_owner_user_id'))
        batch_op.drop_index(batch_op.f('ix_ops_saved_filters_organization_id'))
        batch_op.drop_index(batch_op.f('ix_ops_saved_filters_entity_type'))

    op.drop_table('ops_saved_filters')
    with op.batch_alter_table('ops_project_members', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ops_project_members_user_id'))
        batch_op.drop_index(batch_op.f('ix_ops_project_members_team_id'))
        batch_op.drop_index(batch_op.f('ix_ops_project_members_project_id'))

    op.drop_table('ops_project_members')
    with op.batch_alter_table('ops_assets', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ops_assets_status'))
        batch_op.drop_index(batch_op.f('ix_ops_assets_responsible_team_id'))
        batch_op.drop_index(batch_op.f('ix_ops_assets_project_id'))
        batch_op.drop_index(batch_op.f('ix_ops_assets_parent_asset_id'))
        batch_op.drop_index(batch_op.f('ix_ops_assets_organization_id'))
        batch_op.drop_index(batch_op.f('ix_ops_assets_location_id'))

    op.drop_table('ops_assets')
    with op.batch_alter_table('ops_teams', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ops_teams_project_id'))
        batch_op.drop_index(batch_op.f('ix_ops_teams_parent_team_id'))
        batch_op.drop_index(batch_op.f('ix_ops_teams_organization_id'))

    op.drop_table('ops_teams')
    with op.batch_alter_table('ops_role_permissions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ops_role_permissions_role_id'))
        batch_op.drop_index(batch_op.f('ix_ops_role_permissions_permission_id'))

    op.drop_table('ops_role_permissions')
    with op.batch_alter_table('ops_milestones', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ops_milestones_project_id'))
        batch_op.drop_index(batch_op.f('ix_ops_milestones_organization_id'))

    op.drop_table('ops_milestones')
    with op.batch_alter_table('ops_memberships', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ops_memberships_user_id'))
        batch_op.drop_index(batch_op.f('ix_ops_memberships_role_id'))
        batch_op.drop_index(batch_op.f('ix_ops_memberships_organization_id'))
        batch_op.drop_index(batch_op.f('ix_ops_memberships_member_status'))

    op.drop_table('ops_memberships')
    with op.batch_alter_table('ops_vendors', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ops_vendors_organization_id'))

    op.drop_table('ops_vendors')
    with op.batch_alter_table('ops_user_preferences', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ops_user_preferences_user_id'))
        batch_op.drop_index(batch_op.f('ix_ops_user_preferences_organization_id'))

    op.drop_table('ops_user_preferences')
    with op.batch_alter_table('ops_roles', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ops_roles_organization_id'))

    op.drop_table('ops_roles')
    with op.batch_alter_table('ops_projects', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ops_projects_status'))
        batch_op.drop_index(batch_op.f('ix_ops_projects_public_project_id'))
        batch_op.drop_index(batch_op.f('ix_ops_projects_organization_id'))
        batch_op.drop_index(batch_op.f('ix_ops_projects_lead_user_id'))

    op.drop_table('ops_projects')
    with op.batch_alter_table('ops_notifications', schema=None) as batch_op:
        batch_op.drop_index('ix_ops_notifications_user_unread')
        batch_op.drop_index(batch_op.f('ix_ops_notifications_user_id'))
        batch_op.drop_index(batch_op.f('ix_ops_notifications_organization_id'))
        batch_op.drop_index(batch_op.f('ix_ops_notifications_created_at'))

    op.drop_table('ops_notifications')
    with op.batch_alter_table('ops_locations', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ops_locations_parent_location_id'))
        batch_op.drop_index(batch_op.f('ix_ops_locations_organization_id'))

    op.drop_table('ops_locations')
    with op.batch_alter_table('ops_comments', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ops_comments_parent_comment_id'))
        batch_op.drop_index(batch_op.f('ix_ops_comments_organization_id'))
        batch_op.drop_index('ix_ops_comments_entity')
        batch_op.drop_index(batch_op.f('ix_ops_comments_author_user_id'))

    op.drop_table('ops_comments')
    with op.batch_alter_table('ops_categories', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ops_categories_organization_id'))

    op.drop_table('ops_categories')
    with op.batch_alter_table('ops_audit_events', schema=None) as batch_op:
        batch_op.drop_index('ix_ops_audit_events_org_occurred')
        batch_op.drop_index(batch_op.f('ix_ops_audit_events_event_type'))
        batch_op.drop_index('ix_ops_audit_events_entity')

    op.drop_table('ops_audit_events')
    with op.batch_alter_table('ops_attachments', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ops_attachments_organization_id'))
        batch_op.drop_index('ix_ops_attachments_entity')

    op.drop_table('ops_attachments')
    with op.batch_alter_table('ops_asset_types', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ops_asset_types_organization_id'))

    op.drop_table('ops_asset_types')
    with op.batch_alter_table('ops_sequences', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ops_sequences_organization_id'))

    op.drop_table('ops_sequences')
    with op.batch_alter_table('ops_permissions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ops_permissions_key'))

    op.drop_table('ops_permissions')
    with op.batch_alter_table('ops_organizations', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ops_organizations_slug'))

    op.drop_table('ops_organizations')
