"""Serves the ASME Ops single-page application at ``/app``, the ``/`` entry
redirect and the ``/healthz`` deploy health check.

The Vite build writes ``static/ops/index.html`` plus hashed assets under
``static/ops/assets/``. Every ``/app/*`` path returns the same shell (the SPA
router owns the rest); the shell is never cached because it references
hashed asset names that change on each build.
"""

from __future__ import annotations

from pathlib import Path

from flask import Blueprint, Response, current_app, jsonify, redirect, send_file

bp = Blueprint("ops_app", __name__)

NOT_BUILT_HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8"><title>ASME Ops</title>
<style>body{font-family:Inter,system-ui,sans-serif;background:#f8fafc;color:#111827;margin:0;display:grid;place-items:center;height:100vh}
main{max-width:520px;padding:32px;background:#fff;border:1px solid #d9e1ea;border-radius:8px}code{background:#f3f6f9;padding:2px 6px;border-radius:4px}</style></head>
<body><main><h1 style="font-size:20px;margin:0 0 8px">ASME Ops frontend is not built</h1>
<p>Run <code>npm install</code> and <code>npm run build</code> inside <code>apps/ops-web</code>, or start the dev server with <code>npm run dev</code> and open <code>http://127.0.0.1:5173/app</code>.</p></main></body></html>"""


def _index_path() -> Path:
    return Path(current_app.static_folder) / "ops" / "index.html"


def _no_store(response: Response) -> Response:
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response


@bp.get("/app")
@bp.get("/app/")
@bp.get("/app/<path:path>")
def spa(path: str = ""):
    index = _index_path()
    if not index.exists():
        return _no_store(Response(NOT_BUILT_HTML, status=503, mimetype="text/html"))
    return _no_store(send_file(index, mimetype="text/html", max_age=0, conditional=False))


@bp.get("/")
def root():
    return redirect("/app", code=302)


@bp.get("/healthz")
def healthz():
    """Load-balancer / platform health check. Unauthenticated and not logged."""
    return jsonify({"ok": True, "status": "ok", "service": "asme-web"})
