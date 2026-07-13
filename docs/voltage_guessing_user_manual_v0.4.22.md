# Voltage Guessing — User Manual (v0.4.22)

Deterministic net-voltage classification for the ODB++ Clearance Analyzer.
No LLM, AI model, cloud API, or probabilistic classifier is used: every
assignment comes from editable pattern rules and is fully explainable.

> **Safety notice.** Voltage guesses are derived only from net names.
> Review and correct all values before using them for clearance,
> creepage, isolation, or any safety decision.

## 1. Where to find it

Main window → **Voltage Guessing** tab → six subtabs:
Overview · Review Needed · All Assignments · Revision Import · Export · Advanced.

## 2. Quick start

1. Read ODB++ metadata (or run a full analysis).
2. **Overview → Auto-detect voltage classes.** A dry-run prompt shows what
   will happen if assignments already exist; manual and imported values
   are always preserved.
3. **Review Needed:** work through the queue. Critical rows are red,
   Warning rows yellow, sorted most-severe first.
4. **Export** when the gate is satisfied.

Everything is saved automatically to `net_voltage_assignments.json` in the
output folder and restored when you reopen the project — including your
queue position, skipped nets, and the undo history.

## 3. Review Needed tab

Select one or more nets, then:

| Action | Button / Key | Notes |
|---|---|---|
| Approve | Approve / **A** | Blocked for Warning and Critical severity — those need individual review |
| Accept unknown | Accept unknown / **U** | Records reason; net leaves the queue |
| Waive | Waive… / **W** | Reason required; pick a scope (below) |
| Edit | **E** | Loads the net into the editor |
| Skip | **S** | Remembers the skip in your session |
| Navigate | ← / → arrows | Moves through the queue |

Every batch action shows a **dry-run preview** listing exactly which nets
change and which are blocked, before anything is applied. Each applied
action is a single undo step (Undo last action, 20-step history that
survives restart).

**Waiver scopes** (Rev C §22):

- `current_revision_only` — dropped at the next revision import.
- `this_net_until_changed` — carried while class/voltage are unchanged.
- `project_global` — carried always.

## 4. All Assignments tab

The full sortable table. Selecting a row opens the editor:

- Change final class / voltage / review state, add notes, then
  **Apply manual override**. Overrides record your OS username and a UTC
  timestamp, and are never overwritten by auto-detect or imports.
- **Why?** shows the complete trace: the winning rule and its pattern,
  every rule that matched but lost (and the precedence that decided it),
  import provenance, warnings, and waiver details.
- **Show on board** opens the Geometry Viewer with the net highlighted on
  the first layer where it has copper. Inside the viewer, the
  **Voltage assignment** button jumps back to this table with the net
  selected — review works in both directions.
- **Learn from my fix** (after an override) offers to create a
  project-local rule from your correction and lists similar nets. The
  rule is written to `net_voltage_rules/project_local_corrections.csv`
  in the output folder, loads immediately, and outranks built-in rules.

## 5. Revision Import tab

Reuse review work from a previous board revision:

1. Browse to a prior export (`net_voltage_assignments_<rev>.json`) or an
   interchange CSV.
2. **Match against current nets** — a preview table appears; nothing is
   applied yet. Statuses: `exact`, `case_insensitive`, `normalized`
   (safe), `likely_renamed` (scored suggestion, never auto-applied),
   `conflict` (needs you), `new` (will be rule-guessed), `missing`
   (kept as *Obsolete*).
3. **Apply safe matches** — one undoable operation. Approvals, manual
   values, and eligible waivers carry over.
4. For each yellow suggestion you agree with, select it and
   **Apply selected suggestion**.

Suggestion scores (0–100, threshold 60) combine name similarity, shared
tokens, voltage, detected class, and — when pad data is available —
component fingerprints; without fingerprints the maximum score is 90.
Two CSVs are written on every apply: the full match table and a delta
report (added / deleted / renamed / changed).

Import safety: a malformed file is rejected whole with a clear message;
rows with invalid values are skipped and reported; a project *store*
file is recognized and its session/undo state ignored. Nothing touches
your assignments until you click an Apply button.

## 6. Review gate and Export tab

The gate mode (Overview tab, or CLI `--voltage-gate-mode`) controls
exporting while unreviewed items remain:

- **allow** — always export.
- **warn** (default) — export, but stamp the log with the unreviewed
  counts.
- **block** — refuse to export while unreviewed **Critical** items exist.

Export writes three files:

| File | Purpose |
|---|---|
| `net_voltage_guessing.csv` | Raw rule results incl. winning rule, reason, warning |
| `net_voltage_assignments_<rev>.json` | Portable snapshot for the next revision (cannot be mistaken for the store) |
| `net_voltage_assignments.csv` | Interchange CSV with full review/waiver metadata |

## 7. Advanced tab

- **Rule sandbox** — type any net name and Evaluate to see exactly what
  the active rule pack (including your project-local corrections) would
  decide, with the full Why? trace.
- **Assignment diff viewer** — compare the imported revision against the
  current store: added / deleted / renamed / voltage_changed /
  class_changed / review_state_changed / unchanged.

## 8. Command line

```bash
python -m odb_clearance_analyzer.cli BOARD.zip out/ \
    --voltage-guess \
    --import-voltage-assignments prev/net_voltage_assignments_rev_a.json \
    --voltage-gate-mode block
```

Exit codes (lowest wins): `0` OK · `1` analysis error · `2` gate block ·
`4` revision conflicts pending · `5` import rejected. Status lines for CI
are printed to stderr with the `VOLTAGE_GATE:` / `VOLTAGE_IMPORT:` prefix.

Validate the rule pack alone with `--validate-voltage-rule-pack`; this
also executes the pack's behavioral self-tests (21 cases built in).

## 9. Files on disk

| File | Meaning | Edit by hand? |
|---|---|---|
| `net_voltage_assignments.json` | Project store: assignments + review session + undo | No |
| `net_voltage_assignments_<rev>.json` | Export snapshot | No (regenerate) |
| `net_voltage_guessing.csv` / `net_voltage_assignments.csv` | Reports / interchange | CSV re-importable |
| `net_voltage_assignment_revision_match.csv` / `..._delta.csv` | Import audit trail | No |
| `net_voltage_rules/project_local_corrections.csv` | Your correction rules | Yes — reloaded automatically; invalid regexes are ignored with a log warning |

## 10. Robustness notes

- One malformed net name (control characters) no longer aborts
  auto-detect: the net gets an explicit UNKNOWN / Needs-review
  assignment.
- An invalid regex in a hand-edited rule file is logged and ignored;
  every other rule keeps working.
- A corrupted store file produces a log message on open, never a crash;
  your last good export remains usable via Revision Import.
- Long operations currently run on the UI thread; on very large boards
  expect brief freezes rather than progress bars (scheduled for Phase 5).

## 11. Performance

Measured on the reference container: 20,000 nets guessed in ~0.7 s;
20,000-net revision match with 5% churn in ~2 s. Regression tests keep
these within 2× of the spec targets.


## 10. Robustness notes (v0.4.21+)

- **Invalid regex in a rule file** (e.g. a hand-edited
  `project_local_corrections.csv`) no longer crashes auto-detect: the
  bad pattern is ignored with a warning in the Log tab, and every other
  rule keeps working. Run *Validate rule pack* to find such rules.
- **Garbage net names** (control characters from a corrupt ODB++ job)
  no longer abort guessing: the affected net gets an explicit
  `UNKNOWN / Needs review` assignment whose reason explains that the
  name could not be normalized; the rest of the board proceeds. These
  nets flow safely through exports, revision matching, and similar-net
  suggestions.
- **Corrupt store files** are reported with a clear message on project
  open; your review work is only ever replaced by a store that parses
  and validates.
