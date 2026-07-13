"""Validation for deterministic voltage rule packs.

Also executes the pack's own test CSV (net_voltage_rule_tests.csv) so a
rule pack cannot validate unless its behavioral self-tests pass
(Rev C 29.4 / addendum Phase 1 gate).
"""

from __future__ import annotations

import csv
import re

from .enums import CONFIDENCE_VALUES, MATCH_ON_VALUES, MATCH_TYPES, NET_CLASSES, SEVERITY_VALUES
from .models import RulePack, ValidationIssue, ValidationResult


def _run_rule_pack_tests(rule_pack: RulePack, issues: list[ValidationIssue]) -> tuple[int, int]:
    """Execute the pack test CSV. Columns: net_name, expected_class,
    expected_voltage_v (empty = must be None/any), expected_confidence (optional)."""
    from .rule_engine import guess_net_voltage  # local import: avoid cycle

    if rule_pack.tests_path is None:
        issues.append(ValidationIssue("warning", "", "", "Rule pack has no test CSV (net_voltage_rule_tests.csv)"))
        return (0, 0)
    run = failed = 0
    with rule_pack.tests_path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            net = str(row.get("net_name", "")).strip()
            if not net:
                continue
            run += 1
            result = guess_net_voltage(net, rule_pack)
            problems: list[str] = []
            expected_class = str(row.get("expected_class", "")).strip()
            if expected_class and result.guessed_class != expected_class:
                problems.append(f"class {result.guessed_class!r} != expected {expected_class!r}")
            expected_v = str(row.get("expected_voltage_v", "")).strip()
            if expected_v:
                if result.guessed_voltage_v is None or abs(result.guessed_voltage_v - float(expected_v)) > 1e-9:
                    problems.append(f"voltage {result.guessed_voltage_v!r} != expected {expected_v}")
            elif "expected_voltage_v" in row and row.get("expected_voltage_v") == "" and str(row.get("voltage_must_be_empty", "")).strip().lower() == "true":
                if result.guessed_voltage_v is not None:
                    problems.append(f"voltage {result.guessed_voltage_v!r} != expected empty")
            expected_conf = str(row.get("expected_confidence", "")).strip()
            if expected_conf and result.confidence != expected_conf:
                problems.append(f"confidence {result.confidence!r} != expected {expected_conf!r}")
            expected_sev = str(row.get("expected_severity", "")).strip()
            if expected_sev and result.severity != expected_sev:
                problems.append(f"severity {result.severity!r} != expected {expected_sev!r}")
            expected_state = str(row.get("expected_review_state", "")).strip()
            if expected_state and result.to_assignment().review_state != expected_state:
                problems.append(f"review_state {result.to_assignment().review_state!r} != expected {expected_state!r}")
            if problems:
                failed += 1
                issues.append(ValidationIssue("error", result.winning_rule_id or "", rule_pack.tests_path.name, f"Test {net!r}: " + "; ".join(problems)))
    return (run, failed)


def validate_rule_pack(rule_pack: RulePack) -> ValidationResult:
    issues: list[ValidationIssue] = []
    for name in rule_pack.missing_files:
        issues.append(ValidationIssue("error", "", "manifest.json", f"File listed in manifest is missing: {name}"))
    for name in rule_pack.unlisted_files:
        issues.append(ValidationIssue("warning", "", "manifest.json", f"File present but not listed in manifest: {name}"))
    seen: set[str] = set()
    for rule in rule_pack.rules:
        src = rule.source_file
        for parse_issue in getattr(rule, "parse_issues", []) or []:
            issues.append(ValidationIssue("error", rule.rule_id, src, parse_issue))
        if not rule.rule_id:
            issues.append(ValidationIssue("error", rule.rule_id, src, "Missing rule_id"))
        elif rule.rule_id in seen:
            issues.append(ValidationIssue("error", rule.rule_id, src, "Duplicate rule_id"))
        seen.add(rule.rule_id)
        if not rule.pattern:
            issues.append(ValidationIssue("error", rule.rule_id, src, "Missing pattern"))
        if rule.match_type not in MATCH_TYPES:
            issues.append(ValidationIssue("error", rule.rule_id, src, f"Invalid match_type {rule.match_type!r}"))
        if rule.match_on not in MATCH_ON_VALUES:
            issues.append(ValidationIssue("error", rule.rule_id, src, f"Invalid match_on {rule.match_on!r}"))
        if rule.net_class not in NET_CLASSES:
            issues.append(ValidationIssue("error", rule.rule_id, src, f"Invalid net_class {rule.net_class!r}"))
        if rule.confidence not in CONFIDENCE_VALUES:
            issues.append(ValidationIssue("error", rule.rule_id, src, f"Invalid confidence {rule.confidence!r}"))
        if rule.severity not in SEVERITY_VALUES:
            issues.append(ValidationIssue("error", rule.rule_id, src, f"Invalid severity {rule.severity!r}"))
        if rule.match_type == "regex":
            try:
                re.compile(rule.pattern)
            except re.error as exc:
                issues.append(ValidationIssue("error", rule.rule_id, src, f"Invalid regex: {exc}"))
        if rule.match_type not in {"exact", "token"} and len(rule.pattern) == 1:
            issues.append(ValidationIssue("warning", rule.rule_id, src, "Single-character patterns should use exact/token matching"))
    run, failed = _run_rule_pack_tests(rule_pack, issues)
    return ValidationResult(
        ok=not any(issue.level == "error" for issue in issues),
        issues=issues,
        test_cases_run=run,
        test_cases_failed=failed,
    )
