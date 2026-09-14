"""Account review 3: a production deployment must never build e-mailed reset
links from an attacker-controlled ``Host`` header.

``reset_link`` falls back to ``request.host_url`` whenever
``ASME_PUBLIC_BASE_URL`` is unset, and in production that omission is only a
startup *warning* (``Settings.warnings``), not a refusal (``Settings.validate``).
No ``SERVER_NAME`` / allowed-host list exists either. An attacker posts
``/auth/forgot-password`` for a victim with ``Host: attacker.example``; the victim
receives a genuine ASME e-mail whose link points at the attacker's site, and the
click hands the attacker a working token.

Correct behaviour is either: production refuses to start without a public base
URL, or the link in the queued e-mail does not use the forged host.
"""

from __future__ import annotations

import dataclasses
import json

from asme.models import OutboxJob


def test_production_reset_link_cannot_be_pointed_at_forged_host(app, client, org, users):
    cfg = dataclasses.replace(
        app.config["SETTINGS"],
        env="production",
        public_base_url="",
        secret_key="a-real-production-secret-value",
        smtp_user="chapter@uiowa.edu",
        smtp_pass="app-password",
    )
    if any("PUBLIC_BASE_URL" in problem for problem in cfg.validate()):
        return  # production refuses to start without a trusted origin: defect closed

    app.config["SETTINGS"] = cfg
    response = client.post(
        "/api/v1/auth/forgot-password",
        json={"email": users["member"].email},
        headers={"Host": "attacker.example"},
    )
    assert response.status_code in (200, 400), response.get_data(as_text=True)
    bodies = [json.loads(job.payload_json).get("body", "") for job in OutboxJob.query.filter_by(kind="mail.send").all()]
    assert not any("attacker.example" in body for body in bodies), bodies
