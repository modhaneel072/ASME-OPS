"""Setup Center: ``GET /setup`` plus banner, completion and guide actions."""

from __future__ import annotations

from asme.blueprints.ops import bp, ok
from asme.ops import policy
from asme.ops.services import setup_center


@bp.get("/setup")
@policy.require_permission()
def get_setup():
    ctx = policy.current_context()
    return ok(setup_center.progress(ctx))


@bp.post("/setup/dismiss-banner")
@policy.require_permission()
def dismiss_setup_banner():
    ctx = policy.current_context()
    setup_center.set_banner_dismissed(ctx, True)
    return ok(setup_center.progress(ctx))


@bp.post("/setup/reopen-banner")
@policy.require_permission()
def reopen_setup_banner():
    ctx = policy.current_context()
    setup_center.set_banner_dismissed(ctx, False)
    return ok(setup_center.progress(ctx))


@bp.post("/setup/complete")
@policy.require_permission("chapter.setup.manage")
def complete_setup():
    ctx = policy.current_context()
    setup_center.complete(ctx)
    return ok(setup_center.progress(ctx))


@bp.post("/setup/mark-guide-read")
@policy.require_permission("chapter.setup.manage")
def mark_guide_read():
    ctx = policy.current_context()
    setup_center.mark_guide_read(ctx)
    return ok(setup_center.progress(ctx))
