from asme.ops import bootstrap, permissions as registry
from asme.ops.models import Category, Location, Membership, Permission, Role, RolePermission, Sequence


def test_ensure_default_org_is_idempotent(app, db, users):
    first = bootstrap.ensure_default_organization()
    second = bootstrap.ensure_default_organization()
    assert first.id == second.id
    assert first.slug == "uiowa"

    roles = Role.query.filter_by(organization_id=first.id).all()
    assert {r.system_key for r in roles} == set(registry.SYSTEM_ROLE_KEYS)
    assert Permission.query.count() == len(registry.PERMISSIONS)
    expected_grants = sum(len(g) for g in registry.DEFAULT_GRANTS.values())
    assert RolePermission.query.count() == expected_grants

    assert Location.query.filter_by(organization_id=first.id, is_default=True).count() == 1
    assert Category.query.filter_by(organization_id=first.id).count() == len(bootstrap.SEED_CATEGORIES)
    assert Sequence.query.filter_by(organization_id=first.id, key="work_order").one().next_value == 1


def test_legacy_roles_map_to_ops_roles(org, users):
    by_user = {m.user_id: m for m in Membership.query.filter_by(organization_id=org.id).all()}
    assert by_user[users["admin"].id].role.system_key == "chapter_admin"
    assert by_user[users["lead"].id].role.system_key == "team_lead"
    assert by_user[users["member"].id].role.system_key == "full_member"
    assert all(m.member_status == "active" for m in by_user.values())


def test_membership_never_downgraded_or_changed(org, users, db):
    membership = bootstrap.membership_for(users["admin"], org)
    membership.role = bootstrap.role_by_key(org, "requester")
    db.session.commit()

    again = bootstrap.ensure_membership(users["admin"], org)
    assert again.id == membership.id
    assert again.role.system_key == "requester"
    bootstrap.ensure_default_organization()
    assert bootstrap.membership_for(users["admin"], org).role.system_key == "requester"


def test_sync_role_grants_adds_missing_but_keeps_custom(org, db):
    role = bootstrap.role_by_key(org, "requester")
    extra = Permission.query.filter_by(key="asset.read").one()
    role.grants.append(RolePermission(permission_id=extra.id, scope_type="chapter"))
    removed = next(g for g in role.grants if g.permission.key == "request.submit")
    role.grants.remove(removed)
    db.session.commit()

    added = bootstrap.sync_role_grants(org)
    db.session.commit()
    assert added == 1
    keys = {g.permission.key for g in bootstrap.role_by_key(org, "requester").grants}
    assert {"request.submit", "asset.read"} <= keys


def test_seed_defaults_bootstraps_ops(app, db):
    from asme.services import bootstrap as legacy_bootstrap

    legacy_bootstrap.seed_defaults()
    org = bootstrap.default_organization()
    assert org is not None
    assert Membership.query.filter_by(organization_id=org.id).count() >= 1


def test_sync_role_grants_adds_stage4_grants_without_removing_existing(org, db):
    manager = bootstrap.role_by_key(org, "inventory_manager")
    review = Permission.query.filter_by(key="purchase.review").one()
    manager.grants.append(RolePermission(permission_id=review.id, scope_type="chapter"))
    member = bootstrap.role_by_key(org, "full_member")
    for grant in [g for g in member.grants if g.permission.key in ("inventory.read", "purchase.submit")]:
        member.grants.remove(grant)
    db.session.commit()

    assert bootstrap.sync_role_grants(org) == 2
    db.session.commit()
    assert {"inventory.read", "purchase.submit"} <= {g.permission.key for g in bootstrap.role_by_key(org, "full_member").grants}
    assert "purchase.review" in {g.permission.key for g in bootstrap.role_by_key(org, "inventory_manager").grants}
    advisor_keys = {g.permission.key for g in bootstrap.role_by_key(org, "faculty_advisor").grants}
    assert {"inventory.read", "vendor.read", "purchase.advisor_review"} <= advisor_keys
