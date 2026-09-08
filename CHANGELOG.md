# Changelog — ODB++ Clearance Analyzer

All notable changes to the Voltage Guessing subsystem and related tooling.

## 0.4.37 — 2026-07-21

- Fixed voltage assignment CSV import for exported report tables that use `assigned_voltage_v` instead of `final_voltage_v`.
- Importer now accepts voltage columns in this order: `final_voltage_v`, `assigned_voltage_v`, `guessed_voltage_v`, `voltage_v`.
- Project assignment store JSON files with `file_kind: net_voltage_assignment_store` can now be imported as assignment sources; review session and undo history are ignored.
- Added regression tests using the report-style CSV alias and project-store JSON import path.

## 0.4.36 — 2026-07-21

- Fixed All Assignments table disappearing after geometry navigation / re-analysis workflows.
- Analysis-result clearing now preserves the voltage assignment table because assignments are a separate review artifact.
- Analysis completion now refreshes all voltage views, including All Assignments, review queue, and overview.
- Added GUI regression coverage for preserving All Assignments rows across `_clear_views()` and analysis-result refresh.


## 0.4.35 — 2026-07-17

### Fixed
- **Data-loss fix:** Applying **Apply zone-to-zone voltage** (or any settings-only save) with a fresh GUI no longer atomically replaces an existing, not-yet-loaded `net_voltage_assignments.json` in the selected output folder with the empty in-memory store. The existing store is loaded and merged first; a store that exists but cannot be read is never overwritten (an error dialog is shown instead). The value the user just entered wins over the stale on-disk setting.
- Bumped the lagging `REPORT_SETTINGS_APP_VERSION` (was still 0.4.33).

### Performance
- Added `VoltageRequirementResolver`, which precomputes the zone-enabled flag and inter-zone voltage once and memoizes per-pair results. Per-row resolution previously rescanned every assignment (O(rows × nets)); at the 20k-net performance target a 50k-row export spent ~2 minutes per pass in the resolver alone, ~4 passes per report package. Measured after: 0.37 s first pass, ~0.01 s per repeated pass.
- Reports (CSV, Markdown, Excel), `galvanic_zone_spacing.csv`, the hierarchy summary, and the GUI result tables now share one resolver per snapshot.
- `resolve_required_spacing_voltage` is unchanged in signature and behavior and remains available for one-shot callers.

### Tests
- Added GUI regression tests: existing assignments survive applying the zone voltage before the store is loaded; an unreadable store is not overwritten.
- Added resolver performance budget (20k pairs @ 20k nets < 4 s) and a resolver-vs-one-shot equivalence test. Test suite: 99 passed under Xvfb.

### Packaging
- Cleaned release ZIP metadata/cache files.
- Corrected README GUI launch command to `odb-clearance-gui`.

## 0.4.34 — 2026-07-16

- Added explicit **Apply zone-to-zone voltage** controls in Voltage Guessing Overview and All Assignments.
- The setting is validated as a positive finite voltage before use.
- The setting is saved to the project assignment JSON even before any net assignments exist.
- Voltage Guessing settings now export both `galvanic_zone_voltage_v` and clearer alias `zone_to_zone_voltage_v`.
- The hierarchy remains unchanged: Zone 1 ↔ Zone 2 pairs use the configured zone-to-zone voltage; same-zone pairs use the net-to-net voltage difference.
- Added GUI smoke coverage for persisting the zone-to-zone voltage setting before assignments are created.

## 0.4.33 — 2026-07-16

### Fixed
- Same-zone and incomplete-zone net-pair voltage now uses the actual pair difference `abs(net_a_voltage_v - net_b_voltage_v)` instead of the previous conservative absolute maximum of individual net voltages.
- Examples: 10 V ↔ 21 V reports 11 V; 10 V ↔ 0 V/GND reports 10 V.
- Added fallback recognition for common ground/0 V net names when no explicit ground assignment row exists.

### Notes
- Cross-zone galvanic hierarchy is unchanged: different Zone 1/Zone 2 nets still use the configured zone working voltage as `required_voltage_v`.
- For cross-zone pairs, `voltage_difference_v` remains available as diagnostic pair voltage difference, while OK/NOK uses the hierarchy-resolved `required_voltage_v`.


## 0.4.32 — 2026-07-15

### Added
- Added explicit `standard_voltage_status` OK/NOK/UNKNOWN columns to main clearance CSV exports, the effective air-gap matrix CSV, Excel report sheets, Markdown tables, and GUI result tables.
- Added `voltage_margin_v`, calculated as `effective_max_voltage_v - required_voltage_v`.
- Added the same OK/NOK information to `galvanic_zone_spacing.csv` while preserving the previous PASS/FAIL/UNKNOWN `status` column for compatibility.

### Notes
- `OK` means the actual/hierarchy-resolved required voltage is less than or equal to the maximum voltage calculated from the measured spacing and active standard settings.
- `NOK` means the required voltage is higher than the calculated supported voltage.


## 0.4.31 — 2026-07-15

### Added
- Report package now exports all voltage assignments to `net_voltage_assignments.csv`.
- Excel report now includes an `Assigned voltages` worksheet.
- Markdown report now includes an `Assigned Voltages` preview section.
- Net-to-net measurement, critical, per-net, effective air-gap, and galvanic-zone CSV exports now include `voltage_difference_v`.
- GUI clearance/effective tables now show a `Voltage difference V` column.

### Notes
- `voltage_difference_v` is calculated as `abs(Net A assigned voltage - Net B assigned voltage)` when both assigned voltages are known.
- Final clearance screening should continue to use `required_voltage_v`, because the voltage hierarchy can intentionally prioritize Zone 1 ↔ Zone 2 voltage over local voltage difference.

## 0.4.30 — 2026-07-15

### Fixed
- Fixed Geometry Viewer construction crash caused by the **Voltage assignment** button referencing a callback method that was accidentally placed on `GeometryViewerLauncherMixin` instead of `GeometryViewer`.
- This also prevents secondary `canvas` attribute errors, which were a cascade after viewer construction aborted before creating the canvas.

### Tests
- Added a Tk smoke regression test that constructs `GeometryViewer` with `on_show_voltage_assignment` enabled and verifies the jump callback works.
- Test suite: 87 passed, 4 skipped normally; 91 passed under Xvfb.

## 0.4.29 — 2026-07-14

- Added central Voltage Requirement Hierarchy resolver for spacing rows.
- Cross-zone Zone 1 ↔ Zone 2 pairs now use the configured working voltage before local net/class voltage.
- Same-zone and incomplete-zone pairs use conservative local net/manual/class voltage.
- Added voltage-source, required-voltage, zone, local-voltage, net-voltage, and warning columns to main spacing CSV/Excel/Markdown reports.
- Updated galvanic_zone_spacing.csv to use the same central resolver.
- Added safe All Assignments actions: Apply galvanic zone only and Clear galvanic zone without overwriting class/voltage/review/notes.
- Added hierarchy summary data and GUI/report explanation text.
- Added resolver, report-export, and zone-only bulk-edit regression tests.

## 0.4.28 — 2026-07-14
### Added
- Voltage Guessing now supports two galvanic zones: `Zone 1` and `Zone 2`.
- Added a configurable **Zone 1 ↔ Zone 2 voltage, V** field with default `1000 V`.
- The All Assignments bulk editor can apply a galvanic zone to one or many selected nets using Shift/Ctrl multi-select.
- Assignment store JSON, assignment export JSON/CSV, CSV import, and settings profile JSON now preserve galvanic-zone data and the inter-zone voltage setting.
- Added `galvanic_zone_spacing.csv` export: every measured Zone 1 ↔ Zone 2 net pair is checked against the configured inter-zone voltage using the existing IEC-style effective max voltage estimate.
### Tests
- Added regression coverage for zone normalization, bulk zone edit/undo, store/export/import persistence, and Zone 1 ↔ Zone 2 spacing report generation. Test suite: 79 passed, 3 skipped.

## 0.4.27 — 2026-07-13
### Added
- Voltage Guessing net-name rules now ignore trailing `+` / `-` polarity markers before matching normalized rules. Example: `stack_cell10+` is treated as `STACK_CELL10`.
- Added explicit `Cell0` / `STACK_CELL0` rule: battery-stack zero reference is assigned as `GND`, `0 V`, approved.
- Added NTC mask rule: nets containing an `NTC` token, including indexed forms such as `BMIC_NTC3+` and `BMIC_PCB_NTC1+`, are assigned as `IO_ANALOG`, `5.5 V max`, needs review.
### Tests
- Added regression coverage and rule-pack self-test rows for trailing polarity markers, `Cell0`, and BMIC NTC examples.

## 0.4.26 — 2026-07-13
### Added
- Voltage Guessing now has a user-editable **Max cell voltage, V** field on the Overview tab. Default is 4.3 V/cell.
- Added deterministic `Cell<number>` / `Cell_<number>` cumulative battery-node rule. Example: `Cell3` is assigned `3 × Max cell voltage`.
- The same max-cell-voltage setting is exported/imported with settings profiles and stored in the voltage assignment project store JSON.
### Changed
- Existing `BAT_4S` style cell-count rules now use the same configurable max-cell-voltage value; built-in default changed from 4.2 V/cell to 4.3 V/cell.
### Tests
- Added regression coverage for Cell<number> guessing, custom max-cell-voltage defaults, settings-profile roundtrip, and assignment-store persistence. Test suite: 74 passed, 3 skipped.

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
