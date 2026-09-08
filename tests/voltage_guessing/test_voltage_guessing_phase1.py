from pathlib import Path

from odb_clearance_analyzer.voltage_guessing import (
    guess_net_voltage,
    guess_voltage_for_nets,
    load_rule_pack,
    normalize_net_name,
    parse_voltage_token,
    validate_rule_pack,
)
from odb_clearance_analyzer.voltage_guessing.exports import export_all_voltage_files


def test_normalization_single_algorithm():
    assert normalize_net_name("SEC-GND") == "SEC_GND"
    assert normalize_net_name("SEC.GND") == "SEC_GND"
    assert normalize_net_name("SEC GND") == "SEC_GND"
    assert normalize_net_name("+3V3") == "3V3"


def test_voltage_parser_accepts_explicit_voltage_tokens():
    cases = {
        "3V3": 3.3,
        "1V8": 1.8,
        "5V": 5.0,
        "5V0": 5.0,
        "12V": 12.0,
        "48V": 48.0,
        "400V": 400.0,
        "P3V3": 3.3,
        "M12V": -12.0,
        "N12V": -12.0,
        "+15V": 15.0,
        "-15V": -15.0,
        "VREF_2V5": 2.5,
        "HV400": 400.0,
    }
    for name, expected in cases.items():
        token = parse_voltage_token(name)
        assert token is not None, name
        assert abs(token.voltage_v - expected) < 1e-12


def test_voltage_parser_does_not_parse_indexes():
    for name in ["GPIO12", "ADC_IN1", "UART2_TX", "CH4", "M2_CS", "N1"]:
        assert parse_voltage_token(name) is None, name


def test_builtin_rule_pack_validates():
    pack = load_rule_pack()
    validation = validate_rule_pack(pack)
    assert validation.ok, validation.issues
    assert len(pack.rules) > 10


def test_common_net_guesses():
    pack = load_rule_pack()
    cases = {
        "GND": ("GND", 0.0, "High"),
        "AGND": ("GND", 0.0, "High"),
        "3V3": ("POWER", 3.3, "High"),
        "VDD_1V8": ("POWER", 1.8, "High"),
        "+12V": ("POWER", 12.0, "High"),
        "M12V": ("POWER_NEGATIVE", -12.0, "High"),
        "N12V": ("POWER_NEGATIVE", -12.0, "High"),
        "HV400": ("HIGH_VOLTAGE", 400.0, "High"),
        "DC_LINK_800V": ("HIGH_VOLTAGE", 800.0, "High"),
        "GPIO12": ("IO_DIGITAL", 3.3, "Medium"),
        "ADC_IN1": ("IO_ANALOG", 3.3, "Medium"),
        "USB_VBUS": ("POWER", 5.0, "High"),
        "VBUS_PD": ("POWER_VARIABLE", 20.0, "Medium"),
        "POE_VIN": ("POWER_HIGHER_LOW_VOLTAGE", 57.0, "Medium"),
        "BAT_4S": ("BATTERY", 17.2, "Medium"),
        "Cell3": ("BATTERY", 12.9, "Medium"),
        "CANH": ("COMMUNICATION", None, "Medium"),
        "SEC_GND": ("GND", 0.0, "High"),
    }
    for net, (cls, voltage, confidence) in cases.items():
        result = guess_net_voltage(net, pack)
        assert result.guessed_class == cls, (net, result)
        assert result.confidence == confidence, (net, result)
        if voltage is None:
            assert result.guessed_voltage_v is None, net
        else:
            assert result.guessed_voltage_v is not None, net
            assert abs(result.guessed_voltage_v - voltage) < 1e-9, net


def test_false_positive_guards_for_mains_and_indexes():
    pack = load_rule_pack()
    assert guess_net_voltage("L1_SW", pack).guessed_class != "MAINS"
    assert guess_net_voltage("N_FET_G", pack).guessed_class != "MAINS"
    assert guess_net_voltage("M2_CS", pack).guessed_voltage_v is None
    assert guess_net_voltage("CH4", pack).guessed_voltage_v is None


def test_exports_create_phase1_files(tmp_path: Path):
    pack = load_rule_pack()
    assignments = guess_voltage_for_nets(["GND", "3V3", "GPIO12"], pack)
    files = export_all_voltage_files(assignments, tmp_path, project_revision="test")
    assert (tmp_path / "net_voltage_guessing.csv").exists()
    assert (tmp_path / "net_voltage_assignments.csv").exists()
    assert (tmp_path / "net_voltage_assignments_test.json").exists()
    assert set(files) == {"voltage_guessing_csv", "voltage_assignments_json", "voltage_assignments_csv"}
    import json
    snapshot = json.loads((tmp_path / "net_voltage_assignments_test.json").read_text())
    assert snapshot["file_kind"] == "net_voltage_assignment_export"
    assert "undo_stack" not in snapshot and "review_session" not in snapshot


def test_negative_and_common_alias_coverage():
    pack = load_rule_pack()
    cases = {
        "-12V": ("POWER_NEGATIVE", -12.0),
        "-15V": ("POWER_NEGATIVE", -15.0),
        "NEG12V": ("POWER_NEGATIVE", -12.0),
        "VEE": ("POWER_NEGATIVE", None),
        "VNEG": ("POWER_NEGATIVE", None),
        "BAT+": ("BATTERY", None),
        "BAT-": ("BATTERY", None),
        "VBAT": ("BATTERY", None),
        "VBATT": ("BATTERY", None),
        "PACK+": ("BATTERY", None),
        "PACK-": ("BATTERY", None),
        "HV+": ("HIGH_VOLTAGE", None),
        "HV-": ("HIGH_VOLTAGE", None),
        "BULK+": ("HIGH_VOLTAGE", None),
        "BULK-": ("HIGH_VOLTAGE", None),
        "RECT+": ("HIGH_VOLTAGE", None),
        "RECT-": ("HIGH_VOLTAGE", None),
    }
    for net, (expected_class, expected_voltage) in cases.items():
        result = guess_net_voltage(net, pack)
        assert result.guessed_class == expected_class, (net, result)
        if expected_voltage is None:
            assert result.guessed_voltage_v is None, net
        else:
            assert result.guessed_voltage_v == expected_voltage, net
