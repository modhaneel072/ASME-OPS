"""Operations report: ``GET /reports/operations?range=&start=&end=&filter[project]=&filter[team]=``.

Metric definitions live in ``docs/reporting-metrics.md``."""

from __future__ import annotations

from flask import request

from asme.blueprints.ops import bp, ok, parse_filters
from asme.ops import policy
from asme.ops.services import dashboard

FILTERS = {"project": "single", "team": "single"}


@bp.get("/reports/operations")
@policy.require_permission("report.view")
def operations_report():
    ctx = policy.current_context()
    params = {}
    for name in ("range", "start", "end"):
        value = (request.args.get(name) or "").strip()
        if value:
            params[name] = value
    for name, values in parse_filters(FILTERS).items():
        params[name] = values[0]
    return ok(dashboard.operations_report(ctx, params))
