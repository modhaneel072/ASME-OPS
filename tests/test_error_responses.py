"""An unexpected failure on an API route must still answer with JSON.

The screens parse every ``/api/`` response as JSON. Without this the framework's
HTML error page reaches them and they show a blank breakage with nothing the
owner can search the logs for.
"""

from __future__ import annotations

from asme.extensions import db as _db
from tests.conftest import make_app


def _app_that_breaks():
    app = make_app()
    # Tests and the development debugger normally get the traceback instead.
    app.config["PROPAGATE_EXCEPTIONS"] = False

    @app.get("/api/v1/_break")
    def _api_break():
        raise RuntimeError("kaboom")

    @app.get("/_break")
    def _page_break():
        raise RuntimeError("kaboom")

    return app


def test_api_failures_answer_with_json_and_a_request_id():
    app = _app_that_breaks()
    with app.app_context():
        _db.create_all()
        response = app.test_client().get("/api/v1/_break")
        assert response.status_code == 500
        body = response.get_json()
        assert body["ok"] is False
        assert body["code"] == "server_error"
        assert body["error"] and "kaboom" not in body["error"]  # no internals leak out
        assert body["request_id"] == response.headers.get("X-Request-Id")
        _db.drop_all()


def test_page_failures_are_left_to_the_framework():
    app = _app_that_breaks()
    with app.app_context():
        _db.create_all()
        response = app.test_client().get("/_break")
        assert response.status_code == 500
        assert response.get_json(silent=True) is None
        _db.drop_all()


def test_http_errors_keep_their_own_shape():
    app = _app_that_breaks()
    with app.app_context():
        _db.create_all()
        client = app.test_client()
        assert client.get("/api/v1/does-not-exist").get_json()["code"] == "not_found"
        assert client.get("/does-not-exist").status_code == 404
        _db.drop_all()
