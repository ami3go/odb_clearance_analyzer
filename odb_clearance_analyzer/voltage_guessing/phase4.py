"""Phase 4 productivity helpers for deterministic voltage guessing.

This module deliberately contains no Tk imports.  It gives the GUI and tests
small service functions for batch previews, inline explainability, correction-
to-rule, assignment diffs, copyable summaries, and review-session persistence.
"""

from __future__ import annotations

import copy
import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

from .assignment_store import utc_now
from .models import AssignmentStore, RulePack, VoltageAssignment, VoltageEvidence, VoltageWaiver, VoltageRule
from .normalization import normalize_net_name_safe
from .review_service import apply_manual_override, approve, accept_unknown, waive, default_reviewer, _push_undo

WARNING_BLOCKED_SEVERITIES = {"Warning", "Critical"}
PROJECT_CORRECTION_RULE_FILE = "project_local_corrections.csv"


@dataclass(frozen=True)
class BatchPreviewRow:
    net_name: str
    old_class: str
    old_voltage_v: float | None
    old_review_state: str
    new_class: str
    new_voltage_v: float | None
    new_review_state: str
    reason: str
    blocked: bool = False


@dataclass(frozen=True)
class BatchPreview:
    operation: str
    requested_count: int
    affected_count: int
    blocked_count: int
    rows: list[BatchPreviewRow] = field(default_factory=list)

    @property
    def summary(self) -> str:
        return (
            f"{self.operation}: {self.affected_count} affected, "
            f"{self.blocked_count} blocked, {self.requested_count} requested"
        )


@dataclass(frozen=True)
class WhyExplanation:
    net_name: str
    text: str
    winning_rule_id: str
    losing_rule_ids: list[str]


@dataclass(frozen=True)
class SimilarNetSuggestion:
    net_name: str
    reason: str


@dataclass(frozen=True)
class AssignmentDiffRow:
    category: str
    net_name: str
    old_class: str
    old_voltage_v: float | None
    old_review_state: str
    new_class: str
    new_voltage_v: float | None
    new_review_state: str


def _fmt_voltage(value: float | None) -> str:
    return "" if value is None else f"{value:g}"


def _safe_net_list(store: AssignmentStore, nets: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for net in nets:
        if net in store.assignments and net not in seen:
            seen.add(net)
            result.append(net)
    return result


def make_batch_preview(
    store: AssignmentStore,
    nets: list[str],
    operation: str,
    *,
    final_class: str | None = None,
    final_voltage_v: float | None = None,
    reason: str = "",
) -> BatchPreview:
    """Return a dry-run preview for Phase 4 batch actions.

    No store mutation happens here.  Bulk approve blocks Warning/Critical nets
    according to Rev C 6.3 / addendum 14.1.
    """
    safe_nets = _safe_net_list(store, nets)
    rows: list[BatchPreviewRow] = []
    for net in safe_nets:
        a = store.assignments[net]
        blocked = False
        new_class = a.final_class
        new_voltage = a.final_voltage_v
        new_state = a.review_state
        detail = reason
        if operation == "approve":
            blocked = a.severity in WARNING_BLOCKED_SEVERITIES
            new_state = a.review_state if blocked else "Approved"
            detail = "Blocked: Warning/Critical severity requires individual review" if blocked else (reason or "Batch approve")
        elif operation == "accept_unknown":
            new_class = "UNKNOWN"
            new_voltage = None
            new_state = "Accepted unknown"
            detail = reason or "Batch accept unknown"
        elif operation == "set_class_voltage":
            new_class = final_class or a.final_class
            new_voltage = final_voltage_v
            new_state = "Reviewed"
            detail = reason or "Batch set class/voltage"
        elif operation == "waive":
            new_state = "Waived"
            detail = reason or "Batch waiver"
        else:
            blocked = True
            detail = f"Unsupported batch operation: {operation}"
        rows.append(
            BatchPreviewRow(
                net_name=net,
                old_class=a.final_class,
                old_voltage_v=a.final_voltage_v,
                old_review_state=a.review_state,
                new_class=new_class,
                new_voltage_v=new_voltage,
                new_review_state=new_state,
                reason=detail,
                blocked=blocked,
            )
        )
    return BatchPreview(
        operation=operation,
        requested_count=len(nets),
        affected_count=sum(1 for r in rows if not r.blocked),
        blocked_count=sum(1 for r in rows if r.blocked),
        rows=rows,
    )


def preview_to_text(preview: BatchPreview, *, max_rows: int = 25) -> str:
    lines = [preview.summary, "", "Net | old → new | reason"]
    for row in preview.rows[:max_rows]:
        flag = "BLOCKED " if row.blocked else ""
        lines.append(
            f"{flag}{row.net_name}: "
            f"{row.old_class}/{_fmt_voltage(row.old_voltage_v)}/{row.old_review_state} → "
            f"{row.new_class}/{_fmt_voltage(row.new_voltage_v)}/{row.new_review_state}; {row.reason}"
        )
    if len(preview.rows) > max_rows:
        lines.append(f"... {len(preview.rows) - max_rows} more row(s)")
    return "\n".join(lines)


def apply_batch_action(
    store: AssignmentStore,
    nets: list[str],
    operation: str,
    *,
    final_class: str | None = None,
    final_voltage_v: float | None = None,
    reason: str = "",
    waiver_scope: str = "current_revision_only",
    reviewer: str | None = None,
) -> int:
    """Apply a Phase 4 batch action as one undoable user operation."""
    preview = make_batch_preview(
        store,
        nets,
        operation,
        final_class=final_class,
        final_voltage_v=final_voltage_v,
        reason=reason,
    )
    apply_nets = [row.net_name for row in preview.rows if not row.blocked]
    if operation == "approve":
        return approve(store, apply_nets, reason=reason, reviewer=reviewer)
    if operation in {"accept_unknown", "set_class_voltage"}:
        previous = dict(store.assignments)
        who = reviewer or default_reviewer()
        now = utc_now()
        for net in apply_nets:
            a = copy.deepcopy(store.assignments[net])
            if operation == "accept_unknown":
                a.final_class = "UNKNOWN"
                a.final_voltage_v = None
                a.review_state = "Accepted unknown"
                a.review_reason = reason or a.review_reason
                a.notes = reason or a.notes
            else:
                a.final_class = final_class or "UNKNOWN"
                a.final_voltage_v = final_voltage_v
                a.review_state = "Reviewed"
                a.review_reason = reason
                a.notes = reason
                a.source = "manual"
                a.evidence.evidence_type = "manual_override"
                a.evidence.manual_review_note = reason
            a.reviewed_by = who
            a.reviewed_at_utc = now
            store.assignments[net] = a
        if apply_nets:
            _push_undo(store, f"batch_{operation}", apply_nets, previous)
        return len(apply_nets)
    if operation == "waive":
        return waive(store, apply_nets, reason=reason, scope=waiver_scope, reviewer=reviewer)
    return 0


def explain_assignment(assignment: VoltageAssignment, rule_pack: RulePack | None = None) -> WhyExplanation:
    """Create an inline "Why?" explanation for one assignment."""
    evidence = assignment.evidence
    winning = evidence.matched_rule_id or ""
    matched = list(evidence.all_matched_rule_ids or [])
    losing = [rule for rule in matched if rule != winning]
    lines = [f"Net: {assignment.net_name}"]
    lines.append(f"Class/voltage: {assignment.final_class}, {_fmt_voltage(assignment.final_voltage_v) or 'unknown'} V")
    lines.append(f"Confidence/severity: {assignment.confidence} / {assignment.severity}")
    lines.append(f"Review state/source: {assignment.review_state} / {assignment.source}")
    if winning:
        lines.append(f"Winning rule: {winning}")
        if evidence.matched_pattern:
            lines.append(f"Pattern: {evidence.matched_pattern}")
        if evidence.matched_rule_pack or evidence.matched_rule_file:
            lines.append(f"Rule pack/file: {evidence.matched_rule_pack} / {evidence.matched_rule_file}")
    elif assignment.source == "manual":
        lines.append("Winning rule: none — manual override")
    else:
        lines.append("Winning rule: none — no deterministic rule matched")
    if losing:
        lines.append("Other matched rules that lost: " + ", ".join(losing))
        lines.append("Decision: rule precedence from layer, priority, specificity, pattern length, then rule_id.")
    if evidence.imported_from_file:
        lines.append(
            f"Import provenance: {evidence.imported_from_file}, "
            f"status={evidence.import_match_status}, score={evidence.import_match_score}"
        )
    if evidence.rule_reason:
        lines.append("Reason: " + evidence.rule_reason)
    if evidence.rule_warning:
        lines.append("Warning: " + evidence.rule_warning)
    if evidence.manual_review_note or assignment.review_reason:
        lines.append("Review note: " + (evidence.manual_review_note or assignment.review_reason))
    if assignment.waiver.waived:
        lines.append(f"Waiver: {assignment.waiver.waiver_scope} — {assignment.waiver.waiver_reason}")
    return WhyExplanation(assignment.net_name, "\n".join(lines), winning, losing)


def suggest_similar_nets(store: AssignmentStore, edited_net: str, *, max_items: int = 12) -> list[SimilarNetSuggestion]:
    """Find deterministic similar nets for correction-to-rule."""
    if edited_net not in store.assignments:
        return []
    norm = normalize_net_name_safe(edited_net)
    tokens = [t for t in norm.split("_") if t]
    candidates: list[SimilarNetSuggestion] = []
    for net in sorted(store.assignments):
        if net == edited_net:
            continue
        n = normalize_net_name_safe(net)
        n_tokens = [t for t in n.split("_") if t]
        common = sorted(set(tokens) & set(n_tokens))
        if common:
            candidates.append(SimilarNetSuggestion(net, "shared token(s): " + ", ".join(common)))
            continue
        # Prefix stem fallback, useful for VSYS → VSYS_MCU style edits.
        if norm and (n.startswith(norm + "_") or norm.startswith(n + "_")):
            candidates.append(SimilarNetSuggestion(net, "shared normalized prefix"))
    return candidates[:max_items]


def _rule_id_from_token(token: str) -> str:
    clean = re.sub(r"[^A-Z0-9_]+", "_", normalize_net_name_safe(token)).strip("_").lower()
    return f"user_correction_{clean or 'rule'}"


def create_project_local_rule_from_correction(
    rule_dir: Path,
    *,
    token: str,
    assignment: VoltageAssignment,
    reviewer: str | None = None,
) -> Path:
    """Append a deterministic project-local token rule from a manual correction."""
    rule_dir = Path(rule_dir)
    rule_dir.mkdir(parents=True, exist_ok=True)
    path = rule_dir / PROJECT_CORRECTION_RULE_FILE
    fieldnames = [
        "rule_id", "priority", "enabled", "pattern", "match_type", "match_on", "net_class",
        "voltage_v", "reference_net", "voltage_type", "confidence", "severity", "reason", "warning", "tags",
    ]
    exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not exists:
            writer.writeheader()
        writer.writerow(
            {
                "rule_id": _rule_id_from_token(token),
                "priority": "700",
                "enabled": "true",
                "pattern": normalize_net_name_safe(token),
                "match_type": "token",
                "match_on": "normalized",
                "net_class": assignment.final_class,
                "voltage_v": _fmt_voltage(assignment.final_voltage_v),
                "reference_net": assignment.reference_net,
                "voltage_type": assignment.voltage_type,
                "confidence": "High",
                "severity": assignment.severity,
                "reason": f"Project-local rule from manual correction by {reviewer or default_reviewer()} at {utc_now()}",
                "warning": "",
                "tags": "user_correction;project_local",
            }
        )
    return path


def diff_assignments(old: dict[str, VoltageAssignment], new: dict[str, VoltageAssignment]) -> list[AssignmentDiffRow]:
    rows: list[AssignmentDiffRow] = []
    all_nets = sorted(set(old) | set(new))
    for net in all_nets:
        o = old.get(net)
        n = new.get(net)
        if o is None and n is not None:
            category = "added"
        elif o is not None and n is None:
            category = "deleted"
        elif o and n and (o.final_voltage_v != n.final_voltage_v):
            category = "voltage_changed"
        elif o and n and (o.final_class != n.final_class):
            category = "class_changed"
        elif o and n and (o.review_state != n.review_state):
            category = "review_state_changed"
        else:
            category = "unchanged"
        rows.append(
            AssignmentDiffRow(
                category=category,
                net_name=net,
                old_class=o.final_class if o else "",
                old_voltage_v=o.final_voltage_v if o else None,
                old_review_state=o.review_state if o else "",
                new_class=n.final_class if n else "",
                new_voltage_v=n.final_voltage_v if n else None,
                new_review_state=n.review_state if n else "",
            )
        )
    return rows


def copyable_review_summary(
    store: AssignmentStore,
    *,
    project_name: str = "",
    rule_pack_name: str = "",
    template: str = "",
) -> str:
    values = list(store.assignments.values())
    assigned = sum(1 for a in values if a.final_class != "UNKNOWN" or a.final_voltage_v is not None)
    accepted_unknown = sum(1 for a in values if a.review_state == "Accepted unknown")
    conflicts = sum(1 for a in values if a.review_state == "Conflict")
    waived = sum(1 for a in values if a.waiver.waived)
    need_critical = sum(1 for a in values if a.severity == "Critical" and a.review_state in {"Needs review", "Conflict", "Auto-guessed"})
    need_warning = sum(1 for a in values if a.severity == "Warning" and a.review_state in {"Needs review", "Conflict", "Auto-guessed"})
    return (
        f"Voltage assignment status — {project_name or store.project_revision or 'project'} ({utc_now()[:10]})\n"
        f"Nets: {len(values)} | Assigned: {assigned} | Accepted unknown: {accepted_unknown}\n"
        f"Unreviewed critical: {need_critical} | Unreviewed warning: {need_warning}\n"
        f"Conflicts: {conflicts} | Waived: {waived}\n"
        f"Rule pack: {rule_pack_name or 'active rule pack'}\n"
        f"Template: {template or 'not specified'}"
    )


def update_review_session(store: AssignmentStore, *, queue_position: int | None = None, active_filter: str | None = None, sort_key: str | None = None, skipped_net: str | None = None) -> None:
    if queue_position is not None:
        store.review_session.queue_position = max(0, int(queue_position))
    if active_filter is not None:
        store.review_session.active_filter = active_filter
    if sort_key is not None:
        store.review_session.sort_key = sort_key
    if skipped_net and skipped_net not in store.review_session.skipped_nets:
        store.review_session.skipped_nets.append(skipped_net)
