import csv
from pathlib import Path

from odb_clearance_analyzer.models import AnalysisConfig, AnalysisResult, MeasurementRecord, OdbJob
from odb_clearance_analyzer.reports import ReportWriter
from odb_clearance_analyzer.voltage_guessing.assignment_store import create_assignment_store, save_assignment_store_atomic
from odb_clearance_analyzer.voltage_guessing.galvanic_zones import GALVANIC_ZONE_1, GALVANIC_ZONE_2
from odb_clearance_analyzer.voltage_guessing.models import VoltageAssignment, VoltageEvidence
from odb_clearance_analyzer.voltage_guessing.requirements import (
    REQUIREMENT_SOURCE_GALVANIC_ZONE,
    REQUIREMENT_SOURCE_MANUAL_OVERRIDE,
    REQUIREMENT_SOURCE_RULE_GUESS,
    REQUIREMENT_SOURCE_UNKNOWN,
    resolve_required_spacing_voltage,
    resolve_voltage_standard_compliance,
)
from odb_clearance_analyzer.voltage_guessing import review_service


def _assignment(net: str, voltage: float | None, *, zone: str = "", source: str = "rule") -> VoltageAssignment:
    return VoltageAssignment(
        net_name=net,
        final_class="POWER" if voltage is not None else "UNKNOWN",
        final_voltage_v=voltage,
        reference_net="GND",
        voltage_type="DC",
        confidence="High" if voltage is not None else "Unknown",
        severity="Info" if voltage is not None else "Review",
        review_state="Reviewed" if voltage is not None else "Needs review",
        source=source,
        evidence=VoltageEvidence(evidence_type="test"),
        galvanic_zone=zone,
    )


def _store(*assignments: VoltageAssignment, zone_voltage: float = 1000.0):
    return create_assignment_store(
        list(assignments),
        settings={"galvanic_zone_voltage_v": zone_voltage},
    )


def _analysis_result(tmp_path: Path) -> AnalysisResult:
    job = OdbJob(
        root=tmp_path,
        step_name="rev_a",
        signal_layers=["top"],
        nets_by_number={1: "3V3", 2: "ISO_RX", 3: "GND"},
        feature_net_map={},
        features_by_layer={},
    )
    config = AnalysisConfig(odb_path=tmp_path / "job.zip", output_dir=tmp_path)
    return AnalysisResult(
        config=config,
        job=job,
        measurements=[MeasurementRecord("top", "3V3", "ISO_RX", 1.0, effective_max_voltage_v=1200.0)],
        per_net_minimum=[],
        critical_measurements=[MeasurementRecord("top", "3V3", "ISO_RX", 1.0, effective_max_voltage_v=1200.0)],
        layer_net_counts={"top": 2},
    )


def test_cross_zone_voltage_overrides_local_voltage():
    store = _store(
        _assignment("3V3", 3.3, zone=GALVANIC_ZONE_1),
        _assignment("ISO_RX", 3.3, zone=GALVANIC_ZONE_2),
    )

    result = resolve_required_spacing_voltage("3V3", "ISO_RX", store)

    assert result.required_voltage_v == 1000.0
    assert result.local_voltage_v == 0.0
    assert result.requirement_source == REQUIREMENT_SOURCE_GALVANIC_ZONE


def test_same_zone_uses_local_voltage():
    store = _store(
        _assignment("CELL10", 43.0, zone=GALVANIC_ZONE_1),
        _assignment("GND", 0.0, zone=GALVANIC_ZONE_1),
    )

    result = resolve_required_spacing_voltage("CELL10", "GND", store)

    assert result.required_voltage_v == 43.0
    assert result.voltage_difference_v == 43.0
    assert result.requirement_source == REQUIREMENT_SOURCE_RULE_GUESS


def test_missing_zone_uses_local_voltage_with_warning():
    store = _store(
        _assignment("PRI_12V", 12.0, zone=GALVANIC_ZONE_1),
        _assignment("AUX_5V", 5.0, zone=""),
    )

    result = resolve_required_spacing_voltage("PRI_12V", "AUX_5V", store)

    assert result.required_voltage_v == 7.0
    assert result.voltage_difference_v == 7.0
    assert "Zone assignment incomplete" in result.warning




def test_same_zone_local_voltage_is_pair_difference_not_absolute_max():
    store = _store(
        _assignment("NET_A", 10.0, zone=GALVANIC_ZONE_1),
        _assignment("NET_B", 21.0, zone=GALVANIC_ZONE_1),
    )

    result = resolve_required_spacing_voltage("NET_A", "NET_B", store)

    assert result.required_voltage_v == 11.0
    assert result.local_voltage_v == 11.0
    assert result.voltage_difference_v == 11.0
    assert result.net_a_voltage_v == 10.0
    assert result.net_b_voltage_v == 21.0


def test_ground_name_without_assignment_is_treated_as_zero_for_pair_difference():
    store = _store(_assignment("NET_A", 10.0, zone=GALVANIC_ZONE_1))

    result = resolve_required_spacing_voltage("NET_A", "GND", store)

    assert result.required_voltage_v == 10.0
    assert result.voltage_difference_v == 10.0
    assert result.net_b_voltage_v == 0.0


def test_unknown_local_voltage_returns_unknown():
    store = _store(_assignment("A", None), _assignment("B", None))

    result = resolve_required_spacing_voltage("A", "B", store)

    assert result.required_voltage_v is None
    assert result.requirement_source == REQUIREMENT_SOURCE_UNKNOWN
    assert "unknown" in result.warning.lower()


def test_zone_voltage_setting_change_affects_cross_zone_result():
    store = _store(
        _assignment("PRI", 3.3, zone=GALVANIC_ZONE_1),
        _assignment("SEC", 3.3, zone=GALVANIC_ZONE_2),
        zone_voltage=1500.0,
    )

    result = resolve_required_spacing_voltage("PRI", "SEC", store)

    assert result.required_voltage_v == 1500.0



def test_standard_voltage_compliance_ok_nok_unknown():
    assert resolve_voltage_standard_compliance(1000.0, 1200.0) == ("OK", 200.0)
    assert resolve_voltage_standard_compliance(1250.0, 900.0) == ("NOK", -350.0)
    assert resolve_voltage_standard_compliance(None, 900.0) == ("UNKNOWN", None)
    assert resolve_voltage_standard_compliance(1000.0, None) == ("UNKNOWN", None)


def test_resolver_is_deterministic_and_symmetric_for_requirement():
    store = _store(
        _assignment("PRI", 12.0, zone=GALVANIC_ZONE_1),
        _assignment("SEC", 5.0, zone=GALVANIC_ZONE_2),
    )

    a = resolve_required_spacing_voltage("PRI", "SEC", store)
    b = resolve_required_spacing_voltage("PRI", "SEC", store)
    reversed_pair = resolve_required_spacing_voltage("SEC", "PRI", store)

    assert a == b
    assert a.required_voltage_v == reversed_pair.required_voltage_v
    assert a.requirement_source == reversed_pair.requirement_source
    assert {a.zone_a, a.zone_b} == {reversed_pair.zone_a, reversed_pair.zone_b}


def test_bulk_apply_zone_only_preserves_voltage_class_and_value():
    store = _store(
        _assignment("A", 12.0, source="manual"),
        _assignment("B", 5.0, source="rule"),
    )
    before = {net: assignment.to_dict() for net, assignment in store.assignments.items()}

    changed = review_service.apply_galvanic_zone_bulk(store, ["A", "B"], galvanic_zone=GALVANIC_ZONE_1)

    assert changed == 2
    for net in ("A", "B"):
        assert store.assignments[net].galvanic_zone == GALVANIC_ZONE_1
        assert store.assignments[net].final_class == before[net]["final_class"]
        assert store.assignments[net].final_voltage_v == before[net]["final_voltage_v"]
        assert store.assignments[net].review_state == before[net]["review_state"]
        assert store.assignments[net].source == before[net]["source"]
    assert store.undo_stack[-1].operation == "galvanic_zone_bulk_edit"


def test_report_csv_contains_voltage_hierarchy_columns(tmp_path: Path):
    store = _store(
        _assignment("3V3", 3.3, zone=GALVANIC_ZONE_1),
        _assignment("ISO_RX", 3.3, zone=GALVANIC_ZONE_2),
    )
    save_assignment_store_atomic(store, tmp_path / "net_voltage_assignments.json")
    result = _analysis_result(tmp_path)

    ReportWriter().write_all(result)

    rows = list(csv.DictReader((tmp_path / "net_to_net_measurements_full.csv").open(newline="", encoding="utf-8")))
    assert rows[0]["required_voltage_v"] == "1000.0" or rows[0]["required_voltage_v"] == "1000"
    assert rows[0]["voltage_source"] == REQUIREMENT_SOURCE_GALVANIC_ZONE
    assert rows[0]["zone_a"] == GALVANIC_ZONE_1
    assert rows[0]["zone_b"] == GALVANIC_ZONE_2
    assert "voltage_difference_v" in rows[0]
    assert rows[0]["voltage_difference_v"] == "0.0" or rows[0]["voltage_difference_v"] == "0"
    assert rows[0]["standard_voltage_status"] == "OK"
    assert rows[0]["voltage_margin_v"] == "200.0" or rows[0]["voltage_margin_v"] == "200"

    assignment_rows = list(csv.DictReader((tmp_path / "net_voltage_assignments.csv").open(newline="", encoding="utf-8")))
    assert {row["net_name"] for row in assignment_rows} == {"3V3", "ISO_RX"}
    assert assignment_rows[0]["assigned_voltage_v"] != ""
    markdown = (tmp_path / "net_to_net_clearance_report.md").read_text(encoding="utf-8")
    assert "Assigned Voltages" in markdown
    assert "OK/NOK" in markdown
