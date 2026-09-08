from pathlib import Path

from odb_clearance_analyzer.models import AnalysisConfig, AnalysisResult, MeasurementRecord, OdbJob
from odb_clearance_analyzer.voltage_guessing.assignment_import import import_voltage_assignments
from odb_clearance_analyzer.voltage_guessing.assignment_store import create_assignment_store, load_assignment_store, save_assignment_store_atomic
from odb_clearance_analyzer.voltage_guessing.exports import export_voltage_assignments_csv
from odb_clearance_analyzer.voltage_guessing.galvanic_zones import (
    GALVANIC_ZONE_1,
    GALVANIC_ZONE_2,
    export_galvanic_zone_spacing_csv,
    normalize_galvanic_zone,
)
from odb_clearance_analyzer.voltage_guessing.models import VoltageAssignment, VoltageEvidence
from odb_clearance_analyzer.voltage_guessing import review_service


def _assignment(net: str, *, voltage: float = 5.0) -> VoltageAssignment:
    return VoltageAssignment(
        net_name=net,
        final_class="POWER",
        final_voltage_v=voltage,
        reference_net="GND",
        voltage_type="DC",
        confidence="High",
        severity="Info",
        review_state="Reviewed",
        source="rule",
        evidence=VoltageEvidence(evidence_type="test"),
    )


def _result(tmp_path: Path) -> AnalysisResult:
    job = OdbJob(
        root=tmp_path,
        step_name="rev_a",
        signal_layers=["top"],
        nets_by_number={1: "PRI", 2: "SEC", 3: "AUX"},
        feature_net_map={},
        features_by_layer={},
    )
    config = AnalysisConfig(odb_path=tmp_path / "job.zip", output_dir=tmp_path)
    return AnalysisResult(
        config=config,
        job=job,
        measurements=[
            MeasurementRecord("top", "PRI", "SEC", 1.0, effective_max_voltage_v=900.0),
            MeasurementRecord("top", "PRI", "AUX", 4.0, effective_max_voltage_v=1500.0),
            MeasurementRecord("top", "SEC", "AUX", 2.0, effective_max_voltage_v=1200.0),
        ],
        per_net_minimum=[],
        critical_measurements=[],
        layer_net_counts={},
    )


def test_bulk_manual_override_sets_galvanic_zone_and_undoes():
    store = create_assignment_store([_assignment("PRI"), _assignment("HV")])

    changed = review_service.apply_manual_override_bulk(
        store,
        ["PRI", "HV"],
        final_class="POWER",
        final_voltage_v=12.0,
        review_state="Reviewed",
        notes="primary side",
        reviewer="tester",
        galvanic_zone=GALVANIC_ZONE_1,
    )

    assert changed == 2
    assert {store.assignments[n].galvanic_zone for n in ("PRI", "HV")} == {GALVANIC_ZONE_1}
    assert store.undo_stack[-1].operation == "manual_bulk_edit"
    review_service.undo_last(store)
    assert store.assignments["PRI"].galvanic_zone == ""


def test_store_and_export_import_preserve_galvanic_zone(tmp_path: Path):
    pri = _assignment("PRI")
    pri.galvanic_zone = GALVANIC_ZONE_1
    sec = _assignment("SEC")
    sec.galvanic_zone = GALVANIC_ZONE_2
    store = create_assignment_store(
        [pri, sec],
        settings={"galvanic_zone_voltage_v": 1250.0, "galvanic_zones_supported": [GALVANIC_ZONE_1, GALVANIC_ZONE_2]},
    )

    store_path = tmp_path / "net_voltage_assignments.json"
    save_assignment_store_atomic(store, store_path)
    reloaded = load_assignment_store(store_path)
    assert reloaded.settings["galvanic_zone_voltage_v"] == 1250.0
    assert reloaded.assignments["PRI"].galvanic_zone == GALVANIC_ZONE_1

    csv_path = tmp_path / "assignments.csv"
    export_voltage_assignments_csv(list(reloaded.assignments.values()), csv_path)
    text = csv_path.read_text(encoding="utf-8")
    assert "galvanic_zone" in text
    imported = import_voltage_assignments(csv_path)
    assert imported.ok
    zones = {a.net_name: a.galvanic_zone for a in imported.assignments}
    assert zones == {"PRI": GALVANIC_ZONE_1, "SEC": GALVANIC_ZONE_2}


def test_galvanic_zone_report_checks_only_zone_1_to_zone_2_pairs(tmp_path: Path):
    pri = _assignment("PRI")
    pri.galvanic_zone = GALVANIC_ZONE_1
    sec = _assignment("SEC")
    sec.galvanic_zone = GALVANIC_ZONE_2
    aux = _assignment("AUX")
    aux.galvanic_zone = GALVANIC_ZONE_1
    store = create_assignment_store([pri, sec, aux])

    path, rows, fails = export_galvanic_zone_spacing_csv(_result(tmp_path), store, tmp_path / "galvanic_zone_spacing.csv", inter_zone_voltage_v=1000.0)

    assert path.exists()
    assert rows == 2  # PRI-SEC and SEC-AUX; PRI-AUX is same-zone and ignored.
    assert fails == 1
    body = path.read_text(encoding="utf-8")
    assert "PRI,Zone 1,SEC,Zone 2" in body
    assert "voltage_difference_v" in body
    assert "ok_nok" in body
    assert "NOK" in body
    assert "OK" in body
    assert "FAIL" in body
    assert "PASS" in body


def test_galvanic_zone_normalization_accepts_common_spellings():
    assert normalize_galvanic_zone("zone_1") == GALVANIC_ZONE_1
    assert normalize_galvanic_zone("Z2") == GALVANIC_ZONE_2
    assert normalize_galvanic_zone("not supported") == ""
