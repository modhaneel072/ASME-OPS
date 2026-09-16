"""Parts inventory, work-order parts and purchase requests (Stage 4).

``ops_inventory_transactions`` is an append-only ledger: every quantity change
is a new row written by ``asme.ops.services.inventory_ledger.post`` and
``ops_inventory_balances`` is the cached per-location projection of it. The ORM
refuses to update or delete a transaction (see the listeners at the bottom);
corrections are new transactions that reference the original.
"""

from __future__ import annotations

from sqlalchemy import event, inspect as sa_inspect
from sqlalchemy.orm import Session

from asme.extensions import db
from asme.ops.types import UUID, OpsBase, UTCDateTime, user_fk, utcnow, uuid_fk, uuid_pk

PART_UNITS = ("each", "pack", "box", "pair", "set", "g", "kg", "lb", "oz", "m", "cm", "mm", "ft", "in", "roll", "spool", "sheet", "L", "mL")
INVENTORY_TRANSACTION_TYPES = ("receipt", "issue", "return", "adjustment", "transfer", "reservation", "release", "cycle_count", "scrap")
STOCK_STATES = ("ok", "low", "out", "untracked")
WORK_ORDER_PART_READINESS = ("assigned", "reserved", "kitted", "staged", "issued")
PURCHASE_REQUEST_STATUSES = (
    "draft",
    "submitted",
    "treasurer_review",
    "advisor_review",
    "approved",
    "ordered",
    "partially_received",
    "received",
    "declined",
    "canceled",
)
PURCHASE_REQUEST_REVIEW_STATUSES = ("submitted", "treasurer_review", "advisor_review")
PURCHASE_REQUEST_ORDERED_STATUSES = ("ordered", "partially_received")
PURCHASE_REQUEST_COMMITTED_STATUSES = ("approved", "ordered", "partially_received", "received")
PURCHASE_REQUEST_CLOSED_STATUSES = ("received", "declined", "canceled")
PURCHASE_REQUEST_ACTIONS = ("submit", "approve", "decline", "request_changes", "order", "receive", "cancel", "reopen")
PURCHASE_REQUEST_STEPS = ("project_lead", "treasurer", "advisor")

PART_TYPE_DEFAULT_COLOR = "#475569"
PART_TYPE_DEFAULT_ICON = "package"
IMMUTABLE_TRANSACTION_MESSAGE = "inventory transactions are immutable"


class PartType(OpsBase, db.Model):
    __tablename__ = "ops_part_types"
    __table_args__ = (db.UniqueConstraint("organization_id", "name", name="uq_ops_part_types_org_name"),)

    name = db.Column(db.String(120), nullable=False)
    color = db.Column(db.String(20), nullable=False, default=PART_TYPE_DEFAULT_COLOR)
    icon = db.Column(db.String(60), nullable=False, default=PART_TYPE_DEFAULT_ICON)


class Part(OpsBase, db.Model):
    __tablename__ = "ops_parts"
    __table_args__ = (
        db.UniqueConstraint("organization_id", "sku", name="uq_ops_parts_org_sku"),
        db.UniqueConstraint("organization_id", "qr_code", name="uq_ops_parts_org_qr"),
        db.CheckConstraint(
            "maximum_stock IS NULL OR minimum_stock IS NULL OR maximum_stock >= minimum_stock",
            name="maximum_at_least_minimum",
        ),
    )

    name = db.Column(db.String(200), nullable=False)
    sku = db.Column(db.String(60), nullable=True)
    description = db.Column(db.Text, nullable=True)
    part_type_id = uuid_fk("ops_part_types.id")
    manufacturer = db.Column(db.String(160), nullable=True)
    manufacturer_part_number = db.Column(db.String(160), nullable=True)
    unit = db.Column(db.String(20), nullable=False, default="each")
    unit_cost = db.Column(db.Numeric(12, 4), nullable=True)
    is_critical = db.Column(db.Boolean, nullable=False, default=False)
    minimum_stock = db.Column(db.Numeric(14, 3), nullable=True)
    maximum_stock = db.Column(db.Numeric(14, 3), nullable=True)
    reorder_quantity = db.Column(db.Numeric(14, 3), nullable=True)
    default_location_id = uuid_fk("ops_locations.id")
    qr_code = db.Column(db.String(160), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    part_type = db.relationship("PartType", foreign_keys=[part_type_id], lazy="joined")
    default_location = db.relationship("Location", foreign_keys=[default_location_id])
    created_by = db.relationship("User", foreign_keys="Part.created_by_user_id")
    vendor_links = db.relationship("PartVendor", back_populates="part", cascade="all, delete-orphan", lazy="selectin")
    asset_links = db.relationship("PartAsset", back_populates="part", cascade="all, delete-orphan", lazy="selectin")

    @property
    def preferred_vendor_link(self) -> "PartVendor | None":
        return next((link for link in self.vendor_links if link.preferred), None)


class PartVendor(db.Model):
    __tablename__ = "ops_part_vendors"
    __table_args__ = (db.UniqueConstraint("part_id", "vendor_id", name="uq_ops_part_vendors_part_vendor"),)

    id = uuid_pk()
    part_id = uuid_fk("ops_parts.id", nullable=False, ondelete="CASCADE")
    vendor_id = uuid_fk("ops_vendors.id", nullable=False)
    vendor_part_number = db.Column(db.String(160), nullable=True)
    url = db.Column(db.String(500), nullable=True)
    preferred = db.Column(db.Boolean, nullable=False, default=False)
    last_price = db.Column(db.Numeric(12, 4), nullable=True)
    last_ordered_at = db.Column(UTCDateTime(), nullable=True)

    part = db.relationship("Part", back_populates="vendor_links")
    vendor = db.relationship("Vendor", lazy="joined")


class PartAsset(db.Model):
    """"Spare part for this asset"."""

    __tablename__ = "ops_part_assets"
    __table_args__ = (db.UniqueConstraint("part_id", "asset_id", name="uq_ops_part_assets_part_asset"),)

    id = uuid_pk()
    part_id = uuid_fk("ops_parts.id", nullable=False, ondelete="CASCADE")
    asset_id = uuid_fk("ops_assets.id", nullable=False, ondelete="CASCADE")

    part = db.relationship("Part", back_populates="asset_links")
    asset = db.relationship("Asset", lazy="joined")


class InventoryBalance(db.Model):
    """Cached projection of the ledger per (part, location). Written only by
    ``inventory_ledger.post``."""

    __tablename__ = "ops_inventory_balances"
    __table_args__ = (
        db.UniqueConstraint("part_id", "location_id", name="uq_ops_inventory_balances_part_location"),
        db.CheckConstraint("on_hand >= 0", name="on_hand_not_negative"),
        db.CheckConstraint("reserved >= 0", name="reserved_not_negative"),
    )

    id = uuid_pk()
    organization_id = db.Column(UUID, db.ForeignKey("ops_organizations.id"), nullable=False, index=True)
    part_id = uuid_fk("ops_parts.id", nullable=False, ondelete="CASCADE")
    location_id = uuid_fk("ops_locations.id", nullable=False)
    on_hand = db.Column(db.Numeric(14, 3), nullable=False, default=0)
    reserved = db.Column(db.Numeric(14, 3), nullable=False, default=0)
    updated_at = db.Column(UTCDateTime(), nullable=False, default=utcnow, onupdate=utcnow)

    part = db.relationship("Part", foreign_keys=[part_id])
    location = db.relationship("Location", foreign_keys=[location_id], lazy="joined")

    @property
    def available(self):
        return (self.on_hand or 0) - (self.reserved or 0)


class InventoryTransaction(db.Model):
    """Append-only ledger row. Never updated or deleted."""

    __tablename__ = "ops_inventory_transactions"
    __table_args__ = (
        db.CheckConstraint("quantity >= 0", name="quantity_not_negative"),
        db.CheckConstraint("on_hand_after >= 0", name="on_hand_after_not_negative"),
        db.CheckConstraint("reserved_after >= 0", name="reserved_after_not_negative"),
        db.Index("ix_ops_inventory_transactions_org_created", "organization_id", "created_at"),
    )

    id = uuid_pk()
    organization_id = db.Column(UUID, db.ForeignKey("ops_organizations.id"), nullable=False, index=True)
    part_id = uuid_fk("ops_parts.id", nullable=False)
    location_id = uuid_fk("ops_locations.id", nullable=False)
    transaction_type = db.Column(db.String(20), nullable=False, index=True)
    on_hand_delta = db.Column(db.Numeric(14, 3), nullable=False)
    reserved_delta = db.Column(db.Numeric(14, 3), nullable=False, default=0)
    quantity = db.Column(db.Numeric(14, 3), nullable=False)
    counted_quantity = db.Column(db.Numeric(14, 3), nullable=True)
    on_hand_after = db.Column(db.Numeric(14, 3), nullable=False)
    reserved_after = db.Column(db.Numeric(14, 3), nullable=False)
    unit_cost = db.Column(db.Numeric(12, 4), nullable=True)
    work_order_id = uuid_fk("ops_work_orders.id")
    work_order_part_id = uuid_fk("ops_work_order_parts.id")
    purchase_request_id = uuid_fk("ops_purchase_requests.id")
    purchase_request_item_id = uuid_fk("ops_purchase_request_items.id")
    reference_transaction_id = uuid_fk("ops_inventory_transactions.id")
    note = db.Column(db.Text, nullable=True)
    created_by_user_id = user_fk(index=True)
    created_at = db.Column(UTCDateTime(), nullable=False, default=utcnow)

    # Many-to-one only: a collection on the other side would mark the original
    # row dirty when a correction is appended and trip the immutability guard.
    part = db.relationship("Part", foreign_keys=[part_id])
    location = db.relationship("Location", foreign_keys=[location_id])
    work_order = db.relationship("WorkOrder", foreign_keys=[work_order_id])
    work_order_part = db.relationship("WorkOrderPart", foreign_keys=[work_order_part_id])
    purchase_request = db.relationship("PurchaseRequest", foreign_keys=[purchase_request_id])
    purchase_request_item = db.relationship("PurchaseRequestItem", foreign_keys=[purchase_request_item_id])
    reference = db.relationship("InventoryTransaction", remote_side="InventoryTransaction.id", foreign_keys=[reference_transaction_id])
    created_by = db.relationship("User", foreign_keys=[created_by_user_id])


class WorkOrderPart(OpsBase, db.Model):
    __tablename__ = "ops_work_order_parts"
    __table_args__ = (
        db.UniqueConstraint("work_order_id", "part_id", "location_id", name="uq_ops_work_order_parts_wo_part_location"),
        db.CheckConstraint("quantity_planned > 0", name="quantity_planned_positive"),
        db.CheckConstraint("quantity_reserved >= 0", name="quantity_reserved_not_negative"),
        db.CheckConstraint("quantity_issued >= 0", name="quantity_issued_not_negative"),
        db.CheckConstraint("quantity_returned >= 0", name="quantity_returned_not_negative"),
    )

    work_order_id = uuid_fk("ops_work_orders.id", nullable=False, ondelete="CASCADE")
    part_id = uuid_fk("ops_parts.id", nullable=False)
    location_id = uuid_fk("ops_locations.id")
    quantity_planned = db.Column(db.Numeric(14, 3), nullable=False)
    quantity_reserved = db.Column(db.Numeric(14, 3), nullable=False, default=0)
    quantity_issued = db.Column(db.Numeric(14, 3), nullable=False, default=0)
    quantity_returned = db.Column(db.Numeric(14, 3), nullable=False, default=0)
    readiness = db.Column(db.String(20), nullable=False, default="assigned", index=True)
    note = db.Column(db.Text, nullable=True)

    work_order = db.relationship("WorkOrder", foreign_keys=[work_order_id])
    part = db.relationship("Part", foreign_keys=[part_id], lazy="joined")
    location = db.relationship("Location", foreign_keys=[location_id], lazy="joined")
    created_by = db.relationship("User", foreign_keys="WorkOrderPart.created_by_user_id")


class PurchaseRequest(OpsBase, db.Model):
    __tablename__ = "ops_purchase_requests"
    __table_args__ = (
        db.UniqueConstraint("organization_id", "number", name="uq_ops_purchase_requests_org_number"),
        db.CheckConstraint("shipping_amount >= 0", name="shipping_amount_not_negative"),
        db.CheckConstraint("tax_amount >= 0", name="tax_amount_not_negative"),
    )

    number = db.Column(db.Integer, nullable=False)
    title = db.Column(db.String(200), nullable=False)
    requester_user_id = user_fk(nullable=False, index=True)
    project_id = uuid_fk("ops_projects.id")
    vendor_id = uuid_fk("ops_vendors.id")
    status = db.Column(db.String(30), nullable=False, default="draft", index=True)
    needed_by = db.Column(db.Date, nullable=True)
    purpose = db.Column(db.Text, nullable=True)
    budget_code = db.Column(db.String(60), nullable=True)
    shipping_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    tax_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    estimated_total = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    approved_total = db.Column(db.Numeric(12, 2), nullable=True)
    order_reference = db.Column(db.String(120), nullable=True)
    decline_reason = db.Column(db.Text, nullable=True)
    submitted_at = db.Column(UTCDateTime(), nullable=True)
    approved_at = db.Column(UTCDateTime(), nullable=True)
    ordered_at = db.Column(UTCDateTime(), nullable=True)
    received_at = db.Column(UTCDateTime(), nullable=True)
    declined_at = db.Column(UTCDateTime(), nullable=True)
    canceled_at = db.Column(UTCDateTime(), nullable=True)

    requester = db.relationship("User", foreign_keys=[requester_user_id], lazy="joined")
    project = db.relationship("OpsProject", foreign_keys=[project_id])
    vendor = db.relationship("Vendor", foreign_keys=[vendor_id])
    created_by = db.relationship("User", foreign_keys="PurchaseRequest.created_by_user_id")
    items = db.relationship(
        "PurchaseRequestItem",
        back_populates="purchase_request",
        cascade="all, delete-orphan",
        order_by="(PurchaseRequestItem.position, PurchaseRequestItem.created_at)",
        lazy="selectin",
    )
    events = db.relationship(
        "PurchaseRequestEvent",
        back_populates="purchase_request",
        cascade="all, delete-orphan",
        order_by="(PurchaseRequestEvent.created_at, PurchaseRequestEvent.id)",
    )

    @property
    def display_number(self) -> str:
        return f"PR-{self.number}"


class PurchaseRequestItem(db.Model):
    __tablename__ = "ops_purchase_request_items"
    __table_args__ = (
        db.CheckConstraint("quantity > 0", name="quantity_positive"),
        db.CheckConstraint("unit_price >= 0", name="unit_price_not_negative"),
        db.CheckConstraint("received_quantity >= 0", name="received_quantity_not_negative"),
    )

    id = uuid_pk()
    purchase_request_id = uuid_fk("ops_purchase_requests.id", nullable=False, ondelete="CASCADE")
    part_id = uuid_fk("ops_parts.id")
    description = db.Column(db.String(300), nullable=False)
    vendor_part_number = db.Column(db.String(160), nullable=True)
    url = db.Column(db.String(500), nullable=True)
    quantity = db.Column(db.Numeric(14, 3), nullable=False)
    unit_price = db.Column(db.Numeric(12, 4), nullable=False, default=0)
    received_quantity = db.Column(db.Numeric(14, 3), nullable=False, default=0)
    receive_location_id = uuid_fk("ops_locations.id")
    position = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(UTCDateTime(), nullable=False, default=utcnow)

    purchase_request = db.relationship("PurchaseRequest", back_populates="items")
    part = db.relationship("Part", foreign_keys=[part_id], lazy="joined")
    receive_location = db.relationship("Location", foreign_keys=[receive_location_id], lazy="joined")


class PurchaseRequestEvent(db.Model):
    """Approval timeline entry."""

    __tablename__ = "ops_purchase_request_events"

    id = uuid_pk()
    organization_id = db.Column(UUID, db.ForeignKey("ops_organizations.id"), nullable=False, index=True)
    purchase_request_id = uuid_fk("ops_purchase_requests.id", nullable=False, ondelete="CASCADE")
    from_status = db.Column(db.String(30), nullable=True)
    to_status = db.Column(db.String(30), nullable=False)
    action = db.Column(db.String(30), nullable=False)
    step = db.Column(db.String(20), nullable=True)
    comment = db.Column(db.Text, nullable=True)
    actor_user_id = user_fk(index=True)
    created_at = db.Column(UTCDateTime(), nullable=False, default=utcnow)

    purchase_request = db.relationship("PurchaseRequest", back_populates="events")
    actor = db.relationship("User", foreign_keys=[actor_user_id], lazy="joined")


# --------------------------------------------------------------------------- immutability


def _column_changed(target) -> bool:
    state = sa_inspect(target)
    return any(state.attrs[attr.key].history.has_changes() for attr in state.mapper.column_attrs)


@event.listens_for(InventoryTransaction, "before_update")
def _refuse_transaction_update(mapper, connection, target):  # noqa: ARG001
    if _column_changed(target):
        raise RuntimeError(IMMUTABLE_TRANSACTION_MESSAGE)


@event.listens_for(InventoryTransaction, "before_delete")
def _refuse_transaction_delete(mapper, connection, target):  # noqa: ARG001
    raise RuntimeError(IMMUTABLE_TRANSACTION_MESSAGE)


@event.listens_for(Session, "do_orm_execute")
def _refuse_bulk_transaction_writes(orm_execute_state):
    """``Query.update()`` / ``delete(InventoryTransaction)`` bypass the mapper
    listeners, so ORM-level bulk writes to the ledger are refused here too."""
    if not (orm_execute_state.is_update or orm_execute_state.is_delete):
        return
    mapper = orm_execute_state.bind_mapper
    if mapper is not None and mapper.class_ is InventoryTransaction:
        raise RuntimeError(IMMUTABLE_TRANSACTION_MESSAGE)
