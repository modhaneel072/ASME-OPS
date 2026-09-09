"""Assets service (``ops_assets``, ``ops_asset_types``, ``ops_asset_status_history``).

``change_status`` is the cross-slice contract: work-order completion calls it
with ``commit=False`` inside its own transaction; its signature and behaviour
are stable. Everything else here backs ``/api/v1/assets`` and ``/api/v1/asset-types``.

Visibility: an asset that belongs to a private project is hidden unless the
user may read that project (``policy.visible_project_filter`` on every list,
``can_read_asset`` on single lookups, which answer 404 rather than 403 so the
existence of a private project's equipment is never confirmed).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from types import SimpleNamespace
from uuid import UUID

from sqlalchemy import case, func, or_, select

from asme.extensions import db
from asme.ops import policy
from asme.ops.models import (
    Asset,
    AssetStatusHistory,
    AssetType,
    AssetTypeLink,
    Location,
    Membership,
    OpsProject,
    Team,
    WorkOrder,
    WorkOrderAsset,
)
from asme.ops.models.structure import ASSET_CRITICALITIES, ASSET_STATUSES, DOWNTIME_TYPES
from asme.ops.models.work import OPEN_STATUSES
from asme.ops.serializers.assets import ASSET_SNAPSHOT_FIELDS
from asme.ops.services import audit_events, notifications, work_orders
from asme.ops.types import parse_uuid, utcnow
from asme.ops.validation import Field, ValidationErrors, validate
from asme.services.errors import Forbidden, NotFound, Validation

OFFLINE_STATUSES = ("offline_planned", "offline_unplanned")

SORTS = ("name", "status", "criticality", "created_at", "updated_at")
DEFAULT_SORT = "name"
FILTERS = {
    "status": "multi",
    "criticality": "multi",
    "type": "multi",
    "project": "multi",
    "location": "multi",
    "team": "multi",
    "parent": "single",
    "active": "single",
}
HIERARCHY_FILTERS = ("project", "location")
SEARCH_COLUMNS = (Asset.name, Asset.code, Asset.serial_number, Asset.manufacturer, Asset.model)
DEFAULT_HISTORY_LIMIT = 100
MAX_HISTORY_LIMIT = 500
_TIMELINE_KIND_RANK = {"audit": 0, "status": 1, "work_order": 2}


def _object_only(value) -> str | None:
    return None if isinstance(value, dict) else "Must be an object."


ASSET_SPEC = {
    "name": Field("str", required=True, nullable=False, max_len=200, min_len=1),
    "code": Field("str", max_len=60),
    "description": Field("text"),
    "parent_id": Field("uuid"),
    "project_id": Field("uuid"),
    "location_id": Field("uuid"),
    "responsible_team_id": Field("uuid"),
    "owner_user_id": Field("int", minimum=1),
    "manufacturer": Field("str", max_len=160),
    "model": Field("str", max_len=160),
    "serial_number": Field("str", max_len=160),
    "purchase_date": Field("date"),
    "purchase_cost": Field("decimal", minimum=0),
    "warranty_end": Field("date"),
    "criticality": Field("choice", choices=ASSET_CRITICALITIES, nullable=False, default="none"),
    "status": Field("choice", choices=ASSET_STATUSES, nullable=False, default="online"),
    "qr_code": Field("str", max_len=160),
    "custom_fields": Field("json", check=_object_only),
    "type_ids": Field("list", item=Field("uuid"), max_len=50),
    "is_active": Field("bool", nullable=False),
}
UPDATE_SPEC = {name: spec for name, spec in ASSET_SPEC.items() if name != "status"}
STATUS_NOT_EDITABLE = "Use the status endpoint."

STATUS_SPEC = {
    "status": Field("choice", choices=ASSET_STATUSES, required=True, nullable=False),
    "downtime_type": Field("choice", choices=DOWNTIME_TYPES),
    "downtime_reason": Field("str", max_len=160),
    "note": Field("text"),
}

ASSET_TYPE_SPEC = {
    "name": Field("str", required=True, nullable=False, max_len=120, min_len=1),
    "color": Field("color", nullable=False, default="#475569"),
    "icon": Field("str", nullable=False, max_len=60, default="box"),
}

# payload key -> column; keys missing here map to a column of the same name
_COLUMN_FOR = {"parent_id": "parent_asset_id", "custom_fields": "custom_fields_json"}
_SIMPLE_KEYS = (
    "name",
    "code",
    "description",
    "parent_id",
    "project_id",
    "location_id",
    "responsible_team_id",
    "owner_user_id",
    "manufacturer",
    "model",
    "serial_number",
    "purchase_date",
    "purchase_cost",
    "warranty_end",
    "criticality",
    "qr_code",
    "custom_fields",
    "is_active",
)


# --------------------------------------------------------------------------- status (cross-slice contract)


def change_status(
    ctx,
    asset: Asset,
    status: str,
    *,
    downtime_type: str | None = None,
    downtime_reason: str | None = None,
    note: str | None = None,
    work_order=None,
    commit: bool = True,
) -> AssetStatusHistory:
    """Move ``asset`` to ``status``, closing the previous history row, writing a
    new one plus an audit event, and notifying the responsible people when the
    asset goes offline. Emits ``ASSET_STATUS_CHANGED`` after commit (only when
    ``commit`` is true; callers that pass ``commit=False`` emit themselves)."""
    from asme import events

    if asset.organization_id != ctx.org.id:
        raise NotFound()
    if not policy.can(ctx, "asset.manage", asset):
        policy.authorize(ctx, "asset.status.update", asset)
    errors: dict[str, str] = {}
    if status not in ASSET_STATUSES:
        errors["status"] = "Choose one of: " + ", ".join(ASSET_STATUSES) + "."
    if status in OFFLINE_STATUSES:
        downtime_type = downtime_type or ("planned" if status == "offline_planned" else "unplanned")
        if downtime_type not in DOWNTIME_TYPES:
            errors["downtime_type"] = "Choose planned or unplanned."
    else:
        downtime_type = None
    if errors:
        raise ValidationErrors(errors)

    now = utcnow()
    previous = asset.status
    open_rows = AssetStatusHistory.query.filter_by(asset_id=asset.id).filter(AssetStatusHistory.ended_at.is_(None)).all()
    for row in open_rows:
        row.ended_at = now
    history = AssetStatusHistory(
        organization_id=ctx.org.id,
        asset_id=asset.id,
        from_status=previous,
        to_status=status,
        downtime_type=downtime_type,
        downtime_reason=(downtime_reason or "").strip()[:160] or None,
        note=(note or "").strip() or None,
        started_at=now,
        changed_by_user_id=getattr(ctx, "user_id", None),
        work_order_id=getattr(work_order, "id", None),
    )
    db.session.add(history)
    asset.status = status
    asset.updated_by_user_id = getattr(ctx, "user_id", None)
    audit_events.record(
        ctx,
        "asset.status_changed",
        asset,
        before={"status": previous},
        after={"status": status, "downtime_type": downtime_type, "downtime_reason": history.downtime_reason},
        summary=f"{asset.name}: {previous} -> {status}",
        work_order_id=str(work_order.id) if work_order is not None else None,
    )
    if status in OFFLINE_STATUSES and previous not in OFFLINE_STATUSES:
        recipients: set[int] = set()
        if asset.owner_user_id:
            recipients.add(asset.owner_user_id)
        if asset.responsible_team is not None:
            recipients |= asset.responsible_team.lead_user_ids
        if asset.project is not None and asset.project.lead_user_id:
            recipients.add(asset.project.lead_user_id)
        notifications.notify(
            ctx,
            recipients,
            "asset.offline",
            f"{asset.name} is offline ({downtime_type})",
            history.downtime_reason or note,
            entity=asset,
            dedupe_key=f"asset_offline:{asset.id}:{now.date().isoformat()}",
        )
    if commit:
        db.session.commit()
        events.emit(events.ASSET_STATUS_CHANGED, asset_id=str(asset.id), organization_id=str(ctx.org.id), status=status, previous=previous)
    return history


def change_status_from_payload(ctx, asset: Asset, payload: dict) -> AssetStatusHistory:
    """``POST /assets/:id/status`` body -> ``change_status``."""
    data = validate(payload, STATUS_SPEC)
    return change_status(
        ctx,
        asset,
        data["status"],
        downtime_type=data.get("downtime_type"),
        downtime_reason=data.get("downtime_reason"),
        note=data.get("note"),
    )


# --------------------------------------------------------------------------- reads


def visible_assets_query(ctx):
    """Assets in ``ctx.org`` whose project (if any) the user may read."""
    return Asset.query.filter(Asset.organization_id == ctx.org.id, policy.visible_project_filter(ctx, Asset.project_id))


def can_read_asset(ctx, asset: Asset) -> bool:
    if asset.organization_id != ctx.org.id or not ctx.has("asset.read"):
        return False
    if asset.project is not None and not policy.can_read_project(ctx, asset.project):
        return False
    return True


def get(ctx, asset_id) -> Asset:
    """Load one asset the user may read; anything else (foreign organization,
    hidden project, malformed id) is 404."""
    policy.authorize(ctx, "asset.read")
    parsed = parse_uuid(asset_id)
    if parsed is None:
        raise NotFound()
    asset = policy.get_or_404(ctx, Asset, parsed)
    if not can_read_asset(ctx, asset):
        raise NotFound()
    return asset


def _uuid_values(values: list[str], name: str) -> list[UUID]:
    parsed = []
    for raw in values:
        value = parse_uuid(raw)
        if value is None:
            raise Validation(f"filter[{name}] must contain identifiers.", field=name, code="bad_filter")
        parsed.append(value)
    return parsed


def _choice_values(values: list[str], name: str, choices: tuple[str, ...]) -> list[str]:
    cleaned = [value.strip().lower() for value in values]
    bad = [value for value in cleaned if value not in choices]
    if bad:
        raise Validation(f"filter[{name}] accepts: " + ", ".join(choices) + ".", field=name, code="bad_filter")
    return cleaned


def _parse_active(values: list[str] | None, *, default: bool | None) -> bool | None:
    if not values:
        return default
    raw = values[0].strip().lower()
    if raw in {"true", "1", "yes"}:
        return True
    if raw in {"false", "0", "no"}:
        return False
    if raw == "all":
        return None
    raise Validation("filter[active] must be true, false or all.", field="active", code="bad_filter")


def _apply_scope_filters(query, filters: dict[str, list[str]]):
    if filters.get("project"):
        query = query.filter(Asset.project_id.in_(_uuid_values(filters["project"], "project")))
    if filters.get("location"):
        query = query.filter(Asset.location_id.in_(_uuid_values(filters["location"], "location")))
    return query


def _ordered(query, sort: str):
    descending = sort.startswith("-")
    key = sort[1:] if descending else sort
    if key not in SORTS:
        raise Validation(f"Unknown sort '{sort}'.", field="sort", code="bad_sort")
    if key == "name":
        column = func.lower(Asset.name)
    elif key == "status":
        column = case({status: index for index, status in enumerate(ASSET_STATUSES)}, value=Asset.status, else_=len(ASSET_STATUSES))
    elif key == "criticality":
        column = case(
            {level: index for index, level in enumerate(ASSET_CRITICALITIES)}, value=Asset.criticality, else_=len(ASSET_CRITICALITIES)
        )
    elif key == "created_at":
        column = Asset.created_at
    else:
        column = Asset.updated_at
    primary = column.desc() if descending else column.asc()
    return query.order_by(primary, func.lower(Asset.name).asc(), Asset.id.asc())


def list_query(ctx, *, q: str = "", filters: dict[str, list[str]] | None = None, sort: str = DEFAULT_SORT):
    """Filtered, ordered query of visible assets. The route paginates it."""
    policy.authorize(ctx, "asset.read")
    filters = filters or {}
    query = visible_assets_query(ctx)
    if q:
        needle = f"%{q.lower()}%"
        query = query.filter(or_(*(func.lower(func.coalesce(column, "")).like(needle) for column in SEARCH_COLUMNS)))
    if filters.get("status"):
        query = query.filter(Asset.status.in_(_choice_values(filters["status"], "status", ASSET_STATUSES)))
    if filters.get("criticality"):
        query = query.filter(Asset.criticality.in_(_choice_values(filters["criticality"], "criticality", ASSET_CRITICALITIES)))
    if filters.get("type"):
        type_ids = _uuid_values(filters["type"], "type")
        query = query.filter(Asset.id.in_(select(AssetTypeLink.asset_id).where(AssetTypeLink.asset_type_id.in_(type_ids))))
    query = _apply_scope_filters(query, filters)
    if filters.get("team"):
        query = query.filter(Asset.responsible_team_id.in_(_uuid_values(filters["team"], "team")))
    if filters.get("parent"):
        raw = filters["parent"][0]
        if raw.strip().lower() == "root":
            query = query.filter(Asset.parent_asset_id.is_(None))
        else:
            query = query.filter(Asset.parent_asset_id == _uuid_values([raw], "parent")[0])
    active = _parse_active(filters.get("active"), default=True)
    if active is not None:
        query = query.filter(Asset.is_active.is_(active))
    return _ordered(query, sort)


def counts_for(ctx, assets: list[Asset]) -> dict[UUID, dict[str, int]]:
    """``{asset_id: {"child_count", "open_work_order_count"}}`` for a page of
    assets. Children are active assets; open work orders are those in an open
    status that name the asset as primary or through an ``ops_work_order_assets``
    link, restricted to projects the user may read."""
    ids = [asset.id for asset in assets]
    result = {asset_id: {"child_count": 0, "open_work_order_count": 0} for asset_id in ids}
    if not ids:
        return result
    child_rows = db.session.execute(
        select(Asset.parent_asset_id, func.count(Asset.id))
        .where(Asset.parent_asset_id.in_(ids), Asset.is_active.is_(True))
        .group_by(Asset.parent_asset_id)
    ).all()
    for parent_id, count in child_rows:
        result[parent_id]["child_count"] = int(count)
    open_orders = select(WorkOrder.id).where(
        WorkOrder.organization_id == ctx.org.id,
        WorkOrder.status.in_(OPEN_STATUSES),
        policy.visible_project_filter(ctx, WorkOrder.project_id),
    )
    primary_pairs = db.session.execute(
        select(WorkOrder.primary_asset_id, WorkOrder.id).where(WorkOrder.id.in_(open_orders), WorkOrder.primary_asset_id.in_(ids))
    ).all()
    linked_pairs = db.session.execute(
        select(WorkOrderAsset.asset_id, WorkOrderAsset.work_order_id).where(
            WorkOrderAsset.work_order_id.in_(open_orders), WorkOrderAsset.asset_id.in_(ids)
        )
    ).all()
    per_asset: dict[UUID, set[UUID]] = defaultdict(set)
    for asset_id, work_order_id in list(primary_pairs) + list(linked_pairs):
        per_asset[asset_id].add(work_order_id)
    for asset_id, work_order_ids in per_asset.items():
        result[asset_id]["open_work_order_count"] = len(work_order_ids)
    return result


def hierarchy(ctx, *, filters: dict[str, list[str]] | None = None) -> tuple[list[Asset], dict[UUID, list[Asset]]]:
    """Active visible assets as a forest: ``(roots, children_of)``. An asset whose
    parent falls outside the filtered set is reported as a root."""
    policy.authorize(ctx, "asset.read")
    filters = {name: values for name, values in (filters or {}).items() if name in HIERARCHY_FILTERS}
    query = _apply_scope_filters(visible_assets_query(ctx).filter(Asset.is_active.is_(True)), filters)
    rows = query.order_by(func.lower(Asset.name).asc(), Asset.id.asc()).all()
    by_id = {asset.id: asset for asset in rows}
    children_of: dict[UUID, list[Asset]] = defaultdict(list)
    roots: list[Asset] = []
    for asset in rows:
        if asset.parent_asset_id and asset.parent_asset_id in by_id:
            children_of[asset.parent_asset_id].append(asset)
        else:
            roots.append(asset)
    return roots, children_of


def history(ctx, asset: Asset, *, limit: int = DEFAULT_HISTORY_LIMIT) -> list[tuple[str, datetime, object]]:
    """Merged timeline for one asset, newest first: ``(kind, at, row)`` where
    kind is ``status`` (AssetStatusHistory), ``audit`` (AuditEvent) or
    ``work_order`` (WorkOrder the user may read that references the asset)."""
    policy.authorize(ctx, "asset.read", asset)
    if not can_read_asset(ctx, asset):
        raise NotFound()
    limit = max(1, min(int(limit), MAX_HISTORY_LIMIT))
    status_rows = (
        AssetStatusHistory.query.filter_by(asset_id=asset.id)
        .order_by(AssetStatusHistory.started_at.desc(), AssetStatusHistory.id.desc())
        .limit(limit)
        .all()
    )
    audit_rows = audit_events.list_for_entity(ctx, "asset", asset.id, limit=limit)
    linked = select(WorkOrderAsset.work_order_id).where(WorkOrderAsset.asset_id == asset.id)
    order_rows = (
        work_orders.visible_work_orders_query(ctx)
        .filter(or_(WorkOrder.primary_asset_id == asset.id, WorkOrder.id.in_(linked)))
        .order_by(WorkOrder.created_at.desc(), WorkOrder.number.desc())
        .limit(limit)
        .all()
    )
    entries: list[tuple[str, datetime, object]] = []
    entries.extend(("status", row.started_at, row) for row in status_rows)
    entries.extend(("audit", row.occurred_at, row) for row in audit_rows)
    entries.extend(("work_order", row.created_at, row) for row in order_rows)
    entries.sort(key=lambda entry: (entry[1], -_TIMELINE_KIND_RANK[entry[0]]), reverse=True)
    return entries[:limit]


# --------------------------------------------------------------------------- writes


def _code_taken(ctx, code: str, *, exclude_id=None) -> bool:
    query = Asset.query.filter(Asset.organization_id == ctx.org.id, func.lower(Asset.code) == code.lower())
    if exclude_id is not None:
        query = query.filter(Asset.id != exclude_id)
    return bool(db.session.query(query.exists()).scalar())


def _creates_cycle(asset: Asset, parent: Asset) -> bool:
    """True when making ``parent`` the parent of ``asset`` would loop."""
    seen: set[UUID] = set()
    current = parent
    while current is not None:
        if current.id == asset.id or current.id in seen:
            return True
        seen.add(current.id)
        current = current.parent
    return False


def _default_location_id(ctx):
    row = Location.query.filter_by(organization_id=ctx.org.id, is_default=True).first()
    return row.id if row else None


def _check_references(ctx, data: dict, *, asset: Asset | None = None) -> None:
    """Every id in ``data`` must belong to the organization (and be visible to
    the user). Collects one message per bad field, then raises."""
    errors: dict[str, str] = {}
    cycle = False
    if data.get("code") is not None and _code_taken(ctx, data["code"], exclude_id=asset.id if asset else None):
        errors["code"] = "This code is already used by another asset."
    if data.get("parent_id") is not None:
        parent = db.session.get(Asset, data["parent_id"])
        if parent is None or not can_read_asset(ctx, parent):
            errors["parent_id"] = "Unknown asset."
        elif asset is not None and _creates_cycle(asset, parent):
            cycle = True
    if data.get("project_id") is not None:
        project = db.session.get(OpsProject, data["project_id"])
        if project is None or not policy.can_read_project(ctx, project):
            errors["project_id"] = "Unknown project."
    if data.get("location_id") is not None:
        location = db.session.get(Location, data["location_id"])
        if location is None or location.organization_id != ctx.org.id:
            errors["location_id"] = "Unknown location."
    if data.get("responsible_team_id") is not None:
        team = db.session.get(Team, data["responsible_team_id"])
        if team is None or team.organization_id != ctx.org.id:
            errors["responsible_team_id"] = "Unknown team."
    if data.get("owner_user_id") is not None:
        membership = Membership.query.filter_by(organization_id=ctx.org.id, user_id=data["owner_user_id"], member_status="active").first()
        if membership is None:
            errors["owner_user_id"] = "Choose an active member of this chapter."
    if data.get("type_ids"):
        wanted = set(data["type_ids"])
        found = {
            row[0]
            for row in db.session.execute(select(AssetType.id).where(AssetType.organization_id == ctx.org.id, AssetType.id.in_(list(wanted))))
        }
        if wanted - found:
            errors["type_ids"] = "Unknown asset type."
    purchase_date = data["purchase_date"] if "purchase_date" in data else getattr(asset, "purchase_date", None)
    warranty_end = data["warranty_end"] if "warranty_end" in data else getattr(asset, "warranty_end", None)
    if purchase_date and warranty_end and warranty_end < purchase_date:
        errors["warranty_end"] = "Warranty end must be on or after the purchase date."
    if errors:
        raise ValidationErrors(errors)
    if cycle:
        raise Validation("An asset cannot be placed under one of its own descendants.", field="parent_id", code="asset_cycle")


def _assign(asset: Asset, data: dict) -> None:
    for key in _SIMPLE_KEYS:
        if key in data:
            setattr(asset, _COLUMN_FOR.get(key, key), data[key])


def _set_types(asset: Asset, type_ids: list[UUID]) -> None:
    wanted: list[UUID] = []
    for type_id in type_ids:
        if type_id not in wanted:
            wanted.append(type_id)
    asset.type_links = [AssetTypeLink(asset_type_id=type_id) for type_id in wanted]


def _type_ids(asset: Asset) -> list[str]:
    return sorted(str(link.asset_type_id) for link in asset.type_links)


def create(ctx, payload: dict) -> Asset:
    policy.authorize(ctx, "asset.manage")
    data = validate(payload, ASSET_SPEC)
    _check_references(ctx, data)
    asset = Asset(organization_id=ctx.org.id, created_by_user_id=ctx.user.id, updated_by_user_id=ctx.user.id)
    _assign(asset, data)
    asset.status = data["status"]
    if asset.location_id is None:
        asset.location_id = _default_location_id(ctx)
    if asset.is_active is None:
        asset.is_active = True
    # object-level scope (a project lead manages only their projects' assets)
    policy.authorize(ctx, "asset.manage", asset)
    db.session.add(asset)
    db.session.flush()
    if data.get("type_ids"):
        _set_types(asset, data["type_ids"])
    if asset.status != "online":
        downtime_type = None
        if asset.status in OFFLINE_STATUSES:
            downtime_type = "planned" if asset.status == "offline_planned" else "unplanned"
        db.session.add(
            AssetStatusHistory(
                organization_id=ctx.org.id,
                asset_id=asset.id,
                from_status=None,
                to_status=asset.status,
                downtime_type=downtime_type,
                started_at=utcnow(),
                changed_by_user_id=ctx.user.id,
            )
        )
    db.session.flush()
    audit_events.record(
        ctx,
        "asset.created",
        asset,
        after={**audit_events.snapshot(asset, ASSET_SNAPSHOT_FIELDS), "type_ids": _type_ids(asset)},
        summary=f"Created asset {asset.name}",
    )
    db.session.commit()
    return asset


def _validate_update(payload: dict) -> dict:
    payload = payload if isinstance(payload, dict) else {}
    status_error = {"status": STATUS_NOT_EDITABLE} if "status" in payload else {}
    try:
        data = validate(payload, UPDATE_SPEC, partial=True)
    except ValidationErrors as exc:
        raise ValidationErrors({**exc.errors, **status_error}) from None
    if status_error:
        raise ValidationErrors(status_error)
    return data


def update(ctx, asset: Asset, payload: dict) -> Asset:
    policy.authorize(ctx, "asset.manage", asset)
    data = _validate_update(payload)
    _check_references(ctx, data, asset=asset)
    if "project_id" in data and data["project_id"] != asset.project_id:
        target = SimpleNamespace(
            organization_id=ctx.org.id,
            project_id=data["project_id"],
            responsible_team_id=data.get("responsible_team_id", asset.responsible_team_id),
        )
        if not policy.can(ctx, "asset.manage", target):
            raise Forbidden("You cannot move an asset into that project.", permission="asset.manage")
    before = {**audit_events.snapshot(asset, ASSET_SNAPSHOT_FIELDS), "type_ids": _type_ids(asset)}
    _assign(asset, data)
    if "type_ids" in data:
        _set_types(asset, data["type_ids"] or [])
    asset.updated_by_user_id = ctx.user.id
    db.session.flush()
    after = {**audit_events.snapshot(asset, ASSET_SNAPSHOT_FIELDS), "type_ids": _type_ids(asset)}
    changed = sorted(key for key in after if after[key] != before[key])
    audit_events.record(
        ctx,
        "asset.updated",
        asset,
        before=before,
        after=after,
        summary=f"Updated asset {asset.name}",
        changed_fields=changed,
    )
    db.session.commit()
    return asset


# --------------------------------------------------------------------------- asset types


def list_types(ctx) -> list[tuple[AssetType, int]]:
    """``[(asset_type, asset_count)]`` ordered by name; counts cover active,
    visible assets."""
    policy.authorize(ctx, "asset.read")
    count_rows = db.session.execute(
        select(AssetTypeLink.asset_type_id, func.count(AssetTypeLink.asset_id))
        .join(Asset, Asset.id == AssetTypeLink.asset_id)
        .where(Asset.organization_id == ctx.org.id, Asset.is_active.is_(True), policy.visible_project_filter(ctx, Asset.project_id))
        .group_by(AssetTypeLink.asset_type_id)
    ).all()
    counts = {type_id: int(count) for type_id, count in count_rows}
    rows = AssetType.query.filter_by(organization_id=ctx.org.id).order_by(func.lower(AssetType.name).asc(), AssetType.id.asc()).all()
    return [(row, counts.get(row.id, 0)) for row in rows]


def create_type(ctx, payload: dict) -> AssetType:
    policy.authorize(ctx, "asset.manage")
    data = validate(payload, ASSET_TYPE_SPEC)
    exists = db.session.query(
        AssetType.query.filter(AssetType.organization_id == ctx.org.id, func.lower(AssetType.name) == data["name"].lower()).exists()
    ).scalar()
    if exists:
        raise ValidationErrors({"name": "An asset type with this name already exists."})
    row = AssetType(
        organization_id=ctx.org.id,
        name=data["name"],
        color=data["color"],
        icon=data["icon"],
        created_by_user_id=ctx.user.id,
        updated_by_user_id=ctx.user.id,
    )
    db.session.add(row)
    db.session.flush()
    audit_events.record(
        ctx,
        "asset_type.created",
        row,
        after=audit_events.snapshot(row, ("name", "color", "icon")),
        summary=f"Created asset type {row.name}",
    )
    db.session.commit()
    return row
