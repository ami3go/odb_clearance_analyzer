"""Performance regression tests for addendum 28.1 targets.

Budgets are 2x the spec targets to stay robust on slow CI machines while
still catching order-of-magnitude regressions (the pre-fix matcher was
~170x over budget).
"""

import random
import string
import time

from odb_clearance_analyzer.voltage_guessing import guess_voltage_for_nets, load_rule_pack
from odb_clearance_analyzer.voltage_guessing.models import VoltageAssignment, VoltageEvidence
from odb_clearance_analyzer.voltage_guessing.revision_matcher import match_revision


def _mk(i: int, salt: int = 0) -> str:
    rng = random.Random(i * 7919 + salt)
    return "NET_" + "".join(rng.choices(string.ascii_uppercase, k=8)) + f"_{i}"


def _imported(nets):
    return [
        VoltageAssignment(
            net_name=n, final_class="UNKNOWN", final_voltage_v=None, reference_net="",
            voltage_type="UNKNOWN", confidence="Unknown", severity="Review",
            review_state="Needs review", source="unknown", evidence=VoltageEvidence(),
        )
        for n in nets
    ]


def test_guessing_20k_nets_meets_target():
    pack = load_rule_pack()
    nets = [_mk(i) for i in range(20000)]
    start = time.monotonic()
    guess_voltage_for_nets(nets, pack)
    assert time.monotonic() - start < 4.0  # spec target 2s, 2x budget


def test_matching_20k_nets_with_churn_meets_target():
    pack = load_rule_pack()
    base = [_mk(i) for i in range(20000)]
    new = base[:19000] + [_mk(i, salt=5) for i in range(1000)]
    start = time.monotonic()
    match_revision(_imported(base), new, pack)
    assert time.monotonic() - start < 20.0  # spec target 10s, 2x budget


def test_matching_pathological_all_unmatched_is_bounded():
    pack = load_rule_pack()
    old = [_mk(i) for i in range(500)]
    new = [_mk(i, salt=9) for i in range(500)]
    start = time.monotonic()
    match_revision(_imported(old), new, pack)
    assert time.monotonic() - start < 5.0  # was ~280s before blocking at this size


def test_requirement_resolver_scales_to_20k_nets():
    """Regression: per-pair resolution used to rescan all assignments
    (O(rows x nets)); 20k pairs at 20k nets took minutes. With the
    precomputing resolver it must stay well under a couple of seconds."""
    from odb_clearance_analyzer.voltage_guessing.requirements import VoltageRequirementResolver

    nets = [_mk(i) for i in range(20000)]
    assignments = {
        a.net_name: a for a in _imported(nets)
    }
    rng = random.Random(3)
    pairs = [(rng.choice(nets), rng.choice(nets)) for _ in range(20000)]
    start = time.monotonic()
    resolver = VoltageRequirementResolver(assignments, {"galvanic_zone_voltage_v": 1000.0})
    for a, b in pairs:
        resolver.resolve(a, b)
    assert time.monotonic() - start < 4.0  # 2x budget over a ~2s ceiling


def test_requirement_resolver_matches_one_shot_function():
    from odb_clearance_analyzer.voltage_guessing.requirements import (
        VoltageRequirementResolver,
        resolve_required_spacing_voltage,
    )
    from odb_clearance_analyzer.voltage_guessing.models import VoltageAssignment, VoltageEvidence

    def _a(net, volts, zone=""):
        return VoltageAssignment(
            net_name=net, final_class="LV", final_voltage_v=volts, reference_net="",
            voltage_type="DC", confidence="High", severity="Info",
            review_state="Reviewed", source="manual", evidence=VoltageEvidence(),
            galvanic_zone=zone,
        )

    assignments = {
        "A": _a("A", 10.0, "Zone 1"),
        "B": _a("B", 21.0, "Zone 2"),
        "C": _a("C", 5.0, "Zone 1"),
        "D": _a("D", None),
    }
    settings = {"galvanic_zone_voltage_v": 1200.0}
    resolver = VoltageRequirementResolver(assignments, settings)
    for a, b in [("A", "B"), ("A", "C"), ("A", "D"), ("GND", "A"), ("X", "Y")]:
        assert resolver.resolve(a, b) == resolve_required_spacing_voltage(a, b, assignments, settings)
