# Voltage Guessing — Phase 2 (v0.4.16)

Implements addendum Phase 2 (Review State and Assignment Store) plus the
three Phase 1 gate fixes identified in review.

## Phase 1 fixes
- Rule-pack self-tests (net_voltage_rule_tests.csv) are now executed by
  validate_rule_pack; test CSV expanded to 21 behavioral cases including
  all false-positive guards (L1_SW, N_FET_G, M2_CS, CH4).
- Rule reason and warning are persisted into VoltageAssignment.evidence
  (rule_reason / rule_warning) and appear in net_voltage_guessing.csv.
- Export JSON is now a snapshot (file_kind=net_voltage_assignment_export,
  name net_voltage_assignments_<revision>.json, no session/undo data) and
  is rejected when opened as a project store. The project store remains
  net_voltage_assignments.json.
- Manifest bookkeeping: files listed but missing = validation error;
  files present but unlisted = warning.
- Rule tie-break fixed: lexicographically smallest rule_id wins; full
  ties append a "Priority conflict" warning to the result.

## Phase 2 features (addendum 4.1)
- review_service module: run_auto_detect (merge + preserve manual and
  imported values), apply_manual_override, approve, accept_unknown,
  waive (scope-validated, reason required), review_queue, undo_last,
  review_gate_status. GUI callbacks are thin wrappers (rule 8.1.6).
- Persistent store: loaded automatically when ODB++ metadata is read or
  analysis finishes and net_voltage_assignments.json exists in the
  output folder; saved atomically after every state change.
- Undo: bounded stack (depth 20), one entry per operation, persisted in
  the store, survives restart. Auto-detect, manual edits, and review
  actions are all undoable.
- Review Needed queue tab: multi-select approve / accept unknown /
  waive with scope selector, severity-sorted, Critical first, colored
  rows; waived items leave the queue but remain in All Assignments with
  their waiver reason shown.
- Review gate: allow / warn / block (default warn) selectable on the
  Overview tab and via CLI --voltage-gate-mode. warn logs the stamp
  text; block refuses voltage export while unreviewed Critical items
  exist (CLI exit code 2 with machine-readable VOLTAGE_GATE stderr
  lines).

## Tests
tests/voltage_guessing/test_voltage_guessing_phase2.py — 11 tests
covering the Phase 2 completion gate: store restart survival, manual
override preservation, undo of auto-detect, queue membership, waiver
visibility, gate modes, snapshot rejection, self-test execution, and
reason/warning persistence. Full suite: 36 passed.
