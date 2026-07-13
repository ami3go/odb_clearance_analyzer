# Voltage Guessing — Phase 3 (v0.4.17)

Implements addendum Phase 3 (Revision Import and Matching), all 12 tasks.

## New modules
- assignment_import.py: imports .json export snapshots (and project
  stores, ignoring session/undo) and interchange .csv files. Full
  9.1.1 error handling: invalid JSON with line number, newer schema
  rejection with migration hook for older versions, missing CSV
  columns, duplicate net names (whole-file reject), per-row skips for
  invalid class/confidence/severity/state and non-numeric voltages.
  Returns AssignmentImportResult; never raises for content problems.
- revision_matcher.py: deterministic matching pipeline —
  exact → case-insensitive → normalized → likely-renamed suggestions →
  conflict / new / missing. match_score implements addendum 11.1
  exactly (frozen weights 0.40/0.20/0.15/0.15/0.10, threshold 60,
  top-3 candidates, lexicographic tie-break). Fingerprint prefixes are
  accepted via an optional component_prefixes dict and degrade to
  name-only scoring when absent (11.2 degraded mode, max score 90).
  apply_safe_matches applies only exact/ci/normalized + rule-guesses
  new nets + preserves missing nets as "Obsolete / missing in new
  revision"; suggestions and conflicts are never auto-applied.
  apply_manual_mapping confirms an old→new rename. Waiver carry-forward
  per Rev C Section 22: project_global always, this_net_until_changed
  while values unchanged, current_revision_only never.

## Exports
- net_voltage_assignment_revision_match.csv (match table)
- net_voltage_assignment_revision_delta.csv (added/deleted/renamed/
  class_changed/voltage_changed/waived/unchanged)

## GUI
Revision Import tab: file browse, "Match against current nets" preview
(nothing applied), "Apply safe matches", "Apply selected suggestion"
for likely-renamed rows, "Undo last import", colored rows (conflicts
red, suggestions yellow, applied green), summary line with counts.
Revision CSVs are written to the output folder on every apply.

## CLI
--import-voltage-assignments FILE combined with --voltage-guess runs
import → match → apply-safe → export match/delta CSVs headlessly.
Exit codes: 5 = import rejected, 4 = conflicts require review,
2 = gate block; lowest applicable code wins (Rev C 27 precedence).
The assignment store is now also persisted from the CLI.

## Golden fixture (addendum 29.2.1)
tests/fixtures/{rev_a_assignments.json, rev_b_netlist.txt,
expected_match_table.csv}: 25 Rev A assignments (approvals, one manual
value, project_global + current_revision_only waivers) against 25 Rev B
nets covering exact, case change, separator change, likely rename,
adds, deletes, and one normalized-name conflict. The golden test runs
the full import → match → apply pipeline and compares the produced
match table byte-for-byte against the frozen CSV.

## Tests
test_voltage_guessing_phase3.py — 16 tests. Full suite: 52 passed.
