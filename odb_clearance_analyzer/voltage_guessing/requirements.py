"""Voltage-requirement hierarchy resolver for clearance screening.

This module is intentionally deterministic.  It does not guess isolation from
geometry or components; it only combines reviewed voltage assignments with the
optional two-zone galvanic-barrier setting.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping

from .galvanic_zones import (
    DEFAULT_GALVANIC_ZONE_VOLTAGE_V,
    GALVANIC_ZONE_1,
    GALVANIC_ZONE_2,
    normalize_galvanic_zone,
    validate_inter_zone_voltage,
)
from .models import AssignmentStore, VoltageAssignment

REQUIREMENT_SOURCE_GALVANIC_ZONE = "galvanic_zone"
REQUIREMENT_SOURCE_MANUAL_OVERRIDE = "manual_override"
REQUIREMENT_SOURCE_NET_CLASS = "net_class"
REQUIREMENT_SOURCE_RULE_GUESS = "rule_guess"
REQUIREMENT_SOURCE_UNKNOWN = "unknown"

STANDARD_STATUS_OK = "OK"
STANDARD_STATUS_NOK = "NOK"
STANDARD_STATUS_UNKNOWN = "UNKNOWN"

_ZONE_VALUES = {GALVANIC_ZONE_1, GALVANIC_ZONE_2}
_INCOMPLETE_ZONE_WARNING = "Zone assignment incomplete; result uses local net voltage only."
_UNKNOWN_LOCAL_WARNING = "Local net voltage is unknown; review required before pass/fail use."


@dataclass(frozen=True)
class VoltageRequirementResult:
    """Resolved voltage requirement for one net-to-net spacing row."""

    net_a: str
    net_b: str
    required_voltage_v: float | None
    requirement_source: str
    zone_a: str
    zone_b: str
    zone_voltage_v: float | None
    net_a_voltage_v: float | None
    net_b_voltage_v: float | None
    local_voltage_v: float | None
    voltage_difference_v: float | None
    warning: str = ""

    def as_row(self) -> dict[str, object]:
        return {
            "required_voltage_v": "" if self.required_voltage_v is None else self.required_voltage_v,
            "voltage_source": self.requirement_source,
            "zone_a": self.zone_a,
            "zone_b": self.zone_b,
            "zone_voltage_v": "" if self.zone_voltage_v is None else self.zone_voltage_v,
            "local_voltage_v": "" if self.local_voltage_v is None else self.local_voltage_v,
            "voltage_difference_v": "" if self.voltage_difference_v is None else self.voltage_difference_v,
            "net_a_voltage_v": "" if self.net_a_voltage_v is None else self.net_a_voltage_v,
            "net_b_voltage_v": "" if self.net_b_voltage_v is None else self.net_b_voltage_v,
            "warning": self.warning,
        }


def voltage_requirement_csv_fields() -> list[str]:
    """Stable CSV field order for voltage hierarchy metadata."""

    return [
        "required_voltage_v",
        "voltage_source",
        "zone_a",
        "zone_b",
        "zone_voltage_v",
        "local_voltage_v",
        "voltage_difference_v",
        "net_a_voltage_v",
        "net_b_voltage_v",
        "warning",
    ]


def voltage_requirement_excel_headers() -> list[str]:
    return [
        "Required voltage V",
        "Voltage source",
        "Zone A",
        "Zone B",
        "Zone voltage V",
        "Local voltage V",
        "Voltage difference V",
        "Net A voltage V",
        "Net B voltage V",
        "Voltage warning",
    ]


def voltage_requirement_excel_values(result: VoltageRequirementResult) -> list[object]:
    return [
        result.required_voltage_v,
        result.requirement_source,
        result.zone_a,
        result.zone_b,
        result.zone_voltage_v,
        result.local_voltage_v,
        result.voltage_difference_v,
        result.net_a_voltage_v,
        result.net_b_voltage_v,
        result.warning,
    ]


def _finite_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except Exception:
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _assignment_source(assignments: list[VoltageAssignment]) -> str:
    sources = {str(getattr(a, "source", "") or "") for a in assignments}
    if "manual" in sources:
        return REQUIREMENT_SOURCE_MANUAL_OVERRIDE
    if "rule" in sources:
        return REQUIREMENT_SOURCE_RULE_GUESS
    if any(s and s != "unknown" for s in sources):
        return REQUIREMENT_SOURCE_NET_CLASS
    if assignments:
        return REQUIREMENT_SOURCE_NET_CLASS
    return REQUIREMENT_SOURCE_UNKNOWN


_GROUND_NET_NAMES = {"0", "0V", "GND", "GROUND", "AGND", "DGND", "PGND", "SGND"}


def _is_ground_like_net(net_name: str) -> bool:
    """Return True for common explicit ground/0 V net names.

    This is only a fallback for pair-difference reporting when a project has not
    yet stored a voltage-assignment row for the ground net.  Reviewed/loaded
    assignments still take priority.
    """

    normalized = str(net_name or "").strip().upper().replace("-", "_")
    return normalized in _GROUND_NET_NAMES


def _assigned_or_ground_voltage(net_name: str, assignment: VoltageAssignment | None) -> float | None:
    assigned = _finite_float(getattr(assignment, "final_voltage_v", None) if assignment else None)
    if assigned is not None:
        return assigned
    if _is_ground_like_net(net_name):
        return 0.0
    return None


def resolve_existing_local_net_voltage(
    net_a: str,
    net_b: str,
    assignments: Mapping[str, VoltageAssignment],
) -> VoltageRequirementResult:
    """Resolve local net/manual/class voltage without galvanic-zone priority.

    For an actual net pair, the local electrical stress is the voltage
    difference between the two assigned net potentials: ``abs(Va - Vb)``.
    Examples: 10 V to 21 V is 11 V; 10 V to 0 V/GND is 10 V.  When either net
    voltage is unknown, the pair voltage is unknown and must be reviewed.
    """

    a = assignments.get(net_a)
    b = assignments.get(net_b)
    va = _assigned_or_ground_voltage(net_a, a)
    vb = _assigned_or_ground_voltage(net_b, b)
    voltage_difference = abs(va - vb) if va is not None and vb is not None else None
    local_voltage = voltage_difference
    present_assignments = [x for x in (a, b) if x is not None]
    source = _assignment_source(present_assignments) if local_voltage is not None else REQUIREMENT_SOURCE_UNKNOWN
    if local_voltage is not None and source == REQUIREMENT_SOURCE_UNKNOWN and (_is_ground_like_net(net_a) or _is_ground_like_net(net_b)):
        source = REQUIREMENT_SOURCE_RULE_GUESS
    return VoltageRequirementResult(
        net_a=net_a,
        net_b=net_b,
        required_voltage_v=local_voltage,
        requirement_source=source,
        zone_a=normalize_galvanic_zone(getattr(a, "galvanic_zone", "") if a else ""),
        zone_b=normalize_galvanic_zone(getattr(b, "galvanic_zone", "") if b else ""),
        zone_voltage_v=None,
        net_a_voltage_v=va,
        net_b_voltage_v=vb,
        local_voltage_v=local_voltage,
        voltage_difference_v=voltage_difference,
        warning="" if local_voltage is not None else _UNKNOWN_LOCAL_WARNING,
    )


def _settings_dict(settings: AssignmentStore | Mapping[str, object] | None) -> dict[str, object]:
    if settings is None:
        return {}
    if isinstance(settings, AssignmentStore):
        return dict(settings.settings or {})
    return dict(settings or {})


def _assignments_dict(assignments: AssignmentStore | Mapping[str, VoltageAssignment]) -> Mapping[str, VoltageAssignment]:
    if isinstance(assignments, AssignmentStore):
        return assignments.assignments
    return assignments


def _zones_enabled(assignments: Mapping[str, VoltageAssignment], settings: Mapping[str, object]) -> bool:
    if "galvanic_zones_enabled" in settings:
        return bool(settings.get("galvanic_zones_enabled"))
    return any(normalize_galvanic_zone(getattr(a, "galvanic_zone", "")) in _ZONE_VALUES for a in assignments.values())


_PAIR_CACHE_LIMIT = 200_000


class VoltageRequirementResolver:
    """Resolve required spacing voltages for many net pairs efficiently.

    ``resolve_required_spacing_voltage`` recomputed the settings snapshot and
    rescanned every assignment (to detect whether galvanic zones are in use)
    for each pair, which made report export O(rows × nets) — minutes of pure
    resolver time at the project's 20k-net performance target.  This class
    precomputes the zone-enabled flag and inter-zone voltage once and memoizes
    per-pair results, so resolving each row is O(1).

    Build one resolver per assignments+settings snapshot and reuse it for all
    rows of that snapshot.  Do not mutate assignments or settings while a
    resolver built from them is in use.
    """

    def __init__(
        self,
        assignments: AssignmentStore | Mapping[str, VoltageAssignment],
        settings: AssignmentStore | Mapping[str, object] | None = None,
    ) -> None:
        self._assignments = _assignments_dict(assignments)
        self._settings = _settings_dict(
            settings if settings is not None else assignments if isinstance(assignments, AssignmentStore) else None
        )
        self._zones_enabled = _zones_enabled(self._assignments, self._settings)
        self._zone_voltage = validate_inter_zone_voltage(
            self._settings.get("galvanic_zone_voltage_v", self._settings.get("zone_to_zone_voltage_v", DEFAULT_GALVANIC_ZONE_VOLTAGE_V))
        )
        self._pair_cache: dict[tuple[str, str], VoltageRequirementResult] = {}

    @property
    def zone_voltage_v(self) -> float:
        """Validated Zone 1 ↔ Zone 2 voltage for this snapshot."""

        return self._zone_voltage

    def resolve(self, net_a: str, net_b: str) -> VoltageRequirementResult:
        key = (net_a, net_b)
        cached = self._pair_cache.get(key)
        if cached is not None:
            return cached
        result = self._resolve_uncached(net_a, net_b)
        if len(self._pair_cache) < _PAIR_CACHE_LIMIT:
            self._pair_cache[key] = result
        return result

    def _resolve_uncached(self, net_a: str, net_b: str) -> VoltageRequirementResult:
        local = resolve_existing_local_net_voltage(net_a, net_b, self._assignments)
        zone_a = local.zone_a
        zone_b = local.zone_b
        enabled = self._zones_enabled
        if enabled and zone_a in _ZONE_VALUES and zone_b in _ZONE_VALUES and zone_a != zone_b:
            zone_voltage = self._zone_voltage
            return VoltageRequirementResult(
                net_a=net_a,
                net_b=net_b,
                required_voltage_v=zone_voltage,
                requirement_source=REQUIREMENT_SOURCE_GALVANIC_ZONE,
                zone_a=zone_a,
                zone_b=zone_b,
                zone_voltage_v=zone_voltage,
                net_a_voltage_v=local.net_a_voltage_v,
                net_b_voltage_v=local.net_b_voltage_v,
                local_voltage_v=local.local_voltage_v,
                voltage_difference_v=local.voltage_difference_v,
                warning="",
            )

        warning = local.warning
        if enabled and (zone_a not in _ZONE_VALUES or zone_b not in _ZONE_VALUES):
            warning = _INCOMPLETE_ZONE_WARNING if not warning else f"{_INCOMPLETE_ZONE_WARNING} {warning}"
        return VoltageRequirementResult(
            net_a=net_a,
            net_b=net_b,
            required_voltage_v=local.required_voltage_v,
            requirement_source=local.requirement_source,
            zone_a=zone_a,
            zone_b=zone_b,
            zone_voltage_v=None,
            net_a_voltage_v=local.net_a_voltage_v,
            net_b_voltage_v=local.net_b_voltage_v,
            local_voltage_v=local.local_voltage_v,
            voltage_difference_v=local.voltage_difference_v,
            warning=warning,
        )


def resolve_required_spacing_voltage(
    net_a: str,
    net_b: str,
    assignments: AssignmentStore | Mapping[str, VoltageAssignment],
    settings: AssignmentStore | Mapping[str, object] | None = None,
) -> VoltageRequirementResult:
    """Resolve the final required voltage using hierarchy-first priority.

    Priority:
    1. Different valid galvanic zones: use Zone 1 ↔ Zone 2 voltage.
    2. Same zone or incomplete zone assignment: use local net/class/manual voltage.
    3. Unknown local voltage: return ``None`` and a review warning.

    This one-shot helper builds a fresh :class:`VoltageRequirementResolver`
    per call.  When resolving many pairs against the same assignments and
    settings, construct one resolver and call :meth:`~VoltageRequirementResolver.resolve`
    per pair instead.
    """

    return VoltageRequirementResolver(assignments, settings).resolve(net_a, net_b)



def resolve_voltage_standard_compliance(
    required_voltage_v: object,
    supported_max_voltage_v: object,
) -> tuple[str, float | None]:
    """Compare actual/required voltage against the standard-derived maximum.

    ``supported_max_voltage_v`` is the maximum working voltage estimated from
    the measured spacing and the active standard settings (currently the
    IEC-style ``effective_max_voltage_v`` used throughout the reports).

    Returns ``("OK", margin)`` when the required/actual voltage is lower than
    or equal to the supported maximum, ``("NOK", margin)`` when it is higher,
    and ``("UNKNOWN", None)`` when either value is unavailable.
    """

    required = _finite_float(required_voltage_v)
    supported = _finite_float(supported_max_voltage_v)
    if required is None or supported is None:
        return STANDARD_STATUS_UNKNOWN, None
    margin = supported - required
    return (STANDARD_STATUS_OK if margin >= 0 else STANDARD_STATUS_NOK), margin


def voltage_standard_compliance_row(
    required_voltage_v: object,
    supported_max_voltage_v: object,
) -> dict[str, object]:
    """Return stable CSV/report fields for the OK/NOK voltage check."""

    status, margin = resolve_voltage_standard_compliance(required_voltage_v, supported_max_voltage_v)
    return {
        "standard_voltage_status": status,
        "voltage_margin_v": "" if margin is None else margin,
    }


def voltage_standard_compliance_csv_fields() -> list[str]:
    return ["standard_voltage_status", "voltage_margin_v"]


def voltage_standard_compliance_excel_headers() -> list[str]:
    return ["OK/NOK", "Voltage margin V"]


def voltage_standard_compliance_excel_values(
    required_voltage_v: object,
    supported_max_voltage_v: object,
) -> list[object]:
    status, margin = resolve_voltage_standard_compliance(required_voltage_v, supported_max_voltage_v)
    return [status, margin]

def summarize_voltage_requirements_for_measurements(
    measurements,
    assignments: AssignmentStore | Mapping[str, VoltageAssignment],
    settings: AssignmentStore | Mapping[str, object] | None = None,
) -> dict[str, int | float | None]:
    """Return a compact summary for GUI/report status panels."""

    resolver = VoltageRequirementResolver(assignments, settings)
    assignment_map = resolver._assignments
    zone_voltage = resolver.zone_voltage_v
    summary: dict[str, int | float | None] = {
        "zone_1_nets": sum(1 for a in assignment_map.values() if normalize_galvanic_zone(getattr(a, "galvanic_zone", "")) == GALVANIC_ZONE_1),
        "zone_2_nets": sum(1 for a in assignment_map.values() if normalize_galvanic_zone(getattr(a, "galvanic_zone", "")) == GALVANIC_ZONE_2),
        "zone_voltage_v": zone_voltage,
        "cross_zone_pairs": 0,
        "cross_zone_pass": 0,
        "cross_zone_fail": 0,
        "cross_zone_unknown": 0,
        "local_voltage_pairs": 0,
        "incomplete_zone_pairs": 0,
        "unknown_voltage_pairs": 0,
    }
    for rec in measurements or []:
        req = resolver.resolve(rec.net_a, rec.net_b)
        if req.requirement_source == REQUIREMENT_SOURCE_GALVANIC_ZONE:
            summary["cross_zone_pairs"] = int(summary["cross_zone_pairs"] or 0) + 1
            supported = _finite_float(getattr(rec, "effective_max_voltage_v", None))
            if supported is None:
                summary["cross_zone_unknown"] = int(summary["cross_zone_unknown"] or 0) + 1
            elif req.required_voltage_v is not None and supported >= req.required_voltage_v:
                summary["cross_zone_pass"] = int(summary["cross_zone_pass"] or 0) + 1
            else:
                summary["cross_zone_fail"] = int(summary["cross_zone_fail"] or 0) + 1
        else:
            summary["local_voltage_pairs"] = int(summary["local_voltage_pairs"] or 0) + 1
        if _INCOMPLETE_ZONE_WARNING in req.warning:
            summary["incomplete_zone_pairs"] = int(summary["incomplete_zone_pairs"] or 0) + 1
        if req.required_voltage_v is None:
            summary["unknown_voltage_pairs"] = int(summary["unknown_voltage_pairs"] or 0) + 1
    return summary
