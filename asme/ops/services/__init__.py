"""Domain services for ASME Ops. Every function takes a ``PolicyContext`` first,
enforces object-level authorization, writes audit events inside the same
transaction, and commits (reads never commit)."""
