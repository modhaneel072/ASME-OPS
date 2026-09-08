# ASME Ops – Stage 1 (Foundation + Shell) and Stage 2 (Projects + Work Orders) Implementation Plan

**Goal:** Ship the first mandatory milestone of ASME Ops: tenancy, permissions, audit and API foundation; the reference-style React shell; Setup Center with teams/users/locations/categories; and the complete Projects + Work Orders vertical slice with real persistence, server-side authorization, seed data and an operations dashboard.

**Architecture:** Modular monolith inside the existing Flask app (`asme/ops` package, `ops_*` tables, `/api/v1` JSON API) plus a Vite React 19 + TypeScript SPA served at `/app`. See ADR-0001 and `docs/architecture/overview.md`.

**Tech Stack:** Python 3.13, Flask 3.1, SQLAlchemy 2.0, Alembic (Flask-Migrate), pytest; React 19, TypeScript, Vite, TanStack Query 5, TanStack Table 8, React Router 7, React Hook Form 7, Zod 4, lucide-react, Vitest, Playwright.

**Spec:** `docs/decisions/ADR-0001-transitional-architecture.md`, `docs/architecture/overview.md`, and the embedded product specification delivered with the build prompt (sections 4–10, 19–21, 25.1, 28, 29, 34–41 apply to this plan).

## Global constraints

- No existing table or column is renamed or dropped. Every new table is prefixed `ops_`. Migrations are additive with a working `downgrade()`.
- Every private query is scoped by `organization_id`; every mutation passes a `PolicyContext`; every important mutation writes an `ops_audit_events` row in the same transaction.
- JSON envelope: success `{"ok": true, "payload": ...}`; error `{"ok": false, "code": "...", "error": "...", ...}`; validation `code="validation"` with `errors: {field: message}`.
- Mutating JSON routes require `Content-Type: application/json`; multipart uploads require header `X-Requested-With: ASME-Ops`.
- No decorative controls: a button that cannot work in this stage is not rendered (parts, procedures, recurrence and vendor purchase flows are omitted from the create pane until their stages ship; vendor *selection* is included).
- Seed credentials are development-only, printed by the seed command, never in production (`manage.py seed-ops` refuses when `ASME_ENV=production`).
- No third-party UI template. Tokens from spec §6.2 live in `apps/ops-web/src/ui/tokens.css`.
- Viewports under test: 1440×900, 1366×768, 768×1024, 390×844.
- Commit after each task with a conventional message in the maintainer's voice.

## File structure (created by this plan)

Backend (see `docs/architecture/overview.md` for the full tree): `asme/ops/{types,permissions,policy,validation,serializers,numbering,storage,bootstrap,seeds}.py`, `asme/ops/models/{identity,structure,projects,work,shared}.py`, `asme/ops/services/*.py`, `asme/blueprints/ops/*.py`, `asme/blueprints/ops_app.py`, `migrations/versions/0003_ops_foundation.py`, `tests/ops/*.py`.

Frontend: `apps/ops-web/{vite.config.ts,tsconfig.json,playwright.config.ts,index.html}`, `src/{main.tsx,app,ui,api,features,lib}`, `apps/ops-web/e2e/*.spec.ts`.

Docs: `docs/{permissions-matrix,reporting-metrics,api,test-plan,deployment}.md`, `CHANGELOG.md`, updates to `docs/implementation-status.md` and `docs/migration-plan.md`.

## Shared contracts (binding for every task)

### Permission keys (`asme/ops/permissions.py`)

```
chapter.settings.manage  chapter.setup.manage
user.read  user.manage  role.manage
team.read  team.manage
location.read  location.manage
category.read  category.manage
asset.read  asset.manage  asset.status.update
vendor.read  vendor.manage
project.read  project.read_private  project.create  project.manage  project.archive  milestone.manage
work_order.read_all  work_order.read_assigned  work_order.create  work_order.edit  work_order.assign
work_order.start  work_order.complete  work_order.cancel  work_order.comment  work_order.log_time  work_order.attach
saved_filter.share  report.view  report.export  audit.read  notification.read
# seeded now, enforced by later stages:
request.submit  request.review  inventory.read  inventory.manage  purchase.submit  purchase.review
procedure.read  procedure.manage  procedure.publish  plan.manage  meter.read  meter.record
automation.manage  dashboard.manage  message.read  message.send  sponsor.manage
```

Scopes: `chapter` > `project` > `team` > `assigned` > `own`.

| System role (`system_key`) | Grants (key@scope) |
|---|---|
| `chapter_admin` | every key @chapter |
| `executive_officer` | every key @chapter except `role.manage`, `chapter.settings.manage` |
| `project_lead` | `project.read`, `project.create`, `work_order.create`, `work_order.read_all`, `work_order.comment`, `work_order.attach`, `work_order.log_time`, `team.read`, `asset.read`, `location.read`, `category.read`, `vendor.read`, `report.view`, `notification.read` @chapter; `project.read_private`, `project.manage`, `milestone.manage`, `work_order.edit`, `work_order.assign`, `work_order.start`, `work_order.complete`, `work_order.cancel`, `asset.manage`, `team.manage`, `report.export` @project |
| `team_lead` | `project.read`, `work_order.create`, `work_order.read_all`, `work_order.comment`, `work_order.attach`, `work_order.log_time`, `team.read`, `asset.read`, `location.read`, `category.read`, `vendor.read`, `report.view`, `notification.read` @chapter; `team.manage`, `work_order.edit`, `work_order.assign`, `work_order.start`, `work_order.complete`, `work_order.cancel` @team |
| `full_member` | `project.read`, `work_order.read_all`, `work_order.create`, `work_order.comment`, `work_order.attach`, `team.read`, `asset.read`, `location.read`, `category.read`, `vendor.read`, `report.view`, `request.submit`, `notification.read` @chapter; `work_order.edit` @own; `work_order.start`, `work_order.complete`, `work_order.log_time` @assigned |
| `shop_operator` | `project.read`, `work_order.read_assigned`, `work_order.comment`, `work_order.attach`, `asset.read`, `location.read`, `request.submit`, `notification.read` @chapter; `work_order.start`, `work_order.complete`, `work_order.log_time` @assigned |
| `requester` | `project.read`, `request.submit`, `notification.read` @chapter |
| `inventory_manager` | full_member grants + `inventory.read`, `inventory.manage`, `purchase.submit`, `purchase.review`, `asset.manage`, `vendor.manage`, `work_order.edit`, `work_order.assign` @chapter |
| `safety_officer` | full_member grants + `procedure.read`, `procedure.manage`, `procedure.publish`, `asset.status.update`, `work_order.edit`, `work_order.assign`, `work_order.cancel`, `audit.read` @chapter |
| `treasurer` | full_member grants + `purchase.review`, `vendor.read`, `report.export`, `audit.read` @chapter |
| `faculty_advisor` | `project.read`, `project.read_private`, `work_order.read_all`, `asset.read`, `team.read`, `user.read`, `location.read`, `category.read`, `report.view`, `report.export`, `audit.read`, `purchase.review`, `notification.read` @chapter |
| `sponsor_guest` | `report.view` @chapter |

Legacy mapping at first sight: `admin → chapter_admin`, `team_leader → team_lead`, `member → full_member`.

Scope resolution (`policy.can(ctx, key, obj)`): a grant `key@chapter` always passes. `@project` passes when `obj.project_id in ctx.project_ids` (or `obj.id` for projects). `@team` passes when `obj.team_id in ctx.lead_team_ids`, or `in ctx.team_ids` for read keys. `@assigned` passes when `ctx.user.id in obj.assignee_user_ids` or `ctx.team_ids ∩ obj.assignee_team_ids`. `@own` passes when `obj.created_by_user_id == ctx.user.id`. Private projects are readable only by project members or holders of `project.read_private`.

### Service call shape

Every service function takes `ctx: PolicyContext` first, raises `asme.services.errors.*` (`Validation`, `NotFound`, `Forbidden`, `Conflict`) or `asme.ops.validation.ValidationErrors`, commits itself, and returns ORM objects. Read functions never commit.

### Serializer shapes (`asme/ops/serializers.py`)

```json
user_ref      {"id": 12, "name": "Lee Lead", "email": "lee@uiowa.edu", "avatar_url": null}
team_ref      {"id": "<uuid>", "name": "Robotic Arm"}
project_ref   {"id": "<uuid>", "name": "Crater Cruncher Rover", "code": "CCR"}
location      {"id","name","description","parent_id","building","room","is_default","path": ["Robotics Lab","Bench 2"],"asset_count","created_at","updated_at"}
category      {"id","name","color","icon","description","usage": {"work_orders": 3},"created_at","created_by": user_ref}
team          {"id","name","description","parent_team_id","project": project_ref|null,"leads": [user_ref],"member_count","created_at"}
member(user)  {"id","user": user_ref,"role": {"id","name","system_key"},"status","teams": [team_ref],"joined_at","last_login_at"}
asset         {"id","name","code","description","parent_id","project": project_ref|null,"location": {"id","name"}|null,"team": team_ref|null,"owner": user_ref|null,"manufacturer","model","serial_number","purchase_date","purchase_cost","warranty_end","criticality","status","types": [{"id","name","color"}],"child_count","open_work_order_count","created_at","updated_at"}
project       {"id","name","code","description","status","visibility","risk_level","lead": user_ref|null,"faculty_advisor": user_ref|null,"start_date","target_date","budget_amount","repository_url","cad_url","requirements_url","competition","public_project_id","archived_at","stats": {"open_work_orders","overdue_work_orders","completion_percent","next_milestone": {...}|null,"member_count"},"created_at","updated_at"}
milestone     {"id","project_id","name","description","due_date","status","owner": user_ref|null,"weight","completed_at"}
work_order    {"id","number","title","description","status","priority","work_type","project": project_ref|null,"location": {"id","name"}|null,"asset": {"id","name"}|null,"team": team_ref|null,"assignees": [user_ref],"assignee_teams": [team_ref],"watchers": [user_ref],"categories": [{"id","name","color"}],"vendor": {"id","name"}|null,"parent_id","parent_number","sub_work_orders": {"total","done"},"start_at","due_at","completed_at","canceled_at","estimated_minutes","actual_minutes","is_overdue","is_blocked","budget_code","completion_note","created_by": user_ref,"created_at","updated_at"}
work_order_detail = work_order + {"status_history": [...], "time_entries": [...], "cost_entries": [...], "dependencies": {...}, "children": [work_order]}
comment       {"id","entity_type","entity_id","author": user_ref,"body","parent_comment_id","edited_at","created_at"}
attachment    {"id","entity_type","entity_id","original_name","content_type","size_bytes","uploaded_by": user_ref,"download_url","created_at"}
audit_event   {"id","event_type","entity_type","entity_id","actor": user_ref|null,"summary","before","after","metadata","occurred_at"}
```

Lists return `{"items": [...], "next_cursor": str|null, "total": int}`.

### API surface added by this plan (all under `/api/v1`)

```
POST /auth/login  POST /auth/logout  GET /session
GET|PATCH /organization  GET /setup  POST /setup/dismiss-banner  POST /setup/reopen-banner
GET|POST /teams  GET|PATCH|DELETE /teams/:id  PUT /teams/:id/members
GET /users  POST /users/invite  PATCH /users/:id  (role/status)  GET /roles
GET|POST /locations  GET|PATCH|DELETE /locations/:id
GET|POST /categories  GET|PATCH|DELETE /categories/:id
GET|POST /asset-types  GET|POST /assets  GET|PATCH /assets/:id  POST /assets/:id/status  GET /assets/:id/history
GET|POST /vendors  GET|PATCH /vendors/:id
GET|POST /projects  GET|PATCH /projects/:id  POST /projects/:id/archive  POST /projects/:id/restore
GET /projects/:id/health  GET /projects/:id/activity  PUT /projects/:id/members
GET|POST /projects/:id/milestones  PATCH|DELETE /projects/:id/milestones/:mid
GET|POST /work-orders  GET|PATCH /work-orders/:id
POST /work-orders/:id/(start|hold|resume|complete|cancel|reopen|duplicate)
POST /work-orders/:id/sub-work-orders  PUT /work-orders/:id/assignees  PUT /work-orders/:id/watchers
POST /work-orders/:id/time-entries  DELETE /work-orders/:id/time-entries/:tid
POST /work-orders/:id/cost-entries   DELETE /work-orders/:id/cost-entries/:cid
POST /work-orders/:id/dependencies   DELETE /work-orders/:id/dependencies/:did
GET|POST /:entity/:id/comments  PATCH|DELETE /comments/:id      (entity in work-orders|projects|assets)
GET|POST /:entity/:id/attachments  GET /attachments/:id/download  DELETE /attachments/:id
GET|POST /saved-filters  PATCH|DELETE /saved-filters/:id
GET /notifications  POST /notifications/read  GET /changes?since=
GET /reports/operations?range=  GET /search?q=
```

---

## Phase A – Backend foundation (sequential, one owner)

### Task A1: Ops column types and base mixin

**Files:** Create `asme/ops/__init__.py`, `asme/ops/types.py`; Test `tests/ops/test_types.py`, `tests/ops/__init__.py`, `tests/ops/conftest.py`.

**Interfaces – produces:** `UTCDateTime` (TypeDecorator: stores naive UTC, returns tz-aware UTC), `JSONDoc` (`JSON().with_variant(JSONB, "postgresql")`), `uuid_pk()`, `uuid_fk(target, **kw)`, `utcnow()`, `OpsBase` mixin with `id`, `organization_id` (FK `ops_organizations.id`, indexed), `created_at`, `updated_at` (onupdate), `created_by_user_id`, `updated_by_user_id`.

- [ ] Write `tests/ops/test_types.py::test_utc_datetime_roundtrip_is_aware` (store `utcnow()`, reload, assert `tzinfo is timezone.utc`) and `test_ops_base_defaults` (a throwaway model gets uuid id and timestamps).
- [ ] Run → fails (module missing).
- [ ] Implement `asme/ops/types.py`.
- [ ] Run → passes. Commit `feat(ops): column types and base mixin`.

### Task A2: Identity and tenancy models + permission registry

**Files:** Create `asme/ops/models/__init__.py`, `asme/ops/models/identity.py`, `asme/ops/permissions.py`; Test `tests/ops/test_permissions_registry.py`.

**Interfaces – produces:** models `Organization(ops_organizations: name, slug unique, timezone, academic_year_start_month, settings_json, setup_completed_at, logo_url)`, `Role(ops_roles: organization_id, name, system_key nullable, is_custom, description; unique(organization_id, system_key))`, `Permission(ops_permissions: key unique, description)`, `RolePermission(ops_role_permissions: role_id, permission_id, scope_type; unique(role_id, permission_id))`, `Membership(ops_memberships: organization_id, user_id Integer FK users.id, role_id, member_status active|invited|suspended, joined_at, title; unique(organization_id, user_id))`, `UserPreference(ops_user_preferences: organization_id, user_id, key, value_json; unique(organization_id,user_id,key))`, `Sequence(ops_sequences: organization_id, key, next_value; unique(organization_id,key))`. Registry: `PERMISSIONS: dict[str,str]`, `SCOPES = ("chapter","project","team","assigned","own")`, `SYSTEM_ROLES: list[dict(key,name,description)]`, `DEFAULT_GRANTS: dict[str, dict[str,str]]` (role key → {perm key → scope}), `LEGACY_ROLE_MAP = {"admin":"chapter_admin","team_leader":"team_lead","member":"full_member"}`, `is_read_key(key)`.

- [ ] Test: every grant key in `DEFAULT_GRANTS` exists in `PERMISSIONS`; every scope valid; `chapter_admin` has every key; `sponsor_guest` has only `report.view`.
- [ ] Run → fails. Implement. Run → passes. Commit `feat(ops): tenancy models and permission registry`.

### Task A3: Structure, project, work, shared models

**Files:** Create `asme/ops/models/structure.py`, `projects.py`, `work.py`, `shared.py`; extend `asme/ops/models/__init__.py`; Test `tests/ops/test_models_smoke.py`.

**Interfaces – produces:** tables listed in `docs/migration-plan.md` §2 with these key columns:

- `Team(ops_teams: name, description, parent_team_id, project_id, conversation_id nullable Uuid no-FK, is_active)`, `TeamMember(ops_team_members: team_id, user_id, is_lead; unique(team_id,user_id))`
- `Location(ops_locations: name, description, parent_location_id, building, room, address_json, is_default, is_active)`
- `Category(ops_categories: name, color, icon, description, is_active; unique(organization_id, name))`
- `AssetType(ops_asset_types: name, color, icon)`, `Asset(ops_assets: name, code, description, parent_asset_id, project_id, location_id, responsible_team_id, owner_user_id, manufacturer, model, serial_number, purchase_date, purchase_cost Numeric(12,2), warranty_end, criticality none|low|medium|high, status online|offline_planned|offline_unplanned|do_not_track|retired, qr_code, custom_fields_json, is_active)`, `AssetTypeLink`, `AssetStatusHistory(ops_asset_status_history: asset_id, from_status, to_status, downtime_type, downtime_reason, note, started_at, ended_at, changed_by_user_id)`
- `Vendor(ops_vendors: name, contact_name, email, phone, website, address_json, notes, is_active)`
- `Project(ops_projects: name, code unique per org, description, status planning|active|on_hold|completed|archived, visibility chapter|private, risk_level low|medium|high|critical, lead_user_id, faculty_advisor_user_id, start_date, target_date, budget_amount, repository_url, cad_url, requirements_url, competition, public_project_id Integer FK projects.id nullable, archived_at)`, `ProjectMember(ops_project_members: project_id, user_id, team_id, project_role lead|member|advisor|viewer; unique(project_id,user_id))`, `Milestone(ops_milestones: project_id, name, description, due_date, status planned|in_progress|done|missed, owner_user_id, weight, completed_at, order_index)`
- `WorkOrder(ops_work_orders: number Integer, title, description, status draft|open|in_progress|on_hold|done|canceled|skipped, priority none|low|medium|high|critical, work_type reactive|preventive|project|event|inspection|safety|procurement|documentation, project_id, location_id, primary_asset_id, team_id, vendor_id, parent_work_order_id, source_request_id Uuid nullable no-FK, maintenance_plan_id Uuid nullable no-FK, start_at, due_at, completed_at, canceled_at, estimated_minutes, actual_minutes default 0, recurrence_json, completion_note, is_blocked, budget_code, parent_completion_policy manual|auto; unique(organization_id, number))` with properties `assignee_user_ids`, `assignee_team_ids`, `is_overdue`; `WorkOrderAssignee(user_id nullable, team_id nullable)`, `WorkOrderCategory`, `WorkOrderAsset(relationship_type primary|related)`, `WorkOrderWatcher(user_id)`, `WorkOrderStatusHistory(from_status,to_status,changed_by_user_id,note,changed_at)`, `WorkOrderDependency(blocking_work_order_id, blocked_work_order_id, dependency_type finish_to_start)`, `TimeEntry(work_order_id,user_id,started_at,ended_at,minutes,note)`, `CostEntry(work_order_id,type parts|labor|vendor|other,amount Numeric(12,2),vendor_id,description)`
- `Comment(ops_comments: entity_type, entity_id Uuid, author_user_id, body, parent_comment_id, edited_at, deleted_at)`, `Attachment(ops_attachments: entity_type, entity_id, storage_key, original_name, content_type, size_bytes, uploaded_by_user_id, checksum_sha256)`, `AuditEvent(ops_audit_events: actor_user_id, event_type, entity_type, entity_id, summary, before_json, after_json, metadata_json, occurred_at; no updated_at)`, `SavedFilter(ops_saved_filters: entity_type, owner_user_id, name, visibility private|team|chapter, team_id, filter_json, sort_json, view_type, is_default)`, `Notification(ops_notifications: user_id, type, title, body, entity_type, entity_id, read_at)`

- [ ] Test: `db.create_all()` succeeds; creating org → location → asset → work order with assignee round-trips; `WorkOrder.assignee_user_ids` returns ids.
- [ ] Implement. Run → passes. Commit `feat(ops): structure, project, work and shared models`.

### Task A4: Migration `0003_ops_foundation`

**Files:** Create `migrations/versions/0003_ops_foundation.py`; Test `tests/ops/test_migration.py`.

**Interfaces:** revision `0003_ops_foundation`, down_revision `0002_launchpad`. Creates every `ops_*` table from A2/A3 (hand-written `op.create_table`, not autogenerate output pasted blindly) and `op.add_column("outbox_jobs", sa.Column("idempotency_key", sa.String(160), nullable=True))` + unique constraint `uq_outbox_jobs_idempotency_key` in batch mode. `downgrade()` reverses in dependency order.

- [ ] Test: build a temp SQLite file DB, run `flask_migrate.upgrade()` to head, assert `alembic_version == "0003_ops_foundation"`, assert all `ops_*` tables exist and `outbox_jobs.idempotency_key` column exists; run `downgrade("0002_launchpad")` and assert they are gone and legacy tables intact.
- [ ] Also assert models and migration agree: `alembic.autogenerate.compare_metadata(ctx, db.metadata)` returns no diff for `ops_*` tables after upgrade.
- [ ] Implement. Run → passes. Commit `feat(ops): migration 0003_ops_foundation`.

### Task A5: Bootstrap, numbering, policy, validation, audit events

**Files:** Create `asme/ops/bootstrap.py`, `asme/ops/numbering.py`, `asme/ops/policy.py`, `asme/ops/validation.py`, `asme/ops/services/__init__.py`, `asme/ops/services/audit_events.py`; Modify `asme/services/bootstrap.py` (`seed_defaults` calls `ops_bootstrap.ensure_default_organization(commit=False)`), `asme/auth/session.py::sign_in_user` (calls `ensure_membership(user)` after login), `asme/events/__init__.py` (add `WORK_ORDER_CREATED`, `WORK_ORDER_STATUS_CHANGED`, `PROJECT_CREATED`, `MEMBERSHIP_CREATED`, `ASSET_STATUS_CHANGED` to the list and `ALL_EVENTS`); Test `tests/ops/test_policy.py`, `tests/ops/test_bootstrap.py`, `tests/ops/test_numbering.py`, `tests/ops/test_validation.py`.

**Interfaces – produces:**

```python
# bootstrap.py
DEFAULT_ORG_SLUG = "uiowa"
def ensure_default_organization(commit=True) -> Organization   # org, roles+grants, memberships, General location, seed categories, sequence
def ensure_membership(user, org=None) -> Membership              # idempotent; role from LEGACY_ROLE_MAP; never downgrades
def sync_role_grants(org) -> int                                  # adds missing default grants to system roles (never removes custom ones)
# numbering.py
def next_number(org_id, key: str) -> int                          # UPDATE ... RETURNING on postgres, select+update on sqlite; row created on demand
# policy.py
@dataclass class PolicyContext: user, org, membership, role, grants: dict[str,set[str]], project_ids:set, private_project_ids:set, team_ids:set, lead_team_ids:set
    def has(self, key) -> bool; def scopes(self, key) -> set[str]
def load_context(user, org=None) -> PolicyContext | None
def current_context() -> PolicyContext                            # cached on flask.g; raises Forbidden("no_membership") if absent
def can(ctx, key, obj=None) -> bool
def authorize(ctx, key, obj=None) -> None                         # raises Forbidden
def require_permission(*keys, any_of=False)                       # route decorator: login → membership → key present (any scope)
def visible_project_filter(ctx, column)                           # SQLAlchemy criterion for project visibility
# validation.py
class ValidationErrors(ServiceError): code="validation", status=400, extra={"errors": {...}}
def validate(payload: dict, spec: dict[str, Field]) -> dict       # Field(kind, required, max_len, choices, nullable, coerce)
# services/audit_events.py
def record(ctx, event_type: str, entity, *, before=None, after=None, summary="", **metadata) -> AuditEvent
def snapshot(entity, fields: tuple[str, ...]) -> dict
def list_for_entity(ctx, entity_type, entity_id, limit=100) -> list[AuditEvent]
def recent(ctx, since=None, limit=100) -> list[AuditEvent]
```

- [ ] Tests (write first): `test_ensure_default_org_is_idempotent`, `test_legacy_roles_map_to_ops_roles`, `test_membership_never_downgraded`, `test_next_number_is_sequential_and_per_org`, `test_can_chapter_scope`, `test_can_team_scope_requires_lead_for_manage`, `test_can_assigned_scope`, `test_can_own_scope`, `test_private_project_hidden_from_non_member`, `test_require_permission_denies_without_membership_with_403_no_membership`, `test_validate_reports_all_field_errors`.
- [ ] Implement. Run full suite. Commit `feat(ops): bootstrap, numbering, policy and audit events`.

### Task A6: Ops API skeleton, session/auth, organization, storage

**Files:** Create `asme/blueprints/ops/__init__.py` (bp `ops_api`, url_prefix `/api/v1`, errorhandlers for `ServiceError`/`ValidationErrors`/404/405/413, JSON-content-type guard, helpers `json_body()`, `paginate(query, order_columns, cursor, limit)`, `encode_cursor/decode_cursor`, `parse_filters(allowlist)`), `asme/blueprints/ops/session.py` (`GET /session`), `asme/blueprints/ops/auth.py` (`POST /auth/login` JSON with rate limiter, `POST /auth/logout`), `asme/blueprints/ops/organization.py` (`GET|PATCH /organization`), `asme/ops/storage.py` (`StorageAdapter` protocol, `LocalStorage(root)`, `get_storage()`, `sign_download(attachment_id, expires_in)`, `verify_download(token)`), `asme/blueprints/ops_app.py` (`/app`, `/app/<path:path>` → `static/ops/index.html` or a 503 "frontend not built" page in dev), `asme/ops/serializers.py` (`user_ref`, `organization`, `session_payload`); Modify `asme/blueprints/__init__.py` to register `ops_api` and `ops_app`; `asme/config.py` add `storage_backend`, `upload_root`, `upload_max_bytes` (default 25 MB), `ops_changes_poll_seconds`; `.env.example` documents them; Test `tests/ops/test_api_skeleton.py`, `tests/ops/test_storage.py`.

**Interfaces – produces:** `session_payload(ctx) → {"user": user_ref+role, "organization": {...}, "membership": {"role": {...}, "status"}, "permissions": {key: [scopes]}, "setup": {"banner_dismissed": bool, "completed": bool}, "features": {"realtime": "polling", "poll_seconds": 15}}`.

- [ ] Tests: login JSON success/failure/rate-limit shape; `/session` 401 anonymous, 200 with permissions for admin; POST without JSON content type → 415 `code="json_required"`; `/app` serves index when built, 503 otherwise; local storage put/open/delete and signed URL expiry.
- [ ] Implement. Run. Commit `feat(ops): api skeleton, json auth, session and storage`.

## Phase B – Backend verticals (parallel, one owner per task, no shared files besides `tests/ops/conftest.py` fixtures which Phase A provides: `org`, `ctx_admin`, `ctx_lead`, `ctx_member`, `ctx_requester`, `api_login(client, user)`)

Each task: service module + blueprint module + serializers additions in its **own** section of `asme/ops/serializers.py` (append-only functions) + tests. Register the blueprint module by adding one import line to `asme/blueprints/ops/__init__.py::register_routes()` (append-only list).

### Task B1: Locations and categories
`asme/ops/services/locations.py`, `categories.py`; `asme/blueprints/ops/locations.py`, `categories.py`; tests `tests/ops/test_locations_api.py`, `test_categories_api.py`.
Rules: default `General` cannot be deleted or de-defaulted; deleting a location with assets/work orders → 409 `location_in_use`; nested path computed; category name unique per org; deleting a category in use → 409. Audit `location.created|updated|deleted`, `category.*`. Permissions `location.read/manage`, `category.read/manage`.

### Task B2: Teams, users, roles
`asme/ops/services/teams.py`, `users.py`; `asme/blueprints/ops/teams.py`, `users.py`; tests.
Rules: `PUT /teams/:id/members` body `{"members":[{"user_id":1,"is_lead":true}]}` replaces membership; team lead can manage own team only; `POST /users/invite` `{email,name,role_key}` creates an inactive legacy `User` (random password hash) + membership `invited` and returns an invite token via existing `identity.admin_invite_link_token`; `PATCH /users/:id` changes ops role/status only with `user.manage`, never touches legacy `users.role` except when promoting to `chapter_admin` (also sets legacy `admin`) – documented; `GET /roles` lists roles with grant counts. Audit `team.*`, `membership.role_changed`, `membership.invited`.

### Task B3: Assets, asset types, vendors
`asme/ops/services/assets.py`, `vendors.py`; blueprints; tests.
Rules: parent cycle rejected (`asset_cycle`); status change writes `AssetStatusHistory` (closes previous open row) and audit `asset.status_changed`, emits `ASSET_STATUS_CHANGED`; `GET /assets?view=hierarchy` returns roots with `children` nested; history endpoint merges status history + audit events + work orders touching the asset.

### Task B4: Projects and milestones
`asme/ops/services/projects.py`, `milestones.py`; blueprints; tests.
Rules: code auto-generated from name initials if absent, unique per org; visibility enforcement via `visible_project_filter`; `PUT /projects/:id/members` upserts `ops_project_members` and, when `public_project_id` set, upserts legacy `ProjectMembership` and emits `TEAM_JOINED`; `GET /projects/:id/health` returns `{completion_percent (done/total non-canceled WOs weighted), open, overdue, on_hold, blocked, milestones: {total, done, missed, next}, budget: {amount, used(cost entries), remaining}, members, activity_7d}`; archive/restore audit. Milestone status auto `missed` when `due_date < today` and not done (computed on read, persisted by the nightly scan job in B6).

### Task B5: Work orders (core)
`asme/ops/services/work_orders.py`, `asme/blueprints/ops/work_orders.py`, `tests/ops/test_work_orders_api.py`, `tests/ops/test_work_order_transitions.py`, `tests/ops/test_work_order_authz.py`.
Rules:
- `create(ctx, data)`: number from `next_number`, status `open` (or `draft` when `data["draft"]`), validates project visibility, location/asset/team/vendor belong to org, categories exist; assignees/watchers lists; writes status history `None→open`, audit `work_order.created`, notifications to assignees, emits `WORK_ORDER_CREATED`.
- Transitions table: `open→in_progress (start)`, `in_progress→on_hold (hold)`, `on_hold→in_progress (resume)`, `open|in_progress→done (complete)`, `open|in_progress|on_hold→canceled (cancel)`, `done|canceled→open (reopen, requires work_order.edit)`; `draft→open` via PATCH `{"status":"open"}`; invalid → 409 `invalid_transition`. `complete(ctx, wo, note, time_entries=[], cost_entries=[], asset_status=None)` writes entries, sets `completed_at`, updates `actual_minutes`, applies asset status via B3 service, auto-completes parent when policy `auto` and all children done. Every transition: status history + audit + notify assignees/watchers/creator + emit `WORK_ORDER_STATUS_CHANGED`.
- List filters allowlist: `status, priority, work_type, project, location, asset, team, assignee, category, due (overdue|today|week|month|none), created_by, parent, q, tab (todo|done)`; sorts: `priority, -priority, due_at, -due_at, -updated_at, created_at, number`; `tab=todo` = status in (open,in_progress,on_hold,draft); `tab=done` = (done,canceled,skipped). Visibility: `work_order.read_all` → all in visible projects; `work_order.read_assigned` only → assigned or watching or created.
- Sub work orders: `POST /:id/sub-work-orders` creates child with `parent_work_order_id`; parent serializer aggregates counts/time/cost.
- Dependencies: `is_blocked` recomputed = any blocking WO not done/canceled.
- Duplicate copies fields, categories, assignees; new number; status open.

### Task B6: Time, cost, notifications, changes feed, outbox jobs
`asme/ops/services/notifications.py`, `changes.py`; `asme/jobs/handlers.py` additions `ops.notify.digest` (no-op placeholder is NOT allowed – implement in-app fan-out) and `ops.work_order.scan` (recurring hourly via `ensure_recurring`: flags overdue WOs once by writing a notification with idempotency key `overdue:<wo_id>:<due date>` and marks milestones missed); `asme/jobs/outbox.py` add `enqueue_once(kind, key, payload, run_at=None)`; blueprints `notifications.py`, `changes.py`; tests `tests/ops/test_notifications.py`, `test_changes_feed.py`, `test_outbox_idempotency.py`.
`GET /changes?since=<iso>` → `{"events":[audit_event minimal],"now":iso}` limited to entities the user may read (work orders through visibility filter; others chapter-wide).

### Task B7: Comments and attachments
`asme/ops/services/comments.py`, `attachments.py`; blueprints; tests including an upload of a PNG and rejection of an `.exe`/oversized file; mentions parsed from `@[Name](user:12)` create notifications; comment edit/delete only by author or `work_order.edit` holder; attachments validated by extension + declared type + magic bytes (png/jpg/gif/webp/pdf/txt/csv/stl/step/gcode/3mf/zip ≤ 25 MB); downloads via signed URL (`expires_in=300s`).

### Task B8: Saved filters, search, setup center, operations report
`asme/ops/services/saved_filters.py`, `search.py`, `setup_center.py`, `dashboard.py`; blueprints `saved_filters.py`, `search.py`, `setup.py`, `reports.py`; tests.
Setup center progress derived exactly as spec §8: profile (org timezone set + `settings_json.profile_completed`), locations (≥1 non-default), assets (≥5), teams_users (≥1 team and ≥3 active memberships), project (≥1), categories (≥1), parts/procedure/plan/portal/automation/dashboard → `available: false, stage: N`. Percent = completed / available tasks. Banner dismissed per user via `UserPreference("setup_banner_dismissed")`.
Operations report (`range` = 7d|30d|90d|semester|custom start,end): `created_vs_completed` weekly buckets, `by_work_type`, `repeating_vs_non` (recurrence_json null?), `status_distribution`, `priority_distribution`, `on_time_completion_rate` (done with `completed_at <= due_at` / done with due), `overdue_open`, `avg_completion_hours`, `workload_by_team`, `workload_by_user`, `hours_logged`, `parts_cost` (cost type parts), `other_cost`. Every formula documented in `docs/reporting-metrics.md` by this task.

### Task B9: Seed data
`asme/ops/seeds.py` + `manage.py seed-ops [--reset-ops]` (refuses in production). Dataset: org; users for admin, exec, project lead, 3 team leads, 6 members, safety officer, inventory manager, treasurer, faculty advisor, requester (password printed, `ASME_DEFAULT_USER_PASSWORD`); teams (Executive Board, Wheels and Mobility, Robotic Arm, Electrical, Software and Autonomy, Fabrication, Events and Outreach, Inventory and Procurement); locations (General, Engineering Student Center › Robotics Lab, Machine Shop, Electronics Bench, ASME Storage, Test Field, Trailer); categories (14); asset types; assets hierarchy (Crater Cruncher Rover › Chassis, Mobility System › 4 wheel modules, Robotic Arm › Shoulder/Elbow/End Effector, Electrical System, Compute and Control; 3D Printer 01/02, Soldering Station 01, Battery Charger 01, Oscilloscope, Power Supply, Tool Kit A); vendors (McMaster-Carr, DigiKey, Amazon Business); projects (Crater Cruncher Rover linked to legacy `rover`, General Chapter Operations, Fall Engineering Showcase private) with milestones; ~40 work orders across statuses (open, in progress, on hold, overdue, done, canceled, draft, critical safety, with sub-work orders, dependencies, time and cost entries, comments); notifications; audit trail produced naturally by calling services (not raw inserts). Idempotent by `code`/`number`. Test `tests/ops/test_seeds.py` runs the seed on the test DB and asserts counts and that every work order has a status-history row.

## Phase C – Frontend foundation (sequential)

### Task C1: Vite app, Flask serving, tokens, API client, session, router, shell
Files: `apps/ops-web/{vite.config.ts,tsconfig.json,tsconfig.app.json,tsconfig.node.json,index.html,eslint.config.js,vitest.config.ts,src/main.tsx,src/vite-env.d.ts}`, `src/ui/tokens.css`, `src/ui/global.css`, `src/api/client.ts`, `src/api/contracts/common.ts`, `src/api/contracts/session.ts`, `src/api/queries/session.ts`, `src/app/{routes.tsx,AppShell.tsx,Sidebar.tsx,SidebarNav.ts,SetupBanner.tsx,PageHeader.tsx,ErrorBoundary.tsx,RequireSession.tsx,LoginPage.tsx,NotFound.tsx}`, `src/lib/{cn.ts,dates.ts,permissions.ts}`, tests `src/api/client.test.ts`, `src/app/Sidebar.test.tsx`.
Contracts: `api.get/post/patch/put/delete<T>(path, {params?, body?, signal?})` unwrapping `payload`, throwing `ApiError {status, code, message, errors}`; `useSession()`; `can(key)`; routes list from spec §5 (every route registered; unbuilt ones render `ComingSoon` with stage label – this is navigation, not a decorative action); sidebar groups SETUP/WORK/OPTIMIZE/MANAGE with nested Reporting/Library; collapse to 64 px; overlay drawer < 900 px.

### Task C2: UI primitives
`src/ui/{Button,IconButton,SplitButton,SearchField,FilterChip,FilterPopover,SavedViewSelector,Tabs,SegmentedControl,MasterDetailLayout,DataTable,ListRow,DetailPanel,SideSheet,FormField,Input,Textarea,Select,Combobox,DatePicker,StatusBadge,PriorityBadge,EmptyState,Skeleton,ProgressIndicator,Toast,InlineAlert,Dialog,Popover,DropdownMenu,ContextMenu,Tooltip,ActivityTimeline,CommentComposer,AttachmentUploader,Pagination,ReportCard,ChartFrame}.tsx` + `index.ts`, each with a Vitest render/keyboard test for the interactive ones (Dialog focus trap + Escape, DropdownMenu arrow keys, Tabs roving focus, Combobox typeahead). Reduced motion respected via `prefers-reduced-motion` media query in `tokens.css`.

### Task C3: Reference screen – Locations (list/detail + create pane)
`src/features/locations/{LocationsPage,LocationList,LocationDetail,LocationForm}.tsx`, `src/api/contracts/locations.ts`, `src/api/queries/locations.ts`; e2e `apps/ops-web/e2e/locations.spec.ts`. Demonstrates every required state and the exact pattern other screens copy: header + search + split button, list with skeleton/empty/no-results/error+retry, deep-link `/app/locations/:id`, right pane create/edit with sticky footer and server validation mapping, toast on success, optimistic list update, delete with confirm dialog and 409 handling.

## Phase D – Frontend screens (parallel, one owner per task, each owns only its `src/features/<name>` folder + its `src/api/contracts/<name>.ts` + `src/api/queries/<name>.ts` + `e2e/<name>.spec.ts`)

- **D1 Setup Center** (`/app/setup`): phase cards, progress panel, banner dismiss/reopen, links to each task's screen.
- **D2 Teams / Users** (`/app/teams-users`): tabs; team list/detail with member editor; user list with role/status editing (permission-gated), invite dialog showing the invite link once.
- **D3 Categories** (`/app/categories`): split layout per spec §19 with colour/icon picker and "Use in New Work Order" navigation.
- **D4 Assets** (`/app/assets`, `/app/assets/:id`): Panel/Table/Hierarchy views, filters, create/edit pane, status change dialog with downtime reason, history timeline.
- **D5 Projects** (`/app/projects`, `/app/projects/:id/<tab>`): view selector, filters, 42/58 split, overview cards from `/health`, Work tab reusing the work-order list component with fixed project filter, Milestones editor, Teams tab (members editor), Assets tab, Documents tab (attachments), Budget tab (budget vs cost entries), Activity tab (audit).
- **D6 Work Orders** (`/app/work-orders`, `/new`, `/:id`, `/:id/edit`): header with view selector (Panel, Table; Calendar and Workload deferred and not rendered), search, split button (New Work Order / New Sub-Work Order from selection / Duplicate), filter chips (Assigned To, Due Date, Project, Location, Priority, Team, Asset, Work Type, Status, Category, Add Filter, My Filters with save/rename/share/delete), To Do / Done tabs with counts, sort menu, panel list rows (number, title, priority, due, assignees, project, status), table view (TanStack Table), create pane in spec field order (fields whose modules exist), detail with header actions by status, cards (description + pictures, project/location/asset/team/assignees, schedule, time and cost, sub-work orders, comments, files, activity), completion dialog (note, time entries, costs, asset status, follow-up), cancel dialog, dependency picker, watchers editor, keyboard shortcuts (`n` new, `/` search, `j/k` move selection, `Esc` close pane).
- **D7 Operations dashboard** (`/app/reporting/operations`): date range presets, two-column report cards with chart frame (SVG bars/lines drawn in-house, no chart library) and text summary + data table alternative for accessibility, drill-down links into filtered work-order lists.
- **D8 Notifications, global search, profile** (`/app/settings/profile`, header bell, `Ctrl/Cmd+K` palette searching work orders/projects/assets/users/locations).
- **D9 Playwright suite**: `e2e/{auth,setup,projects,work-orders,authz,screens}.spec.ts` implementing scenarios 1–6 and 11–12 from the build prompt against `python manage.py seed-ops` data, plus screenshot snapshots at the four viewports for Setup Center, Projects, Work Orders (panel + create pane + detail), Categories and Operations dashboard, and axe accessibility checks on each.

## Phase E – Hardening and documentation

- **E1 Authorization audit**: adversarial tests attempting ID tampering across organizations (second org fixture), cross-role actions (requester creating work orders, member editing another's WO, team lead assigning outside own team, member reading a private project, sponsor listing users), CSRF (form-encoded POST → 415), and signed URL expiry.
- **E2 Docs**: `docs/permissions-matrix.md` (generated from the registry by `manage.py permissions-matrix`), `docs/api.md`, `docs/reporting-metrics.md`, `docs/test-plan.md`, `docs/deployment.md` (build SPA in CI, EB/Render commands, backup/restore), `CHANGELOG.md`, update `docs/implementation-status.md` and `docs/migration-plan.md`, README section "ASME Ops".
- **E3 Final gates**: `pytest`, `npm run typecheck`, `npm run lint`, `npm test`, `npm run build`, `npm run test:e2e`; record results in `docs/implementation-status.md`.

## Self-review notes

- Spec coverage for Stage 1–2 checked against build-prompt §10 (Stage 1 and Stage 2 bullets) and product spec §7–10, §19–21, §25.1, §36–37: all items map to a task above; parts/procedures/recurrence on work orders are explicitly deferred with tracking (Stage 4/5).
- Placeholder scan: none of the tasks depend on undefined functions; every route in the API surface list belongs to exactly one B task.
- Type consistency: `PolicyContext`, serializer names and permission keys are defined once in the shared-contracts section and referenced verbatim.
