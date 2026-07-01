"""Voltage screening estimates from measured PCB copper spacing.

This module intentionally provides an engineering screening estimate, not a
formal IEC/UL certification calculation.  It maps measured copper spacing to an
estimated maximum working voltage using conservative lookup curves influenced by
CTI/material group, pollution degree, and altitude correction.

The measured spacing is a same-layer copper-to-copper geometric distance from
ODB++ data.  It is used here as both the clearance proxy and the creepage proxy,
then the lower resulting voltage is reported.
"""

from __future__ import annotations

from bisect import bisect_left


# Conservative reference curve for clearance through air at <=2000 m.
# Values are approximate screening points in mm versus working voltage.
_CLEARANCE_REF = [
    (0.05, 10.0),
    (0.10, 20.0),
    (0.20, 30.0),
    (0.40, 60.0),
    (0.60, 100.0),
    (0.80, 150.0),
    (1.50, 250.0),
    (3.00, 400.0),
    (5.50, 600.0),
    (8.00, 1000.0),
]

# Conservative reference curve for creepage, material group IIIa, pollution degree 2.
# The actual standard table is discrete and application-dependent; this is a
# practical screening curve that can be tuned later to a project-specific ruleset.
_CREEPAGE_PD2_IIIA = [
    (0.20, 10.0),
    (0.40, 25.0),
    (0.85, 50.0),
    (1.50, 100.0),
    (2.00, 150.0),
    (3.20, 250.0),
    (6.30, 400.0),
    (8.00, 500.0),
    (10.00, 630.0),
    (12.50, 800.0),
    (16.00, 1000.0),
]

_MATERIAL_SCALE = {
    "I": 0.70,
    "II": 0.85,
    "IIIa": 1.00,
    "IIIb": 1.12,
    "below IIIb": 1.35,
}

_POLLUTION_SCALE = {
    1: 0.55,
    2: 1.00,
    3: 1.65,
    4: 2.40,
}

_ALTITUDE_FACTOR = [
    (0.0, 1.00),
    (2000.0, 1.00),
    (3000.0, 1.14),
    (4000.0, 1.29),
    (5000.0, 1.48),
    (6000.0, 1.70),
    (7000.0, 1.95),
    (8000.0, 2.25),
    (10000.0, 2.90),
]


def material_group_from_cti(cti: float | int | None) -> str:
    """Return IEC-style material group from CTI value."""

    try:
        value = float(cti)
    except Exception:
        value = 175.0
    if value >= 600.0:
        return "I"
    if value >= 400.0:
        return "II"
    if value >= 175.0:
        return "IIIa"
    if value >= 100.0:
        return "IIIb"
    return "below IIIb"


def altitude_correction_factor(altitude_m: float | int | None) -> float:
    """Return a clearance multiplier for altitude by linear interpolation."""

    try:
        altitude = max(0.0, float(altitude_m))
    except Exception:
        altitude = 5500.0

    points = _ALTITUDE_FACTOR
    if altitude <= points[0][0]:
        return points[0][1]
    for (a0, f0), (a1, f1) in zip(points, points[1:]):
        if altitude <= a1:
            if a1 == a0:
                return f1
            ratio = (altitude - a0) / (a1 - a0)
            return f0 + ratio * (f1 - f0)
    return points[-1][1]


def _voltage_from_required_distance(distance_mm: float, required_table: list[tuple[float, float]]) -> float:
    """Invert a required-distance table using linear interpolation."""

    if distance_mm <= 0:
        return 0.0

    table = sorted(required_table)
    if distance_mm <= table[0][0]:
        req0, v0 = table[0]
        return max(0.0, v0 * distance_mm / req0) if req0 > 0 else 0.0

    for (d0, v0), (d1, v1) in zip(table, table[1:]):
        if distance_mm <= d1:
            ratio = (distance_mm - d0) / (d1 - d0)
            return v0 + ratio * (v1 - v0)

    d0, v0 = table[-2]
    d1, v1 = table[-1]
    slope = (v1 - v0) / (d1 - d0)
    return min(1500.0, v1 + (distance_mm - d1) * slope)


def clearance_limited_voltage(distance_mm: float, altitude_m: float | int | None = 5500.0) -> float:
    """Estimate max voltage limited by air clearance and altitude."""

    factor = altitude_correction_factor(altitude_m)
    sea_level_equivalent = float(distance_mm) / factor if factor > 0 else float(distance_mm)
    return _voltage_from_required_distance(sea_level_equivalent, _CLEARANCE_REF)


def creepage_limited_voltage(
    distance_mm: float,
    cti: float | int | None = 175.0,
    pollution_degree: int | str | None = 2,
) -> float:
    """Estimate max voltage limited by creepage/material/pollution settings."""

    group = material_group_from_cti(cti)
    try:
        pd = int(float(pollution_degree))
    except Exception:
        pd = 2
    pd = min(4, max(1, pd))

    scale = _MATERIAL_SCALE.get(group, 1.35) * _POLLUTION_SCALE.get(pd, 1.0)
    scaled_table = [(req * scale, voltage) for req, voltage in _CREEPAGE_PD2_IIIA]
    return _voltage_from_required_distance(float(distance_mm), scaled_table)


def estimate_effective_max_voltage(
    distance_mm: float | None,
    *,
    cti: float | int | None = 175.0,
    pollution_degree: int | str | None = 2,
    altitude_m: float | int | None = 5500.0,
) -> float | None:
    """Estimate maximum working voltage for a measured spacing.

    The output is the lower of the altitude-corrected clearance estimate and the
    CTI/pollution creepage estimate.  Returned units are volts.
    """

    if distance_mm is None:
        return None
    try:
        spacing = float(distance_mm)
    except Exception:
        return None
    if spacing < 0:
        return None

    by_clearance = clearance_limited_voltage(spacing, altitude_m=altitude_m)
    by_creepage = creepage_limited_voltage(spacing, cti=cti, pollution_degree=pollution_degree)
    return max(0.0, min(by_clearance, by_creepage))


def voltage_settings_summary(cti: float, pollution_degree: int | str, altitude_m: float) -> str:
    """Human-readable settings summary for reports."""

    group = material_group_from_cti(cti)
    factor = altitude_correction_factor(altitude_m)
    return (
        f"CTI={float(cti):g} ({group}), pollution degree={pollution_degree}, "
        f"altitude={float(altitude_m):g} m, altitude factor={factor:.3f}"
    )


# IPC-2221A/B-style conductor-spacing inversion.
# Values are minimum spacing in mm for a voltage range.  B1 = internal
# conductors, B2 = external uncoated conductors up to 3050 m, B3 = external
# uncoated conductors over 3050 m.
_IPC2221_RANGES = [
    # v_min, v_max, B1_internal, B2_external_low_alt, B3_external_high_alt
    (0.0, 15.0, 0.05, 0.10, 0.10),
    (16.0, 30.0, 0.05, 0.10, 0.10),
    (31.0, 50.0, 0.10, 0.60, 0.60),
    (51.0, 100.0, 0.10, 0.60, 1.50),
    (101.0, 150.0, 0.20, 0.60, 3.20),
    (151.0, 170.0, 0.20, 1.25, 3.20),
    (171.0, 250.0, 0.20, 1.25, 6.40),
    (251.0, 300.0, 0.20, 1.25, 12.50),
    (301.0, 500.0, 0.25, 2.50, 12.50),
]

_IPC2221_ABOVE_500_BASE = {
    "internal": 0.25,
    "external": 2.50,
    "external_high_altitude": 12.50,
}
_IPC2221_ABOVE_500_SLOPE = {
    "internal": 0.0025,
    "external": 0.005,
    "external_high_altitude": 0.025,
}


def ipc2221a_spacing_class(layer_role: str | None, altitude_m: float | int | None = 0.0) -> str:
    """Return the IPC-style spacing class for one layer role.

    ``internal`` maps to B1.  ``external`` maps to B2 up to 3050 m and B3
    above 3050 m, because the IPC table distinguishes external uncoated
    conductors by altitude.
    """

    role = str(layer_role or "external").strip().lower()
    if role in {"internal", "inner", "int"}:
        return "internal"
    try:
        altitude = float(altitude_m or 0.0)
    except Exception:
        altitude = 0.0
    if altitude > 3050.0:
        return "external_high_altitude"
    return "external"


def _ipc_required_spacing_for_voltage(voltage: float, spacing_class: str) -> float:
    """Return required IPC-style spacing in mm for a voltage."""

    voltage = max(0.0, float(voltage))
    if voltage > 500.0:
        base = _IPC2221_ABOVE_500_BASE[spacing_class]
        slope = _IPC2221_ABOVE_500_SLOPE[spacing_class]
        return base + (voltage - 500.0) * slope

    column = {"internal": 2, "external": 3, "external_high_altitude": 4}[spacing_class]
    for v_min, v_max, b1, b2, b3 in _IPC2221_RANGES:
        if voltage <= v_max:
            return (b1, b2, b3)[column - 2]
    return _IPC2221_RANGES[-1][column]


def estimate_ipc2221a_max_voltage(
    distance_mm: float | None,
    *,
    layer_role: str | None = "external",
    altitude_m: float | int | None = 0.0,
) -> float | None:
    """Estimate max voltage from measured spacing using IPC-2221A/B style tables.

    The returned value is the largest range endpoint whose required spacing is
    less than or equal to the measured spacing.  For spacing larger than the
    500 V table requirement, the >500 V per-volt increment is inverted.
    """

    if distance_mm is None:
        return None
    try:
        spacing = float(distance_mm)
    except Exception:
        return None
    if spacing < 0:
        return None

    spacing_class = ipc2221a_spacing_class(layer_role, altitude_m=altitude_m)

    # Below the first range, return a proportional estimate rather than a hard 0.
    first_req = _ipc_required_spacing_for_voltage(15.0, spacing_class)
    if spacing < first_req:
        return max(0.0, 15.0 * spacing / first_req) if first_req > 0 else 0.0

    best = 0.0
    for _v_min, v_max, *_spacing_values in _IPC2221_RANGES:
        req = _ipc_required_spacing_for_voltage(v_max, spacing_class)
        if spacing + 1e-12 >= req:
            best = v_max
        else:
            break

    req_500 = _ipc_required_spacing_for_voltage(500.0, spacing_class)
    if spacing > req_500:
        slope = _IPC2221_ABOVE_500_SLOPE[spacing_class]
        best = max(best, 500.0 + (spacing - req_500) / slope)

    return min(5000.0, max(0.0, best))


def ipc2221a_settings_text(layer_role: str | None, altitude_m: float | int | None = 0.0) -> str:
    """Return readable IPC layer class text."""

    spacing_class = ipc2221a_spacing_class(layer_role, altitude_m=altitude_m)
    if spacing_class == "internal":
        return "IPC-2221A/B B1 internal"
    if spacing_class == "external_high_altitude":
        return "IPC-2221A/B B3 external >3050 m"
    return "IPC-2221A/B B2 external <=3050 m"
