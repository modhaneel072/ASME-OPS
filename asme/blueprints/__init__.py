"""Blueprint registration. Order matters only for URL rule precedence, which
these do not overlap."""

from __future__ import annotations


def register_blueprints(app):
    from asme.blueprints import admin, api_legacy, api_v1, auth, kiosk, legacy_ops, ops_app, portal, public
    from asme.blueprints import ops as ops_api

    ops_api.register_routes()
    for module in (public, auth, kiosk, portal, admin, api_v1, api_legacy, legacy_ops, ops_api, ops_app):
        app.register_blueprint(module.bp)
