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


def test_cell_number_rule_uses_configurable_max_cell_voltage():
    from dataclasses import replace

    from odb_clearance_analyzer.voltage_guessing import guess_net_voltage, load_rule_pack

    pack = load_rule_pack()
    default_guess = guess_net_voltage("Cell3", pack)
    assert default_guess.guessed_class == "BATTERY"
    assert default_guess.winning_rule_id == "battery_cell_number"
    assert abs(default_guess.guessed_voltage_v - 12.9) < 1e-9

    custom_defaults = replace(pack.defaults, battery_volts_per_cell_max=4.1)
    custom_guess = guess_net_voltage("BAT_CELL_6", pack, custom_defaults)
    assert custom_guess.guessed_class == "BATTERY"
    assert abs(custom_guess.guessed_voltage_v - 24.6) < 1e-9


def test_voltage_guessing_max_cell_voltage_persists_in_settings_profile(tmp_path):
    from pathlib import Path

    from odb_clearance_analyzer.models import AnalysisConfig
    from odb_clearance_analyzer.settings_profile import analysis_config_to_profile, profile_to_analysis_config

    config = AnalysisConfig(
        odb_path=Path("example.tgz"),
        output_dir=tmp_path,
        voltage_guessing={"assignment_store_path": "net_voltage_assignments.json", "max_cell_voltage_v": 4.35},
    )
    profile = analysis_config_to_profile(config, app_version="test", include_paths=True, source="unit_test")
    assert profile["settings"]["voltage_guessing"]["max_cell_voltage_v"] == 4.35

    restored = profile_to_analysis_config(profile)
    assert restored.voltage_guessing["max_cell_voltage_v"] == 4.35


def test_assignment_store_persists_voltage_guessing_settings(tmp_path):
    import json

    from odb_clearance_analyzer.voltage_guessing.assignment_store import create_assignment_store, load_assignment_store, save_assignment_store_atomic

    store = create_assignment_store([], settings={"max_cell_voltage_v": 4.25})
    path = tmp_path / "net_voltage_assignments.json"
    save_assignment_store_atomic(store, path)
    payload = json.loads(path.read_text())
    assert payload["settings"]["max_cell_voltage_v"] == 4.25

    restored = load_assignment_store(path)
    assert restored.settings["max_cell_voltage_v"] == 4.25

def test_cell_and_ntc_net_name_masks_from_user_examples():
    from odb_clearance_analyzer.voltage_guessing import guess_net_voltage, load_rule_pack, normalize_net_name

    pack = load_rule_pack()

    assert normalize_net_name("stack_cell10+") == "STACK_CELL10"
    assert normalize_net_name("stack_cell10-") == "STACK_CELL10"

    for net in ["stack_cell10+", "stack_cell10-", "STACK_CELL10"]:
        result = guess_net_voltage(net, pack)
        assert result.guessed_class == "BATTERY", (net, result)
        assert result.winning_rule_id == "battery_cell_number", (net, result)
        assert abs(result.guessed_voltage_v - 43.0) < 1e-9, (net, result)

    for net in ["Cell0", "Cell0+", "STACK_CELL0+"]:
        result = guess_net_voltage(net, pack)
        assert result.guessed_class == "GND", (net, result)
        assert result.winning_rule_id == "battery_cell_zero_ground", (net, result)
        assert result.guessed_voltage_v == 0, (net, result)
        assert result.to_assignment().review_state == "Approved", (net, result)

    for net in ["BMIC_NTC3+", "BMIC_PCB_NTC1+", "NTC"]:
        result = guess_net_voltage(net, pack)
        assert result.guessed_class == "IO_ANALOG", (net, result)
        assert result.winning_rule_id == "ntc_low_voltage_max", (net, result)
        assert abs(result.guessed_voltage_v - 5.5) < 1e-9, (net, result)

