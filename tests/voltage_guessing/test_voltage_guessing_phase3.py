"""Phase 3 tests: revision import, deterministic matching, golden fixture."""

import csv
import json
from pathlib import Path

import pytest

from odb_clearance_analyzer.voltage_guessing import load_rule_pack, review_service
from odb_clearance_analyzer.voltage_guessing.assignment_import import import_voltage_assignments
from odb_clearance_analyzer.voltage_guessing.assignment_store import create_assignment_store
from odb_clearance_analyzer.voltage_guessing.revision_matcher import (
    MATCH_SCORE_THRESHOLD_DEFAULT,
    apply_manual_mapping,
    apply_safe_matches,
    compute_match_score,
    export_revision_delta_csv,
    export_revision_match_csv,
    match_revision,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def _fixture_pipeline(tmp_path: Path):
    pack = load_rule_pack()
    imp = import_voltage_assignments(FIXTURES / "rev_a_assignments.json")
    assert imp.ok, imp.rejected_reason
    nets = (FIXTURES / "rev_b_netlist.txt").read_text().splitlines()
    match = match_revision(imp.assignments, nets, pack, source_file="rev_a_assignments.json", source_revision="rev_a")
    store = create_assignment_store([], project_revision="rev_b")
    apply_safe_matches(store, match, imp.assignments, pack, current_revision="rev_b")
    return pack, imp, nets, match, store


# ---------- import error handling (addendum 9.1.1) ----------

def test_import_rejects_invalid_json(tmp_path: Path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    result = import_voltage_assignments(bad)
    assert not result.ok and "Invalid JSON" in result.rejected_reason and not result.assignments


def test_import_rejects_newer_schema(tmp_path: Path):
    f = tmp_path / "future.json"
    f.write_text(json.dumps({"schema_version": 99, "assignments": {"X": {}}}), encoding="utf-8")
    result = import_voltage_assignments(f)
    assert not result.ok and "newer application version" in result.rejected_reason


def test_import_csv_rejects_missing_columns(tmp_path: Path):
    f = tmp_path / "bad.csv"
    f.write_text("net_name,final_class\nGND,GND\n", encoding="utf-8")
    result = import_voltage_assignments(f)
    assert not result.ok and "Missing required columns" in result.rejected_reason


def test_import_csv_rejects_duplicates(tmp_path: Path):
    f = tmp_path / "dup.csv"
    f.write_text(
        "net_name,final_class,final_voltage_v,review_state\nGND,GND,0,Approved\nGND,GND,0,Approved\n",
        encoding="utf-8",
    )
    result = import_voltage_assignments(f)
    assert not result.ok and "Duplicate net names" in result.rejected_reason


def test_import_csv_skips_bad_rows_but_loads(tmp_path: Path):
    f = tmp_path / "mixed.csv"
    f.write_text(
        "net_name,final_class,final_voltage_v,review_state\n"
        "GND,GND,0,Approved\n"
        "BAD1,NOT_A_CLASS,0,Approved\n"
        "BAD2,POWER,abc,Approved\n"
        "3V3,POWER,3.3,Approved\n",
        encoding="utf-8",
    )
    result = import_voltage_assignments(f)
    assert result.ok
    assert {a.net_name for a in result.assignments} == {"GND", "3V3"}
    assert len(result.skipped_rows) == 2


# ---------- match score (addendum 11.1) ----------

def test_match_score_is_deterministic_and_sane():
    pack = load_rule_pack()
    s1 = compute_match_score("Vsys_Main", "VSYS_MAIN_PWR", pack)
    s2 = compute_match_score("Vsys_Main", "VSYS_MAIN_PWR", pack)
    assert s1 == s2 and 0 <= s1 <= 100 and s1 >= MATCH_SCORE_THRESHOLD_DEFAULT
    identical = compute_match_score("VDD_1V8", "VDD_1V8", pack)
    assert identical == 90  # max without fingerprints: fp_pads weight 0.10 unavailable (11.2)
    assert compute_match_score("VDD_1V8", "VDD_1V8", pack, old_prefixes={"U"}, new_prefixes={"U"}) == 100
    unrelated = compute_match_score("GND", "NEW_ETH_TX_P", pack)
    assert unrelated < MATCH_SCORE_THRESHOLD_DEFAULT


def test_fingerprint_prefixes_raise_score():
    pack = load_rule_pack()
    base = compute_match_score("CTRL_A", "CTRL_B2", pack)
    with_fp = compute_match_score(
        "CTRL_A", "CTRL_B2", pack,
        old_prefixes={"R", "U", "C"}, new_prefixes={"R", "U", "C"},
    )
    assert with_fp == base + 10  # Jaccard 1.0 * weight 0.10


# ---------- matching behavior (Phase 3 gate 1-8) ----------

def test_safe_matches_apply_and_suggestions_do_not(tmp_path: Path):
    _, imp, _, match, store = _fixture_pipeline(tmp_path)
    by_status = {}
    for e in match.entries:
        by_status.setdefault(e.match_status, []).append(e)
    assert all(e.applied for e in by_status["exact"])
    assert all(e.applied for e in by_status["case_insensitive"])
    assert all(e.applied for e in by_status["normalized"])
    assert all(not e.applied for e in by_status["likely_renamed"])
    assert all(not e.applied for e in by_status["conflict"])
    # Suggested rename target is NOT in the store yet... it is: as "new"? No — suggestion suppresses "new".
    assert "VSYS_MAIN_PWR" not in store.assignments


def test_review_work_survives_matching(tmp_path: Path):
    _, _, _, _, store = _fixture_pipeline(tmp_path)
    assert store.assignments["DC_LINK_800V"].review_state == "Approved"
    assert store.assignments["DC_LINK_800V"].reviewed_by == "fixture"
    assert store.assignments["mcu_spi_clk"].source == "imported_case_insensitive"
    assert store.assignments["SENSE_DIV"].source == "imported_normalized"


def test_new_nets_get_rule_guesses_and_missing_preserved(tmp_path: Path):
    _, _, _, _, store = _fixture_pipeline(tmp_path)
    assert store.assignments["NEW_ETH_TX_P"].source == "rule"
    assert store.assignments["OLD_ONLY_NET"].review_state == "Obsolete / missing in new revision"


def test_waiver_carry_forward_rules(tmp_path: Path):
    _, _, _, _, store = _fixture_pipeline(tmp_path)
    old_only = store.assignments["OLD_ONLY_NET"]
    assert old_only.waiver.waived and old_only.waiver.waiver_scope == "project_global"
    canl = store.assignments["CANL"]
    assert not canl.waiver.waived, "current_revision_only waiver must not carry forward"
    assert canl.review_state == "Needs review"


def test_manual_mapping_applies_suggestion(tmp_path: Path):
    pack, imp, _, match, store = _fixture_pipeline(tmp_path)
    applied = apply_manual_mapping(store, "Vsys_Main", "VSYS_MAIN_PWR", imp.assignments, match, current_revision="rev_b")
    assert applied.source == "imported_manual_mapping"
    assert store.assignments["VSYS_MAIN_PWR"].final_voltage_v == 3.8
    entry = next(e for e in match.entries if e.match_status == "likely_renamed" and e.new_net == "VSYS_MAIN_PWR")
    assert entry.applied


def test_undo_last_import_restores_previous_state(tmp_path: Path):
    pack = load_rule_pack()
    imp = import_voltage_assignments(FIXTURES / "rev_a_assignments.json")
    nets = (FIXTURES / "rev_b_netlist.txt").read_text().splitlines()
    match = match_revision(imp.assignments, nets, pack)
    store = create_assignment_store([], project_revision="rev_b")
    apply_safe_matches(store, match, imp.assignments, pack, current_revision="rev_b")
    assert store.assignments
    operation = review_service.undo_last(store)
    assert operation == "import_apply"
    assert not store.assignments, "undo must remove everything the import created"


def test_conflict_requires_review_and_is_not_applied(tmp_path: Path):
    _, _, _, match, store = _fixture_pipeline(tmp_path)
    conflicts = [e for e in match.entries if e.match_status == "conflict"]
    assert len(conflicts) == 1
    assert conflicts[0].new_net == "SIG A"
    assert conflicts[0].action_required == "resolve_conflict"
    assert "SIG A" not in store.assignments


# ---------- exports + golden fixture (Phase 3 gate 9-11) ----------

def test_match_and_delta_csv_export(tmp_path: Path):
    _, imp, _, match, store = _fixture_pipeline(tmp_path)
    match_csv = export_revision_match_csv(match, tmp_path / "net_voltage_assignment_revision_match.csv")
    delta_csv = export_revision_delta_csv(imp.assignments, store, match, tmp_path / "net_voltage_assignment_revision_delta.csv")
    with match_csv.open() as f:
        rows = list(csv.DictReader(f))
    assert {r["match_status"] for r in rows} >= {"exact", "case_insensitive", "normalized", "likely_renamed", "conflict", "new", "missing"}
    with delta_csv.open() as f:
        delta_rows = list(csv.DictReader(f))
    assert set(delta_rows[0]) == {
        "delta_type", "old_net", "new_net", "old_class", "new_class",
        "old_voltage_v", "new_voltage_v", "old_review_state", "new_review_state",
        "match_score", "reason", "required_action", "notes",
    }
    by_new = {r["new_net"] or r["old_net"]: r["delta_type"] for r in delta_rows}
    assert by_new["OLD_ONLY_NET"] == "deleted"
    assert by_new["NEW_ETH_TX_P"] == "added"
    assert by_new["SENSE_DIV"] == "renamed"
    assert by_new["GND"] == "unchanged"


def test_golden_end_to_end_fixture(tmp_path: Path):
    """Addendum 29.2.1: pipeline output must equal the frozen expected table byte-for-byte."""
    _, _, _, match, _ = _fixture_pipeline(tmp_path)
    produced = export_revision_match_csv(match, tmp_path / "produced_match_table.csv")
    expected = (FIXTURES / "expected_match_table.csv").read_bytes()
    assert produced.read_bytes() == expected, (
        "Match behavior changed. If intentional, regenerate tests/fixtures/expected_match_table.csv "
        "together with the spec (frozen weights, addendum 11.1)."
    )


def test_import_json_skips_bad_voltage_values(tmp_path: Path):
    f = tmp_path / "bad_voltage.json"
    f.write_text(json.dumps({
        "schema_version": 1,
        "file_kind": "net_voltage_assignment_export",
        "assignments": {
            "BAD": {"final_class": "POWER", "final_voltage_v": "abc", "review_state": "Approved"},
            "NAN": {"final_class": "POWER", "final_voltage_v": "NaN", "review_state": "Approved"},
            "GOOD": {"final_class": "POWER", "final_voltage_v": 3.3, "review_state": "Approved"},
        },
    }), encoding="utf-8")
    result = import_voltage_assignments(f)
    assert result.ok
    assert {a.net_name for a in result.assignments} == {"GOOD"}
    assert len(result.skipped_rows) == 2


def test_import_rejects_project_assignment_store_file(tmp_path: Path):
    f = tmp_path / "net_voltage_assignments.json"
    f.write_text(json.dumps({
        "schema_version": 1,
        "file_kind": "net_voltage_assignment_store",
        "assignments": {"GND": {"final_class": "GND", "final_voltage_v": 0, "review_state": "Approved"}},
    }), encoding="utf-8")
    result = import_voltage_assignments(f)
    assert not result.ok
    assert "project assignment store" in result.rejected_reason
