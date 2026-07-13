import csv
from pathlib import Path

from odb_clearance_analyzer.voltage_guessing import load_rule_pack, validate_rule_pack


def test_rule_validation_rejects_bad_numeric_fields(tmp_path: Path):
    pack_dir = tmp_path / "bad_rule_pack"
    pack_dir.mkdir()
    (pack_dir / "manifest.json").write_text('{"schema_version":1,"files":["bad.csv"]}', encoding="utf-8")
    (pack_dir / "defaults.json").write_text('{"schema_version":1}', encoding="utf-8")
    with (pack_dir / "bad.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "rule_id", "priority", "enabled", "pattern", "match_type", "match_on", "net_class",
            "voltage_v", "reference_net", "voltage_type", "confidence", "severity", "reason", "warning", "tags",
        ])
        writer.writeheader()
        writer.writerow({
            "rule_id": "bad_voltage", "priority": "abc", "enabled": "true", "pattern": "BAD",
            "match_type": "exact", "match_on": "normalized", "net_class": "POWER", "voltage_v": "abc",
            "reference_net": "GND", "voltage_type": "DC", "confidence": "High", "severity": "Info",
            "reason": "bad", "warning": "", "tags": "",
        })
    validation = validate_rule_pack(load_rule_pack(pack_dir))
    assert not validation.ok
    messages = "\n".join(issue.message for issue in validation.issues)
    assert "Invalid numeric value for voltage_v" in messages
    assert "Invalid integer value for priority" in messages


# ---- v0.4.21 crash-hardening regressions ----

def test_invalid_regex_in_user_rule_does_not_crash(tmp_path: Path):
    from odb_clearance_analyzer.voltage_guessing.rule_loader import load_layered_rule_pack
    from odb_clearance_analyzer.voltage_guessing import guess_net_voltage

    (tmp_path / "project_local_corrections.csv").write_text(
        "rule_id,priority,enabled,pattern,match_type,match_on,net_class,voltage_v,"
        "reference_net,voltage_type,confidence,severity,reason,warning,tags\n"
        "bad_regex,700,true,([unclosed,regex,normalized,POWER,5,GND,DC,High,Info,r,,\n"
        "good_token,700,true,FOO,token,normalized,POWER,5,GND,DC,High,Info,ok,,\n",
        encoding="utf-8",
    )
    layered = load_layered_rule_pack(tmp_path)
    # invalid regex degrades to never-matching; other rules still work
    assert guess_net_voltage("ANYNET", layered).guessed_class == "UNKNOWN"
    assert guess_net_voltage("FOO_BAR", layered).guessed_voltage_v == 5.0


def test_control_char_net_gets_fallback_not_abort():
    from odb_clearance_analyzer.voltage_guessing import guess_voltage_for_nets

    out = guess_voltage_for_nets(["GND", "NET\x01BAD", "3V3"], load_rule_pack())
    assert len(out) == 3
    bad = next(a for a in out if a.net_name == "NET\x01BAD")
    assert bad.final_class == "UNKNOWN"
    assert bad.review_state == "Needs review"
    assert "normalized" in bad.evidence.rule_reason


def test_control_char_net_survives_downstream(tmp_path: Path):
    from odb_clearance_analyzer.voltage_guessing import phase4, review_service
    from odb_clearance_analyzer.voltage_guessing.assignment_store import create_assignment_store
    from odb_clearance_analyzer.voltage_guessing.exports import export_all_voltage_files
    from odb_clearance_analyzer.voltage_guessing.revision_matcher import match_revision

    pack = load_rule_pack()
    store = create_assignment_store([])
    review_service.run_auto_detect(store, ["GND", "NET\x01BAD", "VSYS"], pack)
    export_all_voltage_files(list(store.assignments.values()), tmp_path, project_revision="r")
    assert phase4.suggest_similar_nets(store, "VSYS") is not None
    match_revision(list(store.assignments.values()), ["GND", "NET\x01BAD"], pack)


def test_store_loader_rejects_non_object_with_valueerror(tmp_path: Path):
    import pytest
    from odb_clearance_analyzer.voltage_guessing.assignment_store import load_assignment_store

    bad = tmp_path / "list.json"
    bad.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError):
        load_assignment_store(bad)  # AttributeError here would crash the GUI open path


# ---- v0.4.24 GUI auto-detect state regressions ----

def test_gui_voltage_net_list_falls_back_to_analysis_outputs_when_job_net_table_empty():
    """Auto-detect must not warn after analysis when job.named_nets is empty.

    Some real ODB++ jobs can leave the parsed EDA net table empty/stale while
    the completed analysis still contains net names in geometry/report records.
    The GUI should use those analyzed nets instead of telling the user to run
    analysis again.
    """
    from types import SimpleNamespace
    from odb_clearance_analyzer.gui import _collect_voltage_net_names_from_result

    result = SimpleNamespace(
        job=SimpleNamespace(named_nets=set(), nets_by_number={}, feature_net_map={}),
        net_geometry_by_layer={"TOP": {"GND": object(), "3V3": object(), "$NONE$": object()}},
        per_net_minimum=[SimpleNamespace(net="HV_400V", other_net="GND")],
        measurements=[SimpleNamespace(net_a="L1", net_b="N")],
        critical_measurements=[],
    )

    assert _collect_voltage_net_names_from_result(result) == {"3V3", "GND", "HV_400V", "L1", "N"}
