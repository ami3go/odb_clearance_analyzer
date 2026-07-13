# Voltage Guessing — Performance (v0.4.18)

Fixes the matcher performance issue found in the Phase 3 review and
meets both addendum 28.1 targets.

## Changes
1. revision_matcher: per-net feature cache (_NetFeatures — normalized
   name, tokens, voltage token, detected class computed once per net,
   not once per pair) and candidate blocking per 28.1: candidates share
   a token, an equal voltage value, or the same detected class; capped
   at 20 via heapq.nsmallest with deterministic tie-break.
   Blocking is provably lossless at the default threshold: a pair with
   no shared blocking key scores at most 40 + 7.5 + 10 = 57.5 < 60.
2. rule_engine: net name normalized once per guess (was: per rule);
   rule patterns normalized once ever (module cache); regexes compiled
   once ever (module cache).

## Measured (this container)
- guess 20,000 nets:            9.23s -> 0.68s   (target <= 2s)
- match 20,000 nets, 5% churn:  3.12s -> 1.94s   (target <= 10s)
- match 300x300 all-unmatched:  102s  -> 0.30s   (340x)
- match 2000x2000 all-unmatched: n/a  -> 3.71s   (pathological case)

## Behavior
Unchanged: full suite 55/55 including the byte-for-byte golden fixture.
New: test_voltage_guessing_performance.py locks in the budgets at 2x
spec targets so regressions fail CI.
