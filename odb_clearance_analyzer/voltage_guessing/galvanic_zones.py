"""Galvanic-zone helpers for voltage assignment review and spacing reports.

The first implementation intentionally supports only two user-visible zones.
A net assigned to Zone 1 and a net assigned to Zone 2 must be checked against
one configurable inter-zone voltage.  Unassigned nets are ignored by the zone
report so existing projects remain backward compatible.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Iterable

from ..models import AnalysisResult, MeasurementRecord
from .models import AssignmentStore, VoltageAssignment

GALVANIC_ZONE_NONE = ""
GALVANIC_ZONE_1 = "Zone 1"
GALVANIC_ZONE_2 = "Zone 2"
GALVANIC_ZONE_CHOICES = (GALVANIC_ZONE_NONE, GALVANIC_ZONE_1, GALVANIC_ZONE_2)
DEFAULT_GALVANIC_ZONE_VOLTAGE_V = 1000.0
GALVANIC_ZONE_REPORT_CSV = "galvanic_zone_spacing.csv"


def normalize_galvanic_zone(value: object) -> str:
    """Return a supported galvanic-zone label or ``""`` for unassigned.

    The parser accepts a few common spellings to make imported JSON/CSV robust:
    ``1``, ``zone1`` and ``zone_1`` all become ``Zone 1``.
    """

    text = str(value or "").strip()
    if not text:
        return GALVANIC_ZONE_NONE
    compact = text.lower().replace(" ", "").replace("_", "").replace("-", "")
    if compact in {"1", "zone1", "z1", "galvaniczone1"}:
        return GALVANIC_ZONE_1
    if compact in {"2", "zone2", "z2", "galvaniczone2"}:
        return GALVANIC_ZONE_2
    if text in {GALVANIC_ZONE_1, GALVANIC_ZONE_2}:
        return text
    return GALVANIC_ZONE_NONE


def validate_inter_zone_voltage(value: object, *, default: float = DEFAULT_GALVANIC_ZONE_VOLTAGE_V) -> float:
    """Return a positive finite inter-zone voltage, falling back to default."""

    try:
        parsed = float(value)
    except Exception:
        return default
    if not math.isfinite(parsed) or parsed <= 0:
        return default
    return parsed


def zone_for_net(assignments: dict[str, VoltageAssignment], net_name: str) -> str:
    assignment = assignments.get(net_name)
    if assignment is None:
        return GALVANIC_ZONE_NONE
    return normalize_galvanic_zone(getattr(assignment, "galvanic_zone", ""))


def is_inter_zone_pair(assignments: dict[str, VoltageAssignment], net_a: str, net_b: str) -> bool:
    zone_a = zone_for_net(assignments, net_a)
    zone_b = zone_for_net(assignments, net_b)
    return {zone_a, zone_b} == {GALVANIC_ZONE_1, GALVANIC_ZONE_2}


def iter_inter_zone_measurements(
    measurements: Iterable[MeasurementRecord],
    assignments: dict[str, VoltageAssignment],
) -> Iterable[tuple[MeasurementRecord, str, str]]:
    """Yield measurements whose two nets belong to different galvanic zones."""

    for rec in measurements:
        zone_a = zone_for_net(assignments, rec.net_a)
        zone_b = zone_for_net(assignments, rec.net_b)
        if {zone_a, zone_b} == {GALVANIC_ZONE_1, GALVANIC_ZONE_2}:
            yield rec, zone_a, zone_b


def export_galvanic_zone_spacing_csv(
    result: AnalysisResult,
    store: AssignmentStore,
    path: Path,
    *,
    inter_zone_voltage_v: float = DEFAULT_GALVANIC_ZONE_VOLTAGE_V,
) -> tuple[Path, int, int]:
    """Export Zone 1 ↔ Zone 2 spacing checks.

    Returns ``(path, row_count, fail_count)``.  A row fails when the measured
    spacing's existing IEC-style ``effective_max_voltage_v`` is lower than the
    configured inter-zone voltage or is unavailable.
    """

    required = validate_inter_zone_voltage(inter_zone_voltage_v)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Import lazily to avoid a module import cycle: requirements.py imports the
    # zone normalizers defined above.
    from .requirements import REQUIREMENT_SOURCE_GALVANIC_ZONE, VoltageRequirementResolver, resolve_voltage_standard_compliance

    rows = []
    fail_count = 0
    settings = dict(getattr(store, "settings", {}) or {})
    settings["galvanic_zone_voltage_v"] = required
    resolver = VoltageRequirementResolver(store.assignments, settings)
    for rec in result.measurements:
        req = resolver.resolve(rec.net_a, rec.net_b)
        if req.requirement_source != REQUIREMENT_SOURCE_GALVANIC_ZONE:
            continue
        supported = rec.effective_max_voltage_v
        ok_nok, margin_value = resolve_voltage_standard_compliance(req.required_voltage_v or required, supported)
        margin = "" if margin_value is None else f"{margin_value:g}"
        status = "PASS" if ok_nok == "OK" else ("FAIL" if ok_nok == "NOK" else "UNKNOWN")
        if ok_nok != "OK":
            fail_count += 1
        rows.append(
            {
                "layer": rec.layer,
                "net_a": rec.net_a,
                "zone_a": req.zone_a,
                "net_b": rec.net_b,
                "zone_b": req.zone_b,
                "clearance_mm": f"{float(rec.clearance_mm):.6f}",
                "required_inter_zone_voltage_v": f"{float(req.required_voltage_v or required):g}",
                "required_voltage_v": f"{float(req.required_voltage_v or required):g}",
                "voltage_source": req.requirement_source,
                "zone_voltage_v": "" if req.zone_voltage_v is None else f"{float(req.zone_voltage_v):g}",
                "local_voltage_v": "" if req.local_voltage_v is None else f"{float(req.local_voltage_v):g}",
                "voltage_difference_v": "" if req.voltage_difference_v is None else f"{float(req.voltage_difference_v):g}",
                "net_a_voltage_v": "" if req.net_a_voltage_v is None else f"{float(req.net_a_voltage_v):g}",
                "net_b_voltage_v": "" if req.net_b_voltage_v is None else f"{float(req.net_b_voltage_v):g}",
                "warning": req.warning,
                "supported_effective_max_voltage_v": "" if supported is None else f"{float(supported):g}",
                "margin_v": margin,
                "ok_nok": ok_nok,
                "status": status,
                "x_a_mm": "" if rec.x_a_mm is None else f"{float(rec.x_a_mm):.6f}",
                "y_a_mm": "" if rec.y_a_mm is None else f"{float(rec.y_a_mm):.6f}",
                "x_b_mm": "" if rec.x_b_mm is None else f"{float(rec.x_b_mm):.6f}",
                "y_b_mm": "" if rec.y_b_mm is None else f"{float(rec.y_b_mm):.6f}",
            }
        )

    fieldnames = [
        "layer",
        "net_a",
        "zone_a",
        "net_b",
        "zone_b",
        "clearance_mm",
        "required_inter_zone_voltage_v",
        "required_voltage_v",
        "voltage_source",
        "zone_voltage_v",
        "local_voltage_v",
        "voltage_difference_v",
        "net_a_voltage_v",
        "net_b_voltage_v",
        "warning",
        "supported_effective_max_voltage_v",
        "margin_v",
        "ok_nok",
        "status",
        "x_a_mm",
        "y_a_mm",
        "x_b_mm",
        "y_b_mm",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path, len(rows), fail_count
