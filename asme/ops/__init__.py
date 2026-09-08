"""ASME Ops domain package.

Everything the operations platform adds on top of the legacy application lives
here: tenant-scoped models (``ops_*`` tables), the permission registry and
policy engine, storage, numbering, bootstrap/seed data and the domain services.

Layering is the same as the rest of the app: blueprints parse, authorize and
serialize; services own transactions; nothing here reads ``os.environ``.
"""
