"""CSV and JSON exporters for voltage guessing."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import os

from .assignment_store import STORE_SCHEMA_VERSION, utc_now
from .models import VoltageAssignment
from .normalization import normalize_net_name_safe

GUESSING_CSV = "net_voltage_guessing.csv"
ASSIGNMENTS_CSV = "net_voltage_assignments.csv"
EXPORT_FILE_KIND = "net_voltage_assignment_export"


def export_json_name(project_revision: str = "") -> str:
    suffix = "".join(c if c.isalnum() or c in "-_" else "_" for c in project_revision).strip("_")
    return f"net_voltage_assignments_{suffix or 'export'}.json"


def _fmt_voltage(value: float | None) -> str:
    return "" if value is None else f"{value:g}"


def export_voltage_guessing_csv(assignments: list[VoltageAssignment], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "net_name",
        "normalized_name",
        "guessed_class",
        "guessed_voltage_v",
        "reference_net",
        "voltage_type",
        "confidence",
        "severity",
        "winning_rule_id",
        "all_matched_rule_ids",
        "reason",
        "warning",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for a in sorted(assignments, key=lambda item: item.net_name):
            writer.writerow(
                {
                    "net_name": a.net_name,
                    "normalized_name": normalize_net_name_safe(a.net_name),
                    "guessed_class": a.final_class,
                    "guessed_voltage_v": _fmt_voltage(a.final_voltage_v),
                    "reference_net": a.reference_net,
                    "voltage_type": a.voltage_type,
                    "confidence": a.confidence,
                    "severity": a.severity,
                    "winning_rule_id": a.evidence.matched_rule_id,
                    "all_matched_rule_ids": ";".join(a.evidence.all_matched_rule_ids),
                    "reason": a.evidence.rule_reason or a.review_reason,
                    "warning": a.evidence.rule_warning,
                }
            )
    return path


def export_voltage_assignments_csv(assignments: list[VoltageAssignment], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "net_name",
        "final_class",
        "final_voltage_v",
        "reference_net",
        "voltage_type",
        "confidence",
        "severity",
        "review_state",
        "source",
        "galvanic_zone",
        "reviewed_by",
        "reviewed_at_utc",
        "review_reason",
        "waived",
        "waiver_reason",
        "waiver_scope",
        "notes",
        "source_revision",
        "last_seen_revision",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for a in sorted(assignments, key=lambda item: item.net_name):
            writer.writerow(
                {
                    "net_name": a.net_name,
                    "final_class": a.final_class,
                    "final_voltage_v": _fmt_voltage(a.final_voltage_v),
                    "reference_net": a.reference_net,
                    "voltage_type": a.voltage_type,
                    "confidence": a.confidence,
                    "severity": a.severity,
                    "review_state": a.review_state,
                    "source": a.source,
                    "galvanic_zone": getattr(a, "galvanic_zone", ""),
                    "reviewed_by": a.reviewed_by,
                    "reviewed_at_utc": a.reviewed_at_utc,
                    "review_reason": a.review_reason,
                    "waived": "true" if a.waiver.waived else "false",
                    "waiver_reason": a.waiver.waiver_reason,
                    "waiver_scope": a.waiver.waiver_scope,
                    "notes": a.notes,
                    "source_revision": a.source_revision,
                    "last_seen_revision": a.last_seen_revision,
                }
            )
    return path


def export_voltage_assignments_json(assignments: list[VoltageAssignment], path: Path, *, project_revision: str = "", voltage_guessing_settings: dict[str, object] | None = None) -> Path:
    """Write an export SNAPSHOT (assignments only) — not the project store.

    Per addendum 12.1.1 the snapshot excludes review_session and undo_stack
    and carries its own file_kind, so the importer can distinguish it.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": STORE_SCHEMA_VERSION,
        "file_kind": EXPORT_FILE_KIND,
        "project_revision": project_revision,
        "exported_at_utc": utc_now(),
        "voltage_guessing_settings": dict(voltage_guessing_settings or {}),
        "assignments": {a.net_name: a.to_dict() for a in sorted(assignments, key=lambda i: i.net_name)},
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    return path


def export_all_voltage_files(assignments: list[VoltageAssignment], output_dir: Path, *, project_revision: str = "", voltage_guessing_settings: dict[str, object] | None = None) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    return {
        "voltage_guessing_csv": export_voltage_guessing_csv(assignments, output_dir / GUESSING_CSV),
        "voltage_assignments_json": export_voltage_assignments_json(
            assignments, output_dir / export_json_name(project_revision), project_revision=project_revision, voltage_guessing_settings=voltage_guessing_settings
        ),
        "voltage_assignments_csv": export_voltage_assignments_csv(assignments, output_dir / ASSIGNMENTS_CSV),
    }
