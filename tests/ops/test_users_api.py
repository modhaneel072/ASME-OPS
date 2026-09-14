"""Member directory, invitations, role/status changes and the roles list."""

from __future__ import annotations

import uuid
from urllib.parse import parse_qs, urlparse

from asme import events as event_bus
from asme.extensions import db as _db
from asme.models import PasswordResetToken, User
from asme.ops import bootstrap, permissions as registry
from asme.ops.models import AuditEvent, Membership, Notification, Organization, Role, Team, TeamMember
from asme.services import identity
from tests.conftest import PASSWORD
from tests.ops.conftest import make_user


def _membership(org, user) -> Membership:
    return bootstrap.membership_for(user, org)


def _team(org, name, *members, lead=None):
    team = Team(organization_id=org.id, name=name)
    _db.session.add(team)
    _db.session.flush()
    if lead is not None:
        team.members.append(TeamMember(user_id=lead.id, is_lead=True))
    for user in members:
        team.members.append(TeamMember(user_id=user.id, is_lead=False))
    _db.session.commit()
    return team


def _other_org_member(name="Far Away", email="far@other.edu"):
    other = Organization(name="Other Chapter", slug="other")
    _db.session.add(other)
    _db.session.flush()
    role = Role(organization_id=other.id, name="Chapter Administrator", system_key="chapter_admin")
    _db.session.add(role)
    _db.session.flush()
    user = make_user(name, email)
    _db.session.add(Membership(organization_id=other.id, user_id=user.id, role_id=role.id))
    _db.session.commit()
    return other, user


def _items(client, query=""):
    response = client.get(f"/api/v1/users{query}")
    assert response.status_code == 200, response.get_json()
    return response.get_json()["payload"]


# --------------------------------------------------------------------------- directory


def test_directory_shape_search_filters_and_sort(client, org, users, api_login):
    arm = _team(org, "Arm", users["member"], lead=users["lead"])
    wheels = _team(org, "Wheels", users["lead"])
    api_login(users["admin"])

    payload = _items(client)
    assert payload["total"] == 3 and payload["next_cursor"] is None
    by_user = {item["user"]["id"]: item for item in payload["items"]}
    assert [item["user"]["name"] for item in payload["items"]] == ["Ada Admin", "Lee Lead", "Mo Member"]
    lead = by_user[users["lead"].id]
    assert set(lead) == {"id", "user", "role", "status", "title", "teams", "joined_at", "last_login_at"}
    assert lead["id"] == str(_membership(org, users["lead"]).id)
    assert lead["user"] == {"id": users["lead"].id, "name": "Lee Lead", "email": "lee@uiowa.edu", "avatar_url": None}
    assert lead["role"]["system_key"] == "team_lead" and lead["role"]["name"] == "Team Lead" and lead["role"]["id"]
    assert lead["status"] == "active" and lead["joined_at"].endswith("Z")
    assert [t["name"] for t in lead["teams"]] == ["Arm", "Wheels"]
    assert lead["teams"][0] == {"id": str(arm.id), "name": "Arm"}
    assert by_user[users["member"].id]["teams"] == [{"id": str(arm.id), "name": "Arm"}]
    assert by_user[users["admin"].id]["teams"] == []
    # the admin logged in through the API, so last_login_at is populated for them only
    assert by_user[users["admin"].id]["last_login_at"] and lead["last_login_at"] is None

    def names(query):
        return [item["user"]["name"] for item in _items(client, query)["items"]]

    assert names("?q=lee") == ["Lee Lead"]
    assert names("?q=MO@UIOWA") == ["Mo Member"]
    assert names("?q=ada") == ["Ada Admin"]  # username match
    assert names("?filter[role]=team_lead") == ["Lee Lead"]
    assert names("?filter[role]=team_lead,full_member") == ["Lee Lead", "Mo Member"]
    assert names(f"?filter[team]={arm.id}") == ["Lee Lead", "Mo Member"]
    assert names(f"?filter[team]={wheels.id}") == ["Lee Lead"]
    assert names("?sort=-name") == ["Mo Member", "Lee Lead", "Ada Admin"]
    assert names("?sort=-last_login_at")[0] == "Ada Admin"
    assert names("?sort=joined_at") == ["Ada Admin", "Lee Lead", "Mo Member"]
    assert names("?filter[status]=active") == ["Ada Admin", "Lee Lead", "Mo Member"]
    assert names("?filter[status]=invited") == []

    page = _items(client, "?limit=2")
    assert len(page["items"]) == 2 and page["total"] == 3 and page["next_cursor"]
    assert [i["user"]["name"] for i in _items(client, f"?limit=2&cursor={page['next_cursor']}")["items"]] == ["Mo Member"]

    assert client.get("/api/v1/users?filter[bogus]=1").status_code == 400
    assert client.get("/api/v1/users?sort=email").status_code == 400
    assert client.get("/api/v1/users?filter[role]=galactic_overlord").status_code == 400
    assert client.get("/api/v1/users?filter[status]=vaporised").status_code == 400
    assert client.get("/api/v1/users?filter[team]=nope").status_code == 400


def test_directory_gate_accepts_team_read_or_user_read(client, org, users, requester, api_login):
    api_login(requester)
    denied = client.get("/api/v1/users")
    assert denied.status_code == 403 and denied.get_json()["permission"] == ["team.read", "user.read"]
    assert client.get(f"/api/v1/users/{users['lead'].id}").status_code == 403

    api_login(users["member"])  # team.read only
    assert client.get("/api/v1/users").status_code == 200
    assert client.get(f"/api/v1/users/{users['lead'].id}").status_code == 200

    advisor = make_user("Dr. Advisor", "advisor@uiowa.edu", ops_role="faculty_advisor", org=org)  # user.read only
    api_login(advisor)
    assert client.get("/api/v1/users").status_code == 200


def test_suspended_members_visible_only_to_managers_unless_asked(client, org, users, api_login):
    suspended = make_user("Sue Suspended", "sue@uiowa.edu", org=org)
    _membership(org, suspended).member_status = "suspended"
    _db.session.commit()

    api_login(users["member"])
    assert "Sue Suspended" not in [i["user"]["name"] for i in _items(client)["items"]]
    assert _items(client)["total"] == 3
    assert [i["user"]["name"] for i in _items(client, "?filter[status]=suspended")["items"]] == ["Sue Suspended"]
    assert client.get(f"/api/v1/users/{suspended.id}").status_code == 404

    api_login(users["admin"])
    listed = _items(client)
    assert listed["total"] == 4 and "Sue Suspended" in [i["user"]["name"] for i in listed["items"]]
    detail = client.get(f"/api/v1/users/{suspended.id}")
    assert detail.status_code == 200 and detail.get_json()["payload"]["member"]["status"] == "suspended"


def test_get_member_by_legacy_user_id_and_cross_organization(client, org, users, api_login):
    _other, far = _other_org_member()
    api_login(users["admin"])
    detail = client.get(f"/api/v1/users/{users['lead'].id}")
    assert detail.status_code == 200
    member = detail.get_json()["payload"]["member"]
    assert member["user"]["id"] == users["lead"].id and member["role"]["system_key"] == "team_lead" and member["teams"] == []

    assert client.get(f"/api/v1/users/{far.id}").status_code == 404
    assert client.get("/api/v1/users/999999").status_code == 404
    assert client.get("/api/v1/users/not-an-int").status_code == 404
    assert client.patch(f"/api/v1/users/{far.id}", json={"role_key": "requester"}).status_code == 404
    assert _membership(org, far) is None
    assert Membership.query.filter_by(user_id=far.id).one().role.system_key == "chapter_admin"  # untouched
    assert [i["user"]["id"] for i in _items(client)["items"] if i["user"]["id"] == far.id] == []


# --------------------------------------------------------------------------- invite


def test_invite_new_user_creates_login_membership_and_link(client, org, users, api_login, captured_events):
    api_login(users["admin"])
    response = client.post(
        "/api/v1/users/invite",
        json={"email": "New.Person@UIowa.edu", "name": "New Person", "role_key": "team_lead", "title": "Wheels lead"},
    )
    assert response.status_code == 201, response.get_json()
    payload = response.get_json()["payload"]
    member = payload["member"]
    assert member["status"] == "invited" and member["role"]["system_key"] == "team_lead" and member["title"] == "Wheels lead"
    assert member["user"]["email"] == "new.person@uiowa.edu" and member["user"]["name"] == "New Person"
    assert member["teams"] == [] and member["last_login_at"] is None

    user = User.query.filter_by(email="new.person@uiowa.edu").one()
    assert user.username == "newperson" and user.role == "team_leader" and user.is_active is True
    assert user.password_hash and not user.password_hash.startswith("$fake")
    membership = _membership(org, user)
    assert membership.member_status == "invited" and membership.role.system_key == "team_lead"
    assert membership.created_by_user_id == users["admin"].id

    invite_url = urlparse(payload["invite_url"])
    assert invite_url.scheme == "http" and invite_url.netloc == "localhost" and invite_url.path == "/app/auth/reset-password"
    assert invite_url.query == ""
    token = parse_qs(invite_url.fragment)["token"][0]
    reset = PasswordResetToken.query.filter_by(user_id=user.id).one()
    assert reset.token == identity.hash_reset_token(token) and reset.used_at is None

    event = AuditEvent.query.filter_by(event_type="membership.invited").one()
    assert event.entity_type == "membership" and event.entity_id == str(membership.id)
    assert event.after_json["role_key"] == "team_lead" and event.after_json["status"] == "invited"
    assert event.metadata_json["created_user"] is True
    assert (event_bus.MEMBERSHIP_CREATED, {"membership_id": str(membership.id), "organization_id": str(org.id), "user_id": user.id}) in captured_events

    # the invitee cannot log in until they set a password through the link ...
    unset = client.post("/api/v1/auth/login", json={"identifier": user.email, "password": PASSWORD})
    assert unset.status_code == 401
    # ... then the first sign-in activates the membership
    status = client.post("/api/v1/auth/reset-password/status", json={"token": token})
    assert status.status_code == 200 and status.get_json()["payload"]["purpose"] == "invite"
    done = client.post("/api/v1/auth/reset-password", json={"token": token, "password": "brand-new-secret", "confirm_password": "brand-new-secret"})
    assert done.status_code == 200, done.get_json()
    api_login(user, password="brand-new-secret")
    assert _membership(org, user).member_status == "active"
    session = client.get("/api/v1/session").get_json()["payload"]
    assert session["membership"]["role"]["system_key"] == "team_lead" and session["membership"]["status"] == "active"


def test_invite_defaults_role_and_maps_chapter_admin_to_legacy_admin(client, org, users, api_login):
    api_login(users["admin"])
    plain = client.post("/api/v1/users/invite", json={"email": "plain@uiowa.edu", "name": "Plain Member"})
    assert plain.status_code == 201
    assert plain.get_json()["payload"]["member"]["role"]["system_key"] == "full_member"
    assert User.query.filter_by(email="plain@uiowa.edu").one().role == "member"

    admin = client.post("/api/v1/users/invite", json={"email": "boss@uiowa.edu", "name": "Big Boss", "role_key": "chapter_admin"})
    assert admin.status_code == 201
    assert User.query.filter_by(email="boss@uiowa.edu").one().role == "admin"

    # usernames stay unique when the local part collides with an existing username
    clash = client.post("/api/v1/users/invite", json={"email": "ada@example.org", "name": "Other Ada"})
    assert clash.status_code == 201
    assert User.query.filter_by(email="ada@example.org").one().username == "ada2"


def test_invite_validation_conflicts_and_permission(client, org, users, requester, api_login):
    api_login(users["admin"])
    empty = client.post("/api/v1/users/invite", json={})
    assert empty.status_code == 400 and set(empty.get_json()["errors"]) == {"email", "name"}
    bad = client.post("/api/v1/users/invite", json={"email": "not-an-email", "name": "X", "role_key": "overlord", "title": "t" * 200})
    assert bad.status_code == 400 and set(bad.get_json()["errors"]) == {"email", "name", "role_key", "title"}

    taken = client.post("/api/v1/users/invite", json={"email": "LEE@uiowa.edu", "name": "Lee Again"})
    assert taken.status_code == 409 and taken.get_json()["code"] == "already_member"
    assert User.query.count() == 4  # admin, lead, member, requester

    api_login(requester)
    denied = client.post("/api/v1/users/invite", json={"email": "friend@uiowa.edu", "name": "Friend"})
    assert denied.status_code == 403 and denied.get_json()["permission"] == ["user.manage"]
    assert User.query.filter_by(email="friend@uiowa.edu").first() is None
    assert AuditEvent.query.filter_by(event_type="membership.invited").count() == 0


def test_invite_existing_users(client, org, users, api_login, captured_events):
    legacy = make_user("Old Timer", "old@uiowa.edu", legacy_role="team_leader")  # login exists, no ops membership yet
    invited = make_user("Ivy Invited", "ivy@uiowa.edu", org=org)
    _membership(org, invited).member_status = "invited"
    deactivated = make_user("Dee Activated", "dee@uiowa.edu", org=org)
    deactivated.is_active = False
    _membership(org, deactivated).member_status = "suspended"
    _db.session.commit()

    api_login(users["admin"])
    joined = client.post("/api/v1/users/invite", json={"email": "old@uiowa.edu", "name": "ignored", "role_key": "project_lead"})
    assert joined.status_code == 201, joined.get_json()
    member = joined.get_json()["payload"]["member"]
    assert member["status"] == "active" and member["role"]["system_key"] == "project_lead"
    assert member["user"]["name"] == "Old Timer"  # existing profile is left alone
    assert legacy.role == "team_leader"  # legacy role untouched unless promoted to chapter_admin
    assert legacy.password_hash and legacy.username == "old"
    assert User.query.filter_by(email="old@uiowa.edu").count() == 1
    assert any(name == event_bus.MEMBERSHIP_CREATED and payload["user_id"] == legacy.id for name, payload in captured_events)

    # An account that already exists keeps its own credentials: no link, no reset token.
    assert joined.get_json()["payload"]["invite_url"] is None
    assert PasswordResetToken.query.filter_by(user_id=legacy.id).count() == 0

    again = client.post("/api/v1/users/invite", json={"email": "ivy@uiowa.edu", "name": "Ivy", "role_key": "shop_operator"})
    assert again.status_code == 201
    assert again.get_json()["payload"]["member"]["status"] == "invited"
    assert again.get_json()["payload"]["invite_url"] is None
    assert _membership(org, invited).role.system_key == "shop_operator"
    assert PasswordResetToken.query.filter_by(user_id=invited.id).count() == 0
    assert Membership.query.filter_by(user_id=invited.id).count() == 1

    # Reactivating a disabled account is a deliberate admin act, never an invitation side effect.
    revived = client.post("/api/v1/users/invite", json={"email": "dee@uiowa.edu", "name": "Dee"})
    assert revived.status_code == 409 and revived.get_json()["code"] == "inactive_account"
    assert deactivated.is_active is False

    # A brand-new account is the only case that mints a set-password link.
    fresh = client.post("/api/v1/users/invite", json={"email": "fresh@uiowa.edu", "name": "Fresh Face"})
    assert fresh.status_code == 201
    fresh_user = User.query.filter_by(email="fresh@uiowa.edu").one()
    assert "/app/auth/reset-password#token=" in fresh.get_json()["payload"]["invite_url"]
    assert PasswordResetToken.query.filter_by(user_id=fresh_user.id).count() == 1

    promoted = client.post("/api/v1/users/invite", json={"email": "old@uiowa.edu", "name": "Old Timer", "role_key": "chapter_admin"})
    assert promoted.status_code == 409 and promoted.get_json()["code"] == "already_member"
    assert AuditEvent.query.filter_by(event_type="membership.invited").count() == 3


# --------------------------------------------------------------------------- patch


def test_patch_member_role_status_title(client, org, users, api_login):
    api_login(users["admin"])
    lead = users["lead"]

    changed = client.patch(f"/api/v1/users/{lead.id}", json={"role_key": "project_lead", "title": "Rover lead"})
    assert changed.status_code == 200, changed.get_json()
    member = changed.get_json()["payload"]["member"]
    assert member["role"]["system_key"] == "project_lead" and member["title"] == "Rover lead" and member["status"] == "active"
    assert lead.role == "team_leader"  # legacy role untouched
    event = AuditEvent.query.filter_by(event_type="membership.role_changed").one()
    assert event.before_json["role_key"] == "team_lead" and event.after_json["role_key"] == "project_lead"
    assert event.entity_id == member["id"]
    note = Notification.query.filter_by(user_id=lead.id, type="membership.role_changed").one()
    assert "Project Lead" in note.title

    role_id = bootstrap.role_by_key(org, "treasurer").id
    by_id = client.patch(f"/api/v1/users/{lead.id}", json={"role_id": str(role_id)})
    assert by_id.status_code == 200 and by_id.get_json()["payload"]["member"]["role"]["system_key"] == "treasurer"

    suspended = client.patch(f"/api/v1/users/{lead.id}", json={"status": "suspended"})
    assert suspended.status_code == 200 and suspended.get_json()["payload"]["member"]["status"] == "suspended"
    status_event = AuditEvent.query.filter_by(event_type="membership.status_changed").one()
    assert status_event.before_json["status"] == "active" and status_event.after_json["status"] == "suspended"

    # a suspended member can still authenticate but has no workspace
    api_login(lead)
    locked = client.get("/api/v1/session")
    assert locked.status_code == 403 and locked.get_json()["code"] == "no_membership"

    api_login(users["admin"])
    restored = client.patch(f"/api/v1/users/{lead.id}", json={"status": "active"})
    assert restored.status_code == 200 and restored.get_json()["payload"]["member"]["status"] == "active"
    api_login(lead)
    assert client.get("/api/v1/session").status_code == 200
    assert AuditEvent.query.filter_by(event_type="membership.status_changed").count() == 2
    api_login(users["admin"])

    title_only = client.patch(f"/api/v1/users/{lead.id}", json={"title": None})
    assert title_only.status_code == 200 and title_only.get_json()["payload"]["member"]["title"] is None
    assert AuditEvent.query.filter_by(event_type="membership.updated").count() == 1
    assert AuditEvent.query.filter_by(event_type="membership.role_changed").count() == 2

    # a no-op role change writes nothing
    noop = client.patch(f"/api/v1/users/{lead.id}", json={"role_key": "treasurer"})
    assert noop.status_code == 200
    assert AuditEvent.query.filter_by(event_type="membership.role_changed").count() == 2

    # invited members can be activated directly
    invited = make_user("Ivy Invited", "ivy@uiowa.edu", org=org)
    _membership(org, invited).member_status = "invited"
    _db.session.commit()
    activated = client.patch(f"/api/v1/users/{invited.id}", json={"status": "active"})
    assert activated.status_code == 200 and activated.get_json()["payload"]["member"]["status"] == "active"


def test_patch_member_promotion_sets_legacy_admin_but_demotion_leaves_it(client, org, users, api_login):
    api_login(users["admin"])
    member = users["member"]
    promoted = client.patch(f"/api/v1/users/{member.id}", json={"role_key": "chapter_admin"})
    assert promoted.status_code == 200
    assert member.role == "admin"
    demoted = client.patch(f"/api/v1/users/{member.id}", json={"role_key": "full_member"})
    assert demoted.status_code == 200 and demoted.get_json()["payload"]["member"]["role"]["system_key"] == "full_member"
    assert member.role == "admin"


def test_patch_member_rules_validation_and_permission(client, org, users, requester, api_login):
    admin = users["admin"]
    officer = make_user("Ex Officer", "exec@uiowa.edu", ops_role="executive_officer", org=org)
    second_admin = make_user("Second Admin", "admin2@uiowa.edu", ops_role="chapter_admin", org=org)

    api_login(admin)
    for body in ({"role_key": "treasurer"}, {"status": "suspended"}, {"role_id": str(bootstrap.role_by_key(org, "treasurer").id)}):
        response = client.patch(f"/api/v1/users/{admin.id}", json=body)
        assert response.status_code == 409 and response.get_json()["code"] == "cannot_modify_self"
    own_title = client.patch(f"/api/v1/users/{admin.id}", json={"title": "President", "role_key": "chapter_admin"})
    assert own_title.status_code == 200 and own_title.get_json()["payload"]["member"]["title"] == "President"

    empty = client.patch(f"/api/v1/users/{users['lead'].id}", json={})
    assert empty.status_code == 400 and empty.get_json()["code"] == "validation"
    bad = client.patch(f"/api/v1/users/{users['lead'].id}", json={"role_key": "overlord", "status": "banished", "title": "t" * 200})
    assert bad.status_code == 400 and set(bad.get_json()["errors"]) == {"role_key", "status", "title"}
    both = client.patch(f"/api/v1/users/{users['lead'].id}", json={"role_key": "treasurer", "role_id": str(uuid.uuid4())})
    assert both.status_code == 400 and set(both.get_json()["errors"]) == {"role_id"}
    unknown_role = client.patch(f"/api/v1/users/{users['lead'].id}", json={"role_id": str(uuid.uuid4())})
    assert unknown_role.status_code == 400 and set(unknown_role.get_json()["errors"]) == {"role_id"}
    invited_status = client.patch(f"/api/v1/users/{users['lead'].id}", json={"status": "invited"})
    assert invited_status.status_code == 400 and set(invited_status.get_json()["errors"]) == {"status"}

    # two admins: demoting one is fine
    demote = client.patch(f"/api/v1/users/{second_admin.id}", json={"role_key": "full_member"})
    assert demote.status_code == 200

    # now Ada is the last active chapter admin
    api_login(officer)
    last = client.patch(f"/api/v1/users/{admin.id}", json={"role_key": "full_member"})
    assert last.status_code == 409 and last.get_json()["code"] == "last_admin"
    last = client.patch(f"/api/v1/users/{admin.id}", json={"status": "suspended"})
    assert last.status_code == 409 and last.get_json()["code"] == "last_admin"
    title = client.patch(f"/api/v1/users/{admin.id}", json={"title": "Chapter President"})
    assert title.status_code == 200
    assert _membership(org, admin).role.system_key == "chapter_admin" and _membership(org, admin).member_status == "active"

    # an invited admin does not count as an active one
    api_login(admin)
    assert client.patch(f"/api/v1/users/{second_admin.id}", json={"role_key": "chapter_admin"}).status_code == 200
    _membership(org, second_admin).member_status = "invited"
    _db.session.commit()
    api_login(officer)
    still_last = client.patch(f"/api/v1/users/{admin.id}", json={"role_key": "full_member"})
    assert still_last.status_code == 409 and still_last.get_json()["code"] == "last_admin"

    api_login(requester)
    denied = client.patch(f"/api/v1/users/{users['lead'].id}", json={"role_key": "treasurer"})
    assert denied.status_code == 403 and denied.get_json()["permission"] == ["user.manage"]
    api_login(users["member"])
    assert client.patch(f"/api/v1/users/{users['lead'].id}", json={"role_key": "treasurer"}).status_code == 403
    assert _membership(org, users["lead"]).role.system_key == "team_lead"


# --------------------------------------------------------------------------- roles


def test_roles_list_for_any_member(client, org, users, requester, api_login):
    custom = Role(organization_id=org.id, name="Alumni Mentor", is_custom=True, description="Custom role")
    _db.session.add(custom)
    other = Organization(name="Other", slug="other")
    _db.session.add(other)
    _db.session.flush()
    _db.session.add(Role(organization_id=other.id, name="Zed", system_key="chapter_admin"))
    _db.session.commit()

    api_login(requester)
    response = client.get("/api/v1/roles")
    assert response.status_code == 200
    payload = response.get_json()["payload"]
    keys = [role["system_key"] for role in payload["items"]]
    assert keys == list(registry.SYSTEM_ROLE_KEYS) + [None]
    assert payload["total"] == len(registry.SYSTEM_ROLE_KEYS) + 1
    assert payload["items"][-1]["name"] == "Alumni Mentor" and payload["items"][-1]["is_custom"] is True

    by_key = {role["system_key"]: role for role in payload["items"]}
    admin = by_key["chapter_admin"]
    assert set(admin) == {"id", "name", "system_key", "is_custom", "description", "member_count", "grants"}
    assert admin["name"] == "Chapter Administrator" and admin["is_custom"] is False and admin["description"]
    assert admin["member_count"] == 1 and by_key["full_member"]["member_count"] == 1 and by_key["requester"]["member_count"] == 1
    assert {g["key"] for g in admin["grants"]} == set(registry.PERMISSIONS) and {g["scope"] for g in admin["grants"]} == {"chapter"}
    assert by_key["sponsor_guest"]["grants"] == [{"key": "report.view", "scope": "chapter"}]
    assert {g["key"]: g["scope"] for g in by_key["team_lead"]["grants"]}["team.manage"] == "team"
    assert by_key[None]["grants"] == [] and by_key[None]["member_count"] == 0

    assert client.post("/api/v1/auth/logout", json={}).status_code == 200
    anonymous = client.get("/api/v1/roles")
    assert anonymous.status_code == 401 and anonymous.get_json()["code"] == "login_required"
