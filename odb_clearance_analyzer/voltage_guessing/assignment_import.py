"""Phase 3 import of previously exported voltage assignments.

Implements addendum 9.1.1 error handling: an import either fully loads
(possibly with reported skipped rows) or is fully rejected — never
partially applied and never raising for content problems (13.1).
"""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass, field
from pathlib import Path

from .assignment_store import STORE_FILE_KIND, STORE_SCHEMA_VERSION
from .enums import CONFIDENCE_VALUES, NET_CLASSES, REVIEW_STATES, SEVERITY_VALUES
from .exports import EXPORT_FILE_KIND
from .models import VoltageAssignment
from .galvanic_zones import normalize_galvanic_zone


@dataclass
class AssignmentImportResult:
    ok: bool
    assignments: list[VoltageAssignment] = field(default_factory=list)
    schema_version_found: int | None = None
    migrated_from_version: int | None = None
    rejected_reason: str = ""
    skipped_rows: list[tuple[int, str]] = field(default_factory=list)
    source_file: str = ""
    source_revision: str = ""


_REQUIRED_CSV_COLUMNS = {"net_name", "final_class", "review_state"}
_VOLTAGE_CSV_COLUMNS = ("final_voltage_v", "assigned_voltage_v", "guessed_voltage_v", "voltage_v")


def _pick_voltage_csv_column(headers: set[str]) -> str | None:
    for name in _VOLTAGE_CSV_COLUMNS:
        if name in headers:
            return name
    return None


def _parse_voltage_value(value, *, row_label: str) -> tuple[bool, float | None, str]:
    if value is None or value == "":
        return True, None, ""
    if isinstance(value, str) and not value.strip():
        return True, None, ""
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return False, None, f"{row_label}: non-numeric voltage {value!r}"
    if not math.isfinite(parsed):
        return False, None, f"{row_label}: non-finite voltage {value!r}"
    return True, parsed, ""


def _migrate(data: dict, from_version: int) -> dict:
    """Forward-migrate older schema versions. v1 is current: identity."""
    return data


def import_voltage_assignments(path: Path) -> AssignmentImportResult:
    """Import an export snapshot (.json) or interchange CSV (.csv)."""
    path = Path(path)
    result = AssignmentImportResult(ok=False, source_file=path.name)
    if not path.exists():
        result.rejected_reason = f"File not found: {path}"
        return result
    if path.suffix.lower() == ".json":
        return _import_json(path, result)
    if path.suffix.lower() == ".csv":
        return _import_csv(path, result)
    result.rejected_reason = f"Unsupported file type: {path.suffix} (expected .json or .csv)"
    return result


def _import_json(path: Path, result: AssignmentImportResult) -> AssignmentImportResult:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        result.rejected_reason = f"Invalid JSON at line {exc.lineno}: {exc.msg}"
        return result
    except OSError as exc:
        result.rejected_reason = f"Could not read file: {exc}"
        return result
    if not isinstance(data, dict):
        result.rejected_reason = "Invalid file: top level must be a JSON object"
        return result

    kind = data.get("file_kind")
    if kind not in {None, EXPORT_FILE_KIND, STORE_FILE_KIND}:
        result.rejected_reason = f"Unsupported file_kind: {kind!r}"
        return result

    version = int(data.get("schema_version", 0) or 0)
    result.schema_version_found = version
    if version > STORE_SCHEMA_VERSION:
        result.rejected_reason = (
            f"File was created by a newer application version (schema {version} > {STORE_SCHEMA_VERSION})."
        )
        return result
    if version < STORE_SCHEMA_VERSION:
        data = _migrate(data, version)
        result.migrated_from_version = version

    raw_assignments = data.get("assignments")
    if not isinstance(raw_assignments, dict) or not raw_assignments:
        result.rejected_reason = "File contains no assignments"
        return result

    result.source_revision = str(data.get("project_revision", ""))
    row = 0
    for net, raw in sorted(raw_assignments.items()):
        row += 1
        if not isinstance(raw, dict):
            result.skipped_rows.append((row, f"{net}: entry is not an object"))
            continue
        ok_voltage, parsed_voltage, voltage_problem = _parse_voltage_value(raw.get("final_voltage_v"), row_label=str(net))
        if not ok_voltage:
            result.skipped_rows.append((row, voltage_problem))
            continue
        raw = dict(raw)
        raw["final_voltage_v"] = parsed_voltage
        assignment = VoltageAssignment.from_dict({"net_name": net, **raw})
        problem = _validate_assignment(assignment)
        if problem:
            result.skipped_rows.append((row, f"{net}: {problem}"))
            continue
        result.assignments.append(assignment)
    if not result.assignments:
        result.rejected_reason = "All assignment entries were invalid"
        return result
    result.ok = True
    return result


def _import_csv(path: Path, result: AssignmentImportResult) -> AssignmentImportResult:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            headers = set(reader.fieldnames or [])
            missing = _REQUIRED_CSV_COLUMNS - headers
            if missing:
                result.rejected_reason = f"Missing required columns: {', '.join(sorted(missing))}"
                return result
            voltage_column = _pick_voltage_csv_column(headers)
            if voltage_column is None:
                result.rejected_reason = (
                    "Missing required voltage column: one of "
                    + ", ".join(_VOLTAGE_CSV_COLUMNS)
                )
                return result
            seen: set[str] = set()
            duplicates: set[str] = set()
            rows = list(reader)
    except (OSError, csv.Error) as exc:
        result.rejected_reason = f"Could not read CSV: {exc}"
        return result

    for row in rows:
        net = str(row.get("net_name", "")).strip()
        if net in seen:
            duplicates.add(net)
        seen.add(net)
    if duplicates:
        result.rejected_reason = f"Duplicate net names in import file: {', '.join(sorted(duplicates)[:10])}"
        return result

    result.schema_version_found = STORE_SCHEMA_VERSION
    for line_no, row in enumerate(rows, start=2):
        net = str(row.get("net_name", "")).strip()
        if not net:
            result.skipped_rows.append((line_no, "empty net_name"))
            continue
        voltage_raw = str(row.get(voltage_column, "")).strip()
        ok_voltage, voltage, voltage_problem = _parse_voltage_value(voltage_raw, row_label=net)
        if not ok_voltage:
            result.skipped_rows.append((line_no, voltage_problem))
            continue
        assignment = VoltageAssignment.from_dict(
            {
                "net_name": net,
                "final_class": row.get("final_class", "UNKNOWN"),
                "final_voltage_v": voltage,
                "reference_net": row.get("reference_net", ""),
                "voltage_type": row.get("voltage_type", "DC"),
                "confidence": row.get("confidence", "Unknown"),
                "severity": row.get("severity", "Review"),
                "review_state": row.get("review_state", "Needs review"),
                "source": row.get("source", "unknown"),
                "galvanic_zone": normalize_galvanic_zone(row.get("galvanic_zone", "")),
                "reviewed_by": row.get("reviewed_by", ""),
                "reviewed_at_utc": row.get("reviewed_at_utc", ""),
                "review_reason": row.get("review_reason", ""),
                "notes": row.get("notes", ""),
                "source_revision": row.get("source_revision", ""),
                "last_seen_revision": row.get("last_seen_revision", ""),
                "waiver": {
                    "waived": str(row.get("waived", "")).strip().lower() == "true",
                    "waiver_reason": row.get("waiver_reason", ""),
                    "waiver_scope": row.get("waiver_scope", ""),
                },
            }
        )
        problem = _validate_assignment(assignment)
        if problem:
            result.skipped_rows.append((line_no, f"{net}: {problem}"))
            continue
        result.assignments.append(assignment)
        if not result.source_revision and assignment.source_revision:
            result.source_revision = assignment.source_revision
    if not result.assignments:
        result.rejected_reason = "No valid assignment rows found"
        return result
    result.ok = True
    return result


def _validate_assignment(a: VoltageAssignment) -> str:
    if a.final_class not in NET_CLASSES:
        return f"invalid class {a.final_class!r}"
    if a.confidence not in CONFIDENCE_VALUES:
        return f"invalid confidence {a.confidence!r}"
    if a.severity not in SEVERITY_VALUES:
        return f"invalid severity {a.severity!r}"
    if a.review_state not in REVIEW_STATES:
        return f"invalid review_state {a.review_state!r}"
    return ""
