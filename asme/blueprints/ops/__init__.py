"""``/api/v1`` – ASME Ops JSON surface.

Shares the legacy envelope (``{"ok": true, "payload"}`` / ``{"ok": false, "code",
"error"}``) and adds:

* ``code="validation"`` errors carry ``errors: {field: message}``;
* mutating requests must be JSON (or multipart with ``X-Requested-With: ASME-Ops``);
* cursor pagination helpers and filter allow-lists.

Route modules import ``bp`` from here and are loaded by ``register_routes``.
"""

from __future__ import annotations

import base64
import json
from importlib import import_module

from flask import Blueprint, jsonify, request
from werkzeug.exceptions import RequestEntityTooLarge

from asme.services.errors import ServiceError, Validation
from asme.utils import parse_positive_int

bp = Blueprint("ops_api", __name__, url_prefix="/api/v1")

ROUTE_MODULES = (
    "asme.blueprints.ops.session",
    "asme.blueprints.ops.auth",
    "asme.blueprints.ops.organization",
    "asme.blueprints.ops.setup",
    "asme.blueprints.ops.teams",
    "asme.blueprints.ops.users",
    "asme.blueprints.ops.locations",
    "asme.blueprints.ops.categories",
    "asme.blueprints.ops.assets",
    "asme.blueprints.ops.vendors",
    "asme.blueprints.ops.projects",
    "asme.blueprints.ops.work_orders",
    "asme.blueprints.ops.comments",
    "asme.blueprints.ops.attachments",
    "asme.blueprints.ops.saved_filters",
    "asme.blueprints.ops.notifications",
    "asme.blueprints.ops.changes",
    "asme.blueprints.ops.reports",
    "asme.blueprints.ops.search",
    "asme.blueprints.ops.parts",
    "asme.blueprints.ops.purchase_requests",
    "asme.blueprints.ops.work_order_parts",
)

MUTATING_METHODS = {"POST", "PATCH", "PUT", "DELETE"}
UPLOAD_HEADER = "X-Requested-With"
UPLOAD_HEADER_VALUE = "ASME-Ops"


def register_routes() -> None:
    for module_name in ROUTE_MODULES:
        import_module(module_name)


# --------------------------------------------------------------------------- errors


@bp.errorhandler(ServiceError)
def _service_error(exc: ServiceError):
    return jsonify(exc.to_dict()), exc.status


@bp.errorhandler(404)
def _not_found(_exc):
    return jsonify({"ok": False, "code": "not_found", "error": "Not found."}), 404


@bp.errorhandler(405)
def _method_not_allowed(_exc):
    return jsonify({"ok": False, "code": "method_not_allowed", "error": "Method not allowed."}), 405


@bp.errorhandler(RequestEntityTooLarge)
def _too_large(_exc):
    return jsonify({"ok": False, "code": "payload_too_large", "error": "The upload is larger than the configured limit."}), 413


@bp.before_request
def _require_json_for_mutations():
    if request.method not in MUTATING_METHODS:
        return None
    content_type = (request.content_type or "").lower()
    if content_type.startswith("multipart/form-data"):
        if request.headers.get(UPLOAD_HEADER) != UPLOAD_HEADER_VALUE:
            return jsonify({"ok": False, "code": "upload_header_required", "error": f"Uploads must send {UPLOAD_HEADER}: {UPLOAD_HEADER_VALUE}."}), 415
        return None
    if request.method == "DELETE" and not request.content_length:
        return None
    if not request.is_json:
        return jsonify({"ok": False, "code": "json_required", "error": "Send a JSON body with Content-Type: application/json."}), 415
    return None


# --------------------------------------------------------------------------- helpers


def ok(payload=None, status: int = 200, **extra):
    body = {"ok": True}
    if payload is not None:
        body["payload"] = payload
    body.update(extra)
    return jsonify(body), status


def json_body() -> dict:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def encode_cursor(value) -> str:
    return base64.urlsafe_b64encode(json.dumps(value).encode("utf-8")).decode("ascii").rstrip("=")


def decode_cursor(raw):
    if not raw:
        return None
    try:
        padded = raw + "=" * (-len(raw) % 4)
        return json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
    except Exception:
        raise Validation("Invalid cursor.", field="cursor", code="bad_cursor")


def page_limit(default: int = 50, maximum: int = 200) -> int:
    raw = request.args.get("limit") or request.args.get("page[limit]")
    return max(1, min(parse_positive_int(raw, default=default), maximum))


def page_cursor():
    return decode_cursor(request.args.get("cursor") or request.args.get("page[cursor]"))


def paginate(query, *, limit: int | None = None, cursor=None, count: bool = True):
    """Offset-under-the-hood cursor pagination with a stable ordering supplied by
    the caller. Returns ``(rows, next_cursor, total)``."""
    limit = limit or page_limit()
    cursor = cursor if cursor is not None else page_cursor()
    offset = int((cursor or {}).get("offset", 0)) if cursor else 0
    if offset < 0:
        raise Validation("Invalid cursor.", field="cursor", code="bad_cursor")
    rows = query.offset(offset).limit(limit + 1).all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = encode_cursor({"offset": offset + limit}) if has_more else None
    total = query.order_by(None).count() if count else None
    return rows, next_cursor, total


def list_payload(key: str, items: list, next_cursor: str | None, total: int | None) -> dict:
    payload = {"items": items, "next_cursor": next_cursor}
    if total is not None:
        payload["total"] = total
    payload[key] = items  # legacy-friendly alias
    return payload


def parse_filters(allowed: dict[str, str]) -> dict[str, list[str]]:
    """Read ``filter[name]=a,b`` (or ``name=a,b``) for names in ``allowed``.
    ``allowed`` maps name -> "single"|"multi". Unknown filters are rejected."""
    found: dict[str, list[str]] = {}
    for raw_key, raw_value in request.args.items(multi=True):
        name = raw_key
        if raw_key.startswith("filter[") and raw_key.endswith("]"):
            name = raw_key[7:-1]
        elif raw_key in {"limit", "cursor", "sort", "q", "page[limit]", "page[cursor]", "view", "tab", "include", "range", "since", "start", "end"}:
            continue
        elif raw_key not in allowed:
            continue
        if name not in allowed:
            raise Validation(f"Unknown filter '{name}'.", field="filter", code="bad_filter")
        values = [v.strip() for v in str(raw_value).split(",") if v.strip()]
        if not values:
            continue
        if allowed[name] == "single":
            found[name] = values[:1]
        else:
            found.setdefault(name, []).extend(values)
    return found


def parse_sort(allowed: tuple[str, ...], default: str) -> str:
    raw = (request.args.get("sort") or default).strip()
    key = raw[1:] if raw.startswith("-") else raw
    if key not in allowed:
        raise Validation(f"Unknown sort '{raw}'.", field="sort", code="bad_sort")
    return raw


def query_text() -> str:
    return (request.args.get("q") or "").strip()
