"""Small declarative validator for JSON payloads.

Every ops endpoint validates input with ``validate(payload, SPEC)``; failures
raise ``ValidationErrors`` whose envelope is
``{"ok": false, "code": "validation", "error": "...", "errors": {field: message}}``
so the frontend can map messages onto form fields.

No third-party schema library: the shapes here are flat and this keeps the
Python and TypeScript (zod) contracts easy to compare by eye.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field as dc_field
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

from asme.constants import EMAIL_RE
from asme.ops.types import parse_uuid
from asme.services.errors import ServiceError

HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
MISSING = object()

# Bounds for numbers arriving from clients. Integer columns are 32-bit on
# PostgreSQL and money columns are Numeric(12, 2); rejecting out-of-range values
# during validation turns a 500 at INSERT time into a field error.
INT_MIN = -(2**31)
INT_MAX = 2**31 - 1
MONEY_MAX = Decimal("9999999999.99")


class ValidationErrors(ServiceError):
    def __init__(self, errors: dict[str, str], message: str = "Please fix the highlighted fields."):
        super().__init__(message, code="validation", status=400, errors=errors)
        self.errors = errors


@dataclass
class Field:
    kind: str = "str"
    required: bool = False
    nullable: bool = True
    max_len: int | None = None
    min_len: int = 0
    choices: tuple | None = None
    minimum: float | None = None
    maximum: float | None = None
    default: Any = MISSING
    strip: bool = True
    item: "Field | None" = None
    check: Callable[[Any], str | None] | None = None
    extra: dict = dc_field(default_factory=dict)


def _parse_datetime(raw) -> datetime:
    if isinstance(raw, datetime):
        value = raw
    else:
        text = str(raw).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        value = datetime.fromisoformat(text)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_date(raw) -> date:
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    return date.fromisoformat(str(raw).strip()[:10])


def _coerce(name: str, spec: Field, raw):
    kind = spec.kind
    if kind in {"str", "text", "email", "color", "slug", "url"}:
        if not isinstance(raw, str):
            raise ValueError("Must be text.")
        value = raw.strip() if spec.strip else raw
        if kind == "email":
            value = value.lower()
            if value and not EMAIL_RE.match(value):
                raise ValueError("Enter a valid email address.")
        if kind == "color" and value and not HEX_COLOR_RE.match(value):
            raise ValueError("Use a hex colour like #0878d1.")
        if kind == "slug" and value and not re.match(r"^[a-z0-9][a-z0-9\-]{0,78}$", value):
            raise ValueError("Use lowercase letters, numbers and dashes.")
        if kind == "url" and value and not re.match(r"^https?://", value):
            raise ValueError("Enter a full URL starting with http:// or https://.")
        if spec.max_len is not None and len(value) > spec.max_len:
            raise ValueError(f"Keep this under {spec.max_len} characters.")
        if len(value) < spec.min_len:
            raise ValueError("Too short.")
        return value
    if kind == "int":
        if isinstance(raw, bool):
            raise ValueError("Must be a whole number.")
        if isinstance(raw, float) and (raw != raw or raw in (float("inf"), float("-inf")) or not raw.is_integer()):
            # JSON allows the bare literals Infinity and NaN, and 1e30 arrives as a float.
            raise ValueError("Must be a whole number.")
        try:
            value = int(raw)
        except (TypeError, ValueError, OverflowError):
            raise ValueError("Must be a whole number.")
        # Every integer column here is a 32-bit INTEGER on PostgreSQL, so keep
        # client values inside that range instead of failing at INSERT time.
        # A field's own minimum/maximum narrows this further, below.
        if not (INT_MIN <= value <= INT_MAX):
            raise ValueError(f"Must be between {INT_MIN} and {INT_MAX}.")
    elif kind == "decimal":
        if isinstance(raw, bool):
            raise ValueError("Must be a number.")
        try:
            value = Decimal(str(raw))
        except (InvalidOperation, ValueError):
            raise ValueError("Must be a number.")
        if not value.is_finite():
            # NaN and Infinity survive Decimal() and would poison both the
            # Numeric(12, 2) column and the JSON we emit.
            raise ValueError("Must be a number.")
        if spec.maximum is None and abs(value) > MONEY_MAX:
            raise ValueError(f"Must be at most {MONEY_MAX}.")
    elif kind == "bool":
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, str) and raw.strip().lower() in {"true", "1", "yes", "on"}:
            return True
        if isinstance(raw, str) and raw.strip().lower() in {"false", "0", "no", "off"}:
            return False
        raise ValueError("Must be true or false.")
    elif kind == "date":
        try:
            return _parse_date(raw)
        except (TypeError, ValueError):
            raise ValueError("Enter a date as YYYY-MM-DD.")
    elif kind == "datetime":
        try:
            return _parse_datetime(raw)
        except (TypeError, ValueError):
            raise ValueError("Enter a date and time in ISO 8601 format.")
    elif kind == "uuid":
        value = parse_uuid(raw)
        if value is None:
            raise ValueError("Invalid identifier.")
        return value
    elif kind == "choice":
        value = str(raw).strip().lower() if isinstance(raw, str) else raw
        if spec.choices and value not in spec.choices:
            raise ValueError("Choose one of: " + ", ".join(str(c) for c in spec.choices) + ".")
        return value
    elif kind == "list":
        if not isinstance(raw, (list, tuple)):
            raise ValueError("Must be a list.")
        items = []
        item_spec = spec.item or Field("str")
        for index, entry in enumerate(raw):
            items.append(_coerce(f"{name}[{index}]", item_spec, entry))
        if spec.max_len is not None and len(items) > spec.max_len:
            raise ValueError(f"At most {spec.max_len} entries.")
        return items
    elif kind == "json":
        if not isinstance(raw, (dict, list)):
            raise ValueError("Must be an object or list.")
        return raw
    elif kind == "any":
        return raw
    else:  # pragma: no cover - programming error
        raise RuntimeError(f"unknown field kind {kind}")

    try:
        if spec.minimum is not None and value < spec.minimum:
            raise ValueError(f"Must be at least {spec.minimum}.")
        if spec.maximum is not None and value > spec.maximum:
            raise ValueError(f"Must be at most {spec.maximum}.")
    except (InvalidOperation, TypeError):
        raise ValueError("Must be a number.")
    return value


def validate(payload: dict | None, spec: dict[str, Field], *, partial: bool = False) -> dict:
    """Return a cleaned dict containing only keys present in ``payload`` (plus
    defaults when not partial). Raises ``ValidationErrors`` listing every bad field."""
    payload = payload if isinstance(payload, dict) else {}
    cleaned: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for name, field_spec in spec.items():
        present = name in payload
        raw = payload.get(name, MISSING)
        if not present:
            if partial:
                continue
            if field_spec.default is not MISSING:
                cleaned[name] = field_spec.default() if callable(field_spec.default) else field_spec.default
                continue
            if field_spec.required:
                errors[name] = "This field is required."
            continue
        if raw is None or (isinstance(raw, str) and field_spec.strip and not raw.strip() and field_spec.kind not in {"list", "json", "any"}):
            if field_spec.required:
                errors[name] = "This field is required."
            elif field_spec.nullable:
                cleaned[name] = None
            else:
                errors[name] = "This field cannot be empty."
            continue
        try:
            value = _coerce(name, field_spec, raw)
        except ValueError as exc:
            errors[name] = str(exc)
            continue
        if field_spec.check:
            problem = field_spec.check(value)
            if problem:
                errors[name] = problem
                continue
        cleaned[name] = value
    if errors:
        raise ValidationErrors(errors)
    return cleaned


def require_fields(cleaned: dict, *names: str) -> None:
    missing = {name: "This field is required." for name in names if cleaned.get(name) in (None, "", [])}
    if missing:
        raise ValidationErrors(missing)
