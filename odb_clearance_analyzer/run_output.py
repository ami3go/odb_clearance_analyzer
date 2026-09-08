"""Helpers for timestamped per-run report output directories."""

from __future__ import annotations

from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Any


RUN_FOLDER_PREFIX = "run"
RUN_TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S"
_DEFAULT_ASSIGNMENT_STORE = "net_voltage_assignments.json"


def create_timestamped_report_dir(report_root: Path, *, now: datetime | None = None) -> Path:
    """Create a unique ``run_YYYYMMDD_HHMMSS`` folder below ``report_root``."""

    root = Path(report_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    stamp = (now or datetime.now()).strftime(RUN_TIMESTAMP_FORMAT)
    base_name = f"{RUN_FOLDER_PREFIX}_{stamp}"
    candidate = root / base_name
    index = 1
    while candidate.exists():
        candidate = root / f"{base_name}_{index:03d}"
        index += 1
    candidate.mkdir(parents=True, exist_ok=False)
    return candidate


def prepare_timestamped_analysis_output(config: Any) -> Path:
    """Treat ``config.output_dir`` as common root and move this run into a timestamp folder.

    Relative voltage assignment-store paths are resolved against the common root,
    not against the per-run folder.  This keeps reviewed net-voltage work reusable
    while CSV/XLSX/Markdown/ZIP reports are isolated per analysis run.
    """

    report_root = Path(config.output_dir).expanduser().resolve()
    voltage_settings = dict(getattr(config, "voltage_guessing", {}) or {})
    voltage_settings["report_root_dir"] = str(report_root)
    raw_store = str(voltage_settings.get("assignment_store_path", _DEFAULT_ASSIGNMENT_STORE) or _DEFAULT_ASSIGNMENT_STORE)
    store_path = Path(raw_store)
    if not store_path.is_absolute():
        voltage_settings["assignment_store_path"] = str(report_root / store_path)
    config.voltage_guessing = voltage_settings
    config.output_dir = create_timestamped_report_dir(report_root)
    return config.output_dir


def enable_timestamped_report_runs(clearance_analyzer_cls: type) -> None:
    """Patch ``ClearanceAnalyzer.run`` once so every GUI/CLI run uses a fresh report folder."""

    original_run = getattr(clearance_analyzer_cls, "run")
    if getattr(original_run, "_timestamped_report_runs", False):
        return

    @wraps(original_run)
    def run_with_timestamped_reports(self: Any, config: Any, *args: Any, **kwargs: Any):
        run_dir = prepare_timestamped_analysis_output(config)
        progress = getattr(self, "progress", None)
        if callable(progress):
            progress(f"Report output folder: {run_dir}")
        return original_run(self, config, *args, **kwargs)

    setattr(run_with_timestamped_reports, "_timestamped_report_runs", True)
    setattr(run_with_timestamped_reports, "_original_run", original_run)
    setattr(clearance_analyzer_cls, "run", run_with_timestamped_reports)
