"""Phase 2 tests: review state, assignment store persistence, undo, review gate."""

from pathlib import Path

import pytest

from odb_clearance_analyzer.voltage_guessing import load_rule_pack, review_service, validate_rule_pack
from odb_clearance_analyzer.voltage_guessing.assignment_store import (
    create_assignment_store,
    load_assignment_store,
    save_assignment_store_atomic,
)
from odb_clearance_analyzer.voltage_guessing.exports import export_voltage_assignments_json


NETS = ["GND", "3V3", "DC_LINK_800V", "MYSTERY_NET", "L1"]


def _store_with_guesses():
    pack = load_rule_pack()
    store = create_assignment_store([], project_revision="rev_a")
    review_service.run_auto_detect(store, NETS, pack, source_revision="rev_a")
    return store, pack


def test_auto_detect_populates_store_and_records_undo():
    store, _ = _store_with_guesses()
    assert set(store.assignments) == set(NETS)
    assert store.undo_stack and store.undo_stack[-1].operation == "auto_detect"


def test_high_confidence_critical_is_not_auto_approved():
    store, _ = _store_with_guesses()
    dc_link = store.assignments["DC_LINK_800V"]
    assert dc_link.severity == "Critical"
    assert dc_link.review_state == "Needs review"


def test_manual_override_survives_auto_detect_and_is_undoable():
    store, pack = _store_with_guesses()
    review_service.apply_manual_override(
        store, "MYSTERY_NET", final_class="POWER", final_voltage_v=3.8, notes="board doc"
    )
    review_service.run_auto_detect(store, NETS, pack, source_revision="rev_a")
    kept = store.assignments["MYSTERY_NET"]
    assert kept.source == "manual" and kept.final_voltage_v == 3.8
    # Undo stack: manual edit is undoable back to the rule guess.
    review_service.undo_last(store)  # undo the (no-op) auto-detect if recorded, else the edit
    while store.assignments["MYSTERY_NET"].source == "manual" and store.undo_stack:
        review_service.undo_last(store)
    assert store.assignments["MYSTERY_NET"].source != "manual"


def test_undo_auto_detect_restores_previous_state():
    pack = load_rule_pack()
    store = create_assignment_store([], project_revision="rev_a")
    review_service.run_auto_detect(store, ["GND"], pack)
    review_service.run_auto_detect(store, ["GND", "3V3"], pack)
    assert "3V3" in store.assignments
    review_service.undo_last(store)
    assert "3V3" not in store.assignments and "GND" in store.assignments


def test_review_actions_and_metadata():
    store, _ = _store_with_guesses()
    # Bulk approve intentionally skips Warning/Critical nets.
    assert review_service.approve(store, ["DC_LINK_800V"], reason="checked schematic") == 0
    assert store.assignments["DC_LINK_800V"].review_state == "Needs review"
    assert review_service.approve(store, ["GND"], reason="checked schematic") == 1
    a = store.assignments["GND"]
    assert a.review_state == "Approved" and a.reviewed_by and a.reviewed_at_utc.endswith("Z")

    assert review_service.accept_unknown(store, ["MYSTERY_NET"]) == 1
    assert store.assignments["MYSTERY_NET"].review_state == "Accepted unknown"

    with pytest.raises(ValueError):
        review_service.waive(store, ["L1"], reason="   ")
    assert review_service.waive(store, ["L1"], reason="test coupon net", scope="project_global") == 1
    w = store.assignments["L1"].waiver
    assert w.waived and w.waiver_scope == "project_global" and w.waiver_reason


def test_review_queue_contents_and_waived_visibility():
    store, _ = _store_with_guesses()
    queue_nets = {a.net_name for a in review_service.review_queue(store)}
    assert {"DC_LINK_800V", "MYSTERY_NET", "L1"} <= queue_nets
    assert "GND" not in queue_nets and "3V3" not in queue_nets
    # Critical sorts first.
    assert review_service.review_queue(store)[0].severity == "Critical"
    review_service.waive(store, ["L1"], reason="coupon")
    assert "L1" not in {a.net_name for a in review_service.review_queue(store)}
    assert "L1" in store.assignments  # waived items remain visible in assignments


def test_review_gate_modes():
    store, _ = _store_with_guesses()
    warn = review_service.review_gate_status(store, "warn")
    assert warn.export_allowed and "INCOMPLETE" in warn.stamp_text
    block = review_service.review_gate_status(store, "block")
    assert not block.export_allowed and block.unreviewed_critical >= 1
    allow = review_service.review_gate_status(store, "allow")
    assert allow.export_allowed and allow.stamp_text == ""
    # Clearing all critical/review items opens the block gate.
    for assignment in list(store.assignments.values()):
        if assignment.severity in {"Warning", "Critical"}:
            review_service.apply_manual_override(
                store, assignment.net_name,
                final_class=assignment.final_class,
                final_voltage_v=assignment.final_voltage_v,
                review_state="Reviewed",
                notes="individually reviewed",
            )
    review_service.approve(store, list(store.assignments))
    assert review_service.review_gate_status(store, "block").export_allowed


def test_store_survives_restart(tmp_path: Path):
    store, _ = _store_with_guesses()
    review_service.apply_manual_override(store, "MYSTERY_NET", final_class="POWER", final_voltage_v=3.8, notes="n")
    store.review_session.queue_position = 2
    path = tmp_path / "net_voltage_assignments.json"
    save_assignment_store_atomic(store, path)

    reloaded = load_assignment_store(path)
    assert reloaded.assignments["MYSTERY_NET"].final_voltage_v == 3.8
    assert reloaded.assignments["MYSTERY_NET"].source == "manual"
    assert reloaded.review_session.queue_position == 2
    assert reloaded.undo_stack, "undo stack must persist across restart"
    review_service.undo_last(reloaded)
    assert reloaded.assignments["MYSTERY_NET"].source != "manual"


def test_export_snapshot_is_rejected_as_store(tmp_path: Path):
    store, _ = _store_with_guesses()
    snapshot = tmp_path / "net_voltage_assignments_rev_a.json"
    export_voltage_assignments_json(list(store.assignments.values()), snapshot, project_revision="rev_a")
    with pytest.raises(ValueError):
        load_assignment_store(snapshot)


def test_rule_pack_self_tests_are_executed():
    validation = validate_rule_pack(load_rule_pack())
    assert validation.test_cases_run > 5
    assert validation.test_cases_failed == 0
    assert validation.ok, [i.message for i in validation.issues if i.level == "error"]


def test_rule_reason_and_warning_are_persisted():
    store, _ = _store_with_guesses()
    mains = store.assignments["L1"]
    assert mains.evidence.rule_warning, "rule warning must survive into the assignment"
    assert mains.evidence.rule_reason


def test_bulk_manual_override_updates_selected_nets_with_one_undo_entry():
    store, _ = _store_with_guesses()
    before_undo = len(store.undo_stack)

    changed = review_service.apply_manual_override_bulk(
        store,
        ["MYSTERY_NET", "L1"],
        final_class="HIGH_VOLTAGE",
        final_voltage_v=120.0,
        review_state="Reviewed",
        notes="bulk edit from All Assignments selection",
        reviewer="tester",
    )

    assert changed == 2
    assert len(store.undo_stack) == before_undo + 1
    assert store.undo_stack[-1].operation == "manual_bulk_edit"
    for net in ("MYSTERY_NET", "L1"):
        assignment = store.assignments[net]
        assert assignment.source == "manual"
        assert assignment.final_class == "HIGH_VOLTAGE"
        assert assignment.final_voltage_v == 120.0
        assert assignment.review_state == "Reviewed"
        assert assignment.notes == "bulk edit from All Assignments selection"
        assert assignment.reviewed_by == "tester"

    review_service.undo_last(store)
    assert store.assignments["MYSTERY_NET"].source != "manual"
    assert store.assignments["L1"].source != "manual"
