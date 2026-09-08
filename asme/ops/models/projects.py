"""Projects, project membership and milestones."""

from __future__ import annotations

from asme.extensions import db
from asme.ops.types import OpsBase, UTCDateTime, user_fk, utcnow, uuid_fk, uuid_pk

PROJECT_STATUSES = ("planning", "active", "on_hold", "completed", "archived")
PROJECT_VISIBILITIES = ("chapter", "private")
RISK_LEVELS = ("low", "medium", "high", "critical")
PROJECT_ROLES = ("lead", "member", "advisor", "viewer")
MILESTONE_STATUSES = ("planned", "in_progress", "done", "missed")


class OpsProject(OpsBase, db.Model):
    __tablename__ = "ops_projects"
    __table_args__ = (db.UniqueConstraint("organization_id", "code", name="uq_ops_projects_org_code"),)

    name = db.Column(db.String(200), nullable=False)
    code = db.Column(db.String(20), nullable=False)
    description = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), nullable=False, default="active", index=True)
    visibility = db.Column(db.String(20), nullable=False, default="chapter")
    risk_level = db.Column(db.String(20), nullable=False, default="low")
    lead_user_id = user_fk(index=True)
    faculty_advisor_user_id = user_fk()
    start_date = db.Column(db.Date, nullable=True)
    target_date = db.Column(db.Date, nullable=True)
    budget_amount = db.Column(db.Numeric(12, 2), nullable=True)
    repository_url = db.Column(db.String(500), nullable=True)
    cad_url = db.Column(db.String(500), nullable=True)
    requirements_url = db.Column(db.String(500), nullable=True)
    competition = db.Column(db.String(200), nullable=True)
    academic_year = db.Column(db.String(12), nullable=True)
    public_project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=True, index=True)
    archived_at = db.Column(UTCDateTime(), nullable=True)

    lead = db.relationship("User", foreign_keys=[lead_user_id])
    faculty_advisor = db.relationship("User", foreign_keys=[faculty_advisor_user_id])
    members = db.relationship("ProjectMember", back_populates="project", cascade="all, delete-orphan", lazy="selectin")
    milestones = db.relationship(
        "Milestone", back_populates="project", cascade="all, delete-orphan", order_by="Milestone.order_index", lazy="selectin"
    )
    public_project = db.relationship("asme.models.content.Project", foreign_keys=[public_project_id])

    @property
    def member_user_ids(self) -> set[int]:
        return {m.user_id for m in self.members}

    @property
    def is_private(self) -> bool:
        return self.visibility == "private"


class ProjectMember(db.Model):
    __tablename__ = "ops_project_members"
    __table_args__ = (db.UniqueConstraint("project_id", "user_id", name="uq_ops_project_members_project_user"),)

    id = uuid_pk()
    project_id = uuid_fk("ops_projects.id", nullable=False, ondelete="CASCADE")
    user_id = user_fk(nullable=False, index=True)
    team_id = uuid_fk("ops_teams.id")
    project_role = db.Column(db.String(20), nullable=False, default="member")
    joined_at = db.Column(UTCDateTime(), nullable=False, default=utcnow)

    project = db.relationship("OpsProject", back_populates="members")
    user = db.relationship("User", foreign_keys=[user_id], lazy="joined")
    team = db.relationship("Team", foreign_keys=[team_id])


class Milestone(OpsBase, db.Model):
    __tablename__ = "ops_milestones"

    project_id = uuid_fk("ops_projects.id", nullable=False, ondelete="CASCADE")
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    due_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(20), nullable=False, default="planned")
    owner_user_id = user_fk()
    weight = db.Column(db.Integer, nullable=False, default=1)
    order_index = db.Column(db.Integer, nullable=False, default=0)
    completed_at = db.Column(UTCDateTime(), nullable=True)

    project = db.relationship("OpsProject", back_populates="milestones")
    owner = db.relationship("User", foreign_keys=[owner_user_id])
