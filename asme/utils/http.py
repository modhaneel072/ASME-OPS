"""Request/response helpers used by blueprints."""

from __future__ import annotations

import ipaddress

from flask import jsonify, request


def _clean_forwarded_address(value: str) -> str | None:
    """Return ``value`` as a bare IP address, or ``None`` if it is not one.

    Entries in ``X-Forwarded-For`` are written by machines we do not control, so
    anything that is not a plain IPv4/IPv6 address (a hostname, ``unknown``, a
    padded log line, an IPv6 zone identifier) is rejected rather than stored in
    an audit record or used as a rate-limit bucket key.
    """
    candidate = (value or "").strip().strip('"')
    if not candidate:
        return None
    if candidate.startswith("[") and "]" in candidate:  # [2001:db8::1]:443
        candidate = candidate[1 : candidate.index("]")]
    elif candidate.count(":") == 1:  # 203.0.113.7:54321
        candidate = candidate.split(":", 1)[0]
    candidate = candidate.split("%", 1)[0]
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return None


def request_client_ip():
    """The peer address used for rate limiting and audit records.

    ``X-Forwarded-For`` is written by the client unless a proxy we trust
    appended to it, so it is only consulted when ``ASME_TRUSTED_PROXY_COUNT``
    says how many proxies sit in front of the app. With ``n`` trusted proxies
    the client address is the ``n``-th entry counted from the right; everything
    further left was supplied by whoever made the request and must not be
    trusted. With the default of ``0`` the socket peer is used, which is the
    only address nobody can forge.

    A chain with fewer than ``n`` entries did not travel through the proxies we
    were told to expect - a request sent straight to the origin host, bypassing
    the CDN, looks like this - so its leftmost entry is whatever the caller
    typed. In that case the socket peer is used instead of believing the header.

    The residual risk, which no header can remove: if the origin host stays
    publicly reachable, a request sent directly to it travels through one proxy
    fewer than configured while still carrying ``n`` entries, and the value
    selected is then the caller's own. That is enough to pick a different
    rate-limit bucket and to write a wrong address into an audit row. It is not
    enough to get past the per-identifier login counter, which does not use the
    address at all.
    """
    trusted = 0
    try:
        from asme.config import settings

        trusted = max(0, int(settings().trusted_proxy_count))
    except (RuntimeError, KeyError, AttributeError, ValueError):
        trusted = 0
    if trusted:
        chain = [part.strip() for part in (request.headers.get("X-Forwarded-For") or "").split(",") if part.strip()]
        if len(chain) >= trusted:
            candidate = _clean_forwarded_address(chain[len(chain) - trusted])
            if candidate:
                return candidate[:120]
    return (request.remote_addr or "unknown")[:120]


def value_from_request(key, default=None):
    """Read a field from JSON body or form data, whichever the client sent."""
    if request.is_json:
        payload = request.get_json(silent=True) or {}
        return payload.get(key, default)
    return request.form.get(key, default)


def api_error(message, status=400, code="bad_request", **extra):
    body = {"ok": False, "error": message, "code": code}
    if extra:
        body.update(extra)
    return jsonify(body), status


def api_ok(payload=None, message=None, status=200):
    body = {"ok": True}
    if message is not None:
        body["message"] = message
    if payload is not None:
        body["payload"] = payload
    return jsonify(body), status


def idempotency_key():
    value = (request.headers.get("Idempotency-Key") or "").strip()
    if not value and request.is_json:
        value = str((request.get_json(silent=True) or {}).get("idempotency_key") or "").strip()
    if not value:
        value = (request.form.get("idempotency_key") or "").strip()
    return value[:120] or None
