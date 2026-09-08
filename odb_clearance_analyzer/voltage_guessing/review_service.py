"""Phase 2 review-management services for deterministic voltage guessing.

All review logic lives here so the GUI stays a thin caller (addendum 8.1).
Every state-changing operation records one UndoEntry (addendum 13.2).
"""

from __future__ import annotations

import copy
import getpass
import os
from dataclasses import dataclass, field

from .assignment_store import utc_now
from .enums import REVIEW_STATES, validate_choice
from .models import AssignmentStore, RulePack, UndoEntry, VoltageAssignment, VoltageDefaults, VoltageEvidence
from .rule_engine import guess_voltage_for_nets

UNDO_STACK_DEPTH = 20

_IMPORTED_SOURCES = {
    "imported_exact",
    "imported_case_insensitive",
    "imported_normalized",
    "imported_manual_mapping",
}
_PRESERVED_SOURCES = {"manual"} | _IMPORTED_SOURCES

GATE_MODES = ("allow", "warn", "block")
DEFAULT_GATE_MODE = "warn"


def default_reviewer() -> str:
    """Reviewer identity per Rev C Section 19: OS login username."""
    for value in (os.environ.get("USERNAME"), os.environ.get("USER")):
        if value:
            return value
    try:
        return getpass.getuser()
    except Exception:
        return "user"


def _push_undo(store: AssignmentStore, operation: str, changed_nets: list[str], previous: dict[str, VoltageAssignment]) -> None:
    changed = {net: copy.deepcopy(previous[net]) for net in changed_nets if net in previous}
    # Nets that did not exist before are recorded with a sentinel so undo can remove them.
    entry = UndoEntry(operation=operation, timestamp_utc=utc_now(), changed=changed)
    entry_new = [net for net in changed_nets if net not in previous]
    if entry_new:
        entry.changed["__created__"] = VoltageAssignment(
            net_name=";".join(sorted(entry_new)),
            final_class="UNKNOWN", final_voltage_v=None, reference_net="",
            voltage_type="UNKNOWN", confidence="Unknown", severity="Info",
            review_state="Needs review", source="unknown",
            evidence=VoltageEvidence(evidence_type="undo_created_sentinel"),
        )
    store.undo_stack.append(entry)
    del store.undo_stack[:-UNDO_STACK_DEPTH]


def run_auto_detect(store: AssignmentStore, net_names: list[str], rule_pack: RulePack, *, source_revision: str = "", defaults: VoltageDefaults | None = None) -> int:
    """Guess all nets; preserve manual and imported assignments (Rev C 9.8/28).

    Returns the number of assignments changed or added. Records one undo entry.
    """
    previous = dict(store.assignments)
    guessed = guess_voltage_for_nets(net_names, rule_pack, defaults or rule_pack.defaults, source_revision=source_revision)
    changed_nets: list[str] = []
    merged: dict[str, VoltageAssignment] = dict(previous)
    for assignment in guessed:
        old = previous.get(assignment.net_name)
        if old is not None and old.source in _PRESERVED_SOURCES:
            merged[assignment.net_name] = old
            continue
        if old is None or old.to_dict() != assignment.to_dict():
            changed_nets.append(assignment.net_name)
        merged[assignment.net_name] = assignment
    if changed_nets:
        _push_undo(store, "auto_detect", changed_nets, previous)
    store.assignments = merged
    if source_revision:
        store.project_revision = source_revision
    return len(changed_nets)


def _apply_manual_override_to_assignment(
    assignment: VoltageAssignment,
    *,
    final_class: str,
    final_voltage_v: float | None,
    review_state: str,
    notes: str,
    reviewer: str,
    reviewed_at_utc: str,
    galvanic_zone: str | None = None,
) -> VoltageAssignment:
    updated = copy.deepcopy(assignment)
    updated.final_class = final_class or "UNKNOWN"
    updated.final_voltage_v = final_voltage_v
    updated.review_state = review_state
    updated.source = "manual"
    updated.notes = notes
    updated.review_reason = notes
    updated.reviewed_by = reviewer
    updated.reviewed_at_utc = reviewed_at_utc
    if galvanic_zone is not None:
        updated.galvanic_zone = galvanic_zone
    updated.evidence.evidence_type = "manual_override"
    updated.evidence.manual_review_note = notes
    return updated


def apply_manual_override_bulk(
    store: AssignmentStore,
    nets: list[str],
    *,
    final_class: str,
    final_voltage_v: float | None,
    review_state: str = "Reviewed",
    notes: str = "",
    reviewer: str | None = None,
    galvanic_zone: str | None = None,
) -> int:
    """Apply one manual voltage correction to multiple assignments.

    This is used by the GUI All Assignments bulk editor.  It records one
    undo entry for the whole selection instead of one undo entry per net, so
    Shift/Ctrl multi-select behaves as a single user action.
    """
    validate_choice(review_state, REVIEW_STATES, "review_state")
    unique_nets: list[str] = []
    seen: set[str] = set()
    for net in nets:
        if net in seen:
            continue
        seen.add(net)
        if net not in store.assignments:
            raise KeyError(f"Unknown net: {net}")
        unique_nets.append(net)

    if not unique_nets:
        return 0

    previous = dict(store.assignments)
    who = reviewer or default_reviewer()
    now = utc_now()
    for net in unique_nets:
        store.assignments[net] = _apply_manual_override_to_assignment(
            store.assignments[net],
            final_class=final_class,
            final_voltage_v=final_voltage_v,
            review_state=review_state,
            notes=notes,
            reviewer=who,
            reviewed_at_utc=now,
            galvanic_zone=galvanic_zone,
        )
    _push_undo(store, "manual_bulk_edit" if len(unique_nets) > 1 else "manual_edit", unique_nets, previous)
    return len(unique_nets)




def apply_galvanic_zone_bulk(
    store: AssignmentStore,
    nets: list[str],
    *,
    galvanic_zone: str,
    reviewer: str | None = None,
) -> int:
    """Apply only the galvanic zone to selected assignments.

    This intentionally preserves voltage class, voltage value, review state,
    notes, and source.  It is safer than a full manual override when assigning
    many unrelated nets to the same isolation domain.
    """
    unique_nets: list[str] = []
    seen: set[str] = set()
    for net in nets:
        if net in seen:
            continue
        seen.add(net)
        if net not in store.assignments:
            raise KeyError(f"Unknown net: {net}")
        unique_nets.append(net)

    if not unique_nets:
        return 0

    previous = dict(store.assignments)
    who = reviewer or default_reviewer()
    now = utc_now()
    for net in unique_nets:
        updated = copy.deepcopy(store.assignments[net])
        updated.galvanic_zone = galvanic_zone
        updated.reviewed_by = updated.reviewed_by or who
        updated.reviewed_at_utc = updated.reviewed_at_utc or now
        store.assignments[net] = updated
    _push_undo(store, "galvanic_zone_bulk_edit" if len(unique_nets) > 1 else "galvanic_zone_edit", unique_nets, previous)
    return len(unique_nets)


def apply_manual_override(
    store: AssignmentStore,
    net: str,
    *,
    final_class: str,
    final_voltage_v: float | None,
    review_state: str = "Reviewed",
    notes: str = "",
    reviewer: str | None = None,
    galvanic_zone: str | None = None,
) -> VoltageAssignment:
    changed = apply_manual_override_bulk(
        store,
        [net],
        final_class=final_class,
        final_voltage_v=final_voltage_v,
        review_state=review_state,
        notes=notes,
        reviewer=reviewer,
        galvanic_zone=galvanic_zone,
    )
    if not changed:
        raise KeyError(f"Unknown net: {net}")
    return store.assignments[net]


def _review_action(store: AssignmentStore, nets: list[str], operation: str, mutate, reviewer: str | None) -> int:
    previous = dict(store.assignments)
    who = reviewer or default_reviewer()
    now = utc_now()
    changed: list[str] = []
    for net in nets:
        if net not in store.assignments:
            continue
        assignment = copy.deepcopy(store.assignments[net])
        mutate(assignment, who, now)
        store.assignments[net] = assignment
        changed.append(net)
    if changed:
        _push_undo(store, operation, changed, previous)
    return len(changed)


def approve(store: AssignmentStore, nets: list[str], *, reason: str = "", reviewer: str | None = None) -> int:
    """Bulk approve safe nets only.

    Per Rev C 6.3 / addendum 14.1, Warning- and Critical-severity
    assignments must never be approved through the batch/bulk approve
    service. They remain in the review queue for deliberate individual
    review via apply_manual_override(), accept_unknown(), or waive().
    """
    safe_nets = [
        net for net in nets
        if net in store.assignments and store.assignments[net].severity not in {"Warning", "Critical"}
    ]

    def mutate(a: VoltageAssignment, who: str, now: str) -> None:
        a.review_state = "Approved"
        a.reviewed_by, a.reviewed_at_utc = who, now
        if reason:
            a.review_reason = reason

    return _review_action(store, safe_nets, "review_approve", mutate, reviewer)


def accept_unknown(store: AssignmentStore, nets: list[str], *, reason: str = "", reviewer: str | None = None) -> int:
    def mutate(a: VoltageAssignment, who: str, now: str) -> None:
        a.review_state = "Accepted unknown"
        a.reviewed_by, a.reviewed_at_utc = who, now
        a.review_reason = reason or a.review_reason

    return _review_action(store, nets, "review_accept_unknown", mutate, reviewer)


def waive(store: AssignmentStore, nets: list[str], *, reason: str, scope: str = "current_revision_only", reviewer: str | None = None) -> int:
    if not reason.strip():
        raise ValueError("A waiver reason is required")
    if scope not in {"current_revision_only", "this_net_until_changed", "project_global"}:
        raise ValueError(f"Invalid waiver scope: {scope!r}")

    def mutate(a: VoltageAssignment, who: str, now: str) -> None:
        a.review_state = "Waived"
        a.reviewed_by, a.reviewed_at_utc = who, now
        a.waiver.waived = True
        a.waiver.waived_by = who
        a.waiver.waived_at_utc = now
        a.waiver.waiver_reason = reason
        a.waiver.waiver_scope = scope

    return _review_action(store, nets, "review_waive", mutate, reviewer)


def undo_last(store: AssignmentStore) -> str:
    """Undo the most recent operation. Returns the operation name ('' if nothing)."""
    if not store.undo_stack:
        return ""
    entry = store.undo_stack.pop()
    created = entry.changed.pop("__created__", None)
    for net, prior in entry.changed.items():
        store.assignments[net] = prior
    if created is not None:
        for net in created.net_name.split(";"):
            store.assignments.pop(net, None)
    return entry.operation


def needs_review(assignment: VoltageAssignment) -> bool:
    """Queue membership: unresolved states, or unreviewed Warning/Critical severity."""
    if assignment.review_state in {"Needs review", "Conflict", "Auto-guessed"}:
        return True
    if assignment.waiver.waived:
        return False
    if assignment.severity in {"Warning", "Critical"} and assignment.review_state not in {
        "Approved",
        "Reviewed",
        "Accepted unknown",
        "Waived",
    }:
        return True
    return False


def review_queue(store: AssignmentStore) -> list[VoltageAssignment]:
    """Nets requiring attention, most severe first, deterministic order."""
    rank = {"Critical": 0, "Warning": 1, "Review": 2, "Info": 3}
    queue = [a for a in store.assignments.values() if needs_review(a)]
    return sorted(queue, key=lambda a: (rank.get(a.severity, 4), a.net_name))


@dataclass
class ReviewGateStatus:
    mode: str
    export_allowed: bool
    stamp_text: str
    unreviewed_critical: int
    unreviewed_warning: int
    needs_review: int
    conflicts: int
    waived: int
    counts_line: str = field(default="")


def review_gate_status(store: AssignmentStore, mode: str = DEFAULT_GATE_MODE) -> ReviewGateStatus:
    if mode not in GATE_MODES:
        mode = DEFAULT_GATE_MODE
    values = list(store.assignments.values())
    unreviewed = [a for a in values if needs_review(a)]
    unreviewed_critical = sum(1 for a in unreviewed if a.severity == "Critical")
    unreviewed_warning = sum(1 for a in unreviewed if a.severity == "Warning")
    conflicts = sum(1 for a in values if a.review_state == "Conflict")
    waived = sum(1 for a in values if a.waiver.waived)
    export_allowed = True
    stamp = ""
    if unreviewed:
        if mode == "block" and unreviewed_critical > 0:
            export_allowed = False
        if mode in {"warn", "block"}:
            stamp = (
                "VOLTAGE ASSIGNMENTS INCOMPLETE / UNREVIEWED — "
                f"critical: {unreviewed_critical}, warning: {unreviewed_warning}, total needing review: {len(unreviewed)}"
            )
    counts_line = (
        f"Need review: {len(unreviewed)} | Unreviewed critical: {unreviewed_critical} | "
        f"Unreviewed warning: {unreviewed_warning} | Conflicts: {conflicts} | Waived: {waived}"
    )
    return ReviewGateStatus(
        mode=mode,
        export_allowed=export_allowed,
        stamp_text=stamp,
        unreviewed_critical=unreviewed_critical,
        unreviewed_warning=unreviewed_warning,
        needs_review=len(unreviewed),
        conflicts=conflicts,
        waived=waived,
        counts_line=counts_line,
    )
