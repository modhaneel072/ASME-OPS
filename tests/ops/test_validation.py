from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from asme.ops.validation import Field, ValidationErrors, validate

SPEC = {
    "title": Field("str", required=True, max_len=10),
    "priority": Field("choice", choices=("none", "low", "high"), default="none"),
    "due_at": Field("datetime"),
    "start_date": Field("date"),
    "estimated_minutes": Field("int", minimum=0),
    "budget": Field("decimal"),
    "email": Field("email"),
    "color": Field("color"),
    "asset_id": Field("uuid"),
    "assignee_ids": Field("list", item=Field("int")),
    "flag": Field("bool"),
}


def test_reports_every_bad_field_at_once():
    with pytest.raises(ValidationErrors) as excinfo:
        validate(
            {
                "title": "this title is far too long",
                "priority": "urgent",
                "due_at": "yesterday",
                "estimated_minutes": -5,
                "email": "nope",
                "color": "blue",
                "asset_id": "123",
                "assignee_ids": "1,2",
                "flag": "maybe",
            },
            SPEC,
        )
    errors = excinfo.value.errors
    assert set(errors) == {"title", "priority", "due_at", "estimated_minutes", "email", "color", "asset_id", "assignee_ids", "flag"}
    body = excinfo.value.to_dict()
    assert body["ok"] is False and body["code"] == "validation" and body["errors"] == errors


def test_required_and_defaults():
    with pytest.raises(ValidationErrors) as excinfo:
        validate({}, SPEC)
    assert excinfo.value.errors == {"title": "This field is required."}
    cleaned = validate({"title": "ok"}, SPEC)
    assert cleaned == {"title": "ok", "priority": "none"}


def test_partial_skips_missing_and_coerces_present():
    asset = uuid4()
    cleaned = validate(
        {
            "due_at": "2026-09-08T14:30:00Z",
            "start_date": "2026-09-01",
            "budget": "12.50",
            "asset_id": str(asset),
            "assignee_ids": [1, "2"],
            "flag": "true",
            "email": "Lead@UIowa.edu",
            "priority": "HIGH",
        },
        SPEC,
        partial=True,
    )
    assert cleaned["due_at"] == datetime(2026, 9, 8, 14, 30, tzinfo=timezone.utc)
    assert cleaned["start_date"] == date(2026, 9, 1)
    assert cleaned["budget"] == Decimal("12.50")
    assert cleaned["asset_id"] == asset
    assert cleaned["assignee_ids"] == [1, 2]
    assert cleaned["flag"] is True
    assert cleaned["email"] == "lead@uiowa.edu"
    assert cleaned["priority"] == "high"
    assert "title" not in cleaned


def test_empty_string_clears_nullable_field_but_not_required():
    cleaned = validate({"title": "t", "due_at": ""}, SPEC)
    assert cleaned["due_at"] is None
    with pytest.raises(ValidationErrors):
        validate({"title": "   "}, SPEC)
