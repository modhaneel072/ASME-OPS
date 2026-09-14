"""Blueprint registration. Order matters only for URL rule precedence, which
these do not overlap."""

from __future__ import annotations


def register_blueprints(app):
    from asme.blueprints import api_legacy, api_v1, ops_app
    from asme.blueprints import ops as ops_api

    ops_api.register_routes()
    for module in (api_v1, api_legacy, ops_api, ops_app):
        app.register_blueprint(module.bp)
