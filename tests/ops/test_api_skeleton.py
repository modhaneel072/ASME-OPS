from pathlib import Path

from asme.ops import bootstrap
from tests.conftest import PASSWORD
from tests.ops.conftest import make_user


def test_login_logout_and_session_roundtrip(client, org, users):
    anonymous = client.get("/api/v1/session")
    assert anonymous.status_code == 401
    assert anonymous.get_json()["code"] == "login_required"

    bad = client.post("/api/v1/auth/login", json={"identifier": users["admin"].email, "password": "wrong"})
    assert bad.status_code == 401 and bad.get_json()["code"] == "invalid_credentials"

    missing = client.post("/api/v1/auth/login", json={"identifier": ""})
    assert missing.status_code == 400
    assert set(missing.get_json()["errors"]) == {"identifier", "password"}

    good = client.post("/api/v1/auth/login", json={"identifier": users["admin"].username, "password": PASSWORD})
    assert good.status_code == 200, good.get_json()
    payload = good.get_json()["payload"]
    assert payload["user"]["id"] == users["admin"].id
    assert payload["session"]["membership"]["role"]["system_key"] == "chapter_admin"
    assert payload["session"]["permissions"]["role.manage"] == ["chapter"]
    assert payload["session"]["organization"]["slug"] == "uiowa"
    assert payload["session"]["features"]["realtime"] == "polling"

    session = client.get("/api/v1/session")
    assert session.status_code == 200
    body = session.get_json()["payload"]
    assert body["user"]["email"] == users["admin"].email
    assert body["setup"] == {"banner_dismissed": False, "completed": False}
    assert body["scope"] == {"project_ids": [], "team_ids": [], "lead_team_ids": []}

    logout = client.post("/api/v1/auth/logout", json={})
    assert logout.status_code == 200
    assert client.get("/api/v1/session").status_code == 401


def test_login_is_rate_limited(app, org, users):
    limited = app.test_client()
    app.extensions["asme_login_rate_limiter"].max_attempts = 2
    for _ in range(2):
        limited.post("/api/v1/auth/login", json={"identifier": users["member"].email, "password": "nope"})
    blocked = limited.post("/api/v1/auth/login", json={"identifier": users["member"].email, "password": PASSWORD})
    assert blocked.status_code == 429
    assert blocked.get_json()["code"] == "rate_limited"
    app.extensions["asme_login_rate_limiter"].max_attempts = 100


def test_mutations_require_json_content_type(client, org, users, api_login):
    api_login(users["admin"])
    form = client.patch("/api/v1/organization", data={"name": "x"})
    assert form.status_code == 415 and form.get_json()["code"] == "json_required"
    multipart_without_header = client.post("/api/v1/auth/logout", data={"file": (b"x", "a.txt")}, content_type="multipart/form-data")
    assert multipart_without_header.status_code == 415
    assert multipart_without_header.get_json()["code"] == "upload_header_required"
    ok = client.patch("/api/v1/organization", json={"name": "ASME at Iowa"})
    assert ok.status_code == 200 and ok.get_json()["payload"]["organization"]["name"] == "ASME at Iowa"


def test_unknown_route_uses_json_envelope(client):
    missing = client.get("/api/v1/does-not-exist")
    assert missing.status_code == 404
    assert missing.get_json() == {"ok": False, "code": "not_found", "error": "Not found."}


def test_user_without_membership_gets_no_membership(client, app, org, users, db):
    stranger = make_user("Strange R", "stranger@uiowa.edu")
    client.post("/api/v1/auth/login", json={"identifier": stranger.email, "password": PASSWORD})
    # sign-in auto-creates a membership; suspend it to simulate a removed member
    membership = bootstrap.membership_for(stranger, org)
    membership.member_status = "suspended"
    db.session.commit()
    denied = client.get("/api/v1/session")
    assert denied.status_code == 403 and denied.get_json()["code"] == "no_membership"


def test_organization_patch_validates_and_audits(client, org, users, api_login, db):
    from asme.ops.models import AuditEvent

    api_login(users["admin"])
    bad = client.patch("/api/v1/organization", json={"timezone": "Mars/Olympus", "academic_year_start_month": 13, "logo_url": "ftp://x"})
    assert bad.status_code == 400
    assert set(bad.get_json()["errors"]) == {"timezone", "academic_year_start_month", "logo_url"}

    good = client.patch(
        "/api/v1/organization",
        json={"timezone": "America/Chicago", "academic_year_start_month": 8, "settings": {"profile_completed": True, "ignored": 1}},
    )
    assert good.status_code == 200
    body = good.get_json()["payload"]["organization"]
    assert body["settings"] == {"profile_completed": True}
    event = AuditEvent.query.filter_by(event_type="organization.updated").one()
    assert event.actor_user_id == users["admin"].id and event.entity_type == "organization"

    api_login(users["member"])
    forbidden = client.patch("/api/v1/organization", json={"name": "Nope"})
    assert forbidden.status_code == 403 and forbidden.get_json()["permission"] == ["chapter.settings.manage"]


def test_preferences_roundtrip(client, org, users, api_login):
    api_login(users["member"])
    saved = client.put("/api/v1/preferences/setup_banner_dismissed", json={"value": True})
    assert saved.status_code == 200
    assert client.get("/api/v1/session").get_json()["payload"]["setup"]["banner_dismissed"] is True
    unknown = client.put("/api/v1/preferences/not-a-key", json={"value": 1})
    assert unknown.status_code == 400


def test_spa_shell_serves_index_or_503(client, app, tmp_path, monkeypatch):
    static_root = Path(app.static_folder)
    index = static_root / "ops" / "index.html"
    if index.exists():
        response = client.get("/app/work-orders/abc")
        assert response.status_code == 200
        assert b"<html" in response.data.lower()
        assert response.headers["Cache-Control"].startswith("no-store")
    else:
        response = client.get("/app")
        assert response.status_code == 503
        assert b"not built" in response.data
