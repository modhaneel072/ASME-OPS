"""Request/response helpers used by blueprints."""

from __future__ import annotations

from flask import jsonify, request


def request_client_ip():
    """The peer address used for rate limiting and audit records.

    ``X-Forwarded-For`` is written by the client unless a proxy we trust
    appended to it, so it is only consulted when ``ASME_TRUSTED_PROXY_COUNT``
    says how many proxies sit in front of the app. With ``n`` trusted proxies
    the client address is the ``n``-th entry counted from the right; everything
    further left was supplied by whoever made the request and must not be
    trusted. With the default of ``0`` the socket peer is used, which is the
    only address nobody can forge.
    """
    trusted = 0
    try:
        from asme.config import settings

        trusted = max(0, int(settings().trusted_proxy_count))
    except (RuntimeError, KeyError, AttributeError, ValueError):
        trusted = 0
    if trusted:
        chain = [part.strip() for part in (request.headers.get("X-Forwarded-For") or "").split(",") if part.strip()]
        if chain:
            return chain[max(0, len(chain) - trusted)][:120]
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
