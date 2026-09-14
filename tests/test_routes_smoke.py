"""The surviving HTTP surface: the ASME Ops shell, health checks and the JSON APIs.

The public website, member/admin portal, kiosk and standalone auth pages were
removed; their paths must not resolve to anything.
"""

from pathlib import Path

import pytest

REMOVED = [
    "/login",
    "/signup",
    "/admin-login",
    "/logout",
    "/portal",
    "/portal/member",
    "/portal/admin",
    "/kiosk",
    "/checkin",
    "/who-we-are",
    "/executive-team",
    "/projects",
    "/events",
    "/gallery",
    "/join",
    "/contact",
    "/sponsors",
    "/forgot-password",
    "/reset-password/x",
    "/dashboard",
    "/legacy/app",
    "/arm-sim",
]


def test_root_redirects_to_app(client):
    response = client.get("/")
    assert response.status_code == 302
    assert response.headers["Location"] == "/app"


def test_app_serves_shell_or_not_built_page(client, app):
    built = (Path(app.static_folder) / "ops" / "index.html").exists()
    for path in ("/app", "/app/", "/app/auth/login", "/app/work-orders/abc"):
        response = client.get(path)
        assert response.headers["Cache-Control"].startswith("no-store"), path
        if built:
            assert response.status_code == 200, path
            assert b"<html" in response.data.lower()
        else:
            assert response.status_code == 503, path
            assert b"not built" in response.data


def test_healthz(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.get_json() == {"ok": True, "status": "ok", "service": "asme-web"}


def test_api_health(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.get_json()["ok"] is True


@pytest.mark.parametrize("path", REMOVED)
def test_removed_pages_are_gone(client, users, path):
    assert client.get(path).status_code == 404, path


def test_removed_form_posts_are_gone(client, users):
    assert client.post("/login", data={"identifier": users["member"].email, "password": "x"}).status_code == 404
    assert client.post("/logout").status_code == 404


def test_unknown_api_paths_keep_json_envelope(client):
    for path in ("/api/nope", "/api/v1/nope"):
        response = client.get(path)
        assert response.status_code == 404, path
        assert response.get_json() == {"ok": False, "code": "not_found", "error": "Not found."}


def test_only_ops_and_api_blueprints_are_registered(app):
    assert set(app.blueprints) == {"api_v1", "api_legacy", "ops_api", "ops_app"}
    rules = {rule.rule for rule in app.url_map.iter_rules()}
    outside_api = {rule for rule in rules if not rule.startswith(("/api/", "/app"))}
    assert outside_api == {"/", "/healthz", "/static/<path:filename>"}
