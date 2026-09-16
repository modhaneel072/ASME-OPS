"""ASME Ops Stage 4: parts, part types, part vendors and spare-part links,
inventory balances and the append-only inventory ledger, work-order parts,
purchase requests with items and approval events, plus
``ops_cost_entries.inventory_transaction_id``. Additive only.

Revision ID: 0004_ops_inventory
Revises: 0003_ops_foundation
Create Date: 2026-09-14 18:37:23.979399

"""
from alembic import op
import sqlalchemy as sa

import asme.ops.types

# revision identifiers, used by Alembic.
revision = '0004_ops_inventory'
down_revision = '0003_ops_foundation'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('ops_part_types',
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('color', sa.String(length=20), nullable=False),
    sa.Column('icon', sa.String(length=60), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('created_by_user_id', sa.Integer(), nullable=True),
    sa.Column('updated_by_user_id', sa.Integer(), nullable=True),
    sa.Column('created_at', asme.ops.types.UTCDateTime(), nullable=False),
    sa.Column('updated_at', asme.ops.types.UTCDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], name=op.f('fk_ops_part_types_created_by_user_id_users')),
    sa.ForeignKeyConstraint(['organization_id'], ['ops_organizations.id'], name=op.f('fk_ops_part_types_organization_id_ops_organizations')),
    sa.ForeignKeyConstraint(['updated_by_user_id'], ['users.id'], name=op.f('fk_ops_part_types_updated_by_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ops_part_types')),
    sa.UniqueConstraint('organization_id', 'name', name='uq_ops_part_types_org_name')
    )
    with op.batch_alter_table('ops_part_types', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ops_part_types_organization_id'), ['organization_id'], unique=False)

    op.create_table('ops_parts',
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('sku', sa.String(length=60), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('part_type_id', sa.Uuid(), nullable=True),
    sa.Column('manufacturer', sa.String(length=160), nullable=True),
    sa.Column('manufacturer_part_number', sa.String(length=160), nullable=True),
    sa.Column('unit', sa.String(length=20), nullable=False),
    sa.Column('unit_cost', sa.Numeric(precision=12, scale=4), nullable=True),
    sa.Column('is_critical', sa.Boolean(), nullable=False),
    sa.Column('minimum_stock', sa.Numeric(precision=14, scale=3), nullable=True),
    sa.Column('maximum_stock', sa.Numeric(precision=14, scale=3), nullable=True),
    sa.Column('reorder_quantity', sa.Numeric(precision=14, scale=3), nullable=True),
    sa.Column('default_location_id', sa.Uuid(), nullable=True),
    sa.Column('qr_code', sa.String(length=160), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('created_by_user_id', sa.Integer(), nullable=True),
    sa.Column('updated_by_user_id', sa.Integer(), nullable=True),
    sa.Column('created_at', asme.ops.types.UTCDateTime(), nullable=False),
    sa.Column('updated_at', asme.ops.types.UTCDateTime(), nullable=False),
    sa.CheckConstraint('maximum_stock IS NULL OR minimum_stock IS NULL OR maximum_stock >= minimum_stock', name=op.f('ck_ops_parts_maximum_at_least_minimum')),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], name=op.f('fk_ops_parts_created_by_user_id_users')),
    sa.ForeignKeyConstraint(['default_location_id'], ['ops_locations.id'], name=op.f('fk_ops_parts_default_location_id_ops_locations')),
    sa.ForeignKeyConstraint(['organization_id'], ['ops_organizations.id'], name=op.f('fk_ops_parts_organization_id_ops_organizations')),
    sa.ForeignKeyConstraint(['part_type_id'], ['ops_part_types.id'], name=op.f('fk_ops_parts_part_type_id_ops_part_types')),
    sa.ForeignKeyConstraint(['updated_by_user_id'], ['users.id'], name=op.f('fk_ops_parts_updated_by_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ops_parts')),
    sa.UniqueConstraint('organization_id', 'qr_code', name='uq_ops_parts_org_qr'),
    sa.UniqueConstraint('organization_id', 'sku', name='uq_ops_parts_org_sku')
    )
    with op.batch_alter_table('ops_parts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ops_parts_default_location_id'), ['default_location_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_parts_organization_id'), ['organization_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_parts_part_type_id'), ['part_type_id'], unique=False)

    op.create_table('ops_purchase_requests',
    sa.Column('number', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('requester_user_id', sa.Integer(), nullable=False),
    sa.Column('project_id', sa.Uuid(), nullable=True),
    sa.Column('vendor_id', sa.Uuid(), nullable=True),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('needed_by', sa.Date(), nullable=True),
    sa.Column('purpose', sa.Text(), nullable=True),
    sa.Column('budget_code', sa.String(length=60), nullable=True),
    sa.Column('shipping_amount', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('tax_amount', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('estimated_total', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('approved_total', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('order_reference', sa.String(length=120), nullable=True),
    sa.Column('decline_reason', sa.Text(), nullable=True),
    sa.Column('submitted_at', asme.ops.types.UTCDateTime(), nullable=True),
    sa.Column('approved_at', asme.ops.types.UTCDateTime(), nullable=True),
    sa.Column('ordered_at', asme.ops.types.UTCDateTime(), nullable=True),
    sa.Column('received_at', asme.ops.types.UTCDateTime(), nullable=True),
    sa.Column('declined_at', asme.ops.types.UTCDateTime(), nullable=True),
    sa.Column('canceled_at', asme.ops.types.UTCDateTime(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('created_by_user_id', sa.Integer(), nullable=True),
    sa.Column('updated_by_user_id', sa.Integer(), nullable=True),
    sa.Column('created_at', asme.ops.types.UTCDateTime(), nullable=False),
    sa.Column('updated_at', asme.ops.types.UTCDateTime(), nullable=False),
    sa.CheckConstraint('shipping_amount >= 0', name=op.f('ck_ops_purchase_requests_shipping_amount_not_negative')),
    sa.CheckConstraint('tax_amount >= 0', name=op.f('ck_ops_purchase_requests_tax_amount_not_negative')),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], name=op.f('fk_ops_purchase_requests_created_by_user_id_users')),
    sa.ForeignKeyConstraint(['organization_id'], ['ops_organizations.id'], name=op.f('fk_ops_purchase_requests_organization_id_ops_organizations')),
    sa.ForeignKeyConstraint(['project_id'], ['ops_projects.id'], name=op.f('fk_ops_purchase_requests_project_id_ops_projects')),
    sa.ForeignKeyConstraint(['requester_user_id'], ['users.id'], name=op.f('fk_ops_purchase_requests_requester_user_id_users')),
    sa.ForeignKeyConstraint(['updated_by_user_id'], ['users.id'], name=op.f('fk_ops_purchase_requests_updated_by_user_id_users')),
    sa.ForeignKeyConstraint(['vendor_id'], ['ops_vendors.id'], name=op.f('fk_ops_purchase_requests_vendor_id_ops_vendors')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ops_purchase_requests')),
    sa.UniqueConstraint('organization_id', 'number', name='uq_ops_purchase_requests_org_number')
    )
    with op.batch_alter_table('ops_purchase_requests', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ops_purchase_requests_organization_id'), ['organization_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_purchase_requests_project_id'), ['project_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_purchase_requests_requester_user_id'), ['requester_user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_purchase_requests_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_purchase_requests_vendor_id'), ['vendor_id'], unique=False)

    op.create_table('ops_inventory_balances',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('part_id', sa.Uuid(), nullable=False),
    sa.Column('location_id', sa.Uuid(), nullable=False),
    sa.Column('on_hand', sa.Numeric(precision=14, scale=3), nullable=False),
    sa.Column('reserved', sa.Numeric(precision=14, scale=3), nullable=False),
    sa.Column('updated_at', asme.ops.types.UTCDateTime(), nullable=False),
    sa.CheckConstraint('on_hand >= 0', name=op.f('ck_ops_inventory_balances_on_hand_not_negative')),
    sa.CheckConstraint('reserved >= 0', name=op.f('ck_ops_inventory_balances_reserved_not_negative')),
    sa.ForeignKeyConstraint(['location_id'], ['ops_locations.id'], name=op.f('fk_ops_inventory_balances_location_id_ops_locations')),
    sa.ForeignKeyConstraint(['organization_id'], ['ops_organizations.id'], name=op.f('fk_ops_inventory_balances_organization_id_ops_organizations')),
    sa.ForeignKeyConstraint(['part_id'], ['ops_parts.id'], name=op.f('fk_ops_inventory_balances_part_id_ops_parts'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ops_inventory_balances')),
    sa.UniqueConstraint('part_id', 'location_id', name='uq_ops_inventory_balances_part_location')
    )
    with op.batch_alter_table('ops_inventory_balances', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ops_inventory_balances_location_id'), ['location_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_inventory_balances_organization_id'), ['organization_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_inventory_balances_part_id'), ['part_id'], unique=False)

    op.create_table('ops_part_vendors',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('part_id', sa.Uuid(), nullable=False),
    sa.Column('vendor_id', sa.Uuid(), nullable=False),
    sa.Column('vendor_part_number', sa.String(length=160), nullable=True),
    sa.Column('url', sa.String(length=500), nullable=True),
    sa.Column('preferred', sa.Boolean(), nullable=False),
    sa.Column('last_price', sa.Numeric(precision=12, scale=4), nullable=True),
    sa.Column('last_ordered_at', asme.ops.types.UTCDateTime(), nullable=True),
    sa.ForeignKeyConstraint(['part_id'], ['ops_parts.id'], name=op.f('fk_ops_part_vendors_part_id_ops_parts'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['vendor_id'], ['ops_vendors.id'], name=op.f('fk_ops_part_vendors_vendor_id_ops_vendors')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ops_part_vendors')),
    sa.UniqueConstraint('part_id', 'vendor_id', name='uq_ops_part_vendors_part_vendor')
    )
    with op.batch_alter_table('ops_part_vendors', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ops_part_vendors_part_id'), ['part_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_part_vendors_vendor_id'), ['vendor_id'], unique=False)

    op.create_table('ops_purchase_request_events',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('purchase_request_id', sa.Uuid(), nullable=False),
    sa.Column('from_status', sa.String(length=30), nullable=True),
    sa.Column('to_status', sa.String(length=30), nullable=False),
    sa.Column('action', sa.String(length=30), nullable=False),
    sa.Column('step', sa.String(length=20), nullable=True),
    sa.Column('comment', sa.Text(), nullable=True),
    sa.Column('actor_user_id', sa.Integer(), nullable=True),
    sa.Column('created_at', asme.ops.types.UTCDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], name=op.f('fk_ops_purchase_request_events_actor_user_id_users')),
    sa.ForeignKeyConstraint(['organization_id'], ['ops_organizations.id'], name=op.f('fk_ops_purchase_request_events_organization_id_ops_organizations')),
    sa.ForeignKeyConstraint(['purchase_request_id'], ['ops_purchase_requests.id'], name=op.f('fk_ops_purchase_request_events_purchase_request_id_ops_purchase_requests'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ops_purchase_request_events'))
    )
    with op.batch_alter_table('ops_purchase_request_events', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ops_purchase_request_events_actor_user_id'), ['actor_user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_purchase_request_events_organization_id'), ['organization_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_purchase_request_events_purchase_request_id'), ['purchase_request_id'], unique=False)

    op.create_table('ops_purchase_request_items',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('purchase_request_id', sa.Uuid(), nullable=False),
    sa.Column('part_id', sa.Uuid(), nullable=True),
    sa.Column('description', sa.String(length=300), nullable=False),
    sa.Column('vendor_part_number', sa.String(length=160), nullable=True),
    sa.Column('url', sa.String(length=500), nullable=True),
    sa.Column('quantity', sa.Numeric(precision=14, scale=3), nullable=False),
    sa.Column('unit_price', sa.Numeric(precision=12, scale=4), nullable=False),
    sa.Column('received_quantity', sa.Numeric(precision=14, scale=3), nullable=False),
    sa.Column('receive_location_id', sa.Uuid(), nullable=True),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('created_at', asme.ops.types.UTCDateTime(), nullable=False),
    sa.CheckConstraint('quantity > 0', name=op.f('ck_ops_purchase_request_items_quantity_positive')),
    sa.CheckConstraint('received_quantity >= 0', name=op.f('ck_ops_purchase_request_items_received_quantity_not_negative')),
    sa.CheckConstraint('unit_price >= 0', name=op.f('ck_ops_purchase_request_items_unit_price_not_negative')),
    sa.ForeignKeyConstraint(['part_id'], ['ops_parts.id'], name=op.f('fk_ops_purchase_request_items_part_id_ops_parts')),
    sa.ForeignKeyConstraint(['purchase_request_id'], ['ops_purchase_requests.id'], name=op.f('fk_ops_purchase_request_items_purchase_request_id_ops_purchase_requests'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['receive_location_id'], ['ops_locations.id'], name=op.f('fk_ops_purchase_request_items_receive_location_id_ops_locations')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ops_purchase_request_items'))
    )
    with op.batch_alter_table('ops_purchase_request_items', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ops_purchase_request_items_part_id'), ['part_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_purchase_request_items_purchase_request_id'), ['purchase_request_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_purchase_request_items_receive_location_id'), ['receive_location_id'], unique=False)

    op.create_table('ops_part_assets',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('part_id', sa.Uuid(), nullable=False),
    sa.Column('asset_id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['asset_id'], ['ops_assets.id'], name=op.f('fk_ops_part_assets_asset_id_ops_assets'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['part_id'], ['ops_parts.id'], name=op.f('fk_ops_part_assets_part_id_ops_parts'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ops_part_assets')),
    sa.UniqueConstraint('part_id', 'asset_id', name='uq_ops_part_assets_part_asset')
    )
    with op.batch_alter_table('ops_part_assets', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ops_part_assets_asset_id'), ['asset_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_part_assets_part_id'), ['part_id'], unique=False)

    op.create_table('ops_work_order_parts',
    sa.Column('work_order_id', sa.Uuid(), nullable=False),
    sa.Column('part_id', sa.Uuid(), nullable=False),
    sa.Column('location_id', sa.Uuid(), nullable=True),
    sa.Column('quantity_planned', sa.Numeric(precision=14, scale=3), nullable=False),
    sa.Column('quantity_reserved', sa.Numeric(precision=14, scale=3), nullable=False),
    sa.Column('quantity_issued', sa.Numeric(precision=14, scale=3), nullable=False),
    sa.Column('quantity_returned', sa.Numeric(precision=14, scale=3), nullable=False),
    sa.Column('readiness', sa.String(length=20), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('created_by_user_id', sa.Integer(), nullable=True),
    sa.Column('updated_by_user_id', sa.Integer(), nullable=True),
    sa.Column('created_at', asme.ops.types.UTCDateTime(), nullable=False),
    sa.Column('updated_at', asme.ops.types.UTCDateTime(), nullable=False),
    sa.CheckConstraint('quantity_issued >= 0', name=op.f('ck_ops_work_order_parts_quantity_issued_not_negative')),
    sa.CheckConstraint('quantity_planned > 0', name=op.f('ck_ops_work_order_parts_quantity_planned_positive')),
    sa.CheckConstraint('quantity_reserved >= 0', name=op.f('ck_ops_work_order_parts_quantity_reserved_not_negative')),
    sa.CheckConstraint('quantity_returned >= 0', name=op.f('ck_ops_work_order_parts_quantity_returned_not_negative')),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], name=op.f('fk_ops_work_order_parts_created_by_user_id_users')),
    sa.ForeignKeyConstraint(['location_id'], ['ops_locations.id'], name=op.f('fk_ops_work_order_parts_location_id_ops_locations')),
    sa.ForeignKeyConstraint(['organization_id'], ['ops_organizations.id'], name=op.f('fk_ops_work_order_parts_organization_id_ops_organizations')),
    sa.ForeignKeyConstraint(['part_id'], ['ops_parts.id'], name=op.f('fk_ops_work_order_parts_part_id_ops_parts')),
    sa.ForeignKeyConstraint(['updated_by_user_id'], ['users.id'], name=op.f('fk_ops_work_order_parts_updated_by_user_id_users')),
    sa.ForeignKeyConstraint(['work_order_id'], ['ops_work_orders.id'], name=op.f('fk_ops_work_order_parts_work_order_id_ops_work_orders'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ops_work_order_parts')),
    sa.UniqueConstraint('work_order_id', 'part_id', 'location_id', name='uq_ops_work_order_parts_wo_part_location')
    )
    with op.batch_alter_table('ops_work_order_parts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ops_work_order_parts_location_id'), ['location_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_work_order_parts_organization_id'), ['organization_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_work_order_parts_part_id'), ['part_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_work_order_parts_readiness'), ['readiness'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_work_order_parts_work_order_id'), ['work_order_id'], unique=False)

    op.create_table('ops_inventory_transactions',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('part_id', sa.Uuid(), nullable=False),
    sa.Column('location_id', sa.Uuid(), nullable=False),
    sa.Column('transaction_type', sa.String(length=20), nullable=False),
    sa.Column('on_hand_delta', sa.Numeric(precision=14, scale=3), nullable=False),
    sa.Column('reserved_delta', sa.Numeric(precision=14, scale=3), nullable=False),
    sa.Column('quantity', sa.Numeric(precision=14, scale=3), nullable=False),
    sa.Column('counted_quantity', sa.Numeric(precision=14, scale=3), nullable=True),
    sa.Column('on_hand_after', sa.Numeric(precision=14, scale=3), nullable=False),
    sa.Column('reserved_after', sa.Numeric(precision=14, scale=3), nullable=False),
    sa.Column('unit_cost', sa.Numeric(precision=12, scale=4), nullable=True),
    sa.Column('work_order_id', sa.Uuid(), nullable=True),
    sa.Column('work_order_part_id', sa.Uuid(), nullable=True),
    sa.Column('purchase_request_id', sa.Uuid(), nullable=True),
    sa.Column('purchase_request_item_id', sa.Uuid(), nullable=True),
    sa.Column('reference_transaction_id', sa.Uuid(), nullable=True),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('created_by_user_id', sa.Integer(), nullable=True),
    sa.Column('created_at', asme.ops.types.UTCDateTime(), nullable=False),
    sa.CheckConstraint('on_hand_after >= 0', name=op.f('ck_ops_inventory_transactions_on_hand_after_not_negative')),
    sa.CheckConstraint('quantity >= 0', name=op.f('ck_ops_inventory_transactions_quantity_not_negative')),
    sa.CheckConstraint('reserved_after >= 0', name=op.f('ck_ops_inventory_transactions_reserved_after_not_negative')),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], name=op.f('fk_ops_inventory_transactions_created_by_user_id_users')),
    sa.ForeignKeyConstraint(['location_id'], ['ops_locations.id'], name=op.f('fk_ops_inventory_transactions_location_id_ops_locations')),
    sa.ForeignKeyConstraint(['organization_id'], ['ops_organizations.id'], name=op.f('fk_ops_inventory_transactions_organization_id_ops_organizations')),
    sa.ForeignKeyConstraint(['part_id'], ['ops_parts.id'], name=op.f('fk_ops_inventory_transactions_part_id_ops_parts')),
    sa.ForeignKeyConstraint(['purchase_request_id'], ['ops_purchase_requests.id'], name=op.f('fk_ops_inventory_transactions_purchase_request_id_ops_purchase_requests')),
    sa.ForeignKeyConstraint(['purchase_request_item_id'], ['ops_purchase_request_items.id'], name=op.f('fk_ops_inventory_transactions_purchase_request_item_id_ops_purchase_request_items')),
    sa.ForeignKeyConstraint(['reference_transaction_id'], ['ops_inventory_transactions.id'], name=op.f('fk_ops_inventory_transactions_reference_transaction_id_ops_inventory_transactions')),
    sa.ForeignKeyConstraint(['work_order_id'], ['ops_work_orders.id'], name=op.f('fk_ops_inventory_transactions_work_order_id_ops_work_orders')),
    sa.ForeignKeyConstraint(['work_order_part_id'], ['ops_work_order_parts.id'], name=op.f('fk_ops_inventory_transactions_work_order_part_id_ops_work_order_parts')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ops_inventory_transactions'))
    )
    with op.batch_alter_table('ops_inventory_transactions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ops_inventory_transactions_created_by_user_id'), ['created_by_user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_inventory_transactions_location_id'), ['location_id'], unique=False)
        batch_op.create_index('ix_ops_inventory_transactions_org_created', ['organization_id', 'created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_inventory_transactions_organization_id'), ['organization_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_inventory_transactions_part_id'), ['part_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_inventory_transactions_purchase_request_id'), ['purchase_request_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_inventory_transactions_purchase_request_item_id'), ['purchase_request_item_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_inventory_transactions_reference_transaction_id'), ['reference_transaction_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_inventory_transactions_transaction_type'), ['transaction_type'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_inventory_transactions_work_order_id'), ['work_order_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ops_inventory_transactions_work_order_part_id'), ['work_order_part_id'], unique=False)

    with op.batch_alter_table('ops_cost_entries', schema=None) as batch_op:
        batch_op.add_column(sa.Column('inventory_transaction_id', sa.Uuid(), nullable=True))
        batch_op.create_index(batch_op.f('ix_ops_cost_entries_inventory_transaction_id'), ['inventory_transaction_id'], unique=False)
        batch_op.create_foreign_key(batch_op.f('fk_ops_cost_entries_inventory_transaction_id_ops_inventory_transactions'), 'ops_inventory_transactions', ['inventory_transaction_id'], ['id'])



def downgrade():
    with op.batch_alter_table('ops_cost_entries', schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f('fk_ops_cost_entries_inventory_transaction_id_ops_inventory_transactions'), type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_ops_cost_entries_inventory_transaction_id'))
        batch_op.drop_column('inventory_transaction_id')

    with op.batch_alter_table('ops_inventory_transactions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ops_inventory_transactions_work_order_part_id'))
        batch_op.drop_index(batch_op.f('ix_ops_inventory_transactions_work_order_id'))
        batch_op.drop_index(batch_op.f('ix_ops_inventory_transactions_transaction_type'))
        batch_op.drop_index(batch_op.f('ix_ops_inventory_transactions_reference_transaction_id'))
        batch_op.drop_index(batch_op.f('ix_ops_inventory_transactions_purchase_request_item_id'))
        batch_op.drop_index(batch_op.f('ix_ops_inventory_transactions_purchase_request_id'))
        batch_op.drop_index(batch_op.f('ix_ops_inventory_transactions_part_id'))
        batch_op.drop_index(batch_op.f('ix_ops_inventory_transactions_organization_id'))
        batch_op.drop_index('ix_ops_inventory_transactions_org_created')
        batch_op.drop_index(batch_op.f('ix_ops_inventory_transactions_location_id'))
        batch_op.drop_index(batch_op.f('ix_ops_inventory_transactions_created_by_user_id'))

    op.drop_table('ops_inventory_transactions')
    with op.batch_alter_table('ops_work_order_parts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ops_work_order_parts_work_order_id'))
        batch_op.drop_index(batch_op.f('ix_ops_work_order_parts_readiness'))
        batch_op.drop_index(batch_op.f('ix_ops_work_order_parts_part_id'))
        batch_op.drop_index(batch_op.f('ix_ops_work_order_parts_organization_id'))
        batch_op.drop_index(batch_op.f('ix_ops_work_order_parts_location_id'))

    op.drop_table('ops_work_order_parts')
    with op.batch_alter_table('ops_part_assets', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ops_part_assets_part_id'))
        batch_op.drop_index(batch_op.f('ix_ops_part_assets_asset_id'))

    op.drop_table('ops_part_assets')
    with op.batch_alter_table('ops_purchase_request_items', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ops_purchase_request_items_receive_location_id'))
        batch_op.drop_index(batch_op.f('ix_ops_purchase_request_items_purchase_request_id'))
        batch_op.drop_index(batch_op.f('ix_ops_purchase_request_items_part_id'))

    op.drop_table('ops_purchase_request_items')
    with op.batch_alter_table('ops_purchase_request_events', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ops_purchase_request_events_purchase_request_id'))
        batch_op.drop_index(batch_op.f('ix_ops_purchase_request_events_organization_id'))
        batch_op.drop_index(batch_op.f('ix_ops_purchase_request_events_actor_user_id'))

    op.drop_table('ops_purchase_request_events')
    with op.batch_alter_table('ops_part_vendors', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ops_part_vendors_vendor_id'))
        batch_op.drop_index(batch_op.f('ix_ops_part_vendors_part_id'))

    op.drop_table('ops_part_vendors')
    with op.batch_alter_table('ops_inventory_balances', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ops_inventory_balances_part_id'))
        batch_op.drop_index(batch_op.f('ix_ops_inventory_balances_organization_id'))
        batch_op.drop_index(batch_op.f('ix_ops_inventory_balances_location_id'))

    op.drop_table('ops_inventory_balances')
    with op.batch_alter_table('ops_purchase_requests', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ops_purchase_requests_vendor_id'))
        batch_op.drop_index(batch_op.f('ix_ops_purchase_requests_status'))
        batch_op.drop_index(batch_op.f('ix_ops_purchase_requests_requester_user_id'))
        batch_op.drop_index(batch_op.f('ix_ops_purchase_requests_project_id'))
        batch_op.drop_index(batch_op.f('ix_ops_purchase_requests_organization_id'))

    op.drop_table('ops_purchase_requests')
    with op.batch_alter_table('ops_parts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ops_parts_part_type_id'))
        batch_op.drop_index(batch_op.f('ix_ops_parts_organization_id'))
        batch_op.drop_index(batch_op.f('ix_ops_parts_default_location_id'))

    op.drop_table('ops_parts')
    with op.batch_alter_table('ops_part_types', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ops_part_types_organization_id'))

    op.drop_table('ops_part_types')
