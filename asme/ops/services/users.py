"""Member directory, invitations and role/status changes (``ops_memberships``).

The directory is the list of memberships in the organization joined to the
legacy ``users`` table; ``/users/:id`` routes key on the legacy integer id.

Legacy ``users.role`` is left alone by everything here with one documented
exception: making someone a ``chapter_admin`` also sets ``users.role = "admin"``
so the legacy portal agrees about who administers the chapter. Demotions never
touch it (``permissions.OPS_ROLES_IMPLYING_LEGACY_ADMIN``).

Invitations reuse the legacy password-reset flow, but **only for accounts this
call creates**: a set-password link is a credential for the account it points
at, so handing one to the inviter for an e-mail that already belongs to a live
account (a legacy portal user, a member of another chapter, a suspended member)
would be an account takeover. Someone who already has an account is added to
the chapter and signs in with the password they already use; the response says
so with ``invite_url = null``. Re-sending a lost invitation is deliberately not
supported here: the invitee can use "Forgot password" on the sign-in screen,
which e-mails a fresh link to the address itself rather than to the inviter.

A new invitee receives a link to ``/app/auth/reset-password?token=<token>``;
their first sign-in flips the membership from ``invited`` to ``active``
(``bootstrap.ensure_membership``).
"""

from __future__ import annotations

import secrets

from sqlalchemy import func, or_, select
from werkzeug.security import generate_password_hash

from asme import events
from asme.extensions import db
from asme.models import User
from asme.ops import bootstrap, permissions as registry, policy
from asme.ops.models import Membership, Role, Team, TeamMember
from asme.ops.models.identity import MEMBER_STATUSES
from asme.ops.services import audit_events, notifications
from asme.ops.types import parse_uuid
from asme.ops.validation import INT_MAX, INT_MIN, Field, ValidationErrors, validate
from asme.services import identity
from asme.services.errors import Conflict, Forbidden, NotFound, Validation

DIRECTORY_PERMISSIONS = ("team.read", "user.read")
FILTERS = {"role": "multi", "status": "multi", "team": "multi"}
SORTS = ("name", "joined_at", "last_login_at")
DEFAULT_SORT = "name"
PATCHABLE_STATUSES = ("active", "suspended")
MEMBERSHIP_FIELDS = ("role_id", "member_status", "title")
# ops role -> legacy users.role for accounts created by an invitation
LEGACY_ROLE_FOR_OPS = {"chapter_admin": "admin", "team_lead": "team_leader"}

UNKNOWN_ROLE = "Unknown role."
ROLE_KEY_OR_ID = "Provide either role_key or role_id, not both."
NOTHING_TO_UPDATE = "Provide role_key, role_id, status or title."
ADMIN_GRANT_DENIED = "Only a Chapter Administrator can grant the Chapter Administrator role."
INACTIVE_ACCOUNT = "That account is deactivated. Reactivate it in the members admin before inviting them."

INVITE_SPEC = {
    "email": Field("email", required=True, nullable=False, max_len=160),
    "name": Field("str", required=True, nullable=False, max_len=160, min_len=2),
    "role_key": Field("choice", choices=registry.SYSTEM_ROLE_KEYS, nullable=False, default="full_member"),
    "title": Field("str", max_len=120),
}
UPDATE_SPEC = {
    "role_key": Field("choice", choices=registry.SYSTEM_ROLE_KEYS, nullable=False),
    "role_id": Field("uuid", nullable=False),
    "status": Field("choice", choices=PATCHABLE_STATUSES, nullable=False),
    "title": Field("str", max_len=120),
}


# --------------------------------------------------------------------------- reads


def _bad_filter(message: str):
    return Validation(message, field="filter", code="bad_filter")


def directory_query(ctx, *, q: str = "", role_keys=None, statuses=None, team_ids=None, sort: str = DEFAULT_SORT):
    """Ordered membership query behind ``GET /users``.

    Suspended members are hidden unless the viewer holds ``user.manage`` or the
    ``status`` filter names them explicitly.
    """
    query = (
        Membership.query.filter(Membership.organization_id == ctx.org.id)
        .join(User, Membership.user_id == User.id)
        .join(Role, Membership.role_id == Role.id)
    )
    statuses = list(statuses or ())
    for status in statuses:
        if status not in MEMBER_STATUSES:
            raise _bad_filter("filter[status] must be one of: " + ", ".join(MEMBER_STATUSES) + ".")
    if statuses:
        query = query.filter(Membership.member_status.in_(statuses))
    elif not ctx.has("user.manage"):
        query = query.filter(Membership.member_status != "suspended")
    role_keys = list(role_keys or ())
    for key in role_keys:
        if key not in registry.SYSTEM_ROLE_KEYS:
            raise _bad_filter("filter[role] must contain system role keys.")
    if role_keys:
        query = query.filter(Role.system_key.in_(role_keys))
    teams = []
    for raw in team_ids or ():
        parsed = parse_uuid(raw)
        if parsed is None:
            raise _bad_filter("filter[team] must contain team identifiers.")
        teams.append(parsed)
    if teams:
        in_teams = (
            select(TeamMember.user_id)
            .join(Team, Team.id == TeamMember.team_id)
            .where(Team.organization_id == ctx.org.id, Team.id.in_(teams))
        )
        query = query.filter(Membership.user_id.in_(in_teams))
    text = (q or "").strip().lower()
    if text:
        like = f"%{text}%"
        query = query.filter(
            or_(
                func.lower(User.name).like(like),
                func.lower(User.email).like(like),
                func.lower(func.coalesce(User.username, "")).like(like),
            )
        )
    descending = sort.startswith("-")
    key = sort[1:] if descending else sort
    if key not in SORTS:
        raise Validation(f"Unknown sort '{sort}'.", field="sort", code="bad_sort")
    if key == "name":
        column = func.lower(User.name)
    elif key == "joined_at":
        column = Membership.joined_at
    else:
        column = User.last_login_at
    order = column.desc().nulls_last() if descending else column.asc().nulls_last()
    return query.order_by(order, Membership.id.asc())


def teams_for_users(ctx, user_ids) -> dict[int, list[Team]]:
    """``{user_id: [Team, ...]}`` for the organization's teams, ordered by name."""
    ids = sorted({user_id for user_id in user_ids if user_id})
    if not ids:
        return {}
    rows = db.session.execute(
        select(TeamMember.user_id, Team)
        .join(Team, Team.id == TeamMember.team_id)
        .where(Team.organization_id == ctx.org.id, TeamMember.user_id.in_(ids))
        .order_by(func.lower(Team.name), Team.id)
    ).all()
    grouped: dict[int, list[Team]] = {}
    for user_id, team in rows:
        grouped.setdefault(user_id, []).append(team)
    return grouped


def _membership_or_404(ctx, user_id) -> Membership:
    # Flask's <int:...> converter happily parses an id far larger than the
    # column, which the driver then refuses; no such member can exist.
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        raise NotFound()
    if not (INT_MIN <= user_id <= INT_MAX):
        raise NotFound()
    membership = Membership.query.filter_by(organization_id=ctx.org.id, user_id=user_id).first()
    if membership is None:
        raise NotFound()
    return membership


def get(ctx, user_id) -> Membership:
    """One directory entry by legacy user id; suspended members are 404 to
    viewers without ``user.manage`` (matching the list)."""
    membership = _membership_or_404(ctx, user_id)
    if membership.member_status == "suspended" and not ctx.has("user.manage"):
        raise NotFound()
    return membership


def list_roles(ctx) -> list[tuple[Role, int]]:
    """Every role of the organization with its ACTIVE member count, system
    roles first in registry order, then custom roles by name."""
    roles = Role.query.filter_by(organization_id=ctx.org.id).all()
    counts = dict(
        db.session.execute(
            select(Membership.role_id, func.count(Membership.id))
            .where(Membership.organization_id == ctx.org.id, Membership.member_status == "active")
            .group_by(Membership.role_id)
        ).all()
    )
    order = {key: index for index, key in enumerate(registry.SYSTEM_ROLE_KEYS)}
    roles.sort(key=lambda role: (order.get(role.system_key, len(order)), role.name.lower(), str(role.id)))
    return [(role, int(counts.get(role.id, 0))) for role in roles]


# --------------------------------------------------------------------------- helpers


def _validate_collecting(payload: dict, spec: dict, *, partial: bool = False) -> tuple[dict, dict[str, str]]:
    """``validate`` that keeps going: returns the cleaned values of the fields that
    passed plus the format errors, so semantic checks can add theirs and the
    client sees every bad field in one response."""
    try:
        return validate(payload, spec, partial=partial), {}
    except ValidationErrors as exc:
        payload = payload if isinstance(payload, dict) else {}
        good_spec = {name: field for name, field in spec.items() if name not in exc.errors}
        good_payload = {name: value for name, value in payload.items() if name in good_spec}
        return validate(good_payload, good_spec, partial=True), dict(exc.errors)


def _membership_snapshot(membership: Membership) -> dict:
    data = audit_events.snapshot(membership, MEMBERSHIP_FIELDS)
    data["role_key"] = membership.role.system_key if membership.role is not None else None
    data["status"] = data.pop("member_status")
    return data


def _active_admin_count(ctx, *, exclude_membership_id=None) -> int:
    stmt = (
        select(func.count(Membership.id))
        .join(Role, Role.id == Membership.role_id)
        .where(
            Membership.organization_id == ctx.org.id,
            Membership.member_status == "active",
            Role.system_key == "chapter_admin",
        )
    )
    if exclude_membership_id is not None:
        stmt = stmt.where(Membership.id != exclude_membership_id)
    return int(db.session.scalar(stmt) or 0)


def _sync_legacy_admin(user, role: Role) -> None:
    if role.system_key in registry.OPS_ROLES_IMPLYING_LEGACY_ADMIN and user.role != "admin":
        user.role = "admin"


# --------------------------------------------------------------------------- invite


def invite(ctx, payload: dict) -> tuple[Membership, str | None]:
    """Invite ``payload["email"]`` into the chapter.

    Returns the membership and, **only when this call created the account**, the
    password-reset token that forms the invite link (``None`` otherwise - see the
    module docstring for why an existing account never yields one).

    * unknown e-mail: a legacy ``User`` is created with a random password and an
      ``invited`` membership, and a set-password link is issued;
    * known e-mail without a membership: one is created; the person signs in with
      their existing credentials;
    * known e-mail with an ``invited``/``suspended`` membership: it is (re)set to
      ``invited``; no new credential is minted;
    * known e-mail with an active membership: 409 ``already_member``;
    * deactivated account: 409 ``inactive_account`` - reactivating someone is a
      deliberate act, not a side effect of an invitation.
    """
    policy.authorize(ctx, "user.manage")
    data = validate(payload, INVITE_SPEC)
    role = bootstrap.role_by_key(ctx.org, data["role_key"])
    if role is None:
        raise ValidationErrors({"role_key": UNKNOWN_ROLE})
    _guard_admin_grant(ctx, role)
    email = data["email"]
    user = User.query.filter(func.lower(User.email) == email).first()
    created_user = created_membership = False
    if user is not None:
        membership = Membership.query.filter_by(organization_id=ctx.org.id, user_id=user.id).first()
        if membership is not None and membership.member_status == "active":
            raise Conflict("That person is already an active member of this chapter.", code="already_member")
        if membership is None:
            membership = bootstrap.ensure_membership(user, ctx.org, commit=False)
            membership.created_by_user_id = ctx.user.id
            created_membership = True
        if not user.is_active:
            raise Conflict(INACTIVE_ACCOUNT, code="inactive_account")
        if membership.member_status != "active":
            membership.member_status = "invited"
    else:
        user = User(
            name=data["name"][:160],
            email=email,
            username=identity.make_unique_username(email.split("@", 1)[0]),
            password_hash=generate_password_hash(secrets.token_urlsafe(32)),
            role=LEGACY_ROLE_FOR_OPS.get(role.system_key, "member"),
            is_active=True,
        )
        db.session.add(user)
        db.session.flush()
        membership = Membership(
            organization_id=ctx.org.id,
            user_id=user.id,
            role_id=role.id,
            member_status="invited",
            created_by_user_id=ctx.user.id,
        )
        db.session.add(membership)
        created_user = created_membership = True
    membership.role = role
    membership.role_id = role.id
    if "title" in data:
        membership.title = data["title"]
    membership.updated_by_user_id = ctx.user.id
    _sync_legacy_admin(user, role)
    db.session.flush()
    audit_events.record(
        ctx,
        "membership.invited",
        membership,
        after=_membership_snapshot(membership),
        summary=f"Invited {user.email} as {role.name}",
        user_id=user.id,
        email=user.email,
        created_user=created_user,
        created_membership=created_membership,
        link_issued=created_user,
    )
    token = None
    if created_user:
        # Adds the reset token, records the legacy audit line and commits everything above.
        token = identity.admin_invite_link_token(user, ctx.user)
    else:
        db.session.commit()
    if created_membership:
        events.emit(events.MEMBERSHIP_CREATED, membership_id=str(membership.id), organization_id=str(ctx.org.id), user_id=user.id)
    return membership, token


# --------------------------------------------------------------------------- update


def _guard_admin_grant(ctx, role: Role | None) -> None:
    """Handing out ``chapter_admin`` is a ``role.manage`` act.

    ``user.manage`` alone (an executive officer) may move people between the
    other roles, but not mint the role that holds ``role.manage`` and
    ``chapter.settings.manage`` - otherwise those two withheld permissions are
    one invitation away, plus legacy portal admin through ``_sync_legacy_admin``.
    """
    if role is not None and role.system_key == "chapter_admin" and not ctx.is_chapter_admin:
        raise Forbidden(ADMIN_GRANT_DENIED, permission="role.manage")


def update(ctx, user_id, payload: dict) -> Membership:
    """Change a member's ops role, status or title (``PATCH /users/:id``)."""
    policy.authorize(ctx, "user.manage")
    membership = _membership_or_404(ctx, user_id)
    data, errors = _validate_collecting(payload, UPDATE_SPEC, partial=True)
    if not data and not errors:
        raise ValidationErrors({"payload": NOTHING_TO_UPDATE})
    new_role = None
    if "role_key" in data and "role_id" in data:
        errors["role_id"] = ROLE_KEY_OR_ID
    elif "role_key" in data:
        new_role = bootstrap.role_by_key(ctx.org, data["role_key"])
        if new_role is None:
            errors["role_key"] = UNKNOWN_ROLE
    elif "role_id" in data:
        new_role = db.session.get(Role, data["role_id"])
        if new_role is None or new_role.organization_id != ctx.org.id:
            new_role = None
            errors["role_id"] = UNKNOWN_ROLE
    if errors:
        raise ValidationErrors(errors)
    if new_role is not None and new_role.id != membership.role_id:
        _guard_admin_grant(ctx, new_role)

    role_changes = new_role is not None and new_role.id != membership.role_id
    status_changes = "status" in data and data["status"] != membership.member_status
    title_changes = "title" in data and data["title"] != membership.title
    if membership.user_id == ctx.user.id and (role_changes or status_changes):
        raise Conflict("You cannot change your own role or status.", code="cannot_modify_self")
    losing_admin = (
        membership.role.system_key == "chapter_admin"
        and membership.member_status == "active"
        and ((role_changes and new_role.system_key != "chapter_admin") or (status_changes and data["status"] != "active"))
    )
    if losing_admin and _active_admin_count(ctx, exclude_membership_id=membership.id) == 0:
        raise Conflict("At least one active Chapter Administrator must remain.", code="last_admin")
    if not (role_changes or status_changes or title_changes):
        return membership

    user = membership.user
    before = _membership_snapshot(membership)
    if role_changes:
        membership.role = new_role
        membership.role_id = new_role.id
        _sync_legacy_admin(user, new_role)
    if status_changes:
        membership.member_status = data["status"]
    if title_changes:
        membership.title = data["title"]
    membership.updated_by_user_id = ctx.user.id
    after = _membership_snapshot(membership)
    display = user.display_name if user is not None else str(membership.user_id)

    if role_changes:
        audit_events.record(
            ctx,
            "membership.role_changed",
            membership,
            before=before,
            after=after,
            summary=f"{display}: {before['role_key'] or 'custom'} -> {after['role_key'] or 'custom'}",
            user_id=membership.user_id,
        )
        notifications.notify(
            ctx,
            [membership.user_id],
            "membership.role_changed",
            f"Your role is now {new_role.name}",
            f"{ctx.user.display_name} changed your role in {ctx.org.name}.",
            entity=membership,
        )
    if status_changes:
        audit_events.record(
            ctx,
            "membership.status_changed",
            membership,
            before=before,
            after=after,
            summary=f"{display}: {before['status']} -> {after['status']}",
            user_id=membership.user_id,
        )
        notifications.notify(
            ctx,
            [membership.user_id],
            "membership.status_changed",
            "Your membership was reactivated" if after["status"] == "active" else "Your membership was suspended",
            f"{ctx.user.display_name} changed your membership status in {ctx.org.name}.",
            entity=membership,
        )
    if title_changes and not (role_changes or status_changes):
        audit_events.record(
            ctx,
            "membership.updated",
            membership,
            before=before,
            after=after,
            summary=f"Updated {display}'s title",
            user_id=membership.user_id,
        )
    db.session.commit()
    return membership
