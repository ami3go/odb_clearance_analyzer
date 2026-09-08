"""Rule-pack loading for deterministic voltage guessing."""

from __future__ import annotations

import csv
import json
import math
from importlib import resources
from pathlib import Path
from typing import Iterable

from .models import RulePack, VoltageDefaults, VoltageRule

PACKAGE_RULE_DIR = "data/net_voltage_rules"


def builtin_rule_pack_path() -> Path:
    ref = resources.files("odb_clearance_analyzer").joinpath(PACKAGE_RULE_DIR)
    with resources.as_file(ref) as path:
        return Path(path)


def _bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"0", "false", "no", "off", ""}


def _optional_float_strict(value, field_name: str, issues: list[str]) -> float | None:
    """Parse optional numeric fields without silently hiding bad data."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = float(text)
    except Exception:
        issues.append(f"Invalid numeric value for {field_name}: {text!r}")
        return None
    if not math.isfinite(parsed):
        issues.append(f"Invalid numeric value for {field_name}: {text!r}")
        return None
    return parsed


def _int_strict(value, field_name: str, issues: list[str], default: int = 0) -> int:
    text = str(value if value is not None else "").strip()
    if not text:
        return default
    try:
        return int(text)
    except Exception:
        issues.append(f"Invalid integer value for {field_name}: {text!r}")
        return default


def _tags(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [token.strip() for token in str(value).split(";") if token.strip()]


def _rule_from_mapping(raw: dict, *, source_file: Path, source_layer: str) -> VoltageRule:
    issues: list[str] = []
    return VoltageRule(
        rule_id=str(raw.get("rule_id", "")).strip(),
        priority=_int_strict(raw.get("priority", 0), "priority", issues),
        enabled=_bool(raw.get("enabled", True)),
        pattern=str(raw.get("pattern", "")).strip(),
        match_type=str(raw.get("match_type", "exact")).strip(),
        match_on=str(raw.get("match_on", "normalized")).strip() or "normalized",
        net_class=str(raw.get("net_class", "UNKNOWN")).strip(),
        voltage_v=_optional_float_strict(raw.get("voltage_v"), "voltage_v", issues),
        cell_count_from_pattern=_bool(raw.get("cell_count_from_pattern", False)),
        volts_per_cell=_optional_float_strict(raw.get("volts_per_cell"), "volts_per_cell", issues),
        reference_net=str(raw.get("reference_net", "")).strip(),
        voltage_type=str(raw.get("voltage_type", "DC")).strip() or "DC",
        confidence=str(raw.get("confidence", "Medium")).strip() or "Medium",
        severity=str(raw.get("severity", "Review")).strip() or "Review",
        reason=str(raw.get("reason", "")).strip(),
        warning=str(raw.get("warning", "")).strip(),
        tags=_tags(raw.get("tags")),
        source_layer=source_layer,
        source_file=source_file.name,
        parse_issues=issues,
    )


def _load_defaults(path: Path) -> VoltageDefaults:
    defaults_path = path / "defaults.json"
    if not defaults_path.exists():
        return VoltageDefaults()
    data = json.loads(defaults_path.read_text(encoding="utf-8-sig"))
    return VoltageDefaults(
        mains_rms_v=float(data.get("mains_rms_v", 230.0)),
        mains_peak_v=float(data.get("mains_peak_v", 325.0)),
        battery_volts_per_cell_max=float(data.get("battery_volts_per_cell_max", 4.3)),
        logic_io_v=float(data.get("logic_io_v", 3.3)),
        analog_io_v=float(data.get("analog_io_v", 3.3)),
        usb_vbus_v=float(data.get("usb_vbus_v", 5.0)),
        usb_pd_max_v=float(data.get("usb_pd_max_v", 20.0)),
        poe_voltage_v=float(data.get("poe_voltage_v", 57.0)),
        unknown_severity=str(data.get("unknown_severity", "Review")),
    )


def _load_rule_file(path: Path, *, source_layer: str) -> list[VoltageRule]:
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            return [_rule_from_mapping(row, source_file=path, source_layer=source_layer) for row in csv.DictReader(f)]
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        items: Iterable[dict]
        if isinstance(data, dict) and "rules" in data:
            items = data["rules"]
        elif isinstance(data, list):
            items = data
        else:
            items = []
        return [_rule_from_mapping(item, source_file=path, source_layer=source_layer) for item in items]
    return []


def load_rule_pack(path: Path | None = None, *, source_layer: str = "built-in") -> RulePack:
    """Load a rule pack folder. If *path* is None, load the built-in pack."""

    pack_path = Path(path) if path is not None else builtin_rule_pack_path()
    manifest_path = pack_path / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        file_names = list(manifest.get("files", []))
    else:
        manifest = {"schema_version": 1, "pack_name": pack_path.name, "pack_version": "0"}
        file_names = [p.name for p in sorted(pack_path.glob("*.csv"))] + [p.name for p in sorted(pack_path.glob("*.json")) if p.name not in {"manifest.json", "defaults.json"}]
    rules: list[VoltageRule] = []
    source_files: list[Path] = []
    missing_files: list[str] = []
    for file_name in file_names:
        rule_path = pack_path / str(file_name)
        if not rule_path.exists():
            missing_files.append(str(file_name))
            continue
        source_files.append(rule_path)
        rules.extend(_load_rule_file(rule_path, source_layer=source_layer))
    reserved = {"manifest.json", "defaults.json", str(manifest.get("test_file", ""))}
    on_disk = {p.name for p in pack_path.glob("*.csv")} | {p.name for p in pack_path.glob("*.json")}
    unlisted_files = sorted(on_disk - set(map(str, file_names)) - reserved)
    tests_name = str(manifest.get("test_file", "")) or "net_voltage_rule_tests.csv"
    tests_path = pack_path / tests_name
    return RulePack(
        manifest=manifest,
        rules=rules,
        defaults=_load_defaults(pack_path),
        source_files=source_files,
        layer_counts={source_layer: len(rules)},
        missing_files=missing_files,
        unlisted_files=unlisted_files,
        tests_path=tests_path if tests_path.exists() else None,
    )


def load_layered_rule_pack(project_rule_dir: Path | None = None) -> RulePack:
    """Load the built-in pack plus optional project-local correction rules.

    Project-local rules (Rev C Section 13 layering) load with
    source_layer="project-local" so they win over built-in rules per the
    13.0 precedence ordering. The project directory needs no manifest:
    every *.csv / *.json rule file in it loads in sorted filename order.
    """
    pack = load_rule_pack()
    if project_rule_dir is None:
        return pack
    project_rule_dir = Path(project_rule_dir)
    if not project_rule_dir.is_dir():
        return pack
    project_rules: list[VoltageRule] = []
    project_files: list[Path] = []
    for rule_path in sorted(project_rule_dir.glob("*.csv")) + sorted(project_rule_dir.glob("*.json")):
        if rule_path.name in {"manifest.json", "defaults.json"}:
            continue
        project_files.append(rule_path)
        project_rules.extend(_load_rule_file(rule_path, source_layer="project-local"))
    if not project_rules:
        return pack
    layer_counts = dict(pack.layer_counts)
    layer_counts["project-local"] = len(project_rules)
    return RulePack(
        manifest=pack.manifest,
        rules=list(pack.rules) + project_rules,
        defaults=pack.defaults,
        source_files=list(pack.source_files) + project_files,
        layer_counts=layer_counts,
        missing_files=list(pack.missing_files),
        unlisted_files=list(pack.unlisted_files),
        tests_path=pack.tests_path,
    )
