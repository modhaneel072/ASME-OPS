"""Teams, locations, categories, assets and vendors."""

from __future__ import annotations

from asme.extensions import db
from asme.ops.types import UUID, JSONDoc, OpsBase, UTCDateTime, user_fk, utcnow, uuid_fk, uuid_pk

ASSET_STATUSES = ("online", "offline_planned", "offline_unplanned", "do_not_track", "retired")
ASSET_CRITICALITIES = ("none", "low", "medium", "high")
DOWNTIME_TYPES = ("planned", "unplanned")


class Team(OpsBase, db.Model):
    __tablename__ = "ops_teams"
    __table_args__ = (db.UniqueConstraint("organization_id", "name", name="uq_ops_teams_org_name"),)

    name = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text, nullable=True)
    parent_team_id = uuid_fk("ops_teams.id")
    project_id = uuid_fk("ops_projects.id")
    conversation_id = db.Column(UUID, nullable=True)  # filled by the messaging module (Stage 3)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    members = db.relationship("TeamMember", back_populates="team", cascade="all, delete-orphan", lazy="selectin")
    parent = db.relationship("Team", remote_side="Team.id", foreign_keys=[parent_team_id])
    project = db.relationship("OpsProject", foreign_keys=[project_id])

    @property
    def lead_user_ids(self) -> set[int]:
        return {m.user_id for m in self.members if m.is_lead}

    @property
    def member_user_ids(self) -> set[int]:
        return {m.user_id for m in self.members}


class TeamMember(db.Model):
    __tablename__ = "ops_team_members"
    __table_args__ = (db.UniqueConstraint("team_id", "user_id", name="uq_ops_team_members_team_user"),)

    id = uuid_pk()
    team_id = uuid_fk("ops_teams.id", nullable=False, ondelete="CASCADE")
    user_id = user_fk(nullable=False, index=True)
    is_lead = db.Column(db.Boolean, nullable=False, default=False)
    joined_at = db.Column(UTCDateTime(), nullable=False, default=utcnow)

    team = db.relationship("Team", back_populates="members")
    user = db.relationship("User", foreign_keys=[user_id], lazy="joined")


class Location(OpsBase, db.Model):
    __tablename__ = "ops_locations"

    name = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text, nullable=True)
    parent_location_id = uuid_fk("ops_locations.id")
    building = db.Column(db.String(160), nullable=True)
    room = db.Column(db.String(80), nullable=True)
    address_json = db.Column(JSONDoc, nullable=True)
    is_default = db.Column(db.Boolean, nullable=False, default=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    parent = db.relationship("Location", remote_side="Location.id", foreign_keys=[parent_location_id])


class Category(OpsBase, db.Model):
    __tablename__ = "ops_categories"
    __table_args__ = (db.UniqueConstraint("organization_id", "name", name="uq_ops_categories_org_name"),)

    name = db.Column(db.String(120), nullable=False)
    color = db.Column(db.String(20), nullable=False, default="#0878d1")
    icon = db.Column(db.String(60), nullable=False, default="tag")
    description = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)


class AssetType(OpsBase, db.Model):
    __tablename__ = "ops_asset_types"
    __table_args__ = (db.UniqueConstraint("organization_id", "name", name="uq_ops_asset_types_org_name"),)

    name = db.Column(db.String(120), nullable=False)
    color = db.Column(db.String(20), nullable=False, default="#475569")
    icon = db.Column(db.String(60), nullable=False, default="box")


class Asset(OpsBase, db.Model):
    __tablename__ = "ops_assets"
    __table_args__ = (db.UniqueConstraint("organization_id", "code", name="uq_ops_assets_org_code"),)

    name = db.Column(db.String(200), nullable=False)
    code = db.Column(db.String(60), nullable=True)
    description = db.Column(db.Text, nullable=True)
    parent_asset_id = uuid_fk("ops_assets.id")
    project_id = uuid_fk("ops_projects.id")
    location_id = uuid_fk("ops_locations.id")
    responsible_team_id = uuid_fk("ops_teams.id")
    owner_user_id = user_fk()
    manufacturer = db.Column(db.String(160), nullable=True)
    model = db.Column(db.String(160), nullable=True)
    serial_number = db.Column(db.String(160), nullable=True)
    purchase_date = db.Column(db.Date, nullable=True)
    purchase_cost = db.Column(db.Numeric(12, 2), nullable=True)
    warranty_end = db.Column(db.Date, nullable=True)
    criticality = db.Column(db.String(20), nullable=False, default="none")
    status = db.Column(db.String(30), nullable=False, default="online", index=True)
    qr_code = db.Column(db.String(160), nullable=True)
    custom_fields_json = db.Column(JSONDoc, nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    parent = db.relationship("Asset", remote_side="Asset.id", foreign_keys=[parent_asset_id])
    project = db.relationship("OpsProject", foreign_keys=[project_id])
    location = db.relationship("Location", foreign_keys=[location_id])
    responsible_team = db.relationship("Team", foreign_keys=[responsible_team_id])
    owner = db.relationship("User", foreign_keys=[owner_user_id])
    type_links = db.relationship("AssetTypeLink", back_populates="asset", cascade="all, delete-orphan", lazy="selectin")

    @property
    def types(self) -> list["AssetType"]:
        return [link.asset_type for link in self.type_links if link.asset_type]


class AssetTypeLink(db.Model):
    __tablename__ = "ops_asset_type_links"
    __table_args__ = (db.UniqueConstraint("asset_id", "asset_type_id", name="uq_ops_asset_type_links_asset_type"),)

    id = uuid_pk()
    asset_id = uuid_fk("ops_assets.id", nullable=False, ondelete="CASCADE")
    asset_type_id = uuid_fk("ops_asset_types.id", nullable=False)

    asset = db.relationship("Asset", back_populates="type_links")
    asset_type = db.relationship("AssetType", lazy="joined")


class AssetStatusHistory(db.Model):
    __tablename__ = "ops_asset_status_history"

    id = uuid_pk()
    organization_id = db.Column(UUID, db.ForeignKey("ops_organizations.id"), nullable=False, index=True)
    asset_id = uuid_fk("ops_assets.id", nullable=False, ondelete="CASCADE")
    from_status = db.Column(db.String(30), nullable=True)
    to_status = db.Column(db.String(30), nullable=False)
    downtime_type = db.Column(db.String(20), nullable=True)
    downtime_reason = db.Column(db.String(160), nullable=True)
    note = db.Column(db.Text, nullable=True)
    started_at = db.Column(UTCDateTime(), nullable=False, default=utcnow)
    ended_at = db.Column(UTCDateTime(), nullable=True)
    changed_by_user_id = user_fk()
    work_order_id = uuid_fk("ops_work_orders.id")

    changed_by = db.relationship("User", foreign_keys=[changed_by_user_id])


class Vendor(OpsBase, db.Model):
    __tablename__ = "ops_vendors"
    __table_args__ = (db.UniqueConstraint("organization_id", "name", name="uq_ops_vendors_org_name"),)

    name = db.Column(db.String(200), nullable=False)
    contact_name = db.Column(db.String(160), nullable=True)
    email = db.Column(db.String(160), nullable=True)
    phone = db.Column(db.String(40), nullable=True)
    website = db.Column(db.String(300), nullable=True)
    address_json = db.Column(JSONDoc, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
