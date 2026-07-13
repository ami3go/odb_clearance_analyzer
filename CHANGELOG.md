# Changelog — ODB++ Clearance Analyzer

All notable changes to the Voltage Guessing subsystem and related tooling.

## 0.4.25 — 2026-07-04
### Added
- All Assignments table now supports explicit extended multi-selection for bulk manual edits. Use Shift/Ctrl to select multiple nets, set Class/Voltage/Review/Notes once, and apply the same manual rule to every selected net.
- Bulk manual edits are recorded as one undoable review operation (`manual_bulk_edit`) instead of many independent single-net edits.
### Fixed
- Details panel now shows a selected-count preview for multi-selection and guards against accidentally applying unresolved mixed Class/Voltage/Review values.
- "Learn from my fix" now requires one seed assignment when the table has multiple selected rows.
### Tests
- Added regression coverage for bulk manual override service behavior and GUI extended-selection workflow. Test suite: 71 passed, 3 skipped.

## 0.4.24 — 2026-07-04
### Fixed
- Voltage Guessing Auto-detect no longer shows “Read ODB++ metadata or run analysis first” after a completed analysis when `job.named_nets` is empty or stale.
- GUI net discovery now falls back to analyzed geometry, per-net minimum records, measurements, critical measurements, `nets_by_number`, and `feature_net_map`, while still excluding the ODB++ `$NONE$` placeholder.
### Tests
- Added regression coverage for completed-analysis net discovery fallback. Test suite: 70 passed, 2 skipped.

## 0.4.23 — 2026-07-04
### Fixed
- **GUI startup crash** (`TclError: cannot use geometry manager grid ...
  which already has slaves managed by pack`): `_make_card` packs its title
  labels into the card frame, and `_create_voltage_assignments_view`
  gridded the net-editor widgets into that same frame. The editor now
  grids into a packed body frame inside the card. A code scan confirmed
  this was the only card with gridded children.
### Added
- `tests/voltage_guessing/test_gui_smoke.py`: constructs the full
  ClearanceGui, selects every notebook tab, and populates the voltage
  views with data — under Xvfb in headless CI, auto-skipping when no
  display exists. GUI-construction errors of this class now fail tests
  instead of shipping.


## 0.4.22 — 2026-07-04
### Documentation
- API reference regenerated from live source signatures
  (`docs/voltage_guessing_api_reference_v0.4.22.md`).
- Voltage guessing user manual updated with v0.4.21 robustness notes.
- README: Voltage Guessing feature summary, CLI examples, version notes.
- This changelog introduced.

## 0.4.21 — 2026-07-04
### Fixed (crash hardening)
- Invalid regex in user-editable rule files (e.g. project-local corrections)
  degrades to a never-matching pattern with one logged warning instead of
  crashing auto-detect.
- A net name containing control/format characters yields an explicit
  `UNKNOWN / Needs review` assignment instead of aborting guessing for the
  entire board.
- Corrupt assignment-store files whose top level is not a JSON object raise
  `ValueError` (GUI-catchable) instead of `AttributeError` on project open.
- Added `normalize_net_name_safe` / `net_tokens_safe`; exports, similar-net
  suggestions, correction rule-id derivation, and revision matching now use
  the tolerant variant so fallback nets flow through the whole pipeline.
### Tests
- 4 crash-hardening regression tests (69 total).

## 0.4.20 — 2026-07-04
### Fixed (Phase 4 review findings)
- Restored v0.4.18 performance work dropped by the Phase 4 branch:
  rule-engine pattern/regex caches, matcher per-net feature cache and
  lossless candidate blocking, performance regression tests.
  Measured: 20k nets guessed in 0.6 s; 300x300 unmatched match in 0.3 s.
- Correction-to-rule rules are now loaded back via layered rule packs
  (`rule_loader.load_layered_rule_pack`) with cache invalidation; verified by
  an end-to-end test.
- Geometry Viewer -> assignment reverse jump added (both directions of
  Phase 4 gate 11 now work).
### Added
- Visible keyboard-shortcut legend in Review Needed (spec 28.2.3).

## 0.4.19 — Phase 4 (Advanced UX)
- Batch review actions with mandatory dry-run previews; bulk approve blocks
  Warning and Critical severities.
- Keyboard-first review queue: A/U/W/E/S plus arrow navigation.
- Inline "Why?" explainability: winning rule, losing rules, precedence,
  import provenance, waiver details.
- Correction-to-rule workflow with similar-net suggestions.
- Rule sandbox; assignment diff viewer; copyable review summary.
- Persistent review sessions (queue position, filter, skipped nets).
- Regex rules may derive voltage from a named `voltage` group.

## 0.4.18 — Performance
- Rule engine: per-guess normalization; module-level caches for normalized
  patterns and compiled regexes.
- Revision matcher: `_NetFeatures` per-net cache; candidate blocking by
  shared token / equal voltage / same class (provably lossless at the
  default threshold 60); heap-capped candidate sets.
- Meets addendum 28.1 targets: guess 20k nets <= 2 s; match 20k <= 10 s.

## 0.4.17 — Phase 3 (Revision import and matching)
- `assignment_import`: JSON/CSV import with full 9.1.1 error handling
  (reject vs skip+report; schema migration hook; newer-schema rejection).
- `revision_matcher`: exact -> case-insensitive -> normalized ->
  likely-renamed (frozen 11.1 score, threshold 60, top-3) -> conflict /
  new / missing; safe-match apply; manual mapping; waiver carry-forward
  per Rev C 22; match + delta CSV exports.
- Golden end-to-end fixture compared byte-for-byte (addendum 29.2.1).
- CLI: `--import-voltage-assignments` with exit codes 5/4.

## 0.4.16 — Phase 2 (Review state and assignment store)
- `review_service`: auto-detect merge preserving manual/imported values,
  manual override, approve / accept-unknown / waive (scoped), review queue,
  bounded persistent undo (depth 20), review gate (allow/warn/block).
- Store restored automatically on project reopen; atomic writes.
- Export snapshot separated from the project store (distinct file_kind;
  store loader rejects snapshots).
- Rule-pack behavioral self-tests executed by the validator (21 cases).
- Rule precedence tie-break fixed (lexicographically smallest rule_id wins;
  ties emit a priority-conflict warning).
- CLI: `--voltage-gate-mode` with exit code 2 and `VOLTAGE_GATE:` stderr.

## 0.4.15 — Phase 1 (Core engine, MVP)
- Deterministic guessing engine, built-in rule pack, Rev C 9.5
  normalization, numeric voltage token parser with false-positive guards
  (GPIO12, ADC_IN1, M2_CS, L1_SW...), Voltage Guessing GUI tab, manual
  overrides, JSON/CSV exports, `--voltage-guess` /
  `--validate-voltage-rule-pack` CLI flags. No LLM or AI backend.
