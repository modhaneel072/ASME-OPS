"""JSON shapes for the member directory (``/api/v1/users``) and roles (``/api/v1/roles``).

``member`` serialises an ``ops_memberships`` row: its ``id`` is the membership
id, the legacy account lives under ``user`` (whose ``id`` is ``users.id``, the
integer the ``/users/:id`` routes key on).
"""

from __future__ import annotations

from asme.ops.serializers import iso, role_ref, team_ref, uid, user_ref


def member(m, teams=()) -> dict:
    user = m.user
    return {
        "id": uid(m.id),
        "user": user_ref(user),
        "role": role_ref(m.role),
        "status": m.member_status,
        "title": m.title,
        "teams": [team_ref(t) for t in teams],
        "joined_at": iso(m.joined_at),
        "last_login_at": iso(user.last_login_at) if user is not None else None,
    }


def role(r, member_count: int = 0) -> dict:
    grants = sorted(
        ({"key": grant.permission.key, "scope": grant.scope_type} for grant in r.grants if grant.permission),
        key=lambda grant: grant["key"],
    )
    return {
        "id": uid(r.id),
        "name": r.name,
        "system_key": r.system_key,
        "is_custom": bool(r.is_custom),
        "description": r.description,
        "member_count": int(member_count),
        "grants": grants,
    }


def roles(rows) -> list[dict]:
    """``rows`` is an iterable of ``(Role, active_member_count)`` pairs, already ordered."""
    return [role(r, count) for r, count in rows]
