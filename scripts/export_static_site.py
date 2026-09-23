"""Export the public welcome page as a static site for GitHub Pages.

    python scripts/export_static_site.py [out_dir]      (default: _site)

GitHub Pages can only host static files, so this renders ``/`` through the
Flask app, rewrites every asset URL to a relative path (Pages serves project
sites from ``/<repo>/``, so absolute ``/static/...`` paths would break), and
copies the assets next to it.

Links into the rest of the Flask app (events, join, gallery, login ...) are
prefixed with ``ASME_APP_URL`` when that environment variable is set, e.g.
``https://asme-at-iowa.onrender.com``. Without it they are left relative and
will not resolve on Pages; the landing page itself is complete either way.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_ROUTES = ["/events", "/projects", "/gallery", "/contact", "/join", "/sponsors", "/login", "/portal", "/intro", "/who-we-are"]


def export(out: Path) -> None:
    os.environ.setdefault("ASME_OUTBOX_WORKER", "0")
    sys.path.insert(0, str(ROOT))
    from app import app  # noqa: WPS433  (import after the environment is set)

    html = app.test_client().get("/").get_data(as_text=True)

    html = re.sub(r'/static/css/welcome\.css\?v=\w+', "welcome.css", html)
    html = re.sub(r'/static/js/welcome\.js\?v=\w+', "welcome.js", html)
    html = re.sub(r"/static/images/executive/([\w\-]+\.jpg)", r"images/\1", html)
    html = html.replace("/static/asme_logo.png", "asme_logo.png")
    html = html.replace('<a class="wordmark" href="/">', '<a class="wordmark" href="./">')
    # og:image needs an absolute URL; the page is only shared once it has a real host.
    html = re.sub(r'<meta property="og:image" content="[^"]*">\n', "", html)

    app_url = (os.environ.get("ASME_APP_URL") or "").rstrip("/")
    if app_url:
        for route in APP_ROUTES:
            html = html.replace(f'href="{route}"', f'href="{app_url}{route}"')

    if out.exists():
        shutil.rmtree(out)
    (out / "images").mkdir(parents=True)
    (out / "index.html").write_text(html, encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    shutil.copy(ROOT / "static/css/welcome.css", out / "welcome.css")
    shutil.copy(ROOT / "static/js/welcome.js", out / "welcome.js")
    shutil.copy(ROOT / "static/asme_logo.png", out / "asme_logo.png")
    referenced = set(re.findall(r"images/([\w\-]+\.jpg)", html))
    for name in sorted(referenced):
        shutil.copy(ROOT / "static/images/executive" / name, out / "images" / name)

    leftover = html.count("/static/")
    size_kb = sum(f.stat().st_size for f in out.rglob("*") if f.is_file()) // 1024
    print(f"exported {out} ({size_kb} KB, {len(referenced)} portraits, {leftover} unresolved /static refs)")
    if leftover:
        raise SystemExit("unresolved /static references remain")


if __name__ == "__main__":
    export(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "_site")
