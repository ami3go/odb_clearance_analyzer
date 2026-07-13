# Voltage Guessing — Phase 4 review fixes (v0.4.20)

Fixes the three must-fix findings from the Phase 4 review of v0.4.19.

## 1. Performance regression repaired (v0.4.19 had branched from v0.4.17)
Re-applied the v0.4.18 optimizations onto the Phase 4 code without
losing v0.4.19's additions (regex voltage groups, extended delta CSV):
- rule_engine: pattern-normalization and compiled-regex module caches;
  net name normalized once per guess. Measured: 20,000 nets 0.7s
  (was ~9s; target <=2s).
- revision_matcher: _NetFeatures per-net cache + lossless candidate
  blocking (shared token / equal voltage / same class, heapq cap 20).
  Measured: 300x300 all-unmatched 0.3s (was ~102s).
- test_voltage_guessing_performance.py and the v0.4.18 perf doc
  restored so this cannot silently regress again.

## 2. Correction-to-rule now actually affects guessing (gate 3)
- rule_loader.load_layered_rule_pack(): built-in pack + every rule
  file in the project rule directory loaded as source_layer
  "project-local" (wins per 13.0 precedence). No manifest needed.
- GUI _current_voltage_rule_pack() uses layered loading, caches per
  rule directory, and is invalidated immediately after a correction
  rule is written; the log line reports active project-local rules.
- The rule sandbox therefore evaluates correction rules too.
- New end-to-end test: create correction rule -> layered pack ->
  VSYS_SNS guesses POWER 3.8 V via user_correction rule, while the
  built-in-only pack does not.

## 3. Viewer -> assignment reverse jump (gate 11 second direction)
- GeometryViewer accepts on_show_voltage_assignment callback and shows
  a "Voltage assignment" button; it jumps using Net A (or Net B).
- gui passes the callback at all GeometryViewer call sites; the
  handler switches to Voltage Guessing -> All Assignments, selects and
  reveals the net row, and populates the selected-net editor.

## Minor
- Keyboard shortcut legend now visible in the Review Needed tab
  (spec 28.2.3).

Tests: 65 passed (64 prior + correction-rule end-to-end).
