"""ORM models for the ``ops_*`` tables. Import this package (it is imported by
``asme.models``) so ``db.create_all`` and Alembic see every table."""

from asme.ops.models.identity import Membership, Organization, Permission, Role, RolePermission, Sequence, UserPreference
from asme.ops.models.projects import Milestone, OpsProject, ProjectMember
from asme.ops.models.shared import Attachment, AuditEvent, Comment, Notification, SavedFilter
from asme.ops.models.structure import Asset, AssetStatusHistory, AssetType, AssetTypeLink, Category, Location, Team, TeamMember, Vendor
from asme.ops.models.work import (
    CostEntry,
    TimeEntry,
    WorkOrder,
    WorkOrderAsset,
    WorkOrderAssignee,
    WorkOrderCategory,
    WorkOrderDependency,
    WorkOrderStatusHistory,
    WorkOrderWatcher,
)

__all__ = [
    "Asset",
    "AssetStatusHistory",
    "AssetType",
    "AssetTypeLink",
    "Attachment",
    "AuditEvent",
    "Category",
    "Comment",
    "CostEntry",
    "Location",
    "Membership",
    "Milestone",
    "Notification",
    "Organization",
    "Permission",
    "OpsProject",
    "ProjectMember",
    "Role",
    "RolePermission",
    "SavedFilter",
    "Sequence",
    "Team",
    "TeamMember",
    "TimeEntry",
    "UserPreference",
    "Vendor",
    "WorkOrder",
    "WorkOrderAsset",
    "WorkOrderAssignee",
    "WorkOrderCategory",
    "WorkOrderDependency",
    "WorkOrderStatusHistory",
    "WorkOrderWatcher",
]
