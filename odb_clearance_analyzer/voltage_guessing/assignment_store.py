"""Project assignment store persistence for voltage guessing."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .models import AssignmentStore, ReviewSessionState, UndoEntry, VoltageAssignment

STORE_SCHEMA_VERSION = 1
STORE_FILE_KIND = "net_voltage_assignment_store"
DEFAULT_ASSIGNMENT_STORE_NAME = "net_voltage_assignments.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def assignment_store_path(output_dir: Path) -> Path:
    return Path(output_dir) / DEFAULT_ASSIGNMENT_STORE_NAME


def create_assignment_store(assignments: list[VoltageAssignment], *, project_revision: str = "", settings: dict[str, object] | None = None) -> AssignmentStore:
    now = utc_now()
    return AssignmentStore(
        schema_version=STORE_SCHEMA_VERSION,
        project_revision=project_revision,
        assignments={assignment.net_name: assignment for assignment in assignments},
        review_session=ReviewSessionState(),
        undo_stack=[],
        settings=dict(settings or {}),
        created_utc=now,
        modified_utc=now,
    )


def store_to_dict(store: AssignmentStore) -> dict:
    return {
        "schema_version": store.schema_version,
        "file_kind": STORE_FILE_KIND,
        "project_revision": store.project_revision,
        "created_utc": store.created_utc,
        "modified_utc": store.modified_utc,
        "review_session": asdict(store.review_session),
        "settings": dict(getattr(store, "settings", {}) or {}),
        "assignments": {net: assignment.to_dict() for net, assignment in sorted(store.assignments.items())},
        "undo_stack": [
            {
                "operation": entry.operation,
                "timestamp_utc": entry.timestamp_utc,
                "changed": {net: assignment.to_dict() for net, assignment in entry.changed.items()},
            }
            for entry in store.undo_stack
        ],
    }


def _store_from_dict(data: dict) -> AssignmentStore:
    kind = data.get("file_kind")
    if kind == "net_voltage_assignment_export":
        raise ValueError(
            "This file is an export snapshot, not the project assignment store. "
            "Use Revision Import to load exported assignments."
        )
    if kind not in {None, STORE_FILE_KIND}:
        raise ValueError("Unsupported voltage assignment file_kind")
    if int(data.get("schema_version", 0) or 0) > STORE_SCHEMA_VERSION:
        raise ValueError("Voltage assignment store was created by a newer application version")
    assignments = {
        str(net): VoltageAssignment.from_dict({"net_name": net, **raw})
        for net, raw in dict(data.get("assignments", {})).items()
    }
    session_raw = data.get("review_session") or {}
    undo_stack = []
    for raw_entry in data.get("undo_stack", []) or []:
        changed = {
            str(net): VoltageAssignment.from_dict({"net_name": net, **raw_assignment})
            for net, raw_assignment in dict(raw_entry.get("changed", {})).items()
        }
        undo_stack.append(UndoEntry(str(raw_entry.get("operation", "")), str(raw_entry.get("timestamp_utc", "")), changed))
    return AssignmentStore(
        schema_version=int(data.get("schema_version", STORE_SCHEMA_VERSION)),
        project_revision=str(data.get("project_revision", "")),
        assignments=assignments,
        review_session=ReviewSessionState(
            queue_position=int(session_raw.get("queue_position", 0) or 0),
            active_filter=str(session_raw.get("active_filter", "")),
            sort_key=str(session_raw.get("sort_key", "")),
            skipped_nets=list(session_raw.get("skipped_nets", []) or []),
        ),
        undo_stack=undo_stack,
        settings=dict(data.get("settings", {}) or {}),
        created_utc=str(data.get("created_utc", "")),
        modified_utc=str(data.get("modified_utc", "")),
    )


def load_assignment_store(path: Path) -> AssignmentStore:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Invalid assignment store: top level must be a JSON object")
    return _store_from_dict(data)


def save_assignment_store_atomic(store: AssignmentStore, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    store.modified_utc = utc_now()
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(store_to_dict(store), f, indent=2, sort_keys=True)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
