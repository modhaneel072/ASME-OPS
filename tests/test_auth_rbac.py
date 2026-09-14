from urllib.parse import parse_qs, urlsplit

from flask import Blueprint, g, jsonify

from asme.auth.session import require_entitlement, require_login, require_role
from asme.constants import ENT_SHOP_ACCESS
from asme.services.onboarding import entitlements
from tests.conftest import PASSWORD, login


def _register_probes(app):
    """Non-API pages guarded by each decorator, to exercise the browser denial paths."""
    bp = Blueprint("auth_probe", __name__)

    @bp.get("/probe/login")
    @require_login
    def probe_login():
        return jsonify({"ok": True})

    @bp.get("/probe/lead")
    @require_role("team_leader")
    def probe_lead():
        return jsonify({"ok": True})

    @bp.get("/probe/shop")
    @require_entitlement(ENT_SHOP_ACCESS)
    def probe_shop():
        return jsonify({"ok": True})

    app.register_blueprint(bp)


def test_login_success_and_session_guard(client, users):
    response = login(client, users["member"])
    assert response.status_code == 200
    assert response.get_json()["payload"]["user"]["name"] == "Mo Member"
    me = client.get("/api/v1/me")
    assert me.status_code == 200
    assert me.get_json()["payload"]["user"]["email"] == "mo@uiowa.edu"
    assert "no-store" in me.headers.get("Cache-Control", "")


def test_login_rejects_bad_password(client, users):
    response = client.post("/api/v1/auth/login", json={"identifier": users["member"].email, "password": "nope"})
    assert response.status_code == 401
    assert response.get_json()["code"] == "invalid_credentials"
    assert client.get("/api/v1/me").status_code == 401


def test_login_rate_limit(app, users):
    app.extensions["asme_login_rate_limiter"].max_attempts = 2
    client = app.test_client()
    for _ in range(2):
        client.post("/api/v1/auth/login", json={"identifier": users["member"].email, "password": "nope"})
    response = client.post("/api/v1/auth/login", json={"identifier": users["member"].email, "password": PASSWORD})
    assert response.status_code == 429
    assert response.get_json()["code"] == "rate_limited"


def test_member_cannot_use_lead_routes(client, users, login_as):
    login_as(users["member"])
    response = client.get("/api/v1/availability")
    assert response.status_code == 403
    assert response.get_json() == {"ok": False, "code": "forbidden", "error": "You do not have permission to do that."}


def test_json_routes_get_json_denials(client):
    response = client.get("/api/v1/me")
    assert response.status_code == 401
    assert response.get_json()["code"] == "login_required"


def test_browser_login_denial_redirects_to_app_sign_in(app, users):
    _register_probes(app)
    client = app.test_client()
    response = client.get("/probe/login", headers={"Accept": "text/html"})
    assert response.status_code == 302
    location = urlsplit(response.headers["Location"])
    assert location.path == "/app/auth/login"
    assert parse_qs(location.query) == {"next": ["/probe/login"]}

    json_client = app.test_client()
    denied = json_client.get("/probe/login", headers={"Accept": "application/json"})
    assert denied.status_code == 401 and denied.get_json()["code"] == "login_required"


def test_browser_role_denial_is_json_403(app, users):
    _register_probes(app)
    client = app.test_client()
    assert login(client, users["member"]).status_code == 200
    response = client.get("/probe/lead", headers={"Accept": "text/html"})
    assert response.status_code == 403
    assert response.get_json()["code"] == "forbidden"
    assert "Location" not in response.headers

    lead = app.test_client()
    assert login(lead, users["lead"]).status_code == 200
    assert lead.get("/probe/lead", headers={"Accept": "text/html"}).status_code == 200


def test_browser_entitlement_denial_is_json_403(enforced_app):
    from tests.conftest import _db, _user

    member = _user("Mo Member", "mo@uiowa.edu", "member")
    _db.session.commit()
    _register_probes(enforced_app)
    client = enforced_app.test_client()
    assert login(client, member).status_code == 200
    response = client.get("/probe/shop", headers={"Accept": "text/html"})
    assert response.status_code == 403
    body = response.get_json()
    assert body["code"] == "entitlement_required"
    assert body["entitlement"] == ENT_SHOP_ACCESS
    assert body["phase"] == "shop_ready"


def test_shadow_mode_lets_checkout_through_and_records_block(client, users, item, login_as):
    login_as(users["member"])
    assert not entitlements.has_entitlement(users["member"], ENT_SHOP_ACCESS)
    with client:
        response = client.post("/api/v1/checkouts", json={"item_id": item.id, "qty": 1}, headers={"Idempotency-Key": "shadow-1"})
        assert response.status_code == 201, response.data
        assert ENT_SHOP_ACCESS in g.shadow_entitlement_blocks
    assert response.get_json()["payload"]["checkout"]["state"] == "open"


def test_enforced_mode_blocks_checkout_with_phase_hint(enforced_app, monkeypatch):
    from tests.conftest import _db, _user

    member = _user("Mo Member", "mo@uiowa.edu", "member")
    from asme.models import Item

    row = Item(name="Mill", total_qty=1, available_qty=1, active=True)
    _db.session.add(row)
    _db.session.commit()
    client = enforced_app.test_client()
    login(client, member)
    response = client.post(
        "/api/v1/checkouts",
        json={"item_id": row.id, "qty": 1},
        headers={"Idempotency-Key": "k1"},
    )
    assert response.status_code == 403
    body = response.get_json()
    assert body["code"] == "entitlement_required"
    assert body["entitlement"] == ENT_SHOP_ACCESS
    assert body["phase"] == "shop_ready"


def test_admin_bypasses_entitlements(enforced_app):
    from tests.conftest import _db, _user

    admin = _user("Ada", "ada@uiowa.edu", "admin")
    _db.session.commit()
    assert entitlements.has_entitlement(admin, ENT_SHOP_ACCESS)


def test_logout_clears_session(client, users, login_as):
    login_as(users["member"])
    assert client.get("/api/v1/me").status_code == 200
    assert client.post("/api/v1/auth/logout", json={}).status_code == 200
    assert client.get("/api/v1/me").status_code == 401
