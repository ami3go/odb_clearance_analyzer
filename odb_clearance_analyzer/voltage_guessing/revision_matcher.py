"""Phase 3 deterministic revision matching.

Match statuses (Rev C 9.4/9.5): exact, case_insensitive, normalized,
likely_renamed (suggestion only), conflict, missing, new.

match_score implements addendum 11.1 exactly — the weights are frozen
together with the golden fixture test; change both or neither.
"""

from __future__ import annotations

import copy
import csv
import difflib
import heapq
from dataclasses import dataclass, field
from pathlib import Path

from .assignment_store import utc_now
from .models import AssignmentStore, RulePack, VoltageAssignment
from .normalization import net_tokens_safe, normalize_net_name_safe
from .review_service import _push_undo  # shared undo bookkeeping
from .rule_engine import guess_net_voltage
from .voltage_parser import parse_voltage_token

MATCH_SCORE_THRESHOLD_DEFAULT = 60
MAX_CANDIDATES_PER_NET = 3
MAX_BLOCKED_CANDIDATES = 20  # addendum 28.1: cap candidates before scoring
_SAFE_STATUSES = {"exact", "case_insensitive", "normalized"}
_W_SIMILARITY, _W_TOKENS, _W_VOLTAGE, _W_CLASS, _W_FP = 0.40, 0.20, 0.15, 0.15, 0.10


@dataclass(frozen=True)
class _NetFeatures:
    """Per-net inputs to the score, computed exactly once (perf: 28.1)."""

    normalized: str
    tokens: frozenset
    voltage_v: float | None
    net_class: str


def _features(net: str, rule_pack: RulePack, cache: dict) -> "_NetFeatures":
    cached = cache.get(net)
    if cached is not None:
        return cached
    token = parse_voltage_token(net)
    feature = _NetFeatures(
        normalized=normalize_net_name_safe(net),
        tokens=frozenset(net_tokens_safe(net)),
        voltage_v=None if token is None else token.voltage_v,
        net_class=guess_net_voltage(net, rule_pack).guessed_class,
    )
    cache[net] = feature
    return feature


def _score_features(
    old: "_NetFeatures",
    new: "_NetFeatures",
    old_prefixes: set | None,
    new_prefixes: set | None,
) -> int:
    similarity = difflib.SequenceMatcher(None, old.normalized, new.normalized).ratio()
    token_overlap = len(old.tokens & new.tokens) / max(len(old.tokens), 1)
    if old.voltage_v is not None and new.voltage_v is not None:
        voltage_match = 1.0 if abs(old.voltage_v - new.voltage_v) < 1e-9 else 0.0
    elif old.voltage_v is None and new.voltage_v is None:
        voltage_match = 0.5
    else:
        voltage_match = 0.0
    class_match = 1.0 if old.net_class == new.net_class else 0.0
    if old_prefixes and new_prefixes:
        union = old_prefixes | new_prefixes
        fp_pads = len(old_prefixes & new_prefixes) / len(union) if union else 0.0
    else:
        fp_pads = 0.0
    return round(
        100
        * (
            _W_SIMILARITY * similarity
            + _W_TOKENS * token_overlap
            + _W_VOLTAGE * voltage_match
            + _W_CLASS * class_match
            + _W_FP * fp_pads
        )
    )


@dataclass
class RevisionMatchEntry:
    old_net: str | None
    new_net: str | None
    match_status: str
    match_score: int | None = None
    applied: bool = False
    action_required: str = ""
    detail: str = ""


@dataclass
class RevisionMatchResult:
    entries: list[RevisionMatchEntry] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    source_file: str = ""
    source_revision: str = ""

    def recount(self) -> None:
        counts: dict[str, int] = {}
        for entry in self.entries:
            counts[entry.match_status] = counts.get(entry.match_status, 0) + 1
        self.counts = counts


def compute_match_score(
    old_net: str,
    new_net: str,
    rule_pack: RulePack,
    *,
    old_prefixes: set[str] | None = None,
    new_prefixes: set[str] | None = None,
) -> int:
    """Deterministic 0-100 score per addendum 11.1. Same inputs, same score."""
    cache: dict = {}
    return _score_features(
        _features(old_net, rule_pack, cache),
        _features(new_net, rule_pack, cache),
        old_prefixes,
        new_prefixes,
    )


def match_revision(
    imported: list[VoltageAssignment],
    current_nets: list[str],
    rule_pack: RulePack,
    *,
    score_threshold: int = MATCH_SCORE_THRESHOLD_DEFAULT,
    component_prefixes: dict[str, set[str]] | None = None,
    source_file: str = "",
    source_revision: str = "",
) -> RevisionMatchResult:
    """Match imported assignments to the current net list. Pure function, no store mutation."""
    result = RevisionMatchResult(source_file=source_file, source_revision=source_revision)
    current = sorted(set(current_nets))
    imported_by_name = {a.net_name: a for a in imported}
    by_casefold: dict[str, list[str]] = {}
    by_normalized: dict[str, list[str]] = {}
    for name in imported_by_name:
        by_casefold.setdefault(name.casefold(), []).append(name)
        by_normalized.setdefault(normalize_net_name_safe(name), []).append(name)

    matched_old: set[str] = set()
    unmatched_new: list[str] = []

    for net in current:
        if net in imported_by_name:
            result.entries.append(RevisionMatchEntry(net, net, "exact", applied=False))
            matched_old.add(net)
            continue
        ci = [n for n in by_casefold.get(net.casefold(), []) if n not in matched_old]
        if len(ci) == 1:
            result.entries.append(RevisionMatchEntry(ci[0], net, "case_insensitive"))
            matched_old.add(ci[0])
            continue
        if len(ci) > 1:
            result.entries.append(
                RevisionMatchEntry(None, net, "conflict", action_required="resolve_conflict",
                                   detail="Multiple imported nets match case-insensitively: " + ", ".join(sorted(ci)))
            )
            continue
        norm = [n for n in by_normalized.get(normalize_net_name_safe(net), []) if n not in matched_old]
        if len(norm) == 1:
            result.entries.append(RevisionMatchEntry(norm[0], net, "normalized"))
            matched_old.add(norm[0])
            continue
        if len(norm) > 1:
            result.entries.append(
                RevisionMatchEntry(None, net, "conflict", action_required="resolve_conflict",
                                   detail="Multiple imported nets match after normalization: " + ", ".join(sorted(norm)))
            )
            continue
        unmatched_new.append(net)

    # Likely-renamed suggestions for still-unmatched current nets.
    # Perf (addendum 28.1): per-net features are computed once; candidate
    # blocking restricts scoring to old nets sharing a token, an equal voltage
    # value, or the same detected class. Lossless at the default threshold:
    # a pair with no shared key scores at most 40 + 7.5 + 10 = 57.5 < 60.
    remaining_old = sorted(set(imported_by_name) - matched_old)
    prefixes = component_prefixes or {}
    feature_cache: dict = {}
    old_features = {old: _features(old, rule_pack, feature_cache) for old in remaining_old}
    by_token: dict = {}
    by_voltage: dict = {}
    by_class: dict = {}
    for old, f in old_features.items():
        for token in f.tokens:
            by_token.setdefault(token, set()).add(old)
        if f.voltage_v is not None:
            by_voltage.setdefault(f.voltage_v, set()).add(old)
        by_class.setdefault(f.net_class, set()).add(old)

    for net in unmatched_new:
        nf = _features(net, rule_pack, feature_cache)
        candidates: set = set()
        for token in nf.tokens:
            candidates |= by_token.get(token, set())
        if nf.voltage_v is not None:
            candidates |= by_voltage.get(nf.voltage_v, set())
        candidates |= by_class.get(nf.net_class, set())
        if len(candidates) > MAX_BLOCKED_CANDIDATES:
            candidates = set(
                heapq.nsmallest(
                    MAX_BLOCKED_CANDIDATES,
                    candidates,
                    key=lambda old: (-len(old_features[old].tokens & nf.tokens), old),
                )
            )
        scored: list[tuple[int, str]] = []
        for old in sorted(candidates):
            score = _score_features(
                old_features[old], nf, prefixes.get(old), prefixes.get(net)
            )
            if score >= score_threshold:
                scored.append((score, old))
        scored.sort(key=lambda item: (-item[0], item[1]))
        if scored:
            for score, old in scored[:MAX_CANDIDATES_PER_NET]:
                result.entries.append(
                    RevisionMatchEntry(old, net, "likely_renamed", match_score=score,
                                       action_required="review_suggestion")
                )
        else:
            result.entries.append(RevisionMatchEntry(None, net, "new",
                                                     detail="No imported match; rule-based guess will apply."))

    suggested_old = {e.old_net for e in result.entries if e.match_status == "likely_renamed"}
    conflict_candidates: set[str] = set()
    for e in result.entries:
        if e.match_status == "conflict" and ": " in e.detail:
            conflict_candidates.update(n.strip() for n in e.detail.split(": ", 1)[1].split(","))
    for old in remaining_old:
        if old in conflict_candidates:
            detail = "Conflict candidate awaiting resolution"
        elif old in suggested_old:
            detail = "Suggested as likely rename"
        else:
            detail = "Net not present in current revision"
        result.entries.append(RevisionMatchEntry(old, None, "missing", detail=detail))

    result.recount()
    return result


def _carry_waiver(assignment: VoltageAssignment, imported: VoltageAssignment, changed: bool) -> None:
    """Waiver carry-forward per Rev C Section 22 rules."""
    scope = imported.waiver.waiver_scope
    if not imported.waiver.waived:
        return
    if scope == "project_global":
        assignment.waiver = copy.deepcopy(imported.waiver)
        assignment.review_state = "Waived"
    elif scope == "this_net_until_changed" and not changed:
        assignment.waiver = copy.deepcopy(imported.waiver)
        assignment.review_state = "Waived"
    # current_revision_only: never carried; net re-enters review.


def apply_safe_matches(
    store: AssignmentStore,
    match_result: RevisionMatchResult,
    imported: list[VoltageAssignment],
    rule_pack: RulePack,
    *,
    current_revision: str = "",
) -> int:
    """Apply exact/case-insensitive/normalized matches and rule-guess new nets.

    Likely-renamed and conflicts are NOT applied (Phase 3 gate items 4-5).
    Missing old nets are preserved as 'Obsolete / missing in new revision'.
    Records one undo entry.
    """
    imported_by_name = {a.net_name: a for a in imported}
    previous = dict(store.assignments)
    changed_nets: list[str] = []
    source_by_status = {
        "exact": "imported_exact",
        "case_insensitive": "imported_case_insensitive",
        "normalized": "imported_normalized",
    }

    for entry in match_result.entries:
        if entry.match_status in _SAFE_STATUSES and entry.old_net and entry.new_net:
            old_assignment = imported_by_name[entry.old_net]
            assignment = copy.deepcopy(old_assignment)
            assignment.net_name = entry.new_net
            assignment.source = source_by_status[entry.match_status]
            assignment.evidence.evidence_type = "revision_import"
            assignment.evidence.imported_from_file = match_result.source_file
            assignment.evidence.import_match_status = entry.match_status
            assignment.last_seen_revision = current_revision or assignment.last_seen_revision
            value_changed = (
                previous.get(entry.new_net) is not None
                and (
                    previous[entry.new_net].final_class != assignment.final_class
                    or previous[entry.new_net].final_voltage_v != assignment.final_voltage_v
                )
            )
            _carry_waiver(assignment, old_assignment, changed=value_changed)
            if assignment.waiver.waived and assignment.waiver.waiver_scope == "current_revision_only":
                assignment.waiver.waived = False
                assignment.review_state = "Needs review"
            store.assignments[entry.new_net] = assignment
            entry.applied = True
            changed_nets.append(entry.new_net)
        elif entry.match_status == "new" and entry.new_net:
            guess = guess_net_voltage(entry.new_net, rule_pack).to_assignment(source_revision=current_revision)
            store.assignments[entry.new_net] = guess
            entry.applied = True
            changed_nets.append(entry.new_net)
        elif entry.match_status == "missing" and entry.old_net and entry.detail.startswith("Net not present"):
            preserved = copy.deepcopy(imported_by_name[entry.old_net])
            preserved.review_state = "Obsolete / missing in new revision"
            preserved.evidence.evidence_type = "revision_import"
            preserved.evidence.imported_from_file = match_result.source_file
            preserved.evidence.import_match_status = "missing"
            store.assignments[preserved.net_name] = preserved
            changed_nets.append(preserved.net_name)

    if changed_nets:
        _push_undo(store, "import_apply", changed_nets, previous)
    if match_result.source_revision and not store.project_revision:
        store.project_revision = match_result.source_revision
    return len(changed_nets)


def apply_manual_mapping(
    store: AssignmentStore,
    old_net: str,
    new_net: str,
    imported: list[VoltageAssignment],
    match_result: RevisionMatchResult,
    *,
    current_revision: str = "",
) -> VoltageAssignment:
    """User-confirmed old→new mapping (Phase 3 gate item 8)."""
    imported_by_name = {a.net_name: a for a in imported}
    if old_net not in imported_by_name:
        raise KeyError(f"Unknown imported net: {old_net}")
    previous = dict(store.assignments)
    assignment = copy.deepcopy(imported_by_name[old_net])
    assignment.net_name = new_net
    assignment.source = "imported_manual_mapping"
    assignment.review_state = "Reviewed"
    assignment.reviewed_at_utc = utc_now()
    assignment.evidence.evidence_type = "revision_import"
    assignment.evidence.imported_from_file = match_result.source_file
    assignment.evidence.import_match_status = "manual_mapping"
    assignment.evidence.manual_review_note = f"Manually mapped from {old_net}"
    assignment.last_seen_revision = current_revision or assignment.last_seen_revision
    _push_undo(store, "import_apply", [new_net], previous)
    store.assignments[new_net] = assignment
    for entry in match_result.entries:
        if entry.new_net == new_net and entry.match_status == "likely_renamed" and entry.old_net == old_net:
            entry.applied = True
            entry.action_required = ""
    return assignment


_MATCH_CSV_COLUMNS = ["old_net", "new_net", "match_status", "match_score", "applied", "action_required", "detail"]


def export_revision_match_csv(match_result: RevisionMatchResult, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_MATCH_CSV_COLUMNS)
        writer.writeheader()
        for e in sorted(match_result.entries, key=lambda x: (x.new_net or "", x.old_net or "", x.match_status)):
            writer.writerow(
                {
                    "old_net": e.old_net or "",
                    "new_net": e.new_net or "",
                    "match_status": e.match_status,
                    "match_score": "" if e.match_score is None else e.match_score,
                    "applied": "true" if e.applied else "false",
                    "action_required": e.action_required,
                    "detail": e.detail,
                }
            )
    return path


_DELTA_CSV_COLUMNS = [
    "delta_type",
    "old_net",
    "new_net",
    "old_class",
    "new_class",
    "old_voltage_v",
    "new_voltage_v",
    "old_review_state",
    "new_review_state",
    "match_score",
    "reason",
    "required_action",
    "notes",
]


def _fmt_voltage(value: float | None) -> str:
    return "" if value is None else f"{value:g}"


def export_revision_delta_csv(
    imported: list[VoltageAssignment],
    store: AssignmentStore,
    match_result: RevisionMatchResult,
    path: Path,
) -> Path:
    """Delta between imported (old revision) and current store (Rev C 11.6)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    imported_by_name = {a.net_name: a for a in imported}
    applied_by_new = {e.new_net: e for e in match_result.entries if e.applied and e.old_net and e.new_net}
    missing_old = {e.old_net: e for e in match_result.entries if e.match_status == "missing" and e.old_net}
    rows: list[dict] = []

    for net, a in sorted(store.assignments.items()):
        if a.review_state == "Obsolete / missing in new revision":
            e = missing_old.get(net)
            old_name, new_name = net, ""
            old = imported_by_name.get(net)
            delta = "deleted"
            required_action = "none"
            reason = "Imported net is missing in current PCB revision"
            score = e.match_score if e else None
        else:
            e = applied_by_new.get(net)
            old_name = e.old_net if e else (net if net in imported_by_name else "")
            new_name = net
            old = imported_by_name.get(old_name) if old_name else None
            score = e.match_score if e else None
            if old is None:
                delta = "added"
                required_action = "review"
                reason = "New current PCB net"
            elif old_name != net:
                delta = "renamed"
                required_action = "review" if a.source != "imported_manual_mapping" else "none"
                reason = f"Imported net {old_name} mapped to current net {net}"
            elif old.final_class != a.final_class:
                delta = "class_changed"
                required_action = "review"
                reason = "Voltage class changed"
            elif old.final_voltage_v != a.final_voltage_v:
                delta = "voltage_changed"
                required_action = "review"
                reason = "Voltage value changed"
            elif a.review_state != old.review_state:
                delta = "review_state_changed"
                required_action = "review" if a.review_state in {"Needs review", "Conflict"} else "none"
                reason = "Review state changed"
            elif a.waiver.waived and not old.waiver.waived:
                delta = "waived"
                required_action = "none"
                reason = "Waiver added"
            else:
                delta = "unchanged"
                required_action = "none"
                reason = "No assignment change"
        rows.append(
            {
                "delta_type": delta,
                "old_net": old_name or "",
                "new_net": new_name or "",
                "old_class": old.final_class if old else "",
                "new_class": "" if a.review_state == "Obsolete / missing in new revision" else a.final_class,
                "old_voltage_v": _fmt_voltage(old.final_voltage_v if old else None),
                "new_voltage_v": "" if a.review_state == "Obsolete / missing in new revision" else _fmt_voltage(a.final_voltage_v),
                "old_review_state": old.review_state if old else "",
                "new_review_state": a.review_state,
                "match_score": "" if score is None else score,
                "reason": reason,
                "required_action": required_action,
                "notes": a.notes,
            }
        )
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_DELTA_CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return path
