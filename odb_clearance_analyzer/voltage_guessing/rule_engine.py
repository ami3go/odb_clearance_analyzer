"""Deterministic net-voltage guessing rule engine."""

from __future__ import annotations

import logging
import re
from dataclasses import replace

from .models import RuleMatchResult, RulePack, VoltageDefaults, VoltageRule
from .normalization import normalize_net_name
from .voltage_parser import parse_voltage_token

logger = logging.getLogger("voltage_guessing")

_LAYER_RANK = {"built-in": 0, "user-global": 1, "project-local": 2, "manual": 3}
_SPECIFICITY_RANK = {"regex": 0, "suffix": 1, "prefix": 1, "token": 2, "exact": 3}


# Perf (addendum 28.1): rule patterns and regexes are normalized/compiled once
# and reused across all nets; the net name is normalized once per guess.
_NORMALIZED_PATTERN_CACHE: dict[str, str] = {}
_COMPILED_REGEX_CACHE: dict[tuple[str, int], "re.Pattern"] = {}


def _normalized_pattern(pattern: str) -> str:
    cached = _NORMALIZED_PATTERN_CACHE.get(pattern)
    if cached is None:
        cached = normalize_net_name(pattern)
        _NORMALIZED_PATTERN_CACHE[pattern] = cached
    return cached


_NEVER_MATCH = re.compile(r"(?!x)x")  # matches nothing


def _compiled_regex(pattern: str, flags: int) -> "re.Pattern":
    """Compile a rule regex defensively.

    Rule packs are user-editable data (e.g. hand-edited project-local
    correction files), so an invalid regex must degrade to "matches
    nothing" with a log line instead of crashing auto-detect (13.1:
    user-data problems are results, not exceptions).
    """
    key = (pattern, flags)
    cached = _COMPILED_REGEX_CACHE.get(key)
    if cached is None:
        try:
            cached = re.compile(pattern, flags)
        except re.error as exc:
            logger.warning("Invalid regex in rule pattern %r ignored: %s", pattern, exc)
            cached = _NEVER_MATCH
        _COMPILED_REGEX_CACHE[key] = cached
    return cached


def _matches(rule: VoltageRule, raw_name: str, norm_name: str, norm_tokens: tuple) -> re.Match | bool | None:
    if rule.match_on == "raw":
        target, pattern = raw_name, rule.pattern
    else:
        target, pattern = norm_name, _normalized_pattern(rule.pattern)
    if rule.match_type == "exact":
        return target == pattern
    if rule.match_type == "token":
        return pattern in (norm_tokens if rule.match_on != "raw" else tuple(t for t in raw_name.split("_") if t))
    if rule.match_type == "prefix":
        return target.startswith(pattern)
    if rule.match_type == "suffix":
        return target.endswith(pattern)
    if rule.match_type == "regex":
        flags = 0 if rule.match_on == "raw" else re.IGNORECASE
        return _compiled_regex(rule.pattern, flags).search(target)
    return None


def _sort_key(rule: VoltageRule) -> tuple[int, int, int, int, str]:
    """Ordering per addendum 13.0 / 14.2: pick min() of this key.

    Layer, priority, specificity, and pattern length are negated so that
    higher values win; rule_id is ascending so the lexicographically
    smallest rule_id wins deterministically on full ties.
    """
    return (
        -_LAYER_RANK.get(rule.source_layer, 0),
        -int(rule.priority),
        -_SPECIFICITY_RANK.get(rule.match_type, 0),
        -len(rule.pattern),
        rule.rule_id,
    )


def _voltage_from_match_group(rule: VoltageRule, match) -> float | None:
    """Parse a regex named group called ``voltage`` if one exists.

    This is required for rules such as NEG12V and DC_LINK_800V where the
    matched regex proves the semantic class/polarity. The free-form rule
    expression field is intentionally not implemented.
    """
    if not hasattr(match, "groupdict") or "voltage" not in match.groupdict():
        return None
    raw = match.group("voltage")
    if raw is None:
        return None
    token = parse_voltage_token(str(raw))
    if token is None:
        return None
    value = token.voltage_v
    if rule.net_class == "POWER_NEGATIVE":
        return -abs(value)
    return value


def _voltage_for_rule(rule: VoltageRule, net_name: str, match, defaults: VoltageDefaults) -> float | None:
    if rule.cell_count_from_pattern:
        cells = None
        if hasattr(match, "groupdict") and "cells" in match.groupdict():
            cells = match.group("cells")
        elif hasattr(match, "groups") and match.groups():
            cells = match.group(1)
        try:
            cell_count = int(cells)
            if cell_count <= 0:
                return None
            return cell_count * float(rule.volts_per_cell or defaults.battery_volts_per_cell_max)
        except Exception:
            return None
    if rule.voltage_v is not None:
        return -abs(rule.voltage_v) if rule.net_class == "POWER_NEGATIVE" else rule.voltage_v
    # Regex-derived voltage group.
    grouped_voltage = _voltage_from_match_group(rule, match)
    if grouped_voltage is not None:
        return grouped_voltage
    # Default-driven class behavior.
    if rule.net_class == "IO_DIGITAL":
        return defaults.logic_io_v
    if rule.net_class == "IO_ANALOG":
        return defaults.analog_io_v
    if rule.net_class == "POWER_VARIABLE":
        return defaults.usb_pd_max_v
    if rule.net_class == "POWER_HIGHER_LOW_VOLTAGE":
        return defaults.poe_voltage_v
    if rule.net_class == "MAINS":
        return defaults.mains_rms_v
    # Explicit voltage token if present.
    token = parse_voltage_token(net_name)
    if token is not None:
        return -abs(token.voltage_v) if rule.net_class == "POWER_NEGATIVE" else token.voltage_v
    return None


def guess_net_voltage(net_name: str, rule_pack: RulePack, defaults: VoltageDefaults | None = None) -> RuleMatchResult:
    defaults = defaults or rule_pack.defaults
    raw_name = str(net_name)
    try:
        norm_name = normalize_net_name(raw_name)
    except ValueError as exc:
        # Defensive: ODB++ data occasionally contains garbage names. One bad
        # net must not abort auto-detect for the entire board (13.1).
        logger.warning("Net %r rejected by normalization: %s", raw_name, exc)
        return RuleMatchResult(
            net_name=raw_name,
            guessed_class="UNKNOWN",
            guessed_voltage_v=None,
            reference_net="",
            voltage_type="UNKNOWN",
            confidence="Unknown",
            severity="Review",
            winning_rule_id="",
            all_matched_rule_ids=[],
            reason="Net name could not be normalized (control/format characters); review manually.",
            warning=str(exc),
        )
    norm_tokens = tuple(token for token in norm_name.split("_") if token)
    matched: list[tuple[VoltageRule, re.Match | bool]] = []
    for rule in rule_pack.rules:
        if not rule.enabled:
            continue
        match = _matches(rule, raw_name, norm_name, norm_tokens)
        if match:
            matched.append((rule, match))
    if not matched:
        return RuleMatchResult(
            net_name=net_name,
            guessed_class="UNKNOWN",
            guessed_voltage_v=None,
            reference_net="",
            voltage_type="UNKNOWN",
            confidence="Unknown",
            severity=defaults.unknown_severity,
            winning_rule_id=None,
            all_matched_rule_ids=[],
            reason="No deterministic net-name rule matched.",
            warning="Review voltage manually.",
        )
    ordered = sorted(matched, key=lambda pair: _sort_key(pair[0]))
    winning_rule, winning_match = ordered[0]
    tie_warning = ""
    if len(ordered) > 1 and _sort_key(ordered[0][0])[:4] == _sort_key(ordered[1][0])[:4]:
        tie_warning = (
            f" Priority conflict: rules {ordered[0][0].rule_id!r} and {ordered[1][0].rule_id!r} "
            "tie on layer/priority/specificity/length; smallest rule_id won."
        )
    voltage = _voltage_for_rule(winning_rule, net_name, winning_match, defaults)
    net_class = winning_rule.net_class
    if net_class == "POWER" and voltage is not None and voltage < 0:
        net_class = "POWER_NEGATIVE"
    return RuleMatchResult(
        net_name=net_name,
        guessed_class=net_class,
        guessed_voltage_v=voltage,
        reference_net=winning_rule.reference_net,
        voltage_type=winning_rule.voltage_type,
        confidence=winning_rule.confidence,
        severity=winning_rule.severity,
        winning_rule_id=winning_rule.rule_id,
        all_matched_rule_ids=[rule.rule_id for rule, _ in matched],
        reason=winning_rule.reason,
        warning=(winning_rule.warning + tie_warning).strip(),
        matched_pattern=winning_rule.pattern,
        matched_rule_pack=str(rule_pack.manifest.get("pack_name", "")),
        matched_rule_file=winning_rule.source_file,
    )


def guess_voltage_for_nets(net_names: list[str], rule_pack: RulePack, defaults: VoltageDefaults | None = None, *, source_revision: str = ""):
    return [guess_net_voltage(name, rule_pack, defaults).to_assignment(source_revision=source_revision) for name in sorted(set(net_names))]
