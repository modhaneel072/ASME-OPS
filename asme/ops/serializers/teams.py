"""JSON shapes for teams (``/api/v1/teams``).

``team`` is the list/summary shape from the plan's serializer contract;
``team_detail`` adds the full membership list.
"""

from __future__ import annotations

from asme.ops.serializers import iso, project_ref, uid, user_ref


def _member_sort_key(member) -> tuple:
    user = member.user
    name = (user.display_name if user is not None else "").lower()
    return (0 if member.is_lead else 1, name, member.user_id)


def team(t) -> dict:
    members = list(t.members)
    leads = sorted((m for m in members if m.is_lead), key=_member_sort_key)
    return {
        "id": uid(t.id),
        "name": t.name,
        "description": t.description,
        "parent_team_id": uid(t.parent_team_id),
        "project": project_ref(t.project),
        "leads": [user_ref(m.user) for m in leads],
        "member_count": len(members),
        "is_active": bool(t.is_active),
        "created_at": iso(t.created_at),
        "updated_at": iso(t.updated_at),
    }


def team_member(m) -> dict:
    return {"user": user_ref(m.user), "is_lead": bool(m.is_lead), "joined_at": iso(m.joined_at)}


def team_detail(t) -> dict:
    data = team(t)
    data["members"] = [team_member(m) for m in sorted(t.members, key=_member_sort_key)]
    return data
