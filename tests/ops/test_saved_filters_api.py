import pytest

from asme.extensions import db as _db
from asme.ops import policy
from asme.ops.models import AuditEvent, Organization, SavedFilter, Team, TeamMember
from asme.ops.services import saved_filters
from asme.ops.validation import ValidationErrors
from asme.services.errors import Forbidden, NotFound
from tests.ops.conftest import make_user

URL = "/api/v1/saved-filters"


def _team(org, name, members=()):
    team = Team(organization_id=org.id, name=name)
    _db.session.add(team)
    _db.session.flush()
    for user in members:
        team.members.append(TeamMember(user_id=user.id, is_lead=False))
    _db.session.commit()
    return team


def _filter(org, owner, name, entity_type="work_order", **kw):
    row = SavedFilter(organization_id=org.id, owner_user_id=owner.id, entity_type=entity_type, name=name, filter_json={"status": ["open"]}, **kw)
    _db.session.add(row)
    _db.session.commit()
    return row


def test_member_creates_private_filter_and_lists_it(client, org, users, api_login):
    api_login(users["member"])
    created = client.post(
        URL,
        json={"entity_type": "work_order", "name": "My open", "filter": {"status": ["open"]}, "sort": "-due_at", "view_type": "table", "is_default": True},
    )
    assert created.status_code == 201, created.get_json()
    body = created.get_json()["payload"]["saved_filter"]
    assert body["entity_type"] == "work_order" and body["visibility"] == "private" and body["team"] is None
    assert body["owner"]["id"] == users["member"].id and body["filter"] == {"status": ["open"]}
    assert body["sort"] == "-due_at" and body["view_type"] == "table" and body["is_default"] is True
    assert body["created_at"].endswith("Z")

    listed = client.get(URL + "?entity_type=work_order").get_json()["payload"]
    assert [f["id"] for f in listed["personal"]] == [body["id"]]
    assert listed["shared"] == []
    assert client.get(URL + "?entity_type=asset").get_json()["payload"] == {"personal": [], "shared": []}

    event = AuditEvent.query.filter_by(event_type="saved_filter.created").one()
    assert event.entity_type == "saved_filter" and event.entity_id == body["id"] and event.after_json["name"] == "My open"


def test_create_validation_lists_every_bad_field(client, org, users, api_login):
    api_login(users["member"])
    bad = client.post(URL, json={"entity_type": "widget", "name": "x" * 121, "visibility": "public", "filter": ["nope"], "view_type": "v" * 21, "is_default": "maybe"})
    assert bad.status_code == 400
    assert bad.get_json()["code"] == "validation"
    assert set(bad.get_json()["errors"]) == {"entity_type", "name", "visibility", "filter", "view_type", "is_default"}

    missing = client.post(URL, json={})
    assert missing.status_code == 400 and set(missing.get_json()["errors"]) == {"entity_type", "name", "filter"}

    unknown_type = client.get(URL + "?entity_type=widget")
    assert unknown_type.status_code == 400 and set(unknown_type.get_json()["errors"]) == {"entity_type"}


def test_sharing_requires_permission_and_team_membership(client, org, users, api_login):
    team = _team(org, "Electrical", members=[users["lead"]])
    api_login(users["member"])  # full_member has no saved_filter.share
    denied = client.post(URL, json={"entity_type": "work_order", "name": "Chapter", "visibility": "chapter", "filter": {}})
    assert denied.status_code == 403 and denied.get_json()["permission"] == "saved_filter.share"

    api_login(users["lead"])  # team_lead also lacks saved_filter.share
    denied = client.post(URL, json={"entity_type": "work_order", "name": "Team", "visibility": "team", "team_id": str(team.id), "filter": {}})
    assert denied.status_code == 403

    api_login(users["admin"])
    no_team = client.post(URL, json={"entity_type": "work_order", "name": "Team", "visibility": "team", "filter": {}})
    assert no_team.status_code == 400 and set(no_team.get_json()["errors"]) == {"team_id"}
    shared = client.post(URL, json={"entity_type": "work_order", "name": "Team", "visibility": "team", "team_id": str(team.id), "filter": {"team": [str(team.id)]}})
    assert shared.status_code == 201
    assert shared.get_json()["payload"]["saved_filter"]["team"] == {"id": str(team.id), "name": "Electrical"}


def test_team_sharing_requires_membership_for_non_admins(org, users):
    officer = make_user("Eve Exec", "eve@uiowa.edu", ops_role="executive_officer", org=org)
    mine = _team(org, "Arm", members=[officer])
    other = _team(org, "Wheels")
    ctx = policy.load_context(officer, org)
    with pytest.raises(ValidationErrors) as excinfo:
        saved_filters.create(ctx, {"entity_type": "asset", "name": "Wheels", "visibility": "team", "team_id": str(other.id), "filter": {}})
    assert set(excinfo.value.errors) == {"team_id"}
    row = saved_filters.create(ctx, {"entity_type": "asset", "name": "Arm", "visibility": "team", "team_id": str(mine.id), "filter": {}})
    assert row.team_id == mine.id and row.visibility == "team"


def test_shared_lists_chapter_and_own_team_filters_excluding_own(client, org, users, api_login):
    team = _team(org, "Electrical", members=[users["member"]])
    other_team = _team(org, "Software")
    _filter(org, users["admin"], "Everyone", visibility="chapter")
    _filter(org, users["admin"], "Electrical only", visibility="team", team_id=team.id)
    _filter(org, users["admin"], "Software only", visibility="team", team_id=other_team.id)
    _filter(org, users["admin"], "Admin private")
    _filter(org, users["member"], "Mine chapter", visibility="chapter")
    _filter(org, users["admin"], "Projects", entity_type="project", visibility="chapter")

    api_login(users["member"])
    listed = client.get(URL + "?entity_type=work_order").get_json()["payload"]
    assert [f["name"] for f in listed["personal"]] == ["Mine chapter"]
    assert sorted(f["name"] for f in listed["shared"]) == ["Electrical only", "Everyone"]

    everything = client.get(URL).get_json()["payload"]
    assert sorted(f["name"] for f in everything["shared"]) == ["Electrical only", "Everyone", "Projects"]

    api_login(users["lead"])  # not in any team
    listed = client.get(URL + "?entity_type=work_order").get_json()["payload"]
    assert [f["name"] for f in listed["shared"]] == ["Everyone", "Mine chapter"]


def test_only_one_default_per_user_and_entity_type(client, org, users, api_login):
    api_login(users["member"])
    first = client.post(URL, json={"entity_type": "work_order", "name": "First", "filter": {}, "is_default": True}).get_json()["payload"]["saved_filter"]
    project_default = client.post(URL, json={"entity_type": "project", "name": "Proj", "filter": {}, "is_default": True}).get_json()["payload"]["saved_filter"]
    second = client.post(URL, json={"entity_type": "work_order", "name": "Second", "filter": {}, "is_default": True}).get_json()["payload"]["saved_filter"]
    assert second["is_default"] is True
    defaults = {f.name: f.is_default for f in SavedFilter.query.filter_by(owner_user_id=users["member"].id).all()}
    assert defaults == {"First": False, "Proj": True, "Second": True}

    # another user's default for the same entity type is untouched
    api_login(users["lead"])
    client.post(URL, json={"entity_type": "work_order", "name": "Lead default", "filter": {}, "is_default": True})
    assert SavedFilter.query.filter_by(name="Second").one().is_default is True

    # promoting via PATCH clears the previous default too
    api_login(users["member"])
    patched = client.patch(f"{URL}/{first['id']}", json={"is_default": True})
    assert patched.status_code == 200 and patched.get_json()["payload"]["saved_filter"]["is_default"] is True
    assert SavedFilter.query.filter_by(name="Second").one().is_default is False
    assert SavedFilter.query.filter_by(name="Proj").one().is_default is True
    assert SavedFilter.query.filter_by(name="Lead default").one().is_default is True


def test_patch_and_delete_by_owner_or_chapter_admin(client, org, users, api_login):
    row = _filter(org, users["member"], "Mine")
    api_login(users["lead"])
    assert client.patch(f"{URL}/{row.id}", json={"name": "Hijack"}).status_code == 403
    assert client.delete(f"{URL}/{row.id}").status_code == 403

    api_login(users["member"])
    patched = client.patch(f"{URL}/{row.id}", json={"name": "Renamed", "filter": {"priority": ["high"]}, "sort": None})
    assert patched.status_code == 200
    body = patched.get_json()["payload"]["saved_filter"]
    assert body["name"] == "Renamed" and body["filter"] == {"priority": ["high"]} and body["sort"] is None
    invalid = client.patch(f"{URL}/{row.id}", json={"name": "", "filter": None})
    assert invalid.status_code == 400 and set(invalid.get_json()["errors"]) == {"name", "filter"}
    # owner without saved_filter.share cannot widen visibility
    widen = client.patch(f"{URL}/{row.id}", json={"visibility": "chapter"})
    assert widen.status_code == 403
    event = AuditEvent.query.filter_by(event_type="saved_filter.updated").one()
    assert event.before_json["name"] == "Mine" and event.after_json["name"] == "Renamed"

    api_login(users["admin"])
    admin_patch = client.patch(f"{URL}/{row.id}", json={"visibility": "chapter"})
    assert admin_patch.status_code == 200 and admin_patch.get_json()["payload"]["saved_filter"]["visibility"] == "chapter"
    deleted = client.delete(f"{URL}/{row.id}")
    assert deleted.status_code == 200 and deleted.get_json()["payload"] == {"deleted": True}
    assert _db.session.get(SavedFilter, row.id) is None
    assert AuditEvent.query.filter_by(event_type="saved_filter.deleted", entity_id=str(row.id)).count() == 1
    assert client.delete(f"{URL}/{row.id}").status_code == 404


def test_narrowing_to_private_drops_team_and_needs_no_share_permission(org, users):
    team = _team(org, "Electrical", members=[users["member"]])
    row = _filter(org, users["member"], "Team view", visibility="team", team_id=team.id)
    ctx = policy.load_context(users["member"], org)
    updated = saved_filters.update(ctx, str(row.id), {"visibility": "private"})
    assert updated.visibility == "private" and updated.team_id is None


def test_cross_organization_filter_is_404(client, org, users, api_login):
    other = Organization(name="Other", slug="other")
    _db.session.add(other)
    _db.session.flush()
    foreign = SavedFilter(organization_id=other.id, owner_user_id=users["admin"].id, entity_type="work_order", name="Foreign", filter_json={})
    _db.session.add(foreign)
    _db.session.commit()

    api_login(users["admin"])
    assert client.patch(f"{URL}/{foreign.id}", json={"name": "x"}).status_code == 404
    assert client.delete(f"{URL}/{foreign.id}").status_code == 404
    assert client.patch(f"{URL}/not-a-uuid", json={"name": "x"}).status_code == 404
    assert [f["name"] for f in client.get(URL).get_json()["payload"]["personal"]] == []

    ctx = policy.load_context(users["admin"], org)
    with pytest.raises(NotFound):
        saved_filters.get(ctx, str(foreign.id))
    with pytest.raises(Forbidden):
        saved_filters.get(policy.load_context(users["lead"], org), str(_filter(org, users["member"], "Private").id))


def test_requester_can_use_private_filters(client, org, requester, api_login):
    api_login(requester)
    created = client.post(URL, json={"entity_type": "project", "name": "Mine", "filter": {"status": ["active"]}})
    assert created.status_code == 201
    assert client.get(URL).get_json()["payload"]["personal"][0]["name"] == "Mine"
