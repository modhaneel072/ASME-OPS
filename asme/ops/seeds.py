"""Development seed dataset for ASME Ops (``python manage.py seed-ops``).

Builds a realistic chapter - people in every system role, teams, locations,
asset hierarchy, vendors, three projects with milestones and about fifty work
orders in every status - **by calling the services as the right people**, so
status history, notifications, audit events, legacy project-membership mirrors
and domain events are all produced the same way the UI produces them.

Rules of the road:

* Development only. ``seed_ops`` raises ``RuntimeError`` when
  ``settings().is_production`` or ``settings().ops_seed_allowed`` is false.
* Idempotent. The organization is considered seeded once it has an ops project
  with code ``CCR``; a second run returns ``{"skipped": True, ...counts}``.
  ``seed_ops(reset=True)`` first deletes the organization's ops rows in
  dependency order (see ``reset_ops``) and rebuilds; it keeps the organization,
  roles, memberships, the default location and the fourteen seed categories,
  and restarts the work-order number sequence at 1.
* No raw SQL and no bare model inserts where a service exists. The one field
  written directly on the model is ``WorkOrder.recurrence_json`` on the two
  preventive inspections: the create/update specs deliberately omit recurrence
  until the maintenance-plans stage ships, so there is no service path yet.
* Timestamps are real: rows are created "now". Overdue work orders are overdue
  because their ``due_at`` is in the past, not because history was backdated.

Accounts get ``settings().default_user_password`` (the bootstrap admin keeps
``settings().default_admin_password``); the command prints the table.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from sqlalchemy import delete, func, or_, select, update
from werkzeug.security import generate_password_hash

from asme.config import settings
from asme.extensions import db
from asme.models import Project as LegacyProject
from asme.models import User
from asme.ops import bootstrap, policy, storage
from asme.ops.models import (
    Asset,
    AssetStatusHistory,
    AssetType,
    AssetTypeLink,
    Attachment,
    AuditEvent,
    Category,
    Comment,
    CostEntry,
    Location,
    Membership,
    Milestone,
    Notification,
    OpsProject,
    ProjectMember,
    SavedFilter,
    Sequence,
    Team,
    TeamMember,
    TimeEntry,
    Vendor,
    WorkOrder,
    WorkOrderAsset,
    WorkOrderAssignee,
    WorkOrderCategory,
    WorkOrderDependency,
    WorkOrderStatusHistory,
    WorkOrderWatcher,
)
from asme.ops.models.work import OPEN_STATUSES
from asme.ops.services import assets as assets_service
from asme.ops.services import comments as comments_service
from asme.ops.services import locations as locations_service
from asme.ops.services import milestones as milestones_service
from asme.ops.services import projects as projects_service
from asme.ops.services import teams as teams_service
from asme.ops.services import vendors as vendors_service
from asme.ops.services import work_orders as work_orders_service
from asme.ops.types import utcnow
from asme.services import bootstrap as legacy_bootstrap
from asme.services import identity

log = logging.getLogger("asme.ops.seeds")

SEEDED_PROJECT_CODE = "CCR"
EMAIL_DOMAIN = "uiowa.edu"
LEGACY_ROLE_FOR_OPS = {"chapter_admin": "admin", "team_lead": "team_leader"}
RECURRENCE_MONTHLY = {"every": "month"}

# key, first name, last name, ops role, membership title
PEOPLE: tuple[tuple[str, str, str, str, str | None], ...] = (
    ("priya", "Priya", "Natarajan", "executive_officer", "President"),
    ("marcus", "Marcus", "Bell", "project_lead", None),
    ("elena", "Elena", "Ortiz", "team_lead", None),
    ("jordan", "Jordan", "Kim", "team_lead", None),
    ("sam", "Sam", "Okafor", "team_lead", None),
    ("ava", "Ava", "Chen", "full_member", None),
    ("liam", "Liam", "Patel", "full_member", None),
    ("noah", "Noah", "Garcia", "full_member", None),
    ("mia", "Mia", "Johnson", "full_member", None),
    ("ethan", "Ethan", "Nguyen", "full_member", None),
    ("zoe", "Zoe", "Williams", "full_member", None),
    ("dana", "Dana", "Reyes", "safety_officer", "Safety Officer"),
    ("owen", "Owen", "Brooks", "inventory_manager", "Inventory Manager"),
    ("grace", "Grace", "Lee", "treasurer", "Treasurer"),
    ("alan", "Alan", "Whitfield", "faculty_advisor", "Faculty Advisor"),
    ("riley", "Riley", "Park", "requester", None),
    ("casey", "Casey", "Morgan", "shop_operator", None),
)

# key, name, description, lead, members, project code
TEAMS: tuple[tuple[str, str, str, str, tuple[str, ...], str | None], ...] = (
    ("exec", "Executive Board", "Chapter officers.", "priya", ("grace", "dana"), None),
    ("ccr", "Crater Cruncher Rover", "Lunabotics rover integration team.", "marcus", ("elena", "jordan", "sam"), "CCR"),
    ("wheels", "Wheels and Mobility", "Drivetrain, wheel modules and suspension.", "elena", ("ava", "liam"), "CCR"),
    ("arm", "Robotic Arm", "Excavation arm structure, actuators and end effector.", "jordan", ("noah", "mia"), "CCR"),
    ("elec", "Electrical", "Power distribution, harnesses and bench instruments.", "sam", ("ethan",), None),
    ("sw", "Software and Autonomy", "Telemetry, controls and autonomy stack.", "marcus", ("zoe",), "CCR"),
    ("fab", "Fabrication", "Machine shop and 3D printing.", "owen", ("casey",), None),
    ("events", "Events and Outreach", "General body meetings, showcase and outreach.", "priya", ("mia",), None),
    ("inv", "Inventory and Procurement", "Parts, tools and purchasing.", "owen", ("grace",), None),
)

# name, color, icon
ASSET_TYPES = (
    ("Vehicle", "#0878d1", "truck"),
    ("Subsystem", "#475569", "component"),
    ("3D Printer", "#7c5ce7", "printer"),
    ("Test Equipment", "#2563eb", "gauge"),
    ("Tool", "#b45309", "wrench"),
    ("Power", "#e58a00", "battery-charging"),
    ("Compute", "#0f766e", "cpu"),
)

VENDORS = (
    ("McMaster-Carr", "https://www.mcmaster.com", "Fasteners, bearings, raw stock."),
    ("DigiKey", "https://www.digikey.com", "Electronic components."),
    ("Amazon Business", "https://business.amazon.com", "Consumables and event supplies."),
    ("Bambu Lab", "https://bambulab.com", "Printers, nozzles and filament."),
)


# --------------------------------------------------------------------------- guards / helpers


def _refuse_in_production() -> None:
    cfg = settings()
    if cfg.is_production or not cfg.ops_seed_allowed:
        raise RuntimeError("seed-ops is development-only and refuses to run when ASME_ENV=production.")


def next_may_15(today: date | None = None) -> date:
    today = today or utcnow().date()
    candidate = date(today.year, 5, 15)
    return candidate if candidate > today else date(today.year + 1, 5, 15)


def academic_year(today: date | None = None) -> tuple[str, date]:
    """``("2026-27", date(2026, 8, 25))`` for any day of the 2026-27 academic year."""
    today = today or utcnow().date()
    start_year = today.year if today.month >= 8 else today.year - 1
    return f"{start_year}-{(start_year + 1) % 100:02d}", date(start_year, 8, 25)


def is_seeded(org) -> bool:
    return OpsProject.query.filter_by(organization_id=org.id, code=SEEDED_PROJECT_CODE).first() is not None


def _user_by_email(email: str) -> User | None:
    return User.query.filter(func.lower(User.email) == email.lower()).first()


# --------------------------------------------------------------------------- reset


def reset_ops(org, *, commit: bool = True) -> dict[str, int]:
    """Delete the organization's ops rows in dependency order. Keeps the
    organization, roles, memberships, user preferences, the default location
    and the categories; restarts work-order numbering at 1."""
    _refuse_in_production()
    org_id = org.id
    removed: dict[str, int] = {}
    work_order_ids = select(WorkOrder.id).where(WorkOrder.organization_id == org_id)
    asset_ids = select(Asset.id).where(Asset.organization_id == org_id)
    team_ids = select(Team.id).where(Team.organization_id == org_id)
    project_ids = select(OpsProject.id).where(OpsProject.organization_id == org_id)

    def run(name: str, statement) -> None:
        removed[name] = int(db.session.execute(statement).rowcount or 0)

    attachments = Attachment.query.filter_by(organization_id=org_id).all()
    if attachments:
        store = storage.get_storage()
        for row in attachments:
            try:
                store.delete(row.storage_key)
            except Exception:  # a missing file must not stop the reset
                log.warning("could not delete stored object %s", row.storage_key, exc_info=True)
            db.session.delete(row)
        db.session.flush()
    removed["attachments"] = len(attachments)

    run("notifications", delete(Notification).where(Notification.organization_id == org_id))
    run("saved_filters", delete(SavedFilter).where(SavedFilter.organization_id == org_id))
    run("comments", delete(Comment).where(Comment.organization_id == org_id))
    run("audit_events", delete(AuditEvent).where(AuditEvent.organization_id == org_id))

    run(
        "dependencies",
        delete(WorkOrderDependency).where(
            or_(
                WorkOrderDependency.blocked_work_order_id.in_(work_order_ids),
                WorkOrderDependency.blocking_work_order_id.in_(work_order_ids),
            )
        ),
    )
    run("time_entries", delete(TimeEntry).where(TimeEntry.organization_id == org_id))
    run("cost_entries", delete(CostEntry).where(CostEntry.organization_id == org_id))
    for model in (WorkOrderStatusHistory, WorkOrderAssignee, WorkOrderCategory, WorkOrderAsset, WorkOrderWatcher):
        run(model.__tablename__.removeprefix("ops_"), delete(model).where(model.work_order_id.in_(work_order_ids)))
    run("asset_status_history", delete(AssetStatusHistory).where(AssetStatusHistory.organization_id == org_id))
    db.session.execute(update(WorkOrder).where(WorkOrder.organization_id == org_id).values(parent_work_order_id=None))
    run("work_orders", delete(WorkOrder).where(WorkOrder.organization_id == org_id))

    run("milestones", delete(Milestone).where(Milestone.organization_id == org_id))
    run("project_members", delete(ProjectMember).where(ProjectMember.project_id.in_(project_ids)))

    run("asset_type_links", delete(AssetTypeLink).where(AssetTypeLink.asset_id.in_(asset_ids)))
    db.session.execute(update(Asset).where(Asset.organization_id == org_id).values(parent_asset_id=None))
    run("assets", delete(Asset).where(Asset.organization_id == org_id))
    run("asset_types", delete(AssetType).where(AssetType.organization_id == org_id))

    run("team_members", delete(TeamMember).where(TeamMember.team_id.in_(team_ids)))
    db.session.execute(update(Team).where(Team.organization_id == org_id).values(parent_team_id=None))
    run("teams", delete(Team).where(Team.organization_id == org_id))
    run("projects", delete(OpsProject).where(OpsProject.organization_id == org_id))
    run("vendors", delete(Vendor).where(Vendor.organization_id == org_id))

    db.session.execute(update(Location).where(Location.organization_id == org_id).values(parent_location_id=None))
    run("locations", delete(Location).where(Location.organization_id == org_id, Location.is_default.is_(False)))

    db.session.execute(
        update(Sequence).where(Sequence.organization_id == org_id, Sequence.key == bootstrap.WORK_ORDER_SEQUENCE).values(next_value=1)
    )
    if commit:
        db.session.commit()
    db.session.expire_all()
    log.info("reset ops data for %s: %s", org.slug, removed)
    return removed


# --------------------------------------------------------------------------- builder


class _Builder:
    def __init__(self, org, cfg):
        self.org = org
        self.cfg = cfg
        self.now = utcnow().replace(minute=0, second=0, microsecond=0)
        self.today = self.now.date()
        self.people: dict[str, User] = {}
        self.teams: dict[str, Team] = {}
        self.locations: dict[str, Location] = {}
        self.categories: dict[str, Category] = {}
        self.types: dict[str, AssetType] = {}
        self.vendors: dict[str, Vendor] = {}
        self.projects: dict[str, OpsProject] = {}
        self.assets: dict[str, Asset] = {}
        self.work_orders: dict[str, WorkOrder] = {}
        self.created: dict[str, int] = {"users": 0}

    # -- plumbing -------------------------------------------------------------

    def ctx(self, key: str) -> policy.PolicyContext:
        """A fresh context every time: team and project membership change as we build."""
        ctx = policy.load_context(self.people[key], self.org)
        if ctx is None:
            raise RuntimeError(f"seed user {key!r} has no active membership in {self.org.slug}")
        return ctx

    def user_id(self, key: str) -> int:
        return self.people[key].id

    def mention(self, key: str) -> str:
        user = self.people[key]
        return f"@[{user.display_name}](user:{user.id})"

    def days(self, offset: float):
        return self.now + timedelta(days=offset)

    def build(self) -> None:
        self._people()
        self._projects()
        self._teams()
        self._project_members()
        self._milestones()
        self._locations()
        self._categories()
        self._asset_types()
        self._vendors()
        self._assets()
        self._work_orders()
        self._comments()

    # -- people ---------------------------------------------------------------

    def _people(self) -> None:
        admin = _user_by_email(self.cfg.default_admin_email)
        if admin is None:
            raise RuntimeError("seed_defaults() did not create the default admin account")
        membership = bootstrap.ensure_membership(admin, self.org, commit=False)
        admin_role = bootstrap.role_by_key(self.org, "chapter_admin")
        if membership.role_id != admin_role.id:
            membership.role = admin_role
            membership.role_id = admin_role.id
        membership.member_status = "active"
        if not admin.is_active:
            admin.is_active = True
        self.people["admin"] = admin

        password_hash = generate_password_hash(self.cfg.default_user_password)
        for key, first, last, role_key, title in PEOPLE:
            base = f"{first[0]}{last}".lower()
            email = f"{base}@{EMAIL_DOMAIN}"
            user = _user_by_email(email)
            if user is None:
                username = identity.make_unique_username(base)
                email = f"{username}@{EMAIL_DOMAIN}"
                user = _user_by_email(email)
            if user is None:
                user = User(
                    name=f"{first} {last}",
                    email=email,
                    username=username,
                    password_hash=password_hash,
                    role=LEGACY_ROLE_FOR_OPS.get(role_key, "member"),
                    is_active=True,
                )
                db.session.add(user)
                db.session.flush()
                self.created["users"] += 1
            membership = bootstrap.ensure_membership(user, self.org, commit=False)
            role = bootstrap.role_by_key(self.org, role_key)
            if role is None:
                raise RuntimeError(f"system role {role_key!r} is missing; run manage.py upgrade first")
            membership.role = role
            membership.role_id = role.id
            membership.member_status = "active"
            if title and not membership.title:
                membership.title = title
            self.people[key] = user
        db.session.commit()

    # -- projects -------------------------------------------------------------

    def _project(self, code: str, actor: str, payload: dict) -> OpsProject:
        row = OpsProject.query.filter_by(organization_id=self.org.id, code=code).first()
        if row is None:
            row = projects_service.create(self.ctx(actor), {**payload, "code": code})
        self.projects[code] = row
        return row

    def _projects(self) -> None:
        year, start = academic_year(self.today)
        target = next_may_15(self.today)
        rover = LegacyProject.query.filter_by(slug="rover").first()
        self._project(
            "CCR",
            "marcus",
            {
                "name": "Crater Cruncher Rover",
                "description": "Chapter entry for NASA Lunabotics: a regolith-excavating rover with a four-wheel mobility system and a robotic arm.",
                "status": "active",
                "visibility": "chapter",
                "risk_level": "medium",
                "lead_user_id": self.user_id("marcus"),
                "faculty_advisor_user_id": self.user_id("alan"),
                "start_date": start,
                "target_date": target,
                "budget_amount": "18500",
                "competition": "Lunabotics 2027",
                "academic_year": year,
                "public_project_id": rover.id if rover is not None else None,
            },
        )
        self._project(
            "OPS",
            "priya",
            {
                "name": "General Chapter Operations",
                "description": "Meetings, budget, procurement and the day-to-day running of the chapter.",
                "status": "active",
                "visibility": "chapter",
                "risk_level": "low",
                "lead_user_id": self.user_id("priya"),
                "start_date": start,
                "academic_year": year,
            },
        )
        self._project(
            "FES",
            "priya",
            {
                "name": "Fall Engineering Showcase",
                "description": "Chapter booth and rover demo at the college's fall showcase.",
                "status": "planning",
                "visibility": "private",
                "risk_level": "low",
                "lead_user_id": self.user_id("priya"),
                "start_date": self.today,
                "target_date": self.today + timedelta(days=45),
                "academic_year": year,
            },
        )

    # -- teams ----------------------------------------------------------------

    def _teams(self) -> None:
        for key, name, description, lead, members, project_code in TEAMS:
            row = Team.query.filter(Team.organization_id == self.org.id, func.lower(Team.name) == name.lower()).first()
            if row is None:
                payload = {
                    "name": name,
                    "description": description,
                    "members": [{"user_id": self.user_id(lead), "is_lead": True}]
                    + [{"user_id": self.user_id(member), "is_lead": False} for member in members],
                }
                if project_code:
                    payload["project_id"] = self.projects[project_code].id
                row = teams_service.create(self.ctx("admin"), payload)
            self.teams[key] = row

    def _member(self, key: str, role: str = "member", team: str | None = None) -> dict:
        item = {"user_id": self.user_id(key), "project_role": role}
        if team:
            item["team_id"] = self.teams[team].id
        return item

    def _project_members(self) -> None:
        projects_service.replace_members(
            self.ctx("marcus"),
            self.projects["CCR"],
            {
                "members": [
                    self._member("marcus", "lead", "ccr"),
                    self._member("alan", "advisor"),
                    self._member("elena", "member", "wheels"),
                    self._member("ava", "member", "wheels"),
                    self._member("liam", "member", "wheels"),
                    self._member("jordan", "member", "arm"),
                    self._member("noah", "member", "arm"),
                    self._member("mia", "member", "arm"),
                    self._member("sam", "member", "elec"),
                    self._member("ethan", "member", "elec"),
                    self._member("zoe", "member", "sw"),
                    self._member("owen", "member", "fab"),
                    self._member("casey", "member", "fab"),
                    self._member("dana", "viewer"),
                ]
            },
        )
        projects_service.replace_members(
            self.ctx("priya"),
            self.projects["OPS"],
            {
                "members": [
                    self._member("priya", "lead", "exec"),
                    self._member("admin", "member"),
                    self._member("grace", "member", "exec"),
                    self._member("dana", "member", "exec"),
                    self._member("owen", "member", "inv"),
                ]
            },
        )
        projects_service.replace_members(
            self.ctx("priya"),
            self.projects["FES"],
            {"members": [self._member("priya", "lead", "events"), self._member("mia", "member", "events"), self._member("admin", "member")]},
        )

    # -- milestones -----------------------------------------------------------

    def _milestone(self, project_code: str, actor: str, name: str, status: str, due: date | None, owner: str, weight: int = 1) -> Milestone:
        project = self.projects[project_code]
        payload = {"name": name, "status": status, "owner_user_id": self.user_id(owner), "weight": weight}
        if due is not None:
            payload["due_date"] = due
        return milestones_service.create(self.ctx(actor), project, payload)

    def _milestones(self) -> None:
        if self.projects["CCR"].milestones:
            return
        d = self.today
        target = self.projects["CCR"].target_date or next_may_15(d)
        self._milestone("CCR", "marcus", "Requirements freeze", "done", d - timedelta(days=75), "marcus", 1)
        self._milestone("CCR", "marcus", "CAD release", "done", d - timedelta(days=40), "jordan", 2)
        self._milestone("CCR", "marcus", "Chassis fabricated", "in_progress", d + timedelta(days=30), "owen", 3)
        self._milestone("CCR", "marcus", "Mobility test day", "planned", d + timedelta(days=60), "elena", 2)
        self._milestone("CCR", "marcus", "Arm integration", "planned", d + timedelta(days=90), "jordan", 3)
        self._milestone("CCR", "marcus", "Competition", "planned", target, "marcus", 5)
        self._milestone("OPS", "priya", "Fall GBM series", "in_progress", d + timedelta(days=14), "priya", 1)
        self._milestone("OPS", "priya", "Budget approval", "done", d - timedelta(days=20), "grace", 1)
        self._milestone("FES", "priya", "Venue booked", "planned", d + timedelta(days=20), "mia", 1)

    # -- structure ------------------------------------------------------------

    def _location(self, name: str, parent: str | None = None, **fields) -> Location:
        parent_row = self.locations[parent] if parent else None
        query = Location.query.filter(Location.organization_id == self.org.id, func.lower(Location.name) == name.lower())
        query = query.filter(Location.parent_location_id == (parent_row.id if parent_row else None))
        row = query.first()
        if row is None:
            payload = {"name": name, **fields}
            if parent_row is not None:
                payload["parent_id"] = parent_row.id
            row = locations_service.create(self.ctx("admin"), payload)
        self.locations[name] = row
        return row

    def _locations(self) -> None:
        general = Location.query.filter_by(organization_id=self.org.id, is_default=True).first()
        if general is not None:
            self.locations[general.name] = general
        self._location("Engineering Student Center", building="Engineering Student Center", description="Main chapter building.")
        self._location("Robotics Lab", "Engineering Student Center", building="Engineering Student Center", room="1245")
        self._location("Bench 1", "Robotics Lab", room="1245")
        self._location("Bench 2", "Robotics Lab", room="1245")
        self._location("Electronics Bench", "Robotics Lab", room="1245", description="ESD-safe bench with the scope and supplies.")
        self._location("Machine Shop", "Engineering Student Center", building="Engineering Student Center", room="1130")
        self._location("ASME Storage", "Engineering Student Center", building="Engineering Student Center", room="B12")
        self._location("Test Field", description="Regolith test pit behind the building.")
        self._location("Trailer", description="Chapter equipment trailer used for competition travel.")

    def _categories(self) -> None:
        for row in Category.query.filter_by(organization_id=self.org.id).all():
            self.categories[row.name.lower()] = row
        missing = [name for name, _color, _icon in bootstrap.SEED_CATEGORIES if name.lower() not in self.categories]
        if missing:
            raise RuntimeError("seed categories are missing: " + ", ".join(missing))

    def category(self, name: str) -> Category:
        return self.categories[name.lower()]

    def _asset_types(self) -> None:
        existing = {row.name.lower(): row for row in AssetType.query.filter_by(organization_id=self.org.id).all()}
        for name, color, icon in ASSET_TYPES:
            row = existing.get(name.lower())
            if row is None:
                row = assets_service.create_type(self.ctx("admin"), {"name": name, "color": color, "icon": icon})
            self.types[name] = row

    def _vendors(self) -> None:
        existing = {row.name.lower(): row for row in Vendor.query.filter_by(organization_id=self.org.id).all()}
        for name, website, notes in VENDORS:
            row = existing.get(name.lower())
            if row is None:
                row = vendors_service.create(self.ctx("owen"), {"name": name, "website": website, "notes": notes})
            self.vendors[name] = row

    # -- assets ---------------------------------------------------------------

    def _asset(self, code: str, actor: str, name: str, *, types: tuple[str, ...], parent: str | None = None, project: str | None = None, location: str | None = None, team: str | None = None, criticality: str = "medium", **fields) -> Asset:
        row = Asset.query.filter(Asset.organization_id == self.org.id, func.lower(Asset.code) == code.lower()).first()
        if row is None:
            payload = {"name": name, "code": code, "criticality": criticality, "type_ids": [self.types[t].id for t in types], **fields}
            if parent:
                payload["parent_id"] = self.assets[parent].id
            if project:
                payload["project_id"] = self.projects[project].id
            if location:
                payload["location_id"] = self.locations[location].id
            if team:
                payload["responsible_team_id"] = self.teams[team].id
            row = assets_service.create(self.ctx(actor), payload)
        self.assets[code] = row
        return row

    def _assets(self) -> None:
        rover = dict(project="CCR", location="Robotics Lab")
        self._asset("CCR-ROVER", "marcus", "Crater Cruncher Rover", types=("Vehicle",), team="ccr", criticality="high", manufacturer="ASME at Iowa", model="CCR Mk II", **rover)
        self._asset("CCR-CHASSIS", "marcus", "Chassis", types=("Subsystem",), parent="CCR-ROVER", team="ccr", criticality="high", **rover)
        self._asset("CCR-MOB", "marcus", "Mobility System", types=("Subsystem",), parent="CCR-ROVER", team="wheels", criticality="high", **rover)
        for suffix, name in (("FL", "Front Left"), ("FR", "Front Right"), ("RL", "Rear Left"), ("RR", "Rear Right")):
            self._asset(f"CCR-WM-{suffix}", "marcus", f"{name} Wheel Module", types=("Subsystem",), parent="CCR-MOB", team="wheels", **rover)
        self._asset("CCR-ARM", "marcus", "Robotic Arm", types=("Subsystem",), parent="CCR-ROVER", team="arm", criticality="high", **rover)
        self._asset("CCR-ARM-SHOULDER", "marcus", "Shoulder Assembly", types=("Subsystem",), parent="CCR-ARM", team="arm", **rover)
        self._asset("CCR-ARM-ELBOW", "marcus", "Elbow Assembly", types=("Subsystem",), parent="CCR-ARM", team="arm", **rover)
        self._asset("CCR-ARM-EE", "marcus", "End Effector", types=("Subsystem",), parent="CCR-ARM", team="arm", **rover)
        self._asset("CCR-ELEC", "marcus", "Electrical System", types=("Subsystem",), parent="CCR-ROVER", team="elec", criticality="high", **rover)
        self._asset("CCR-COMPUTE", "marcus", "Compute and Control", types=("Subsystem", "Compute"), parent="CCR-ROVER", team="sw", criticality="high", **rover)

        printers = dict(types=("3D Printer",), location="Robotics Lab", team="fab", owner_user_id=self.user_id("owen"), manufacturer="Bambu Lab")
        self._asset("PRN-01", "owen", "3D Printer 01", model="X1C", serial_number="01P00A381900123", purchase_cost="1199.00", **printers)
        printer_02 = self._asset("PRN-02", "owen", "3D Printer 02", model="P1S", serial_number="01P00A382000456", purchase_cost="699.00", **printers)
        bench = dict(location="Electronics Bench", team="elec")
        self._asset("SOL-01", "owen", "Soldering Station 01", types=("Tool",), criticality="low", manufacturer="Hakko", model="FX-888D", **bench)
        self._asset("CHG-01", "owen", "Battery Charger 01", types=("Power",), manufacturer="iCharger", model="X8", **bench)
        self._asset("OSC-01", "owen", "Oscilloscope 01", types=("Test Equipment",), manufacturer="Rigol", model="DS1054Z", **bench)
        self._asset("PSU-01", "owen", "Bench Power Supply 01", types=("Power", "Test Equipment"), manufacturer="Rigol", model="DP832", **bench)
        self._asset("TK-A", "owen", "Tool Kit A", types=("Tool",), location="ASME Storage", team="inv", criticality="low")
        self._asset("CAM-01", "owen", "Camera Kit", types=("Test Equipment",), location="Robotics Lab", team="sw", criticality="low", manufacturer="Intel", model="RealSense D435")
        rig = self._asset("RIG-01", "owen", "Test Rig 01", types=("Test Equipment",), location="Test Field", team="wheels")

        if printer_02.status == "online":
            assets_service.change_status(self.ctx("owen"), printer_02, "offline_unplanned", downtime_reason="Nozzle clog", note="Clogged mid-print; nozzle swap scheduled.")
        if rig.status == "online":
            assets_service.change_status(self.ctx("owen"), rig, "offline_planned", downtime_reason="Load cell recalibration")

    # -- work orders ----------------------------------------------------------

    def _wo(
        self,
        key: str,
        *,
        by: str,
        title: str,
        description: str | None = None,
        priority: str = "medium",
        work_type: str = "reactive",
        project: str | None = None,
        location: str | None = None,
        asset: str | None = None,
        related: tuple[str, ...] = (),
        team: str | None = None,
        assignees: tuple[str, ...] = (),
        assignee_teams: tuple[str, ...] = (),
        watchers: tuple[str, ...] = (),
        categories: tuple[str, ...] = (),
        due: float | None = None,
        start: float | None = None,
        estimated_minutes: int | None = None,
        vendor: str | None = None,
        budget_code: str | None = None,
        parent: str | None = None,
        completion_policy: str = "manual",
        draft: bool = False,
        recurrence: dict | None = None,
    ) -> WorkOrder:
        payload: dict = {"title": title, "priority": priority, "work_type": work_type, "parent_completion_policy": completion_policy, "draft": draft}
        if description:
            payload["description"] = description
        if project:
            payload["project_id"] = self.projects[project].id
        if location:
            payload["location_id"] = self.locations[location].id
        if asset:
            payload["primary_asset_id"] = self.assets[asset].id
        if related:
            payload["asset_ids"] = [self.assets[code].id for code in related]
        if team:
            payload["team_id"] = self.teams[team].id
        if assignees:
            payload["assignee_user_ids"] = [self.user_id(k) for k in assignees]
        if assignee_teams:
            payload["assignee_team_ids"] = [self.teams[k].id for k in assignee_teams]
        if watchers:
            payload["watcher_user_ids"] = [self.user_id(k) for k in watchers]
        if categories:
            payload["category_ids"] = [self.category(name).id for name in categories]
        if due is not None:
            payload["due_at"] = self.days(due)
        if start is not None:
            payload["start_at"] = self.days(start)
        if estimated_minutes is not None:
            payload["estimated_minutes"] = estimated_minutes
        if vendor:
            payload["vendor_id"] = self.vendors[vendor].id
        if budget_code:
            payload["budget_code"] = budget_code
        parent_row = self.work_orders[parent] if parent else None
        row = work_orders_service.create(self.ctx(by), payload, parent=parent_row)
        if recurrence is not None:
            # No service path exists for recurrence yet (maintenance plans are a later stage).
            row.recurrence_json = dict(recurrence)
            db.session.commit()
        self.work_orders[key] = row
        return row

    def _start(self, key: str, actor: str) -> None:
        work_orders_service.transition(self.ctx(actor), self.work_orders[key], "start")

    def _hold(self, key: str, actor: str, note: str) -> None:
        work_orders_service.transition(self.ctx(actor), self.work_orders[key], "hold", note=note)

    def _cancel(self, key: str, actor: str, note: str) -> None:
        work_orders_service.transition(self.ctx(actor), self.work_orders[key], "cancel", note=note)

    def _complete(self, key: str, actor: str, *, note: str | None = None, time=(), cost=(), asset_status: dict | None = None, follow_up: dict | None = None, follow_up_key: str | None = None) -> None:
        time_entries = [{"user_id": self.user_id(who), "minutes": minutes, "note": text} for who, minutes, text in time]
        cost_entries = [
            {"type": kind, "amount": amount, "vendor_id": self.vendors[vendor].id if vendor else None, "description": text}
            for kind, amount, vendor, text in cost
        ]
        result = work_orders_service.complete(
            self.ctx(actor),
            self.work_orders[key],
            note=note,
            time_entries=time_entries,
            cost_entries=cost_entries,
            asset_status=asset_status,
            follow_up=follow_up,
        )
        if follow_up_key and result["follow_up"] is not None:
            self.work_orders[follow_up_key] = result["follow_up"]

    def _depends(self, key: str, blocking: str, actor: str) -> None:
        work_orders_service.add_dependency(self.ctx(actor), self.work_orders[key], self.work_orders[blocking].id)

    def _work_orders(self) -> None:
        self._wheels_work()
        self._arm_work()
        self._electrical_work()
        self._software_work()
        self._project_work()
        self._safety_work()
        self._shop_work()
        self._chapter_work()

    def _wheels_work(self) -> None:
        lab = dict(project="CCR", location="Robotics Lab", team="wheels")
        self._wo(
            "hub_inspection",
            by="elena",
            title="Inspect wheel hub fasteners",
            description="Monthly check of all sixteen hub bolts for torque and thread damage.",
            work_type="preventive",
            asset="CCR-MOB",
            related=("CCR-WM-FL", "CCR-WM-FR", "CCR-WM-RL", "CCR-WM-RR"),
            assignees=("ava",),
            watchers=("marcus",),
            categories=("Mechanical", "Inspection", "Preventive"),
            due=7,
            estimated_minutes=60,
            recurrence=RECURRENCE_MONTHLY,
            **lab,
        )
        self._start("hub_inspection", "ava")

        self._wo(
            "torque_check",
            by="elena",
            title="Torque check before test day",
            description="Full torque pass on the drivetrain before the mobility test day.",
            priority="high",
            work_type="inspection",
            asset="CCR-MOB",
            assignees=("liam",),
            assignee_teams=("wheels",),
            watchers=("marcus",),
            categories=("Mechanical", "Inspection"),
            due=14,
            estimated_minutes=120,
            **lab,
        )
        self._wo("torque_front", by="elena", title="Torque front wheel modules", parent="torque_check", assignees=("ava",), categories=("Mechanical",), due=13, team="wheels")
        self._wo("torque_rear", by="elena", title="Torque rear wheel modules", parent="torque_check", assignees=("liam",), categories=("Mechanical",), due=13, team="wheels")

        self._wo(
            "stage_rover",
            by="elena",
            title="Stage rover for mobility test day",
            description="Move the rover to the test field, check tyre pressure and load the ballast plates.",
            priority="high",
            work_type="project",
            asset="CCR-ROVER",
            assignees=("ava", "liam"),
            categories=("Project", "Mechanical"),
            due=21,
            estimated_minutes=90,
            project="CCR",
            location="Test Field",
            team="wheels",
        )
        self._depends("stage_rover", "torque_check", "elena")  # torque check is still open -> blocked

        self._wo(
            "rl_bearing",
            by="elena",
            title="Replace rear left wheel module bearing",
            description="Bearing growls under load; replace with the sealed unit and re-shim.",
            priority="high",
            asset="CCR-WM-RL",
            assignees=("liam",),
            categories=("Mechanical", "Damage"),
            due=-2,
            start=-6,
            estimated_minutes=150,
            **lab,
        )
        self._start("rl_bearing", "liam")
        self._complete(
            "rl_bearing",
            "elena",
            note="Bearing replaced and preload set to spec.",
            time=(("liam", 120, "Teardown and rebuild"), ("ava", 45, "Shimming and test spin")),
            cost=(("parts", "38.40", "McMaster-Carr", "6205-2RS sealed bearing x2"),),
        )

        self._wo(
            "hub_adapters",
            by="elena",
            title="Print spare wheel hub adapters",
            description="Two spare adapters in PETG-CF for the competition kit.",
            work_type="project",
            asset="CCR-WM-FR",
            assignees=("casey",),
            categories=("Fabrication",),
            due=5,
            estimated_minutes=60,
            **lab,
        )
        self._start("hub_adapters", "casey")
        self._complete("hub_adapters", "casey", note="Printed on Printer 01, dimensions checked.", time=(("casey", 55, "Print setup and post-processing"),), cost=(("parts", "12.00", "Bambu Lab", "PETG-CF filament"),))

        self._wo(
            "fr_shimmy",
            by="ava",
            title="Front right wheel module shimmy under load",
            description="Shimmy appears above 1.2 m/s on the gravel patch. Suspect a loose steering link.",
            priority="high",
            asset="CCR-WM-FR",
            assignees=("ava",),
            watchers=("elena",),
            categories=("Mechanical", "Damage"),
            due=-3,
            **lab,
        )

        self._wo(
            "test_checklist",
            by="elena",
            title="Update mobility test checklist",
            description="Fold the advisor's comments into the pre-drive checklist.",
            priority="low",
            work_type="documentation",
            assignees=("liam",),
            categories=("Documentation",),
            due=-1,
            **lab,
        )
        self._start("test_checklist", "elena")
        self._hold("test_checklist", "elena", "Waiting for advisor review of the revised checklist.")
        work_orders_service.set_watchers(self.ctx("elena"), self.work_orders["test_checklist"], [self.user_id("alan"), self.user_id("marcus")])

    def _arm_work(self) -> None:
        lab = dict(project="CCR", location="Robotics Lab", team="arm")
        self._wo(
            "arm_current",
            by="jordan",
            title="Validate robotic arm current limits",
            description="Confirm the shoulder and elbow drivers trip at 18 A before the integration test.",
            priority="high",
            work_type="inspection",
            asset="CCR-ARM",
            assignees=("noah",),
            categories=("Electrical", "Software"),
            due=-4,
            start=-9,
            estimated_minutes=120,
            **lab,
        )
        self._start("arm_current", "noah")
        self._complete("arm_current", "jordan", note="Both joints trip between 17.6 A and 18.2 A.", time=(("noah", 150, "Bench test with the dyno"),))

        self._wo(
            "arm_integration",
            by="jordan",
            title="Integrate arm controller with rover compute",
            description="Bring the arm controller onto the rover CAN bus and expose joint telemetry.",
            priority="high",
            work_type="project",
            asset="CCR-COMPUTE",
            related=("CCR-ARM",),
            assignees=("noah", "zoe"),
            watchers=("marcus",),
            categories=("Software", "Embedded Systems"),
            due=45,
            estimated_minutes=480,
            **lab,
        )
        self._depends("arm_integration", "arm_current", "jordan")  # blocker already done -> not blocked

        self._wo(
            "shoulder_rebuild",
            by="jordan",
            title="Rebuild shoulder assembly with new bushings",
            description="Replace the worn nylon bushings with bronze and re-shim the joint.",
            priority="high",
            asset="CCR-ARM-SHOULDER",
            assignees=("mia",),
            categories=("Mechanical",),
            due=3,
            estimated_minutes=240,
            completion_policy="auto",
            **lab,
        )
        self._wo("shoulder_order", by="jordan", title="Order bronze bushings", parent="shoulder_rebuild", work_type="procurement", assignees=("owen",), categories=("Procurement",), due=1, vendor="McMaster-Carr")
        self._wo("shoulder_machine", by="jordan", title="Machine bushing seats", parent="shoulder_rebuild", assignees=("casey",), categories=("Fabrication",), due=2, location="Machine Shop")
        self._wo("shoulder_reassemble", by="jordan", title="Reassemble and test shoulder joint", parent="shoulder_rebuild", assignees=("mia",), categories=("Mechanical",), due=3)
        self._complete("shoulder_order", "owen", note="Received and checked.", cost=(("parts", "27.90", "McMaster-Carr", "SAE 841 bronze bushings x4"),))
        self._start("shoulder_machine", "casey")
        self._complete("shoulder_machine", "casey", note="Seats bored to 12.02 mm.", time=(("casey", 90, "Lathe work"),))
        self._start("shoulder_reassemble", "mia")
        self._complete("shoulder_reassemble", "mia", note="Joint sweeps full range with no play.", time=(("mia", 75, "Reassembly and range test"),))

        self._wo(
            "grip_test",
            by="jordan",
            title="End effector grip force test",
            description="Measure grip force across the actuator range with the load cell.",
            work_type="inspection",
            asset="CCR-ARM-EE",
            assignees=("mia",),
            categories=("Mechanical", "Inspection"),
            due=-5,
            **lab,
        )
        self._start("grip_test", "mia")
        work_orders_service.set_assignees(self.ctx("jordan"), self.work_orders["grip_test"], [self.user_id("mia"), self.user_id("noah")], [])

        self._wo(
            "encoder_drift",
            by="noah",
            title="Elbow joint encoder drift",
            description="Elbow reports a slow drift of about 2 degrees per hour at rest.",
            asset="CCR-ARM-ELBOW",
            assignees=("noah",),
            categories=("Electrical", "Embedded Systems"),
            due=6,
            **lab,
        )
        self._cancel("encoder_drift", "jordan", "Duplicate of the encoder firmware fix tracked in the software backlog.")

        self._wo(
            "arm_sop",
            by="jordan",
            title="Draft arm operating procedure",
            description="Power-up sequence, keep-out zone and e-stop checks for anyone running the arm.",
            priority="low",
            work_type="documentation",
            asset="CCR-ARM",
            categories=("Documentation", "Standard Operating Procedure"),
            due=30,
            draft=True,
            **lab,
        )

    def _electrical_work(self) -> None:
        self._wo(
            "harness_test",
            by="sam",
            title="Wire harness continuity test",
            description="Ring out every conductor in the main harness against the pinout sheet.",
            work_type="inspection",
            project="CCR",
            location="Electronics Bench",
            asset="CCR-ELEC",
            team="elec",
            assignees=("ethan",),
            categories=("Electrical", "Inspection"),
            due=-1,
            start=-3,
            estimated_minutes=90,
        )
        self._start("harness_test", "ethan")
        self._complete("harness_test", "sam", note="Two swapped pins on J4 corrected.", time=(("ethan", 80, "Continuity checks"), ("sam", 30, "Pinout review")))

        self._wo(
            "cell_balance",
            by="sam",
            title="Battery pack cell balance check",
            description="Monthly balance charge and cell-voltage log for both packs.",
            work_type="preventive",
            project="CCR",
            location="Electronics Bench",
            asset="CCR-ELEC",
            related=("CHG-01",),
            team="elec",
            assignee_teams=("elec",),
            categories=("Electrical", "Preventive", "Safety"),
            due=10,
            estimated_minutes=45,
            recurrence=RECURRENCE_MONTHLY,
        )

        self._wo(
            "psu_calibration",
            by="sam",
            title="Calibrate bench power supply",
            description="Verify all three channels against the reference meter.",
            work_type="preventive",
            location="Electronics Bench",
            asset="PSU-01",
            team="elec",
            assignees=("ethan",),
            categories=("Electrical", "Preventive"),
            due=0,
            start=-1,
            estimated_minutes=40,
        )
        self._complete("psu_calibration", "sam", note="All channels within 0.5 percent.", time=(("ethan", 40, "Calibration"),))

        self._wo(
            "blown_fuse",
            by="ethan",
            title="Replace blown fuse on motor controller",
            description="Channel 3 fuse opened during the last drive; find the cause before replacing.",
            priority="high",
            project="CCR",
            location="Robotics Lab",
            asset="CCR-ELEC",
            team="elec",
            assignees=("ethan",),
            categories=("Electrical", "Damage"),
            due=-2,
        )

        self._wo(
            "scope_probe",
            by="sam",
            title="Oscilloscope probe channel 2 intermittent",
            description="Channel 2 drops out when the probe cable is flexed.",
            priority="low",
            location="Electronics Bench",
            asset="OSC-01",
            team="elec",
            assignees=("ethan",),
            categories=("Electrical",),
            vendor="DigiKey",
            due=5,
        )
        self._start("scope_probe", "sam")
        self._hold("scope_probe", "sam", "Waiting for the replacement probe from DigiKey.")

    def _software_work(self) -> None:
        sw = dict(project="CCR", location="Robotics Lab", team="sw")
        self._wo(
            "telemetry_parser",
            by="marcus",
            title="Update telemetry packet parser",
            description="Handle the new joint-state packet and drop malformed frames instead of raising.",
            priority="high",
            work_type="project",
            asset="CCR-COMPUTE",
            assignees=("zoe",),
            categories=("Software",),
            due=3,
            estimated_minutes=240,
            **sw,
        )
        self._start("telemetry_parser", "zoe")
        work_orders_service.add_time_entry(self.ctx("zoe"), self.work_orders["telemetry_parser"], {"minutes": 60, "note": "Parser refactor"})

        self._wo(
            "waypoint_test",
            by="marcus",
            title="Autonomy waypoint follower field test",
            description="Run the five-waypoint course three times and log cross-track error.",
            work_type="project",
            asset="CCR-ROVER",
            assignees=("zoe",),
            assignee_teams=("sw",),
            categories=("Software", "Project"),
            due=40,
            estimated_minutes=180,
            project="CCR",
            location="Test Field",
            team="sw",
        )
        self._wo("waypoint_course", by="marcus", title="Load test course waypoints", parent="waypoint_test", assignees=("zoe",), categories=("Software",), due=38)
        self._wo("waypoint_batteries", by="marcus", title="Charge rover battery packs for the field test", parent="waypoint_test", assignees=("ethan",), categories=("Electrical",), due=39, location="Electronics Bench")

        self._wo(
            "telemetry_dropout",
            by="zoe",
            title="Fix telemetry dropout on long runs",
            description="Link drops after about twenty minutes; suspect the radio watchdog.",
            priority="high",
            asset="CCR-COMPUTE",
            assignees=("zoe",),
            categories=("Software", "Embedded Systems"),
            due=-1,
            start=-5,
            **sw,
        )
        self._start("telemetry_dropout", "zoe")
        self._complete("telemetry_dropout", "zoe", note="Watchdog timeout raised and reconnect logic added.", time=(("zoe", 200, "Debugging and fix"),))

        self._wo(
            "camera_calibration",
            by="marcus",
            title="Camera calibration for arm vision",
            description="Intrinsics and hand-eye calibration for the depth camera on the end effector.",
            asset="CAM-01",
            related=("CCR-ARM-EE",),
            assignees=("zoe", "noah"),
            categories=("Software",),
            due=-7,
            estimated_minutes=120,
            **sw,
        )

    def _project_work(self) -> None:
        self._wo(
            "weld_inspection",
            by="marcus",
            title="Chassis weld inspection",
            description="Visual and dye-penetrant check of the chassis welds after the second fabrication pass.",
            priority="high",
            work_type="inspection",
            project="CCR",
            location="Machine Shop",
            asset="CCR-CHASSIS",
            team="ccr",
            assignees=("dana",),
            watchers=("alan",),
            categories=("Mechanical", "Inspection"),
            due=-1,
            start=-2,
            estimated_minutes=60,
        )
        self._start("weld_inspection", "dana")
        self._complete("weld_inspection", "marcus", note="No indications; two cosmetic grinds noted.", time=(("dana", 60, "Inspection"),))

        self._wo(
            "sensor_mount",
            by="marcus",
            title="Print spare sensor mount",
            description="Spare mount for the lidar in case the field unit cracks.",
            work_type="project",
            project="CCR",
            location="Robotics Lab",
            asset="CCR-COMPUTE",
            team="fab",
            assignees=("casey",),
            categories=("Fabrication",),
            due=2,
            estimated_minutes=45,
        )
        self._start("sensor_mount", "casey")
        self._complete("sensor_mount", "casey", note="Printed in ASA.", time=(("casey", 50, "Print and clean-up"),), cost=(("parts", "6.75", "Bambu Lab", "ASA filament"),))

        self._wo(
            "pack_crates",
            by="marcus",
            title="Pack competition crates",
            description="Pack the rover, spares and tools into the travel crates against the manifest.",
            work_type="project",
            project="CCR",
            location="Trailer",
            asset="CCR-ROVER",
            team="ccr",
            assignees=("liam", "mia"),
            assignee_teams=("ccr",),
            watchers=("priya", "alan"),
            categories=("Project",),
            due=(next_may_15(self.today) - self.today).days - 14,
            estimated_minutes=360,
        )
        self._wo("crate_labels", by="marcus", title="Print crate labels", parent="pack_crates", assignees=("casey",), categories=("Fabrication",), due=30)
        self._wo("spares_kit", by="marcus", title="Inventory the spare parts kit", parent="pack_crates", assignees=("grace",), categories=("Procurement",), due=30, location="ASME Storage")
        self._depends("pack_crates", "sensor_mount", "marcus")  # blocker already done -> not blocked

    def _safety_work(self) -> None:
        safety = dict(priority="critical", work_type="safety")
        self._wo(
            "estop_verification",
            by="dana",
            title="E-stop circuit verification",
            description="Prove every e-stop opens the main contactor within 100 ms.",
            project="CCR",
            location="Robotics Lab",
            asset="CCR-ELEC",
            team="elec",
            assignees=("dana",),
            assignee_teams=("elec",),
            watchers=("marcus", "priya"),
            categories=("Safety", "Electrical", "Inspection"),
            due=-1,
            start=-2,
            estimated_minutes=45,
            **safety,
        )
        self._start("estop_verification", "dana")
        self._complete("estop_verification", "dana", note="All four e-stops trip in under 60 ms.", time=(("dana", 45, "Verification"),))

        self._wo(
            "predrive_inspection",
            by="dana",
            title="Run pre-drive safety inspection",
            description="Checklist inspection before the rover leaves the lab.",
            project="CCR",
            location="Robotics Lab",
            asset="CCR-ROVER",
            team="ccr",
            assignees=("dana", "marcus"),
            watchers=("alan",),
            categories=("Safety", "Inspection"),
            due=0,
            estimated_minutes=30,
            **safety,
        )
        self._start("predrive_inspection", "dana")
        self._complete(
            "predrive_inspection",
            "dana",
            note="Passed with one finding: the e-stop cable jacket is frayed near the strain relief.",
            time=(("dana", 35, "Inspection"),),
            follow_up={"title": "Replace frayed e-stop cable", "priority": "high", "description": "Frayed jacket near the strain relief on the rear e-stop."},
            follow_up_key="estop_cable",
        )

        self._wo(
            "loto_audit",
            by="dana",
            title="Lockout tagout audit for machine shop",
            description="Confirm every machine has a tag station and the log is current.",
            location="Machine Shop",
            assignees=("dana", "owen"),
            assignee_teams=("fab",),
            categories=("Safety", "Inspection"),
            due=-10,
            estimated_minutes=60,
            **safety,
        )

        self._wo(
            "hot_work_training",
            by="dana",
            title="Hot work permit refresher training",
            description="Thirty-minute refresher for everyone who welds or grinds.",
            priority="high",
            work_type="safety",
            location="Machine Shop",
            assignee_teams=("fab",),
            categories=("Safety", "Event"),
            due=12,
        )
        self._cancel("hot_work_training", "dana", "Rescheduled into the fall GBM series.")

    def _shop_work(self) -> None:
        self._wo(
            "printer_nozzle",
            by="owen",
            title="Replace 3D Printer 02 nozzle",
            description="Printer 02 is offline with a clogged nozzle; fit the 0.4 mm hardened nozzle.",
            priority="high",
            location="Robotics Lab",
            asset="PRN-02",
            team="fab",
            assignees=("casey", "owen"),
            categories=("Fabrication", "Damage"),
            vendor="Bambu Lab",
            due=-1,
            estimated_minutes=30,
        )
        self._start("printer_nozzle", "casey")
        work_orders_service.add_cost_entry(
            self.ctx("owen"),
            self.work_orders["printer_nozzle"],
            {"type": "parts", "amount": "14.99", "vendor_id": self.vendors["Bambu Lab"].id, "description": "0.4 mm hardened steel nozzle"},
        )

        self._wo(
            "m4_inventory",
            by="owen",
            title="Inventory M4 fasteners",
            description="Count the M4 bins and update the reorder points.",
            priority="low",
            work_type="procurement",
            location="ASME Storage",
            team="inv",
            assignees=("grace",),
            categories=("Procurement",),
            due=0,
            start=-1,
            estimated_minutes=40,
        )
        self._start("m4_inventory", "grace")
        self._complete("m4_inventory", "grace", note="Reorder points updated; short on M4x16 socket heads.", time=(("grace", 35, "Count"),))

        self._wo(
            "filament_restock",
            by="owen",
            title="Restock PLA filament",
            description="Six spools of PLA Basic for the printers.",
            work_type="procurement",
            location="Robotics Lab",
            team="inv",
            assignees=("owen",),
            categories=("Procurement",),
            vendor="Bambu Lab",
            due=-2,
            start=-4,
            budget_code="OPS-CONSUMABLES",
        )
        self._complete("filament_restock", "owen", note="Order received.", cost=(("vendor", "89.97", "Bambu Lab", "PLA Basic 1 kg x6"),))

        self._wo(
            "toolkit_audit",
            by="owen",
            title="Quarterly tool kit audit",
            description="Check Tool Kit A against its inventory card and replace missing bits.",
            priority="low",
            work_type="preventive",
            location="ASME Storage",
            asset="TK-A",
            team="inv",
            assignees=("grace",),
            categories=("Inspection", "Preventive"),
            due=20,
        )

        self._wo(
            "rig_load_cell",
            by="owen",
            title="Service Test Rig 01 load cell",
            description="Recalibrate the load cell and replace the cracked mounting plate.",
            location="Test Field",
            asset="RIG-01",
            team="fab",
            assignees=("owen", "liam"),
            categories=("Mechanical", "Preventive"),
            due=1,
            start=-1,
            estimated_minutes=90,
        )
        self._start("rig_load_cell", "owen")
        self._complete(
            "rig_load_cell",
            "owen",
            note="Load cell recalibrated with the 20 kg reference mass.",
            time=(("owen", 70, "Calibration and plate swap"),),
            asset_status={"status": "online", "note": "Back in service after calibration."},
        )

        self._wo(
            "bin_labels",
            by="owen",
            title="Label storage bins",
            description="Print and apply labels for the reorganised fastener wall.",
            priority="low",
            location="ASME Storage",
            team="inv",
            categories=("Documentation",),
            draft=True,
        )

    def _chapter_work(self) -> None:
        self._wo(
            "venue",
            by="priya",
            title="Book venue for Fall Engineering Showcase",
            description="Confirm the atrium booking and power drop for the rover demo.",
            priority="high",
            work_type="event",
            project="FES",
            team="events",
            assignees=("mia",),
            categories=("Event",),
            due=15,
        )
        self._wo(
            "poster",
            by="priya",
            title="Design showcase poster",
            description="A0 poster for the chapter booth.",
            work_type="event",
            project="FES",
            team="events",
            assignees=("mia",),
            categories=("Event", "Documentation"),
            due=25,
            estimated_minutes=180,
        )
        self._start("poster", "mia")

        self._wo(
            "gbm_deck",
            by="priya",
            title="Prepare fall GBM slide deck",
            description="Kick-off deck: teams, calendar and how to get involved.",
            work_type="event",
            project="OPS",
            team="exec",
            assignees=("priya",),
            categories=("Event",),
            due=-1,
            start=-3,
        )
        self._start("gbm_deck", "priya")
        self._complete("gbm_deck", "priya", note="Deck shared with the officers.", time=(("priya", 90, "Slides"),))

        self._wo(
            "budget_request",
            by="grace",
            title="Submit spring budget request",
            description="Compile the spring budget request from the team estimates.",
            priority="high",
            project="OPS",
            team="exec",
            assignees=("grace",),
            watchers=("priya", "alan"),
            categories=("Procurement", "Documentation"),
            due=-3,
            start=-8,
            budget_code="OPS-ADMIN",
        )
        self._start("budget_request", "grace")
        self._complete("budget_request", "grace", note="Submitted to student government.", time=(("grace", 120, "Compilation and submission"),))

        self._wo(
            "team_polos",
            by="priya",
            title="Order team polos",
            description="Embroidered polos for the officer team.",
            priority="low",
            work_type="procurement",
            project="OPS",
            team="exec",
            assignees=("grace",),
            categories=("Procurement",),
            vendor="Amazon Business",
            due=9,
        )
        self._cancel("team_polos", "priya", "Vendor is out of stock; reorder next semester.")

        self._wo(
            "sponsor_letters",
            by="priya",
            title="Sponsor thank-you letters",
            description="Letters and photos for the spring sponsors.",
            work_type="event",
            project="OPS",
            team="events",
            assignees=("mia",),
            categories=("Event", "Documentation"),
            due=-4,
        )

        self._wo(
            "stem_night",
            by="priya",
            title="Plan outreach demo at Iowa City STEM night",
            description="Table, rover demo loop and a sign-up sheet.",
            work_type="event",
            project="OPS",
            team="events",
            assignee_teams=("events",),
            watchers=("marcus",),
            categories=("Event",),
            due=30,
        )
        self._wo("reserve_trailer", by="priya", title="Reserve chapter trailer for STEM night", parent="stem_night", assignees=("mia",), categories=("Event",), due=25, location="Trailer")
        self._wo("demo_table", by="priya", title="Build demo table display", parent="stem_night", assignee_teams=("events",), categories=("Event", "Fabrication"), due=28)

    # -- comments -------------------------------------------------------------

    def _comment(self, actor: str, segment: str, entity_id, body: str, parent=None) -> Comment:
        payload = {"body": body}
        if parent is not None:
            payload["parent_comment_id"] = parent.id
        return comments_service.create(self.ctx(actor), segment, entity_id, payload)

    def _comments(self) -> None:
        wo = self.work_orders
        self._comment("ava", "work-orders", wo["fr_shimmy"].id, f"Shimmy starts at about 1.2 m/s on the gravel patch. {self.mention('elena')} can we borrow the tracker from the arm team?")
        self._comment("casey", "work-orders", wo["printer_nozzle"].id, "Nozzle is out; waiting on the hardened replacement before I put the hotend back together.")
        first = self._comment("zoe", "work-orders", wo["telemetry_parser"].id, "Parser now tolerates truncated frames. Running the 20-minute soak test next.")
        self._comment("marcus", "work-orders", wo["telemetry_parser"].id, "Great. Log the frame counts so we can compare with the field test.", parent=first)
        self._comment("dana", "work-orders", wo["estop_cable"].id, f"{self.mention('marcus')} this needs to be done before the next drive.")
        self._comment("alan", "projects", self.projects["CCR"].id, "Looking forward to the chassis review. Send the weld inspection notes ahead of time.")
        self._comment("marcus", "assets", self.assets["CCR-ROVER"].id, "Mk II frame; the Mk I is on the shelf in ASME Storage for spares.")


# --------------------------------------------------------------------------- summary / report


def accounts(org, cfg) -> list[dict]:
    """The seed accounts with the passwords they were created with."""
    rows: list[dict] = []
    seen: set[int] = set()

    def add(user, password):
        if user is None or user.id in seen:
            return
        membership = bootstrap.membership_for(user, org)
        rows.append(
            {
                "name": user.name,
                "email": user.email,
                "username": user.username,
                "role": membership.role.name if membership is not None and membership.role is not None else None,
                "role_key": membership.role.system_key if membership is not None and membership.role is not None else None,
                "title": membership.title if membership is not None else None,
                "password": password,
            }
        )
        seen.add(user.id)

    add(_user_by_email(cfg.default_admin_email), cfg.default_admin_password)
    for _key, first, last, _role, _title in PEOPLE:
        add(_user_by_email(f"{first[0]}{last}@{EMAIL_DOMAIN}".lower()), cfg.default_user_password)
    return rows


def summary(org, *, skipped: bool = False) -> dict:
    """Counts of the organization's ops data (what the tests assert on)."""
    org_id = org.id

    def count(model, **filters) -> int:
        return model.query.filter_by(organization_id=org_id, **filters).count()

    def scalar(statement) -> int:
        return int(db.session.scalar(statement) or 0)

    now = utcnow()
    status_rows = db.session.execute(
        select(WorkOrder.status, func.count(WorkOrder.id)).where(WorkOrder.organization_id == org_id).group_by(WorkOrder.status)
    ).all()
    work_order_ids = select(WorkOrder.id).where(WorkOrder.organization_id == org_id)
    return {
        "skipped": skipped,
        "organization": org.slug,
        "users": count(Membership),
        "teams": count(Team),
        "locations": count(Location),
        "categories": count(Category),
        "asset_types": count(AssetType),
        "vendors": count(Vendor),
        "projects": count(OpsProject),
        "milestones": count(Milestone),
        "assets": count(Asset),
        "work_orders": count(WorkOrder),
        "work_order_statuses": {status: int(total) for status, total in sorted(status_rows)},
        "overdue_work_orders": scalar(
            select(func.count(WorkOrder.id)).where(
                WorkOrder.organization_id == org_id, WorkOrder.status.in_(OPEN_STATUSES), WorkOrder.due_at < now
            )
        ),
        "critical_work_orders": count(WorkOrder, priority="critical"),
        "sub_work_orders": scalar(
            select(func.count(WorkOrder.id)).where(WorkOrder.organization_id == org_id, WorkOrder.parent_work_order_id.is_not(None))
        ),
        "dependencies": scalar(select(func.count(WorkOrderDependency.id)).where(WorkOrderDependency.blocked_work_order_id.in_(work_order_ids))),
        "time_entries": count(TimeEntry),
        "cost_entries": count(CostEntry),
        "comments": count(Comment),
        "notifications": Notification.query.filter_by(organization_id=org_id).count(),
        "audit_events": AuditEvent.query.filter_by(organization_id=org_id).count(),
    }


def format_report(result: dict) -> str:
    lines = ["", "ASME Ops seed data - DEVELOPMENT ONLY. Do not use these accounts anywhere public.", ""]
    if result.get("skipped"):
        lines.append("Already seeded (project CCR exists); nothing changed. Use --reset to rebuild.")
        lines.append("")
    rows = result.get("accounts") or []
    if rows:
        widths = (
            max(len("Email"), *(len(r["email"]) for r in rows)),
            max(len("Role"), *(len(r["role"] or "") for r in rows)),
            max(len("Name"), *(len(r["name"] or "") for r in rows)),
        )
        header = f"{'Email':<{widths[0]}}  {'Role':<{widths[1]}}  {'Name':<{widths[2]}}  Password"
        lines.append(header)
        lines.append("-" * len(header))
        for r in rows:
            lines.append(f"{r['email']:<{widths[0]}}  {(r['role'] or ''):<{widths[1]}}  {(r['name'] or ''):<{widths[2]}}  {r['password']}")
        lines.append("")
    counts = {k: v for k, v in result.items() if k not in ("accounts", "skipped", "organization", "work_order_statuses")}
    lines.append("Counts: " + ", ".join(f"{k} {v}" for k, v in counts.items()))
    statuses = result.get("work_order_statuses") or {}
    if statuses:
        lines.append("Work orders by status: " + ", ".join(f"{k} {v}" for k, v in statuses.items()))
    return "\n".join(lines)


# --------------------------------------------------------------------------- entry point


def seed_ops(reset: bool = False, *, echo=print) -> dict:
    """Build the demo dataset. Returns the counts (``skipped`` is true when the
    organization was already seeded and ``reset`` was false). Pass ``echo=None``
    to suppress the printed credentials table."""
    _refuse_in_production()
    cfg = settings()
    legacy_bootstrap.seed_defaults()
    org = bootstrap.default_organization()
    if org is None:
        raise RuntimeError("the default organization does not exist; run `python manage.py upgrade` first")
    if reset:
        reset_ops(org)
    elif is_seeded(org):
        result = summary(org, skipped=True)
        result["accounts"] = accounts(org, cfg)
        if echo:
            echo(format_report(result))
        return result
    _Builder(org, cfg).build()
    result = summary(org)
    result["accounts"] = accounts(org, cfg)
    if echo:
        echo(format_report(result))
    log.info("seeded ops demo data for %s", org.slug)
    return result
