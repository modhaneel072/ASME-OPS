"""Work orders and their satellite tables."""

from __future__ import annotations

from asme.extensions import db
from asme.ops.types import UUID, JSONDoc, OpsBase, UTCDateTime, user_fk, utcnow, uuid_fk, uuid_pk

WORK_ORDER_STATUSES = ("draft", "open", "in_progress", "on_hold", "done", "canceled", "skipped")
OPEN_STATUSES = ("draft", "open", "in_progress", "on_hold")
CLOSED_STATUSES = ("done", "canceled", "skipped")
PRIORITIES = ("none", "low", "medium", "high", "critical")
PRIORITY_RANK = {p: i for i, p in enumerate(PRIORITIES)}
WORK_TYPES = ("reactive", "preventive", "project", "event", "inspection", "safety", "procurement", "documentation")
COST_TYPES = ("parts", "labor", "vendor", "other")
PARENT_COMPLETION_POLICIES = ("manual", "auto")
DEPENDENCY_TYPES = ("finish_to_start",)


class WorkOrder(OpsBase, db.Model):
    __tablename__ = "ops_work_orders"
    __table_args__ = (
        db.UniqueConstraint("organization_id", "number", name="uq_ops_work_orders_org_number"),
        db.Index("ix_ops_work_orders_org_status_due", "organization_id", "status", "due_at"),
    )

    number = db.Column(db.Integer, nullable=False)
    title = db.Column(db.String(240), nullable=False)
    description = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), nullable=False, default="open", index=True)
    priority = db.Column(db.String(20), nullable=False, default="none")
    work_type = db.Column(db.String(30), nullable=False, default="reactive")
    project_id = uuid_fk("ops_projects.id")
    location_id = uuid_fk("ops_locations.id")
    primary_asset_id = uuid_fk("ops_assets.id")
    team_id = uuid_fk("ops_teams.id")
    vendor_id = uuid_fk("ops_vendors.id")
    parent_work_order_id = uuid_fk("ops_work_orders.id")
    source_request_id = db.Column(UUID, nullable=True)  # Stage 3
    maintenance_plan_id = db.Column(UUID, nullable=True)  # Stage 5
    start_at = db.Column(UTCDateTime(), nullable=True)
    due_at = db.Column(UTCDateTime(), nullable=True, index=True)
    completed_at = db.Column(UTCDateTime(), nullable=True)
    canceled_at = db.Column(UTCDateTime(), nullable=True)
    estimated_minutes = db.Column(db.Integer, nullable=True)
    actual_minutes = db.Column(db.Integer, nullable=False, default=0)
    recurrence_json = db.Column(JSONDoc, nullable=True)
    completion_note = db.Column(db.Text, nullable=True)
    is_blocked = db.Column(db.Boolean, nullable=False, default=False)
    budget_code = db.Column(db.String(60), nullable=True)
    parent_completion_policy = db.Column(db.String(20), nullable=False, default="manual")

    project = db.relationship("OpsProject", foreign_keys=[project_id])
    location = db.relationship("Location", foreign_keys=[location_id])
    primary_asset = db.relationship("Asset", foreign_keys=[primary_asset_id])
    team = db.relationship("Team", foreign_keys=[team_id])
    vendor = db.relationship("Vendor", foreign_keys=[vendor_id])
    created_by = db.relationship("User", foreign_keys="WorkOrder.created_by_user_id")
    parent = db.relationship("WorkOrder", remote_side="WorkOrder.id", foreign_keys=[parent_work_order_id], back_populates="children")
    children = db.relationship("WorkOrder", foreign_keys=[parent_work_order_id], back_populates="parent", order_by="WorkOrder.number")

    assignees = db.relationship("WorkOrderAssignee", back_populates="work_order", cascade="all, delete-orphan", lazy="selectin")
    category_links = db.relationship("WorkOrderCategory", back_populates="work_order", cascade="all, delete-orphan", lazy="selectin")
    asset_links = db.relationship("WorkOrderAsset", back_populates="work_order", cascade="all, delete-orphan", lazy="selectin")
    watchers = db.relationship("WorkOrderWatcher", back_populates="work_order", cascade="all, delete-orphan", lazy="selectin")
    status_history = db.relationship(
        "WorkOrderStatusHistory", back_populates="work_order", cascade="all, delete-orphan", order_by="WorkOrderStatusHistory.changed_at"
    )
    time_entries = db.relationship("TimeEntry", back_populates="work_order", cascade="all, delete-orphan", order_by="TimeEntry.created_at")
    cost_entries = db.relationship("CostEntry", back_populates="work_order", cascade="all, delete-orphan", order_by="CostEntry.created_at")
    blocked_by = db.relationship(
        "WorkOrderDependency",
        foreign_keys="WorkOrderDependency.blocked_work_order_id",
        back_populates="blocked",
        cascade="all, delete-orphan",
    )
    blocking = db.relationship(
        "WorkOrderDependency",
        foreign_keys="WorkOrderDependency.blocking_work_order_id",
        back_populates="blocking_work_order",
        cascade="all, delete-orphan",
    )

    # -- policy helpers ---------------------------------------------------------
    @property
    def assignee_user_ids(self) -> set[int]:
        return {a.user_id for a in self.assignees if a.user_id}

    @property
    def assignee_team_ids(self) -> set:
        return {a.team_id for a in self.assignees if a.team_id}

    @property
    def watcher_user_ids(self) -> set[int]:
        return {w.user_id for w in self.watchers}

    @property
    def category_ids(self) -> list:
        return [link.category_id for link in self.category_links]

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_STATUSES

    @property
    def is_overdue(self) -> bool:
        return bool(self.due_at) and self.is_open and self.due_at < utcnow()


class WorkOrderAssignee(db.Model):
    __tablename__ = "ops_work_order_assignees"
    __table_args__ = (
        db.UniqueConstraint("work_order_id", "user_id", name="uq_ops_work_order_assignees_wo_user"),
        db.UniqueConstraint("work_order_id", "team_id", name="uq_ops_work_order_assignees_wo_team"),
    )

    id = uuid_pk()
    work_order_id = uuid_fk("ops_work_orders.id", nullable=False, ondelete="CASCADE")
    user_id = user_fk(index=True)
    team_id = uuid_fk("ops_teams.id")
    assigned_at = db.Column(UTCDateTime(), nullable=False, default=utcnow)

    work_order = db.relationship("WorkOrder", back_populates="assignees")
    user = db.relationship("User", foreign_keys=[user_id], lazy="joined")
    team = db.relationship("Team", foreign_keys=[team_id], lazy="joined")


class WorkOrderCategory(db.Model):
    __tablename__ = "ops_work_order_categories"
    __table_args__ = (db.UniqueConstraint("work_order_id", "category_id", name="uq_ops_work_order_categories_wo_category"),)

    id = uuid_pk()
    work_order_id = uuid_fk("ops_work_orders.id", nullable=False, ondelete="CASCADE")
    category_id = uuid_fk("ops_categories.id", nullable=False)

    work_order = db.relationship("WorkOrder", back_populates="category_links")
    category = db.relationship("Category", lazy="joined")


class WorkOrderAsset(db.Model):
    __tablename__ = "ops_work_order_assets"
    __table_args__ = (db.UniqueConstraint("work_order_id", "asset_id", name="uq_ops_work_order_assets_wo_asset"),)

    id = uuid_pk()
    work_order_id = uuid_fk("ops_work_orders.id", nullable=False, ondelete="CASCADE")
    asset_id = uuid_fk("ops_assets.id", nullable=False)
    relationship_type = db.Column(db.String(20), nullable=False, default="related")

    work_order = db.relationship("WorkOrder", back_populates="asset_links")
    asset = db.relationship("Asset", lazy="joined")


class WorkOrderWatcher(db.Model):
    __tablename__ = "ops_work_order_watchers"
    __table_args__ = (db.UniqueConstraint("work_order_id", "user_id", name="uq_ops_work_order_watchers_wo_user"),)

    id = uuid_pk()
    work_order_id = uuid_fk("ops_work_orders.id", nullable=False, ondelete="CASCADE")
    user_id = user_fk(nullable=False, index=True)

    work_order = db.relationship("WorkOrder", back_populates="watchers")
    user = db.relationship("User", foreign_keys=[user_id], lazy="joined")


class WorkOrderStatusHistory(db.Model):
    __tablename__ = "ops_work_order_status_history"

    id = uuid_pk()
    work_order_id = uuid_fk("ops_work_orders.id", nullable=False, ondelete="CASCADE")
    from_status = db.Column(db.String(20), nullable=True)
    to_status = db.Column(db.String(20), nullable=False)
    changed_by_user_id = user_fk()
    note = db.Column(db.Text, nullable=True)
    changed_at = db.Column(UTCDateTime(), nullable=False, default=utcnow, index=True)

    work_order = db.relationship("WorkOrder", back_populates="status_history")
    changed_by = db.relationship("User", foreign_keys=[changed_by_user_id], lazy="joined")


class WorkOrderDependency(db.Model):
    __tablename__ = "ops_work_order_dependencies"
    __table_args__ = (
        db.UniqueConstraint("blocking_work_order_id", "blocked_work_order_id", name="uq_ops_work_order_dependencies_pair"),
    )

    id = uuid_pk()
    blocking_work_order_id = uuid_fk("ops_work_orders.id", nullable=False, ondelete="CASCADE")
    blocked_work_order_id = uuid_fk("ops_work_orders.id", nullable=False, ondelete="CASCADE")
    dependency_type = db.Column(db.String(30), nullable=False, default="finish_to_start")
    created_at = db.Column(UTCDateTime(), nullable=False, default=utcnow)

    blocking_work_order = db.relationship("WorkOrder", foreign_keys=[blocking_work_order_id], back_populates="blocking")
    blocked = db.relationship("WorkOrder", foreign_keys=[blocked_work_order_id], back_populates="blocked_by")


class TimeEntry(OpsBase, db.Model):
    __tablename__ = "ops_time_entries"

    work_order_id = uuid_fk("ops_work_orders.id", nullable=False, ondelete="CASCADE")
    user_id = user_fk(nullable=False, index=True)
    started_at = db.Column(UTCDateTime(), nullable=True)
    ended_at = db.Column(UTCDateTime(), nullable=True)
    minutes = db.Column(db.Integer, nullable=False)
    note = db.Column(db.String(400), nullable=True)

    work_order = db.relationship("WorkOrder", back_populates="time_entries")
    user = db.relationship("User", foreign_keys=[user_id], lazy="joined")


class CostEntry(OpsBase, db.Model):
    __tablename__ = "ops_cost_entries"

    work_order_id = uuid_fk("ops_work_orders.id", nullable=False, ondelete="CASCADE")
    type = db.Column(db.String(20), nullable=False, default="other")
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    vendor_id = uuid_fk("ops_vendors.id")
    description = db.Column(db.String(400), nullable=True)
    # Set on system-created parts costs; such entries cannot be deleted by hand.
    inventory_transaction_id = uuid_fk("ops_inventory_transactions.id")

    work_order = db.relationship("WorkOrder", back_populates="cost_entries")
    vendor = db.relationship("Vendor", foreign_keys=[vendor_id])
