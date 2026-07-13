"""Data models for deterministic net-voltage assignment."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class NormalizeOptions:
    strip_leading_plus: bool = True


@dataclass(frozen=True)
class VoltageToken:
    raw_token: str
    voltage_v: float
    polarity: int
    marker: str
    start: int
    end: int


@dataclass
class VoltageDefaults:
    mains_rms_v: float = 230.0
    mains_peak_v: float = 325.0
    battery_volts_per_cell_max: float = 4.2
    logic_io_v: float = 3.3
    analog_io_v: float = 3.3
    usb_vbus_v: float = 5.0
    usb_pd_max_v: float = 20.0
    poe_voltage_v: float = 57.0
    unknown_severity: str = "Review"


@dataclass
class VoltageEvidence:
    evidence_type: str = "unknown"
    matched_rule_id: str = ""
    matched_pattern: str = ""
    matched_rule_pack: str = ""
    matched_rule_file: str = ""
    all_matched_rule_ids: list[str] = field(default_factory=list)
    rule_reason: str = ""
    rule_warning: str = ""
    imported_from_file: str = ""
    import_match_status: str = ""
    import_match_score: int | None = None
    manual_review_note: str = ""
    last_exported_value: float | None = None


@dataclass
class VoltageWaiver:
    waived: bool = False
    waived_by: str = ""
    waived_at_utc: str = ""
    waiver_reason: str = ""
    waiver_scope: str = ""
    waiver_expires_revision: str = ""


@dataclass
class VoltageAssignment:
    net_name: str
    final_class: str
    final_voltage_v: float | None
    reference_net: str
    voltage_type: str
    confidence: str
    severity: str
    review_state: str
    source: str
    evidence: VoltageEvidence
    waiver: VoltageWaiver = field(default_factory=VoltageWaiver)
    notes: str = ""
    reviewed_by: str = ""
    reviewed_at_utc: str = ""
    review_reason: str = ""
    source_revision: str = ""
    last_seen_revision: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "VoltageAssignment":
        evidence_raw = data.get("evidence") or {}
        waiver_raw = data.get("waiver") or {}
        return VoltageAssignment(
            net_name=str(data.get("net_name", "")),
            final_class=str(data.get("final_class", "UNKNOWN")),
            final_voltage_v=_optional_float(data.get("final_voltage_v")),
            reference_net=str(data.get("reference_net", "")),
            voltage_type=str(data.get("voltage_type", "DC")),
            confidence=str(data.get("confidence", "Unknown")),
            severity=str(data.get("severity", "Review")),
            review_state=str(data.get("review_state", "Needs review")),
            source=str(data.get("source", "unknown")),
            evidence=VoltageEvidence(**{k: v for k, v in evidence_raw.items() if k in VoltageEvidence.__dataclass_fields__}),
            waiver=VoltageWaiver(**{k: v for k, v in waiver_raw.items() if k in VoltageWaiver.__dataclass_fields__}),
            notes=str(data.get("notes", "")),
            reviewed_by=str(data.get("reviewed_by", "")),
            reviewed_at_utc=str(data.get("reviewed_at_utc", "")),
            review_reason=str(data.get("review_reason", "")),
            source_revision=str(data.get("source_revision", "")),
            last_seen_revision=str(data.get("last_seen_revision", "")),
        )


@dataclass
class VoltageRule:
    rule_id: str
    priority: int
    enabled: bool
    pattern: str
    match_type: str
    net_class: str
    voltage_v: float | None
    cell_count_from_pattern: bool = False
    volts_per_cell: float | None = None
    reference_net: str = ""
    voltage_type: str = "DC"
    confidence: str = "Medium"
    severity: str = "Review"
    reason: str = ""
    warning: str = ""
    tags: list[str] = field(default_factory=list)
    source_layer: str = "built-in"
    source_file: str = ""
    match_on: str = "normalized"
    parse_issues: list[str] = field(default_factory=list)


@dataclass
class RuleMatchResult:
    net_name: str
    guessed_class: str
    guessed_voltage_v: float | None
    reference_net: str
    voltage_type: str
    confidence: str
    severity: str
    winning_rule_id: str | None
    all_matched_rule_ids: list[str]
    reason: str
    warning: str
    matched_pattern: str = ""
    matched_rule_pack: str = ""
    matched_rule_file: str = ""

    def to_assignment(self, source_revision: str = "") -> VoltageAssignment:
        state = "Approved" if self.confidence == "High" and self.severity in {"Info", "Review"} else "Needs review"
        if self.guessed_class == "UNKNOWN":
            state = "Needs review"
        return VoltageAssignment(
            net_name=self.net_name,
            final_class=self.guessed_class,
            final_voltage_v=self.guessed_voltage_v,
            reference_net=self.reference_net,
            voltage_type=self.voltage_type,
            confidence=self.confidence,
            severity=self.severity,
            review_state=state,
            source="rule" if self.winning_rule_id else "unknown",
            evidence=VoltageEvidence(
                evidence_type="rule_match" if self.winning_rule_id else "no_match",
                matched_rule_id=self.winning_rule_id or "",
                matched_pattern=self.matched_pattern,
                matched_rule_pack=self.matched_rule_pack,
                matched_rule_file=self.matched_rule_file,
                all_matched_rule_ids=list(self.all_matched_rule_ids),
                rule_reason=self.reason,
                rule_warning=self.warning,
            ),
            source_revision=source_revision,
            last_seen_revision=source_revision,
        )


@dataclass(frozen=True)
class PadInfo:
    component_refdes: str
    pad_name: str
    layer: str
    x: float
    y: float


class FingerprintDataUnavailable(Exception):
    """Raised when optional net fingerprint data cannot be provided."""


@dataclass(frozen=True)
class VoltageContext:
    net_class: str
    voltage_v: float | None
    review_state: str
    severity: str


@dataclass
class RulePack:
    manifest: dict
    rules: list[VoltageRule]
    defaults: VoltageDefaults
    source_files: list[Path]
    layer_counts: dict[str, int]
    missing_files: list[str] = field(default_factory=list)
    unlisted_files: list[str] = field(default_factory=list)
    tests_path: Path | None = None


@dataclass
class ValidationIssue:
    level: str
    rule_id: str
    source_file: str
    message: str


@dataclass
class ValidationResult:
    ok: bool
    issues: list[ValidationIssue]
    test_cases_run: int = 0
    test_cases_failed: int = 0


@dataclass
class ReviewSessionState:
    queue_position: int = 0
    active_filter: str = ""
    sort_key: str = ""
    skipped_nets: list[str] = field(default_factory=list)


@dataclass
class UndoEntry:
    operation: str
    timestamp_utc: str
    changed: dict[str, VoltageAssignment]


@dataclass
class AssignmentStore:
    schema_version: int
    project_revision: str
    assignments: dict[str, VoltageAssignment]
    review_session: ReviewSessionState = field(default_factory=ReviewSessionState)
    undo_stack: list[UndoEntry] = field(default_factory=list)
    created_utc: str = ""
    modified_utc: str = ""


def _optional_float(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except Exception:
        return None
