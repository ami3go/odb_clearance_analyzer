"""Phase 4 tests: batch previews, explainability, correction-to-rule, summaries."""

import csv

from odb_clearance_analyzer.voltage_guessing import load_rule_pack, review_service
from odb_clearance_analyzer.voltage_guessing import phase4
from odb_clearance_analyzer.voltage_guessing.assignment_store import create_assignment_store, load_assignment_store, save_assignment_store_atomic

NETS = ["GND", "3V3", "DC_LINK_800V", "MYSTERY_NET", "VSYS", "VSYS_MCU", "VSYS_RF"]


def _store():
    pack = load_rule_pack()
    store = create_assignment_store([], project_revision="rev_p4")
    review_service.run_auto_detect(store, NETS, pack, source_revision="rev_p4")
    return store, pack


def test_batch_preview_blocks_warning_and_critical_bulk_approve():
    store, _ = _store()
    preview = phase4.make_batch_preview(store, ["GND", "DC_LINK_800V"], "approve")
    assert preview.affected_count == 1
    assert preview.blocked_count == 1
    assert any(r.net_name == "DC_LINK_800V" and r.blocked for r in preview.rows)
    applied = phase4.apply_batch_action(store, ["GND", "DC_LINK_800V"], "approve", reason="batch")
    assert applied == 1
    assert store.assignments["GND"].review_state == "Approved"
    assert store.assignments["DC_LINK_800V"].review_state == "Needs review"


def test_batch_set_class_voltage_is_one_undoable_operation():
    store, _ = _store()
    count = phase4.apply_batch_action(
        store, ["VSYS", "VSYS_MCU"], "set_class_voltage", final_class="POWER", final_voltage_v=3.8, reason="board power tree"
    )
    assert count == 2
    assert store.assignments["VSYS"].final_voltage_v == 3.8
    assert store.undo_stack[-1].operation == "batch_set_class_voltage"
    review_service.undo_last(store)
    assert store.assignments["VSYS"].final_voltage_v != 3.8


def test_why_explanation_contains_winning_and_losing_rules():
    store, pack = _store()
    why = phase4.explain_assignment(store.assignments["DC_LINK_800V"], pack)
    assert "Winning rule" in why.text
    assert "DC_LINK_800V" in why.text
    assert why.winning_rule_id


def test_correction_to_rule_writes_project_local_csv(tmp_path):
    store, _ = _store()
    review_service.apply_manual_override(store, "VSYS", final_class="POWER", final_voltage_v=3.8, notes="sys rail")
    suggestions = phase4.suggest_similar_nets(store, "VSYS")
    assert {s.net_name for s in suggestions} >= {"VSYS_MCU", "VSYS_RF"}
    path = phase4.create_project_local_rule_from_correction(tmp_path, token="VSYS", assignment=store.assignments["VSYS"], reviewer="tester")
    rows = list(csv.DictReader(path.open()))
    assert rows and rows[-1]["tags"] == "user_correction;project_local"
    assert rows[-1]["net_class"] == "POWER" and rows[-1]["voltage_v"] == "3.8"


def test_copyable_summary_and_diff_and_persistent_review_session(tmp_path):
    old, _ = _store()
    new, _ = _store()
    review_service.apply_manual_override(new, "VSYS", final_class="POWER", final_voltage_v=3.8, notes="changed")
    diff = phase4.diff_assignments(old.assignments, new.assignments)
    assert any(r.net_name == "VSYS" and r.category == "voltage_changed" for r in diff)
    summary = phase4.copyable_review_summary(new, project_name="rev_p4", rule_pack_name="builtin_default", template="default")
    assert "Voltage assignment status" in summary and "rev_p4" in summary
    phase4.update_review_session(new, queue_position=2, active_filter="Review Needed", skipped_net="MYSTERY_NET")
    path = tmp_path / "net_voltage_assignments.json"
    save_assignment_store_atomic(new, path)
    loaded = load_assignment_store(path)
    assert loaded.review_session.queue_position == 2
    assert "MYSTERY_NET" in loaded.review_session.skipped_nets


def test_correction_rule_is_loaded_back_and_wins(tmp_path):
    """Phase 4 gate 3 end-to-end: a correction rule must affect guessing."""
    from odb_clearance_analyzer.voltage_guessing.rule_loader import load_layered_rule_pack
    from odb_clearance_analyzer.voltage_guessing import guess_net_voltage

    store, _ = _store()
    review_service.apply_manual_override(store, "VSYS", final_class="POWER", final_voltage_v=3.8, notes="sys rail")
    phase4.create_project_local_rule_from_correction(
        tmp_path, token="VSYS", assignment=store.assignments["VSYS"], reviewer="tester"
    )
    layered = load_layered_rule_pack(tmp_path)
    assert layered.layer_counts.get("project-local") == 1
    guess = guess_net_voltage("VSYS_SNS", layered)
    assert guess.guessed_class == "POWER"
    assert guess.guessed_voltage_v == 3.8
    assert guess.winning_rule_id.startswith("user_correction_")
    # Built-in-only pack must NOT know this rule (proves layering, not mutation).
    baseline = load_rule_pack()
    assert guess_net_voltage("VSYS_SNS", baseline).guessed_class != "POWER"
