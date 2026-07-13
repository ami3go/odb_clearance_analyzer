"""Canonical enum values for deterministic voltage guessing."""

from __future__ import annotations

NET_CLASSES = {
    "GND",
    "POWER",
    "POWER_NEGATIVE",
    "POWER_VARIABLE",
    "POWER_HIGHER_LOW_VOLTAGE",
    "HIGH_VOLTAGE",
    "MAINS",
    "BATTERY",
    "IO_DIGITAL",
    "IO_ANALOG",
    "DIFFERENTIAL_IO",
    "COMMUNICATION",
    "ISOLATION_DOMAIN_HINT",
    "CONTROL_SIGNAL",
    "REFERENCE",
    "UNKNOWN",
}

CONFIDENCE_VALUES = {"High", "Medium", "Low", "Unknown"}
SEVERITY_VALUES = {"Info", "Review", "Warning", "Critical"}
REVIEW_STATES = {
    "Auto-guessed",
    "Imported",
    "Needs review",
    "Reviewed",
    "Approved",
    "Accepted unknown",
    "Waived",
    "Conflict",
    "Obsolete / missing in new revision",
}
ASSIGNMENT_SOURCES = {
    "rule",
    "manual",
    "imported_exact",
    "imported_case_insensitive",
    "imported_normalized",
    "imported_manual_mapping",
    "unknown",
}
VOLTAGE_TYPES = {"DC", "AC_RMS", "AC_PEAK", "VARIABLE", "UNKNOWN"}
MATCH_TYPES = {"exact", "token", "prefix", "suffix", "regex"}
MATCH_ON_VALUES = {"normalized", "raw"}


def validate_choice(value: str, allowed: set[str], field_name: str) -> None:
    if value not in allowed:
        raise ValueError(f"Invalid {field_name}: {value!r}; allowed: {', '.join(sorted(allowed))}")
