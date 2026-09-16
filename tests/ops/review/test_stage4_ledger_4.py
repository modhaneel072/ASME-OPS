"""``request_changes`` must not leave a stale ``approved_total`` behind.

``_do_reopen`` clears ``approved_total`` when a declined or canceled request goes
back to ``draft``; ``_do_request_changes`` does not. A reviewer who approved an
early version with an explicit ``approved_total`` and then sent the request back
for changes leaves that number on the row, and ``_do_approve`` only fills
``approved_total`` in when it is ``None``. The request is then finally approved
recording the old, abandoned amount - which is also the number
``committed_total`` reports as ``budget.committed`` on ``GET /projects/:id/health``.
"""

from __future__ import annotations

from decimal import Decimal

from asme.extensions import db as _db
from asme.ops import policy
from asme.ops.services import purchase_requests
from tests.ops.conftest import make_user

D = Decimal


def test_approved_total_reflects_what_was_finally_approved(app, org, users, ctx_admin, ctx_member):
    org.settings_json = {"purchasing": {"advisor_review_threshold": "50", "require_project_lead_approval": False}}
    _db.session.commit()
    # Two signatures, two people: the treasurer step and the advisor step are
    # never cleared by the same human.
    ctx_treasurer = policy.load_context(make_user("Tess Treasurer", "tess.treasurer@uiowa.edu", ops_role="treasurer", org=org), org)

    request = purchase_requests.create(
        ctx_member,
        {"title": "Filament", "items": [{"description": "PLA spool", "quantity": 1, "unit_price": 100}]},
    )
    purchase_requests.perform(ctx_member, request, "submit", {})
    assert request.status == "treasurer_review"

    # The treasurer signs off on 100.00, then the advisor sends it back.
    purchase_requests.perform(ctx_treasurer, request, "approve", {"approved_total": 100})
    assert request.status == "advisor_review"
    purchase_requests.perform(ctx_admin, request, "request_changes", {"comment": "Order the whole case."})
    assert request.status == "draft"

    purchase_requests.update(
        ctx_member, request, {"items": [{"description": "PLA spool", "quantity": 50, "unit_price": 100}]}
    )
    assert D(str(request.estimated_total)) == D("5000.00")

    purchase_requests.perform(ctx_member, request, "submit", {})
    purchase_requests.perform(ctx_treasurer, request, "approve", {})
    assert request.status == "advisor_review"
    purchase_requests.perform(ctx_admin, request, "approve", {})

    assert request.status == "approved"
    assert D(str(request.approved_total)) == D("5000.00"), "the approval recorded an amount abandoned by request_changes"
