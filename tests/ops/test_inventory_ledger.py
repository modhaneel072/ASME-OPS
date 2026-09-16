"""The inventory ledger primitive: balances always equal the sum of their
transactions, transactions are immutable, stock never goes negative or
over-reserved, receipts re-weight unit cost, and low-stock alerts fire once on
the transition."""

from __future__ import annotations

import random
from decimal import Decimal

import pytest
from sqlalchemy import delete, func, select, text, update

from asme import events
from asme.extensions import db as _db
from asme.ops import bootstrap
from asme.ops.models import (
    InventoryBalance,
    InventoryTransaction,
    Location,
    Membership,
    Notification,
    Organization,
    Part,
    PurchaseRequest,
    PurchaseRequestItem,
    Team,
    TeamMember,
)
from asme.ops.serializers import part_ref, purchase_request_ref
from asme.ops.services import inventory_ledger as ledger
from asme.services.errors import Conflict, NotFound
from tests.ops.conftest import make_user

D = Decimal


def _location(org, name):
    row = Location(organization_id=org.id, name=name)
    _db.session.add(row)
    _db.session.commit()
    return row


def _part(org, name, **fields):
    row = Part(organization_id=org.id, name=name, **fields)
    _db.session.add(row)
    _db.session.commit()
    return row


def _balance(part, location):
    return InventoryBalance.query.filter_by(part_id=part.id, location_id=location.id).first()


def _receive(ctx, part, location, qty, cost=None):
    txn = ledger.post(ctx, part=part, location=location, transaction_type="receipt", on_hand_delta=qty, quantity=qty, unit_cost=cost)
    _db.session.commit()
    return txn


def _issue(ctx, part, location, qty):
    txn = ledger.post(ctx, part=part, location=location, transaction_type="issue", on_hand_delta=-D(qty), quantity=qty)
    _db.session.commit()
    return txn


def _ledger_sums(part, location):
    row = _db.session.execute(
        select(func.count(InventoryTransaction.id), func.sum(InventoryTransaction.on_hand_delta), func.sum(InventoryTransaction.reserved_delta)).where(
            InventoryTransaction.part_id == part.id, InventoryTransaction.location_id == location.id
        )
    ).one()
    return row[0], ledger._stored(row[1]), ledger._stored(row[2])


# --------------------------------------------------------------------------- property-style sequence


def test_randomized_operations_keep_balances_equal_to_ledger(org, ctx_admin):
    rng = random.Random(20260914)
    locations = [_location(org, f"Shelf {name}") for name in ("A", "B", "C")]
    parts = [_part(org, f"Part {n}", minimum_stock=D("5")) for n in (1, 2, 3)]
    expected = {(p.id, loc.id): [D("0"), D("0")] for p in parts for loc in locations}
    kinds = ("receipt", "issue", "return", "adjustment", "scrap", "reservation", "release", "transfer", "cycle_count")

    def qty():
        return D(rng.randint(1, 15000)).scaleb(-3)

    conflicts = 0
    successes = 0
    for step in range(240):
        kind = rng.choice(kinds)
        part = rng.choice(parts)
        location = rng.choice(locations)
        state = expected[(part.id, location.id)]
        count_before = InventoryTransaction.query.count()
        try:
            if kind == "transfer":
                target = rng.choice([loc for loc in locations if loc.id != location.id])
                amount = qty()
                out = ledger.post(ctx_admin, part=part, location=location, transaction_type="transfer", on_hand_delta=-amount, quantity=amount)
                ledger.post(ctx_admin, part=part, location=target, transaction_type="transfer", on_hand_delta=amount, quantity=amount, reference=out)
                state[0] -= amount
                expected[(part.id, target.id)][0] += amount
            elif kind == "cycle_count":
                counted = D(rng.randint(0, 15000)).scaleb(-3)
                delta = counted - state[0]
                ledger.post(
                    ctx_admin, part=part, location=location, transaction_type="cycle_count", on_hand_delta=delta, quantity=abs(delta), counted_quantity=counted
                )
                state[0] = counted
            else:
                amount = qty()
                on_hand_delta, reserved_delta = {
                    "receipt": (amount, D("0")),
                    "return": (amount, D("0")),
                    "issue": (-amount, D("0")),
                    "scrap": (-amount, D("0")),
                    "adjustment": (amount if rng.random() < 0.5 else -amount, D("0")),
                    "reservation": (D("0"), amount),
                    "release": (D("0"), -amount),
                }[kind]
                ledger.post(
                    ctx_admin,
                    part=part,
                    location=location,
                    transaction_type=kind,
                    on_hand_delta=on_hand_delta,
                    reserved_delta=reserved_delta,
                    quantity=amount,
                    unit_cost=D(rng.randint(1, 900)).scaleb(-2) if kind == "receipt" else None,
                )
                state[0] += on_hand_delta
                state[1] += reserved_delta
            _db.session.commit()
            successes += 1
        except Conflict as exc:
            assert exc.code == "insufficient_stock"
            _db.session.rollback()
            conflicts += 1
            assert InventoryTransaction.query.count() == count_before, f"step {step} wrote rows despite the conflict"

        for (part_id, location_id), (on_hand, reserved) in expected.items():
            balance = InventoryBalance.query.filter_by(part_id=part_id, location_id=location_id).first()
            count, ledger_on_hand, ledger_reserved = _ledger_sums(_db.session.get(Part, part_id), _db.session.get(Location, location_id))
            if balance is None:
                assert count == 0 and on_hand == 0 and reserved == 0
                continue
            assert ledger._stored(balance.on_hand) == ledger_on_hand == on_hand, f"on_hand drift after step {step} ({kind})"
            assert ledger._stored(balance.reserved) == ledger_reserved == reserved, f"reserved drift after step {step} ({kind})"
            assert ledger._stored(balance.reserved) <= ledger._stored(balance.on_hand)
        assert ledger.reconcile(org.id) == []

    assert successes >= 120 and conflicts >= 10, (successes, conflicts)
    # on_hand_after/reserved_after chain matches the running balance for every pair.
    for part in parts:
        for location in locations:
            rows = (
                InventoryTransaction.query.filter_by(part_id=part.id, location_id=location.id)
                .order_by(InventoryTransaction.created_at.asc())
                .all()
            )
            running_on_hand = running_reserved = D("0")
            for row in rows:
                running_on_hand += ledger._stored(row.on_hand_delta)
                running_reserved += ledger._stored(row.reserved_delta)
                assert ledger._stored(row.on_hand_after) == running_on_hand
                assert ledger._stored(row.reserved_after) == running_reserved


# --------------------------------------------------------------------------- immutability


def test_transactions_cannot_be_updated_or_deleted_through_the_orm(org, ctx_admin):
    location = _location(org, "Cabinet")
    part = _part(org, "M3 screw")
    txn = _receive(ctx_admin, part, location, D("10"))

    txn.note = "edited"
    with pytest.raises(RuntimeError, match="immutable"):
        _db.session.commit()
    _db.session.rollback()

    _db.session.delete(_db.session.get(InventoryTransaction, txn.id))
    with pytest.raises(RuntimeError, match="immutable"):
        _db.session.commit()
    _db.session.rollback()

    with pytest.raises(RuntimeError, match="immutable"):
        _db.session.execute(update(InventoryTransaction).where(InventoryTransaction.id == txn.id).values(note="bulk"))
    _db.session.rollback()
    with pytest.raises(RuntimeError, match="immutable"):
        InventoryTransaction.query.filter_by(id=txn.id).delete()
    _db.session.rollback()
    with pytest.raises(RuntimeError, match="immutable"):
        _db.session.execute(delete(InventoryTransaction))
    _db.session.rollback()

    stored = _db.session.get(InventoryTransaction, txn.id)
    assert stored is not None and stored.note is None and InventoryTransaction.query.count() == 1


def test_correction_referencing_an_original_does_not_touch_it(org, ctx_admin):
    location = _location(org, "Cabinet")
    part = _part(org, "Washer")
    original = _receive(ctx_admin, part, location, D("4"))
    correction = ledger.post(
        ctx_admin, part=part, location=location, transaction_type="adjustment", on_hand_delta=D("-1"), quantity=D("1"), reference=original, note="Miscount"
    )
    _db.session.commit()
    assert correction.reference_transaction_id == original.id
    assert correction.reference.id == original.id
    assert ledger._stored(_balance(part, location).on_hand) == D("3")


# --------------------------------------------------------------------------- stock rules


def test_insufficient_stock_is_a_conflict_and_writes_nothing(org, ctx_admin):
    shelf = _location(org, "Shelf")
    empty = _location(org, "Empty bin")
    part = _part(org, "Bearing 608", unit_cost=D("1.2500"))
    _receive(ctx_admin, part, shelf, D("5"))

    with pytest.raises(Conflict) as caught:
        ledger.post(ctx_admin, part=part, location=shelf, transaction_type="issue", on_hand_delta=D("-7"), quantity=D("7"))
    err = caught.value
    assert err.status == 409 and err.code == "insufficient_stock"
    assert err.extra == {"part_id": str(part.id), "location_id": str(shelf.id), "on_hand": 5.0, "reserved": 0.0, "requested": 7.0}
    body = err.to_dict()
    assert body["code"] == "insufficient_stock" and body["requested"] == 7.0
    _db.session.commit()
    assert InventoryTransaction.query.count() == 1
    assert ledger._stored(_balance(part, shelf).on_hand) == D("5")

    with pytest.raises(Conflict):
        ledger.post(ctx_admin, part=part, location=empty, transaction_type="issue", on_hand_delta=D("-1"), quantity=D("1"))
    _db.session.commit()
    assert _balance(part, empty) is None
    assert InventoryTransaction.query.count() == 1
    assert ledger.pending_events() == []


def test_reserved_can_never_exceed_on_hand(org, ctx_admin):
    location = _location(org, "Kit shelf")
    part = _part(org, "Servo")
    _receive(ctx_admin, part, location, D("5"))

    ledger.post(ctx_admin, part=part, location=location, transaction_type="reservation", on_hand_delta=0, reserved_delta=D("5"), quantity=D("5"))
    _db.session.commit()
    for kwargs in (
        {"transaction_type": "reservation", "on_hand_delta": 0, "reserved_delta": D("0.001"), "quantity": D("0.001")},
        {"transaction_type": "issue", "on_hand_delta": D("-1"), "quantity": D("1")},
        {"transaction_type": "release", "on_hand_delta": 0, "reserved_delta": D("-6"), "quantity": D("6")},
    ):
        with pytest.raises(Conflict) as caught:
            ledger.post(ctx_admin, part=part, location=location, **kwargs)
        assert caught.value.code == "insufficient_stock"
        assert caught.value.extra["reserved"] == 5.0

    # Consuming a reservation: release then issue in one transaction.
    ledger.post(ctx_admin, part=part, location=location, transaction_type="release", on_hand_delta=0, reserved_delta=D("-2"), quantity=D("2"))
    issue = ledger.post(ctx_admin, part=part, location=location, transaction_type="issue", on_hand_delta=D("-2"), quantity=D("2"))
    _db.session.commit()
    assert (ledger._stored(issue.on_hand_after), ledger._stored(issue.reserved_after)) == (D("3"), D("3"))
    totals = ledger.part_totals([part.id])[part.id]
    assert (totals["on_hand"], totals["reserved"], totals["available"]) == (D("3"), D("3"), D("0"))


def test_post_guards_its_inputs(org, ctx_admin):
    location = _location(org, "Bench")
    part = _part(org, "Zip tie")
    other = Organization(name="Other Chapter", slug="other-chapter")
    _db.session.add(other)
    _db.session.flush()
    foreign_location = Location(organization_id=other.id, name="Foreign shelf")
    foreign_part = Part(organization_id=other.id, name="Foreign part")
    _db.session.add_all([foreign_location, foreign_part])
    _db.session.commit()

    with pytest.raises(NotFound):
        ledger.post(ctx_admin, part=part, location=foreign_location, transaction_type="receipt", on_hand_delta=1, quantity=1)
    with pytest.raises(NotFound):
        ledger.post(ctx_admin, part=foreign_part, location=location, transaction_type="receipt", on_hand_delta=1, quantity=1)
    with pytest.raises(ValueError):
        ledger.post(ctx_admin, part=part, location=location, transaction_type="teleport", on_hand_delta=1, quantity=1)
    with pytest.raises(ValueError):
        ledger.post(ctx_admin, part=part, location=location, transaction_type="receipt", on_hand_delta=0, quantity=0)
    with pytest.raises(TypeError):
        ledger.post(ctx_admin, part=part, location=location, transaction_type="receipt", on_hand_delta=1.5, quantity=D("1.5"))
    with pytest.raises(ValueError):
        ledger.post(ctx_admin, part=part, location=location, transaction_type="receipt", on_hand_delta=D("NaN"), quantity=1)
    assert InventoryTransaction.query.count() == 0

    # A cycle count that confirms the expected quantity is still recorded.
    _receive(ctx_admin, part, location, D("2"))
    count = ledger.post(ctx_admin, part=part, location=location, transaction_type="cycle_count", on_hand_delta=0, quantity=0, counted_quantity=D("2"))
    _db.session.commit()
    assert count.counted_quantity == D("2") and ledger._stored(count.on_hand_after) == D("2")
    assert count.created_by_user_id == ctx_admin.user_id


def test_quantity_and_cost_helpers():
    assert ledger.to_quantity("1.23456") == D("1.235")
    assert ledger.to_unit_cost(D("0.00005")) == D("0.0001")
    assert ledger.quantity_check(D("1.001")) is None
    assert ledger.quantity_check(D("1.0001")) == "Use at most 3 decimal places."
    assert ledger.quantity_check(D("100000000000")) is not None
    assert ledger.unit_cost_check(D("2.12345")) == "Use at most 4 decimal places."
    assert ledger.unit_cost_check(D("2.1234")) is None
    assert ledger.quantity_number(D("2.5")) == 2.5 and ledger.quantity_number(None) is None
    assert ledger.unit_cost_number(D("1.23456")) == 1.2346


def test_receipts_weight_the_unit_cost_across_locations(org, ctx_admin):
    shelf, bin_ = _location(org, "Shelf"), _location(org, "Bin")
    part = _part(org, "Filament")
    _receive(ctx_admin, part, shelf, D("10"), cost=D("2.00"))
    assert part.unit_cost == D("2.0000")
    _receive(ctx_admin, part, bin_, D("30"), cost=D("4.00"))
    assert part.unit_cost == D("3.5000")  # (10*2 + 30*4) / 40
    _issue(ctx_admin, part, bin_, D("20"))
    _receive(ctx_admin, part, shelf, D("20"), cost=D("5"))
    assert part.unit_cost == D("4.2500")  # (20*3.5 + 20*5) / 40
    _receive(ctx_admin, part, shelf, D("1"))  # no cost: unchanged
    assert part.unit_cost == D("4.2500")
    ledger.post(ctx_admin, part=part, location=shelf, transaction_type="return", on_hand_delta=D("1"), quantity=D("1"), unit_cost=D("99"))
    _db.session.commit()
    assert part.unit_cost == D("4.2500")  # only receipts re-weight

    rounding = _part(org, "Rivet", unit_cost=None)
    _receive(ctx_admin, rounding, shelf, D("3"), cost=D("1"))
    _receive(ctx_admin, rounding, shelf, D("1"), cost=D("0.0001"))
    _db.session.refresh(rounding)
    assert rounding.unit_cost == D("0.7500")  # 3.0001 / 4 = 0.750025 -> 4 places

    emptied = _part(org, "Epoxy", unit_cost=D("9.0000"))
    _receive(ctx_admin, emptied, shelf, D("2"), cost=D("7"))
    assert emptied.unit_cost == D("7.0000")  # nothing on hand before: the new cost wins


# --------------------------------------------------------------------------- totals and state


def test_part_totals_include_ordered_quantities_from_open_orders(org, ctx_admin, users):
    shelf, bin_ = _location(org, "Shelf"), _location(org, "Bin")
    part = _part(org, "Motor")
    other = _part(org, "Gearbox")
    _receive(ctx_admin, part, shelf, D("4"))
    _receive(ctx_admin, part, bin_, D("2.5"))
    ledger.post(ctx_admin, part=part, location=bin_, transaction_type="reservation", on_hand_delta=0, reserved_delta=D("1.5"), quantity=D("1.5"))
    _db.session.commit()

    def request(number, status, lines):
        pr = PurchaseRequest(organization_id=org.id, number=number, title=f"Order {number}", requester_user_id=users["member"].id, status=status)
        for index, (line_part, quantity, received) in enumerate(lines):
            pr.items.append(
                PurchaseRequestItem(part_id=getattr(line_part, "id", None), description="line", quantity=quantity, received_quantity=received, position=index)
            )
        _db.session.add(pr)

    request(1, "ordered", [(part, D("10"), D("4")), (other, D("3"), D("0")), (None, D("8"), D("0"))])
    request(2, "partially_received", [(part, D("5"), D("2"))])
    for number, status in enumerate(("draft", "submitted", "approved", "received", "declined", "canceled"), start=3):
        request(number, status, [(part, D("50"), D("0"))])
    _db.session.commit()

    unknown = org.id  # any id without parts
    totals = ledger.part_totals([part.id, str(other.id), unknown, "not-a-uuid", part.id])
    assert set(totals) == {part.id, other.id, unknown}
    assert totals[part.id] == {"on_hand": D("6.5"), "reserved": D("1.5"), "available": D("5"), "ordered": D("9"), "has_transactions": True}
    assert totals[other.id] == {"on_hand": D("0"), "reserved": D("0"), "available": D("0"), "ordered": D("3"), "has_transactions": False}
    assert totals[unknown]["has_transactions"] is False
    assert ledger.part_totals([]) == {}


def test_stock_state_rules(org):
    part = Part(organization_id=org.id, name="Probe", minimum_stock=None)

    def totals(on_hand, reserved="0", has=True):
        return {"on_hand": D(on_hand), "reserved": D(reserved), "available": D(on_hand) - D(reserved), "ordered": D("0"), "has_transactions": has}

    assert ledger.stock_state(totals("0", has=False), part) == "untracked"
    assert ledger.stock_state(totals("0"), part) == "out"
    assert ledger.stock_state(totals("3", "3"), part) == "out"
    assert ledger.stock_state(totals("0.001"), part) == "ok"
    part.minimum_stock = D("5")
    assert ledger.stock_state(totals("0", has=False), part) == "out"
    assert ledger.stock_state(totals("4.999"), part) == "low"
    assert ledger.stock_state(totals("8", "4"), part) == "low"
    assert ledger.stock_state(totals("5"), part) == "ok"


# --------------------------------------------------------------------------- notifications


def _low_stock_rows(part):
    return Notification.query.filter_by(type="inventory.low_stock", entity_id=str(part.id)).all()


def test_low_stock_notifies_inventory_managers_once_on_the_transition(org, ctx_admin, users):
    manager = make_user("Ina Inventory", "ina@uiowa.edu", ops_role="inventory_manager", org=org)
    suspended = make_user("Sid Suspended", "sid@uiowa.edu", ops_role="inventory_manager", org=org)
    treasurer = make_user("Tess Treasurer", "tess@uiowa.edu", ops_role="treasurer", org=org)
    bootstrap.membership_for(suspended, org).member_status = "suspended"
    _db.session.commit()
    received = []

    def handler(name, **payload):
        received.append((name, payload))

    events.subscribe(events.INVENTORY_LOW_STOCK, handler)
    try:
        shelf = _location(org, "Shelf")
        part = _part(org, "Fuse 5A", minimum_stock=D("5"))
        _receive(ctx_admin, part, shelf, D("10"))  # out -> ok: nothing
        assert _low_stock_rows(part) == []

        _issue(ctx_admin, part, shelf, D("6"))  # ok -> low
        rows = _low_stock_rows(part)
        assert {row.user_id for row in rows} == {users["admin"].id, manager.id}
        assert all(row.title == "Fuse 5A is low on stock" for row in rows)
        assert rows[0].body == "Available: 4 each. Minimum: 5 each."
        today = rows[0].created_at.date().isoformat()
        assert {row.dedupe_key for row in rows} == {f"low_stock:{part.id}:{today}"}
        assert rows[0].entity_type == "part"
        assert received == []  # queued, not emitted before the caller emits
        assert ledger.emit_pending_events() == 1
        assert received == [
            (events.INVENTORY_LOW_STOCK, {"organization_id": str(org.id), "part_id": str(part.id), "state": "low", "previous": "ok", "available": 4.0})
        ]

        _issue(ctx_admin, part, shelf, D("1"))  # low -> low: no transition
        _receive(ctx_admin, part, shelf, D("10"))  # back to ok
        _issue(ctx_admin, part, shelf, D("12"))  # ok -> low again the same day
        _issue(ctx_admin, part, shelf, D("1"))  # low -> out, same day
        assert len(_low_stock_rows(part)) == 2
        member_ids = {users["member"].id, users["lead"].id, treasurer.id, suspended.id}
        assert not any(row.user_id in member_ids for row in Notification.query.filter_by(type="inventory.low_stock"))
        assert len(ledger.pending_events()) == 2

        # Reserving the last units also makes a part unavailable.
        loose = _part(org, "Relay")
        _receive(ctx_admin, loose, shelf, D("2"))  # untracked -> ok
        ledger.post(ctx_admin, part=loose, location=shelf, transaction_type="reservation", on_hand_delta=0, reserved_delta=D("2"), quantity=D("2"))
        _db.session.commit()
        out_rows = _low_stock_rows(loose)
        assert {row.user_id for row in out_rows} == {users["admin"].id, manager.id}
        assert out_rows[0].title == "Relay is out of stock"
    finally:
        events.unsubscribe(events.INVENTORY_LOW_STOCK, handler)


def test_pending_events_are_dropped_when_the_transaction_rolls_back(org, ctx_admin):
    shelf = _location(org, "Shelf")
    part = _part(org, "Cable")
    _receive(ctx_admin, part, shelf, D("1"))
    ledger.emit_pending_events()
    ledger.post(ctx_admin, part=part, location=shelf, transaction_type="issue", on_hand_delta=D("-1"), quantity=D("1"))
    assert len(ledger.pending_events()) == 1
    _db.session.rollback()
    assert ledger.pending_events() == []
    assert InventoryTransaction.query.count() == 1


def test_critical_parts_escalate_to_the_configured_team_leads(org, ctx_admin, users):
    team = Team(organization_id=org.id, name="Electrical")
    team.members.append(TeamMember(user_id=users["member"].id, is_lead=True))
    team.members.append(TeamMember(user_id=users["lead"].id, is_lead=False))
    _db.session.add(team)
    _db.session.flush()
    org.settings_json = {**(org.settings_json or {}), "purchasing": {"critical_parts_team_id": str(team.id)}}
    _db.session.commit()

    shelf = _location(org, "Shelf")
    critical = _part(org, "Motor controller", is_critical=True, minimum_stock=D("2"))
    ordinary = _part(org, "Heat shrink", minimum_stock=D("2"))
    for part in (critical, ordinary):
        _receive(ctx_admin, part, shelf, D("3"))
        _issue(ctx_admin, part, shelf, D("2"))

    assert {row.user_id for row in _low_stock_rows(critical)} == {users["admin"].id, users["member"].id}
    assert {row.user_id for row in _low_stock_rows(ordinary)} == {users["admin"].id}
    assert ledger.critical_parts_team_lead_ids(org) == {users["member"].id}

    membership = Membership.query.filter_by(organization_id=org.id, user_id=users["member"].id).one()
    membership.member_status = "suspended"
    org.settings_json = {"purchasing": {"critical_parts_team_id": "not-a-team"}}
    _db.session.commit()
    assert ledger.critical_parts_team_lead_ids(org) == set()


def test_active_member_ids_with_permission(org, users):
    manager = make_user("Ina Inventory", "ina@uiowa.edu", ops_role="inventory_manager", org=org)
    advisor = make_user("Fay Faculty", "fay@uiowa.edu", ops_role="faculty_advisor", org=org)
    assert ledger.active_member_ids_with_permission(org.id, "inventory.manage") == {users["admin"].id, manager.id}
    assert ledger.active_member_ids_with_permission(org.id, "purchase.advisor_review") == {users["admin"].id, advisor.id}


# --------------------------------------------------------------------------- reconcile


def test_reconcile_reports_mismatches_and_the_command_exits_nonzero(org, ctx_admin):
    import manage

    shelf = _location(org, "Shelf")
    part = _part(org, "Spring")
    _receive(ctx_admin, part, shelf, D("3"))
    lines: list[str] = []
    assert ledger.reconcile(org.id) == [] and manage.reconcile_ops_inventory(write=lines.append) == 0
    assert lines == [f"{org.slug}: 0 mismatch(es)"]

    balance = _balance(part, shelf)
    _db.session.execute(text("UPDATE ops_inventory_balances SET on_hand = 7 WHERE id = :id"), {"id": balance.id.hex})
    _db.session.commit()
    _db.session.expire_all()
    mismatches = ledger.reconcile(org.id)
    assert mismatches == [
        {
            "organization_id": str(org.id),
            "part_id": str(part.id),
            "location_id": str(shelf.id),
            "balance_on_hand": "7.000",
            "ledger_on_hand": "3.000",
            "balance_reserved": "0.000",
            "ledger_reserved": "0.000",
        }
    ]
    lines.clear()
    assert manage.reconcile_ops_inventory(write=lines.append) == 1
    assert lines[0] == f"{org.slug}: 1 mismatch(es)" and "on_hand balance=7.000 ledger=3.000" in lines[1]
    assert ledger._stored(_balance(part, shelf).on_hand) == D("7")  # reported, never corrected
    assert ledger.reconcile("not-a-uuid") == []


# --------------------------------------------------------------------------- shared shapes


def test_reference_shapes_and_event_names(org, users):
    part = _part(org, "Bolt", sku="BLT-1", unit="box")
    pr = PurchaseRequest(organization_id=org.id, number=12, title="Bolts", requester_user_id=users["member"].id)
    _db.session.add(pr)
    _db.session.commit()
    assert part_ref(part) == {"id": str(part.id), "name": "Bolt", "sku": "BLT-1", "unit": "box"}
    assert purchase_request_ref(pr) == {"id": str(pr.id), "number": 12, "display_number": "PR-12", "title": "Bolts", "status": "draft"}
    assert part_ref(None) is None and purchase_request_ref(None) is None
    assert pr.display_number == "PR-12"
    assert events.INVENTORY_LOW_STOCK == "ops.inventory.low_stock"
    assert events.PURCHASE_REQUEST_STATUS_CHANGED == "ops.purchase_request.status_changed"
    assert {events.INVENTORY_LOW_STOCK, events.PURCHASE_REQUEST_STATUS_CHANGED} <= set(events.ALL_EVENTS)
