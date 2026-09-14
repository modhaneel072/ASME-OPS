"""Chapter profile: ``GET|PATCH /api/v1/organization``."""

from __future__ import annotations

from asme.blueprints.ops import bp, json_body, ok
from asme.ops import policy
from asme.ops.serializers import organization as serialize_organization
from asme.ops.services import organizations


@bp.get("/organization")
@policy.require_permission()
def get_organization():
    ctx = policy.current_context()
    return ok({"organization": serialize_organization(ctx.org)})


@bp.patch("/organization")
@policy.require_permission("chapter.settings.manage")
def patch_organization():
    ctx = policy.current_context()
    org = organizations.update(ctx, json_body())
    return ok({"organization": serialize_organization(org)})
