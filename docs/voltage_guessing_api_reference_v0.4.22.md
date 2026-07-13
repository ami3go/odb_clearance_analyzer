# Voltage Guessing — API Reference (v0.4.22)

Generated from live source signatures on 2026-07-04.
Package: `odb_clearance_analyzer.voltage_guessing`

All services are plain Python with no Tk imports; the GUI is a thin caller per addendum 8.1.
User-data problems return result objects or degrade with a logged warning; only OS-level I/O raises (`OSError`) and programming errors raise (13.1).

## `normalization` — Net-name normalization (Rev C 9.5)

Single deterministic net-name normalization implementation.

### `net_tokens(net_name: 'str') -> 'list[str]'`
*(no docstring)*

### `net_tokens_safe(net_name: 'str') -> 'list[str]'`
*(no docstring)*

### `normalize_net_name(net_name: 'str', options: 'NormalizeOptions | None' = None) -> 'str'`
Normalize one net name using the Rev C 9.5 algorithm.

Steps: Unicode NFKC, reject control chars, uppercase, replace common
separators with ``_``, collapse repeated underscores, strip underscores,
optionally remove a leading plus sign.

### `normalize_net_name_safe(net_name: 'str', options: 'NormalizeOptions | None' = None) -> 'str'`
Tolerant normalization for downstream consumers.

Identical to normalize_net_name except control/format characters are
stripped instead of raising. The strict variant remains the guessing
engine's contract (a rejected name produces an explicit UNKNOWN
fallback assignment); this variant lets exports, similarity
suggestions, and revision matching keep working on such nets.

---

## `voltage_parser` — Numeric voltage token parser (Rev C 15)

Deterministic numeric voltage token parser.

### `parse_voltage_token(net_name: 'str') -> 'VoltageToken | None'`
Return the first explicit voltage token, avoiding index numbers.

Digits in GPIO12, ADC_IN1, UART2_TX, CH4, M2_CS and N1 are not voltage
values because they are not attached to an explicit V marker. HV400 is
accepted as a special high-voltage shorthand requested by the spec.

---

## `rule_loader` — Rule pack loading and layering (Rev C 13)

Rule-pack loading for deterministic voltage guessing.

### `builtin_rule_pack_path() -> 'Path'`
*(no docstring)*

### `load_layered_rule_pack(project_rule_dir: 'Path | None' = None) -> 'RulePack'`
Load the built-in pack plus optional project-local correction rules.

Project-local rules (Rev C Section 13 layering) load with
source_layer="project-local" so they win over built-in rules per the
13.0 precedence ordering. The project directory needs no manifest:
every *.csv / *.json rule file in it loads in sorted filename order.

### `load_rule_pack(path: 'Path | None' = None, *, source_layer: 'str' = 'built-in') -> 'RulePack'`
Load a rule pack folder. If *path* is None, load the built-in pack.

**Constants:** `PACKAGE_RULE_DIR` = `'data/net_voltage_rules'`

---

## `rule_validation` — Rule pack validation + self-tests (Rev C 29.4)

Validation for deterministic voltage rule packs.

Also executes the pack's own test CSV (net_voltage_rule_tests.csv) so a
rule pack cannot validate unless its behavioral self-tests pass
(Rev C 29.4 / addendum Phase 1 gate).

### `validate_rule_pack(rule_pack: 'RulePack') -> 'ValidationResult'`
*(no docstring)*

---

## `rule_engine` — Deterministic guessing engine (Rev C 9, 13.0 precedence)

Deterministic net-voltage guessing rule engine.

### `guess_net_voltage(net_name: 'str', rule_pack: 'RulePack', defaults: 'VoltageDefaults | None' = None) -> 'RuleMatchResult'`
*(no docstring)*

### `guess_voltage_for_nets(net_names: 'list[str]', rule_pack: 'RulePack', defaults: 'VoltageDefaults | None' = None, *, source_revision: 'str' = '')`
*(no docstring)*

---

## `assignment_store` — Persistent assignment store (addendum 12.1.1)

Project assignment store persistence for voltage guessing.

### `assignment_store_path(output_dir: 'Path') -> 'Path'`
*(no docstring)*

### `create_assignment_store(assignments: 'list[VoltageAssignment]', *, project_revision: 'str' = '') -> 'AssignmentStore'`
*(no docstring)*

### `load_assignment_store(path: 'Path') -> 'AssignmentStore'`
*(no docstring)*

### `save_assignment_store_atomic(store: 'AssignmentStore', path: 'Path') -> 'None'`
*(no docstring)*

### `store_to_dict(store: 'AssignmentStore') -> 'dict'`
*(no docstring)*

### `utc_now() -> 'str'`
*(no docstring)*

**Constants:** `DEFAULT_ASSIGNMENT_STORE_NAME` = `'net_voltage_assignments.json'`, `STORE_FILE_KIND` = `'net_voltage_assignment_store'`, `STORE_SCHEMA_VERSION` = `1`

---

## `assignment_import` — Import of exported assignments (addendum 9.1.1)

Phase 3 import of previously exported voltage assignments.

Implements addendum 9.1.1 error handling: an import either fully loads
(possibly with reported skipped rows) or is fully rejected — never
partially applied and never raising for content problems (13.1).

### `import_voltage_assignments(path: 'Path') -> 'AssignmentImportResult'`
Import an export snapshot (.json) or interchange CSV (.csv).

**Constants:** `EXPORT_FILE_KIND` = `'net_voltage_assignment_export'`, `STORE_FILE_KIND` = `'net_voltage_assignment_store'`, `STORE_SCHEMA_VERSION` = `1`

---

## `revision_matcher` — Revision matching + delta (addendum 11.1/11.2)

Phase 3 deterministic revision matching.

Match statuses (Rev C 9.4/9.5): exact, case_insensitive, normalized,
likely_renamed (suggestion only), conflict, missing, new.

match_score implements addendum 11.1 exactly — the weights are frozen
together with the golden fixture test; change both or neither.

### `apply_manual_mapping(store: 'AssignmentStore', old_net: 'str', new_net: 'str', imported: 'list[VoltageAssignment]', match_result: 'RevisionMatchResult', *, current_revision: 'str' = '') -> 'VoltageAssignment'`
User-confirmed old→new mapping (Phase 3 gate item 8).

### `apply_safe_matches(store: 'AssignmentStore', match_result: 'RevisionMatchResult', imported: 'list[VoltageAssignment]', rule_pack: 'RulePack', *, current_revision: 'str' = '') -> 'int'`
Apply exact/case-insensitive/normalized matches and rule-guess new nets.

Likely-renamed and conflicts are NOT applied (Phase 3 gate items 4-5).
Missing old nets are preserved as 'Obsolete / missing in new revision'.
Records one undo entry.

### `compute_match_score(old_net: 'str', new_net: 'str', rule_pack: 'RulePack', *, old_prefixes: 'set[str] | None' = None, new_prefixes: 'set[str] | None' = None) -> 'int'`
Deterministic 0-100 score per addendum 11.1. Same inputs, same score.

### `export_revision_delta_csv(imported: 'list[VoltageAssignment]', store: 'AssignmentStore', match_result: 'RevisionMatchResult', path: 'Path') -> 'Path'`
Delta between imported (old revision) and current store (Rev C 11.6).

### `export_revision_match_csv(match_result: 'RevisionMatchResult', path: 'Path') -> 'Path'`
*(no docstring)*

### `match_revision(imported: 'list[VoltageAssignment]', current_nets: 'list[str]', rule_pack: 'RulePack', *, score_threshold: 'int' = 60, component_prefixes: 'dict[str, set[str]] | None' = None, source_file: 'str' = '', source_revision: 'str' = '') -> 'RevisionMatchResult'`
Match imported assignments to the current net list. Pure function, no store mutation.

**Constants:** `MATCH_SCORE_THRESHOLD_DEFAULT` = `60`, `MAX_BLOCKED_CANDIDATES` = `20`, `MAX_CANDIDATES_PER_NET` = `3`

---

## `review_service` — Review workflow: approve/waive/undo/gate (Phase 2)

Phase 2 review-management services for deterministic voltage guessing.

All review logic lives here so the GUI stays a thin caller (addendum 8.1).
Every state-changing operation records one UndoEntry (addendum 13.2).

### `accept_unknown(store: 'AssignmentStore', nets: 'list[str]', *, reason: 'str' = '', reviewer: 'str | None' = None) -> 'int'`
*(no docstring)*

### `apply_manual_override(store: 'AssignmentStore', net: 'str', *, final_class: 'str', final_voltage_v: 'float | None', review_state: 'str' = 'Reviewed', notes: 'str' = '', reviewer: 'str | None' = None) -> 'VoltageAssignment'`
*(no docstring)*

### `approve(store: 'AssignmentStore', nets: 'list[str]', *, reason: 'str' = '', reviewer: 'str | None' = None) -> 'int'`
Bulk approve safe nets only.

Per Rev C 6.3 / addendum 14.1, Warning- and Critical-severity
assignments must never be approved through the batch/bulk approve
service. They remain in the review queue for deliberate individual
review via apply_manual_override(), accept_unknown(), or waive().

### `default_reviewer() -> 'str'`
Reviewer identity per Rev C Section 19: OS login username.

### `needs_review(assignment: 'VoltageAssignment') -> 'bool'`
Queue membership: unresolved states, or unreviewed Warning/Critical severity.

### `review_gate_status(store: 'AssignmentStore', mode: 'str' = 'warn') -> 'ReviewGateStatus'`
*(no docstring)*

### `review_queue(store: 'AssignmentStore') -> 'list[VoltageAssignment]'`
Nets requiring attention, most severe first, deterministic order.

### `run_auto_detect(store: 'AssignmentStore', net_names: 'list[str]', rule_pack: 'RulePack', *, source_revision: 'str' = '') -> 'int'`
Guess all nets; preserve manual and imported assignments (Rev C 9.8/28).

Returns the number of assignments changed or added. Records one undo entry.

### `undo_last(store: 'AssignmentStore') -> 'str'`
Undo the most recent operation. Returns the operation name ('' if nothing).

### `waive(store: 'AssignmentStore', nets: 'list[str]', *, reason: 'str', scope: 'str' = 'current_revision_only', reviewer: 'str | None' = None) -> 'int'`
*(no docstring)*

**Constants:** `DEFAULT_GATE_MODE` = `'warn'`, `GATE_MODES` = `('allow', 'warn', 'block')`, `UNDO_STACK_DEPTH` = `20`

---

## `phase4` — Batch previews, explainability, corrections (Phase 4)

Phase 4 productivity helpers for deterministic voltage guessing.

This module deliberately contains no Tk imports.  It gives the GUI and tests
small service functions for batch previews, inline explainability, correction-
to-rule, assignment diffs, copyable summaries, and review-session persistence.

### `apply_batch_action(store: 'AssignmentStore', nets: 'list[str]', operation: 'str', *, final_class: 'str | None' = None, final_voltage_v: 'float | None' = None, reason: 'str' = '', waiver_scope: 'str' = 'current_revision_only', reviewer: 'str | None' = None) -> 'int'`
Apply a Phase 4 batch action as one undoable user operation.

### `copyable_review_summary(store: 'AssignmentStore', *, project_name: 'str' = '', rule_pack_name: 'str' = '', template: 'str' = '') -> 'str'`
*(no docstring)*

### `create_project_local_rule_from_correction(rule_dir: 'Path', *, token: 'str', assignment: 'VoltageAssignment', reviewer: 'str | None' = None) -> 'Path'`
Append a deterministic project-local token rule from a manual correction.

### `diff_assignments(old: 'dict[str, VoltageAssignment]', new: 'dict[str, VoltageAssignment]') -> 'list[AssignmentDiffRow]'`
*(no docstring)*

### `explain_assignment(assignment: 'VoltageAssignment', rule_pack: 'RulePack | None' = None) -> 'WhyExplanation'`
Create an inline "Why?" explanation for one assignment.

### `make_batch_preview(store: 'AssignmentStore', nets: 'list[str]', operation: 'str', *, final_class: 'str | None' = None, final_voltage_v: 'float | None' = None, reason: 'str' = '') -> 'BatchPreview'`
Return a dry-run preview for Phase 4 batch actions.

No store mutation happens here.  Bulk approve blocks Warning/Critical nets
according to Rev C 6.3 / addendum 14.1.

### `preview_to_text(preview: 'BatchPreview', *, max_rows: 'int' = 25) -> 'str'`
*(no docstring)*

### `suggest_similar_nets(store: 'AssignmentStore', edited_net: 'str', *, max_items: 'int' = 12) -> 'list[SimilarNetSuggestion]'`
Find deterministic similar nets for correction-to-rule.

### `update_review_session(store: 'AssignmentStore', *, queue_position: 'int | None' = None, active_filter: 'str | None' = None, sort_key: 'str | None' = None, skipped_net: 'str | None' = None) -> 'None'`
*(no docstring)*

**Constants:** `PROJECT_CORRECTION_RULE_FILE` = `'project_local_corrections.csv'`

---

## `exports` — CSV/JSON exports (addendum 11.3)

CSV and JSON exporters for voltage guessing.

### `export_all_voltage_files(assignments: 'list[VoltageAssignment]', output_dir: 'Path', *, project_revision: 'str' = '') -> 'dict[str, Path]'`
*(no docstring)*

### `export_json_name(project_revision: 'str' = '') -> 'str'`
*(no docstring)*

### `export_voltage_assignments_csv(assignments: 'list[VoltageAssignment]', path: 'Path') -> 'Path'`
*(no docstring)*

### `export_voltage_assignments_json(assignments: 'list[VoltageAssignment]', path: 'Path', *, project_revision: 'str' = '') -> 'Path'`
Write an export SNAPSHOT (assignments only) — not the project store.

Per addendum 12.1.1 the snapshot excludes review_session and undo_stack
and carries its own file_kind, so the importer can distinguish it.

### `export_voltage_guessing_csv(assignments: 'list[VoltageAssignment]', path: 'Path') -> 'Path'`
*(no docstring)*

**Constants:** `ASSIGNMENTS_CSV` = `'net_voltage_assignments.csv'`, `EXPORT_FILE_KIND` = `'net_voltage_assignment_export'`, `GUESSING_CSV` = `'net_voltage_guessing.csv'`, `STORE_SCHEMA_VERSION` = `1`

---

## Data models (`models`, service dataclasses)

### `models.AssignmentStore`
AssignmentStore(schema_version: 'int', project_revision: 'str', assignments: 'dict[str, VoltageAssignment]', review_session: 'ReviewSessionState' = <factory>, undo_stack: 'list[UndoEntry]' = <factory>, created_utc: 'str' = '', modified_utc: 'str' = '')
Fields: `schema_version`, `project_revision`, `assignments`, `review_session`, `undo_stack`, `created_utc`, `modified_utc`

### `models.NormalizeOptions`
NormalizeOptions(strip_leading_plus: 'bool' = True)
Fields: `strip_leading_plus`

### `models.PadInfo`
PadInfo(component_refdes: 'str', pad_name: 'str', layer: 'str', x: 'float', y: 'float')
Fields: `component_refdes`, `pad_name`, `layer`, `x`, `y`

### `models.ReviewSessionState`
ReviewSessionState(queue_position: 'int' = 0, active_filter: 'str' = '', sort_key: 'str' = '', skipped_nets: 'list[str]' = <factory>)
Fields: `queue_position`, `active_filter`, `sort_key`, `skipped_nets`

### `models.RuleMatchResult`
RuleMatchResult(net_name: 'str', guessed_class: 'str', guessed_voltage_v: 'float | None', reference_net: 'str', voltage_type: 'str', confidence: 'str', severity: 'str', winning_rule_id: 'str | None', all_matched_rule_ids: 'list[str]', reason: 'str', warning: 'str', matched_pattern: 'str' = '', matched_rule_pack: 'str' = '', matched_rule_file: 'str' = '')
Fields: `net_name`, `guessed_class`, `guessed_voltage_v`, `reference_net`, `voltage_type`, `confidence`, `severity`, `winning_rule_id`, `all_matched_rule_ids`, `reason`, `warning`, `matched_pattern`, `matched_rule_pack`, `matched_rule_file`

### `models.RulePack`
RulePack(manifest: 'dict', rules: 'list[VoltageRule]', defaults: 'VoltageDefaults', source_files: 'list[Path]', layer_counts: 'dict[str, int]', missing_files: 'list[str]' = <factory>, unlisted_files: 'list[str]' = <factory>, tests_path: 'Path | None' = None)
Fields: `manifest`, `rules`, `defaults`, `source_files`, `layer_counts`, `missing_files`, `unlisted_files`, `tests_path`

### `models.UndoEntry`
UndoEntry(operation: 'str', timestamp_utc: 'str', changed: 'dict[str, VoltageAssignment]')
Fields: `operation`, `timestamp_utc`, `changed`

### `models.ValidationIssue`
ValidationIssue(level: 'str', rule_id: 'str', source_file: 'str', message: 'str')
Fields: `level`, `rule_id`, `source_file`, `message`

### `models.ValidationResult`
ValidationResult(ok: 'bool', issues: 'list[ValidationIssue]', test_cases_run: 'int' = 0, test_cases_failed: 'int' = 0)
Fields: `ok`, `issues`, `test_cases_run`, `test_cases_failed`

### `models.VoltageAssignment`
VoltageAssignment(net_name: 'str', final_class: 'str', final_voltage_v: 'float | None', reference_net: 'str', voltage_type: 'str', confidence: 'str', severity: 'str', review_state: 'str', source: 'str', evidence: 'VoltageEvidence', waiver: 'VoltageWaiver' = <factory>, notes: 'str' = '', reviewed_by: 'str' = '', reviewed_at_utc: 'str' = '', review_reason: 'str' = '', source_revision: 'str' = '', last_seen_revision: 'str' = '')
Fields: `net_name`, `final_class`, `final_voltage_v`, `reference_net`, `voltage_type`, `confidence`, `severity`, `review_state`, `source`, `evidence`, `waiver`, `notes`, `reviewed_by`, `reviewed_at_utc`, `review_reason`, `source_revision`, `last_seen_revision`

### `models.VoltageContext`
VoltageContext(net_class: 'str', voltage_v: 'float | None', review_state: 'str', severity: 'str')
Fields: `net_class`, `voltage_v`, `review_state`, `severity`

### `models.VoltageDefaults`
VoltageDefaults(mains_rms_v: 'float' = 230.0, mains_peak_v: 'float' = 325.0, battery_volts_per_cell_max: 'float' = 4.2, logic_io_v: 'float' = 3.3, analog_io_v: 'float' = 3.3, usb_vbus_v: 'float' = 5.0, usb_pd_max_v: 'float' = 20.0, poe_voltage_v: 'float' = 57.0, unknown_severity: 'str' = 'Review')
Fields: `mains_rms_v`, `mains_peak_v`, `battery_volts_per_cell_max`, `logic_io_v`, `analog_io_v`, `usb_vbus_v`, `usb_pd_max_v`, `poe_voltage_v`, `unknown_severity`

### `models.VoltageEvidence`
VoltageEvidence(evidence_type: 'str' = 'unknown', matched_rule_id: 'str' = '', matched_pattern: 'str' = '', matched_rule_pack: 'str' = '', matched_rule_file: 'str' = '', all_matched_rule_ids: 'list[str]' = <factory>, rule_reason: 'str' = '', rule_warning: 'str' = '', imported_from_file: 'str' = '', import_match_status: 'str' = '', import_match_score: 'int | None' = None, manual_review_note: 'str' = '', last_exported_value: 'float | None' = None)
Fields: `evidence_type`, `matched_rule_id`, `matched_pattern`, `matched_rule_pack`, `matched_rule_file`, `all_matched_rule_ids`, `rule_reason`, `rule_warning`, `imported_from_file`, `import_match_status`, `import_match_score`, `manual_review_note`, `last_exported_value`

### `models.VoltageRule`
VoltageRule(rule_id: 'str', priority: 'int', enabled: 'bool', pattern: 'str', match_type: 'str', net_class: 'str', voltage_v: 'float | None', cell_count_from_pattern: 'bool' = False, volts_per_cell: 'float | None' = None, reference_net: 'str' = '', voltage_type: 'str' = 'DC', confidence: 'str' = 'Medium', severity: 'str' = 'Review', reason: 'str' = '', warning: 'str' = '', tags: 'list[str]' = <factory>, source_layer: 'str' = 'built-in', source_file: 'str' = '', match_on: 'str' = 'normalized', parse_issues: 'list[str]' = <factory>)
Fields: `rule_id`, `priority`, `enabled`, `pattern`, `match_type`, `net_class`, `voltage_v`, `cell_count_from_pattern`, `volts_per_cell`, `reference_net`, `voltage_type`, `confidence`, `severity`, `reason`, `warning`, `tags`, `source_layer`, `source_file`, `match_on`, `parse_issues`

### `models.VoltageToken`
VoltageToken(raw_token: 'str', voltage_v: 'float', polarity: 'int', marker: 'str', start: 'int', end: 'int')
Fields: `raw_token`, `voltage_v`, `polarity`, `marker`, `start`, `end`

### `models.VoltageWaiver`
VoltageWaiver(waived: 'bool' = False, waived_by: 'str' = '', waived_at_utc: 'str' = '', waiver_reason: 'str' = '', waiver_scope: 'str' = '', waiver_expires_revision: 'str' = '')
Fields: `waived`, `waived_by`, `waived_at_utc`, `waiver_reason`, `waiver_scope`, `waiver_expires_revision`

### `review_service.ReviewGateStatus`
ReviewGateStatus(mode: 'str', export_allowed: 'bool', stamp_text: 'str', unreviewed_critical: 'int', unreviewed_warning: 'int', needs_review: 'int', conflicts: 'int', waived: 'int', counts_line: 'str' = '')
Fields: `mode`, `export_allowed`, `stamp_text`, `unreviewed_critical`, `unreviewed_warning`, `needs_review`, `conflicts`, `waived`, `counts_line`

### `revision_matcher.RevisionMatchEntry`
RevisionMatchEntry(old_net: 'str | None', new_net: 'str | None', match_status: 'str', match_score: 'int | None' = None, applied: 'bool' = False, action_required: 'str' = '', detail: 'str' = '')
Fields: `old_net`, `new_net`, `match_status`, `match_score`, `applied`, `action_required`, `detail`

### `revision_matcher.RevisionMatchResult`
RevisionMatchResult(entries: 'list[RevisionMatchEntry]' = <factory>, counts: 'dict[str, int]' = <factory>, source_file: 'str' = '', source_revision: 'str' = '')
Fields: `entries`, `counts`, `source_file`, `source_revision`

### `assignment_import.AssignmentImportResult`
AssignmentImportResult(ok: 'bool', assignments: 'list[VoltageAssignment]' = <factory>, schema_version_found: 'int | None' = None, migrated_from_version: 'int | None' = None, rejected_reason: 'str' = '', skipped_rows: 'list[tuple[int, str]]' = <factory>, source_file: 'str' = '', source_revision: 'str' = '')
Fields: `ok`, `assignments`, `schema_version_found`, `migrated_from_version`, `rejected_reason`, `skipped_rows`, `source_file`, `source_revision`

### `phase4.AssignmentDiffRow`
AssignmentDiffRow(category: 'str', net_name: 'str', old_class: 'str', old_voltage_v: 'float | None', old_review_state: 'str', new_class: 'str', new_voltage_v: 'float | None', new_review_state: 'str')
Fields: `category`, `net_name`, `old_class`, `old_voltage_v`, `old_review_state`, `new_class`, `new_voltage_v`, `new_review_state`

### `phase4.BatchPreview`
BatchPreview(operation: 'str', requested_count: 'int', affected_count: 'int', blocked_count: 'int', rows: 'list[BatchPreviewRow]' = <factory>)
Fields: `operation`, `requested_count`, `affected_count`, `blocked_count`, `rows`

### `phase4.BatchPreviewRow`
BatchPreviewRow(net_name: 'str', old_class: 'str', old_voltage_v: 'float | None', old_review_state: 'str', new_class: 'str', new_voltage_v: 'float | None', new_review_state: 'str', reason: 'str', blocked: 'bool' = False)
Fields: `net_name`, `old_class`, `old_voltage_v`, `old_review_state`, `new_class`, `new_voltage_v`, `new_review_state`, `reason`, `blocked`

### `phase4.SimilarNetSuggestion`
SimilarNetSuggestion(net_name: 'str', reason: 'str')
Fields: `net_name`, `reason`

### `phase4.WhyExplanation`
WhyExplanation(net_name: 'str', text: 'str', winning_rule_id: 'str', losing_rule_ids: 'list[str]')
Fields: `net_name`, `text`, `winning_rule_id`, `losing_rule_ids`

---

## Exceptions

### `models.FingerprintDataUnavailable`
Raised by `AnalyzerAdapter.get_pads_for_net` when pad data is missing; the matcher degrades to name-based scoring (max score 90).

## Enumerations (`enums`)

- `ASSIGNMENT_SOURCES` = ['imported_case_insensitive', 'imported_exact', 'imported_manual_mapping', 'imported_normalized', 'manual', 'rule', 'unknown']
- `CONFIDENCE_VALUES` = ['High', 'Low', 'Medium', 'Unknown']
- `MATCH_ON_VALUES` = ['normalized', 'raw']
- `MATCH_TYPES` = ['exact', 'prefix', 'regex', 'suffix', 'token']
- `NET_CLASSES` = ['BATTERY', 'COMMUNICATION', 'CONTROL_SIGNAL', 'DIFFERENTIAL_IO', 'GND', 'HIGH_VOLTAGE', 'IO_ANALOG', 'IO_DIGITAL', 'ISOLATION_DOMAIN_HINT', 'MAINS', 'POWER', 'POWER_HIGHER_LOW_VOLTAGE', 'POWER_NEGATIVE', 'POWER_VARIABLE', 'REFERENCE', 'UNKNOWN']
- `REVIEW_STATES` = ['Accepted unknown', 'Approved', 'Auto-guessed', 'Conflict', 'Imported', 'Needs review', 'Obsolete / missing in new revision', 'Reviewed', 'Waived']
- `SEVERITY_VALUES` = ['Critical', 'Info', 'Review', 'Warning']
- `VOLTAGE_TYPES` = ['AC_PEAK', 'AC_RMS', 'DC', 'UNKNOWN', 'VARIABLE']

---

## CLI flags (voltage guessing)

| Flag | Effect | Exit codes |
|---|---|---|
| `--voltage-guess` | Guess all nets, persist store, write 3 export files | — |
| `--voltage-gate-mode {allow,warn,block}` | Review gate; default `warn`. Stderr emits machine-readable `VOLTAGE_GATE:` lines | `2` export blocked |
| `--import-voltage-assignments FILE` | Import prior revision, apply safe matches, write match/delta CSVs | `5` import rejected, `4` conflicts pending |
| `--validate-voltage-rule-pack` | Validate rule pack incl. behavioral self-test CSV | non-zero on error |

Exit-code precedence: the lowest applicable non-zero code wins (Rev C 27).

## Output files

| File | Kind | Notes |
|---|---|---|
| `net_voltage_assignments.json` | Project store | file_kind `net_voltage_assignment_store`; session + undo included; restored on reopen |
| `net_voltage_assignments_<rev>.json` | Export snapshot | file_kind `net_voltage_assignment_export`; assignments only; store loader rejects it |
| `net_voltage_guessing.csv` | Guessing report | rule reason/warning columns populated from evidence |
| `net_voltage_assignments.csv` | Interchange CSV | re-importable; semicolon lists; UTF-8 no BOM |
| `net_voltage_assignment_revision_match.csv` | Match table | statuses: exact/case_insensitive/normalized/likely_renamed/conflict/new/missing |
| `net_voltage_assignment_revision_delta.csv` | Delta report | added/deleted/renamed/class_changed/voltage_changed/waived/unchanged |
| `net_voltage_rules/project_local_corrections.csv` | Correction rules | loaded as `project-local` layer, wins over built-in |
