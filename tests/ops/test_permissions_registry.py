from asme.ops import permissions as reg


def test_registry_is_internally_consistent():
    assert reg.validate_registry() == []


def test_every_system_role_has_grants_and_admin_has_everything():
    assert set(reg.DEFAULT_GRANTS) == set(reg.SYSTEM_ROLE_KEYS)
    admin = reg.DEFAULT_GRANTS["chapter_admin"]
    assert set(admin) == set(reg.PERMISSIONS)
    assert set(admin.values()) == {"chapter"}


def test_sponsor_guest_is_read_only_reporting():
    assert reg.DEFAULT_GRANTS["sponsor_guest"] == {"report.view": "chapter"}


def test_executive_officer_lacks_security_configuration():
    exec_grants = reg.DEFAULT_GRANTS["executive_officer"]
    assert "role.manage" not in exec_grants
    assert "chapter.settings.manage" not in exec_grants
    assert exec_grants["user.manage"] == "chapter"


def test_team_lead_manages_work_only_within_team():
    lead = reg.DEFAULT_GRANTS["team_lead"]
    assert lead["work_order.assign"] == "team"
    assert lead["work_order.create"] == "chapter"
    assert "project.manage" not in lead


def test_full_member_scopes():
    member = reg.DEFAULT_GRANTS["full_member"]
    assert member["work_order.edit"] == "own"
    assert member["work_order.complete"] == "assigned"
    assert member["work_order.read_all"] == "chapter"
    assert "user.manage" not in member


def test_legacy_mapping_covers_every_legacy_role():
    assert set(reg.LEGACY_ROLE_MAP) == {"admin", "team_leader", "member"}
    assert set(reg.LEGACY_ROLE_MAP.values()) <= set(reg.SYSTEM_ROLE_KEYS)


def test_read_key_detection():
    assert reg.is_read_key("work_order.read_all")
    assert reg.is_read_key("report.view")
    assert not reg.is_read_key("work_order.edit")


def test_stage4_inventory_and_purchasing_grants():
    grants = reg.DEFAULT_GRANTS
    assert reg.PERMISSIONS["purchase.advisor_review"] == "Give faculty-advisor sign-off on purchase requests"
    for role in ("full_member", "project_lead", "team_lead", "inventory_manager", "safety_officer", "treasurer"):
        assert grants[role]["inventory.read"] == "chapter", role
        assert grants[role]["purchase.submit"] == "chapter", role
    assert grants["shop_operator"]["inventory.read"] == "chapter"
    assert "purchase.submit" not in grants["shop_operator"]
    advisor = grants["faculty_advisor"]
    assert {advisor[k] for k in ("inventory.read", "vendor.read", "purchase.advisor_review")} == {"chapter"}
    manager = grants["inventory_manager"]
    assert manager["inventory.manage"] == "chapter" and "purchase.review" not in manager
    assert grants["treasurer"]["purchase.review"] == "chapter" and "inventory.manage" not in grants["treasurer"]
    assert "purchase.advisor_review" not in grants["treasurer"]
    assert grants["executive_officer"]["purchase.advisor_review"] == "chapter"
    assert not {"inventory.read", "purchase.submit"} & set(grants["requester"])
    assert grants["sponsor_guest"] == {"report.view": "chapter"}
