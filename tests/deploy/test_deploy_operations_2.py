"""Milestones are marked "missed" on the server's UTC calendar day.

The hourly ``ops.work_order.scan`` job ends in
``asme.ops.services.scans._mark_missed_milestones``, which does::

    today = now.date()                      # now is UTC
    ... Milestone.due_date < today ...

Render runs in UTC; the chapter is in Iowa. ``Organization.timezone`` exists,
defaults to ``America/Chicago`` and is what
``asme.ops.services.dashboard.resolve_range`` correctly uses for every reported
date - this one place does not.

So a milestone due today flips to ``missed`` at 19:00 local time (18:00 in the
winter), on the evening of the day it is due, while the team is still in the
shop working on it. That is not cosmetic: ``_mark_missed_milestones`` writes a
``milestone.missed`` audit event, which is what the project screens and the
``/changes`` poll feed show, and the status is never walked back.

Expressed as a deadline the chapter can check: a milestone due 16 September is
still due until 23:59 on 16 September in Iowa City.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from asme.extensions import db
from asme.ops import bootstrap
from asme.ops.models import Milestone, OpsProject
from asme.ops.services.scans import run_work_order_scan

DUE = date(2026, 9, 16)
# 02:00 UTC on 17 September is 21:00 on 16 September in Iowa City (CDT, UTC-5):
# the milestone's own due day, five hours before it ends.
STILL_THE_DUE_DAY_IN_IOWA = datetime(2026, 9, 17, 2, 0, tzinfo=timezone.utc)


@pytest.fixture
def milestone(app, users):
    org = bootstrap.ensure_default_organization()
    assert org.timezone == "America/Chicago", "the chapter's organization is in Iowa"
    project = OpsProject(organization_id=org.id, name="Baja Frame", code="BAJA", status="active")
    db.session.add(project)
    db.session.flush()
    row = Milestone(
        organization_id=org.id,
        project_id=project.id,
        name="Frame weldment complete",
        due_date=DUE,
        status="in_progress",
    )
    db.session.add(row)
    db.session.commit()
    return row


def test_milestone_is_not_missed_while_its_due_day_is_still_running_in_iowa(milestone):
    totals = run_work_order_scan(now=STILL_THE_DUE_DAY_IN_IOWA)

    db.session.refresh(milestone)
    assert milestone.status == "in_progress", (
        f"milestone due {DUE} was marked {milestone.status!r} at "
        f"{STILL_THE_DUE_DAY_IN_IOWA.astimezone(timezone.utc).isoformat()} "
        "(21:00 on its own due date in Iowa City)"
    )
    assert totals["milestones_missed"] == 0
