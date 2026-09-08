# ODB++ Clearance Analyzer

A Python desktop and command-line tool for inspecting PCB copper spacing from **ODB++** data.

The tool reconstructs same-layer copper geometry, measures net-to-net spacing, highlights critical pairs, visualizes copper in an interactive viewer, and exports engineering reports. It is intended for PCB design review, clearance screening, and early compliance risk analysis.

> **Important:** This software is a screening and engineering-assistance tool. It is not a certified IEC, UL, IPC, or safety-agency compliance engine. Always confirm final required distances from the applicable standard edition, product category, certification body, and test lab.

---

## Key features

- Reads ODB++ archives and extracted ODB++ folders.
- Reconstructs same-layer copper geometry per net.
- Measures minimum net-to-net copper spacing.
- Detects critical pairs below a configurable threshold.
- Exports CSV, Excel, Markdown, and ZIP report packages.
- Provides an interactive Geometry Viewer.
- Supports dark/light Material-style GUI.
- Supports IPC-2221A style maximum-voltage screening.
- Supports IEC 60664-1 style effective-voltage screening.
- Supports IEC 61558 / IEC 62368 isolation-barrier screening.
- Supports JSON settings profiles for reproducible analysis.
- Deterministic **Voltage Guessing**: classifies every net's voltage class/value from editable
  name rules (no AI/LLM), with a keyboard review queue, waivers, revision import with
  rename matching, project-local correction rules, review gates for exports, full undo,
  and two galvanic zones (`Zone 1` / `Zone 2`) for higher-level isolation checks — all
  persisted across restarts. See `docs/voltage_guessing_user_manual_v0.4.22.md`.

---

## Screens and workflows

### Main analysis

The main window combines input, output, and analysis controls in a compact top card.

Typical workflow:

1. Select an ODB++ ZIP archive or extracted ODB++ folder.
2. Select output folder.
3. Set the critical threshold in mm.
4. Optionally enable effective Net-to-Net distance.
5. Configure IEC/IPС/isolation settings.
6. Run analysis.
7. Review critical pairs and open selected rows in Geometry Viewer.
8. Export reports automatically from the output folder.

### Geometry Viewer

The Geometry Viewer provides interactive inspection of reconstructed copper.

Viewer features:

- Layer selector.
- Net A / Net B selection.
- Text filters for nets.
- Click-to-select Net A and Net B.
- Fast mode for smoother viewing of large pours.
- Exact selected-net rendering.
- Component pad overlay.
- Component outline overlay.
- Via overlay.
- PCB outline overlay.
- Minimum-distance line.
- Blocker dots where other copper crosses the spacing line.
- **Zoom min 2/3** button to zoom to the exact minimum-clearance location.

### IEC 60664-1 tab

The IEC 60664-1 tab provides adjustable screening settings:

- CTI.
- Base pollution degree.
- Per-layer pollution-degree assignment.
- External conformal coating option.
- Metallic-particle size correction for external layers.
- Effective max voltage export.

Internal layers can be assigned as pollution degree 1, and external layers can be auto-assigned according to coating and selected base pollution degree.

### IPC-2221A tab

The IPC-2221A tab provides:

- Layer role assignment: internal or external.
- Altitude above sea level.
- IPC-style max-voltage estimate export.
- Automatic role assignment from common copper-layer names.
- Manual override of layer role assignment.

### IEC 61558 / IEC 62368 isolation tab

The isolation tab is intended for transformer and isolation-barrier screening.

You can define an **isolated side** net group, for example:

```text
SEC_GND
SEC+
SEC-
```

The tool checks each isolated-side net against every other net on every same copper layer.

Adjustable variables include:

- Standard/profile label.
- Insulation type: functional, basic, supplementary, reinforced.
- Working voltage.
- Peak / recurring voltage.
- Impulse voltage.
- Overvoltage category.
- Pollution degree.
- Material group / CTI class.
- CTI.
- Altitude.
- Required clearance.
- Required creepage.
- Safety factor.

The isolation result table shows:

- Group.
- Layer.
- Isolated net.
- Other net.
- Measured spacing.
- Required clearance.
- Required creepage.
- Governing required spacing.
- Margin.
- Pass/fail.
- Standard/profile label.

The governing required spacing is calculated as:

```text
max(required_clearance_mm, required_creepage_mm) × safety_factor
```

---

## Limitations

This project currently performs **same-layer 2D copper-geometry screening** from ODB++ data.

It does **not** certify compliance and does not fully evaluate:

- 3D creepage paths over component bodies.
- Creepage over transformer bobbins or insulation systems.
- Internal transformer construction.
- Enclosure, connector, cable, or terminal spacing.
- Actual solder mask qualification as insulation.
- Actual conformal coating certification.
- Slot/routing creepage paths unless represented in analyzable geometry.
- Cross-layer dielectric thickness.
- Manufacturing tolerances, plating, etch compensation, or contamination models.
- Product-specific standard clauses, exceptions, and certification-lab interpretations.

Use it as an engineering review aid before formal compliance review.

---

## Installation

### Requirements

- Python 3.10 or newer.
- Windows, Linux, or macOS.
- Tkinter.
- Shapely.
- openpyxl.

### Install from local source

Clone the repository and install in editable mode:

```bash
git clone https://github.com/your-user/odb-clearance-analyzer.git
cd odb-clearance-analyzer
python -m pip install -e .
```

For development and tests:

```bash
python -m pip install -e ".[dev]"
```

If your environment does not have Tkinter installed, install it through your OS package manager. On Ubuntu/Debian:

```bash
sudo apt install python3-tk
```

---

## Run the GUI

After installation:

```bash
odb-clearance-gui
```

Or run as a module:

```bash
python -m odb_clearance_analyzer.gui
```

---

## Run the CLI

Basic analysis:

```bash
odb-clearance-analyzer path/to/board-odb.zip --output clearance_report
```

Set threshold:

```bash
odb-clearance-analyzer path/to/board-odb.zip --output clearance_report --threshold 0.15
```

Enable effective Net-to-Net matrix:

```bash
odb-clearance-analyzer path/to/board-odb.zip --output clearance_report --effective-air-gap-matrix
```

Voltage guessing (deterministic, no AI):

```bash
# Guess all nets, persist the assignment store, write the 3 export files
odb-clearance-analyzer board-odb.zip --output out --voltage-guess

# CI gate: fail (exit 2) while unreviewed Critical assignments exist
odb-clearance-analyzer board-odb.zip --output out --voltage-guess --voltage-gate-mode block

# Reuse a previous revision's reviewed assignments (exit 5 = import rejected, 4 = conflicts)
odb-clearance-analyzer board-odb.zip --output out --voltage-guess \
  --import-voltage-assignments prev/net_voltage_assignments_rev_a.json

# Validate the rule pack, including its behavioral self-test CSV
odb-clearance-analyzer --validate-voltage-rule-pack
```

Machine-readable `VOLTAGE_GATE:` lines are printed to stderr for CI parsing.
Exit-code precedence: lowest applicable non-zero code wins.

Use IEC-style settings:

```bash
odb-clearance-analyzer path/to/board-odb.zip \
  --output clearance_report \
  --cti 175 \
  --pollution-degree 2 \
  --altitude-m 5500
```

Set layer role for IPC-style screening:

```bash
odb-clearance-analyzer path/to/board-odb.zip \
  --output clearance_report \
  --layer-role F.CU=external \
  --layer-role B.CU=external
```

Set per-layer IEC pollution degree:

```bash
odb-clearance-analyzer path/to/board-odb.zip \
  --output clearance_report \
  --layer-pollution-degree F.CU=2 \
  --layer-pollution-degree In1.CU=1
```

---

## Output files

Typical output folder contains:

```text
analysis_settings.json
geometry_debug_critical_pairs.csv
net_to_net_clearance_report.md
net_to_net_clearance_report.xlsx
net_to_net_critical_under_<threshold>mm.csv
net_to_net_measurements_full.csv
net_to_net_per_net_minimum.csv
net_to_net_report_package.zip
odb_feature_attributes.csv
```

Optional output when effective Net-to-Net matrix is enabled:

```text
net_to_net_effective_air_gap_matrix.csv
```

### `analysis_settings.json`

Every analysis automatically exports the current settings to:

```text
analysis_settings.json
```

This includes:

- Input/output paths.
- Critical threshold.
- IEC settings.
- IPC layer roles.
- IEC layer pollution-degree assignments.
- Effective Net-to-Net option.
- Voltage export flags.
- IEC 61558 / IEC 62368 isolation settings.

This file is useful for reproducible engineering reviews.

---

## Report columns

### Full measurement CSV

Contains net-to-net spacing data such as:

- Layer.
- Net A.
- Net B.
- Clearance mm.
- Effective max voltage estimate.
- IPC-2221A max voltage estimate.
- Nearest point A.
- Nearest point B.

### Critical pairs CSV

Contains only rows below the selected critical threshold.

### Per-net minimum CSV

Contains the minimum spacing found for each net.

### Effective Net-to-Net matrix CSV

When enabled, this reports whether other copper exists on the straight-line path between two nets and estimates the effective clear air gap.

---

## Geometry interpretation

The analyzer works from reconstructed ODB++ feature geometry.

It supports:

- Copper surfaces.
- Pads.
- Lines/arcs converted into geometry.
- Negative/cutout features.
- Plated drill/via projection where metadata is available.
- PCB outline/profile overlay.
- Component outline approximation from common fabrication/courtyard/silkscreen data.

Geometry reconstruction is always an approximation of what is present in the ODB++ export. For critical findings, verify against the PCB CAD source and manufacturing outputs.

---

## Standards support

Implemented as **screening helpers**:

- IPC-2221A-style spacing/voltage screening.
- IEC 60664-1-style insulation coordination screening.
- IEC 61558 / IEC 62368 isolation-barrier screening.

The tool does not embed copyrighted standard tables as authoritative compliance data. Where exact values depend on a standard table, edition, product category, insulation type, or certification interpretation, the GUI provides adjustable fields so the engineer can enter the correct value.

---

## Project structure

```text
odb_clearance_analyzer/
  __init__.py
  analyzer.py
  cli.py
  geometry.py
  geometry_viewer.py
  gui.py
  ipc2221.py
  layer_rules.py
  models.py
  odb_parser.py
  reports.py
  settings_profile.py
  theme.py
  voltage_estimator.py
  assets/

tests/
  test_*.py

docs/
  software_spec_v*.md

pyproject.toml
README.md
```

---

## Development

Run tests:

```bash
python -m pytest -q
```

Run package import smoke test:

```bash
python -c "import odb_clearance_analyzer as p; print(p.__version__)"
```

Run GUI import smoke test:

```bash
python -c "import odb_clearance_analyzer.gui as g; print(g.__version__)"
```

---

## Current version

```text
0.4.37
```

Recent additions:

- Data-loss protection when applying zone-to-zone voltage before assignments are loaded.
- Cached `VoltageRequirementResolver` for large net-pair report generation.
- Explicit zone-to-zone voltage setup and JSON persistence.
- Pair voltage-difference reporting for all net pairs.
- OK/NOK voltage status and voltage margin columns in reports.
- Geometry Viewer startup fix.
- Assigned-voltage export in CSV, Excel, and Markdown reports.

---

## Safety and compliance disclaimer

This software is provided for engineering analysis and design review only.

It does not replace:

- Certified safety evaluation.
- Manufacturer design rules.
- Certification-body review.
- Applicable IEC, UL, EN, DIN, ANSI, or IPC standards.
- Product-specific risk assessment.
- Test-lab interpretation.

The user is responsible for validating results against the actual PCB design, ODB++ export quality, manufacturing constraints, and applicable safety standards.

## v0.4.15 Voltage Guessing Phase 1

This package includes the first implementation phase of deterministic Voltage Guessing: a new GUI tab, built-in CSV/JSON rule pack, net-name normalization, numeric voltage parser, manual overrides, assignment JSON/CSV exports, assignment-store path in settings, and CLI flags `--voltage-guess` / `--validate-voltage-rule-pack`. No LLM or AI backend is used.



## v0.4.18 Voltage Guessing Phase 3 Fixes

This maintenance update fixes review findings from the v0.4.17 Phase 3 package:

- Correctly classifies negative rails such as `-12V`, `-15V`, `M12V`, `N12V`, and `NEG12V`.
- Adds built-in coverage for common battery, negative-rail, and HV polarity aliases such as `BAT+`, `BAT-`, `VBAT`, `VBATT`, `PACK+`, `PACK-`, `VEE`, `VNEG`, `HV+`, `HV-`, `BULK+`, `BULK-`, `RECT+`, and `RECT-`.
- Prevents bulk approval of Warning- and Critical-severity voltage assignments.
- Rejects project assignment-store files in the normal revision-import flow.
- Validates JSON import voltages and skips non-numeric or non-finite values instead of silently converting them to unknown.
- Validates bad numeric rule-pack fields such as invalid `priority` and `voltage_v`.
- Updates revision delta CSV export to the required Rev C schema.
- Fixes CLI analysis-error exit code to `1` so it no longer conflicts with voltage-gate exit code `2`.

Validation command:

```bash
python -m pytest -q
```


## v0.4.19 Voltage Guessing Phase 4 UX

Adds Phase 4 productivity and review-workflow improvements for the deterministic Voltage Guessing feature:

- Batch review dry-run previews for approve / accept unknown / waive / set class-voltage.
- Warning and Critical severity nets remain excluded from batch approve.
- Keyboard-first Review Needed queue shortcuts: A, U, W, E, S, Enter/? for Why.
- Inline Why? explanation for assignments, including winning rule and evidence.
- Rule sandbox in Advanced tab for testing one net name against the active rule pack.
- Correction-to-rule workflow: create project-local CSV rule from a manual fix.
- Similar-net suggestion helper for applying a manual correction to related nets.
- Persistent review-session state updates.
- Assignment diff viewer for comparing imported assignments to the current store.
- Copyable voltage review summary for tickets/email.
- Geometry Viewer launch from selected voltage assignment.

No LLM, local AI model, cloud API, Ollama, llama.cpp, GPT4All, OpenAI-compatible backend, or probabilistic classifier is implemented.


## v0.4.19 Voltage Guessing Phase 4

Advanced UX: batch review actions with dry-run previews, keyboard-first review
queue (A/U/W/E/S), inline "Why?" explainability with winning/losing rules,
correction-to-rule workflow, rule sandbox, assignment diff viewer, copyable
review summary, persistent review sessions, first-run/resume/complete states,
and regex voltage groups in rules.

## v0.4.20 Phase 4 review fixes

- Re-applied the v0.4.18 performance optimizations that the Phase 4 branch had
  dropped (pattern/regex caches; matcher feature cache + lossless candidate
  blocking). 20,000 nets guess in ~0.6 s; performance regression tests restored.
- Correction-to-rule now takes effect: project-local rules are layered onto the
  built-in pack (`load_layered_rule_pack`) and the pack cache is invalidated on
  rule creation.
- Geometry Viewer gained the reverse jump ("Voltage assignment" button) so
  cross-highlighting works in both directions.
- Keyboard shortcut legend made visible in the Review Needed tab.

## v0.4.21 Crash hardening

Adversarial inspection fixes: invalid regex in user rule files degrades to
never-matching with a logged warning instead of crashing auto-detect; a net
name with control characters gets an explicit UNKNOWN fallback instead of
aborting the whole board; corrupt store files raise catchable errors on
project open; tolerant normalization (`normalize_net_name_safe`) keeps
exports, similar-net suggestions, and revision matching working on such nets.

## v0.4.22 Documentation refresh

Regenerated API reference from live signatures
(`docs/voltage_guessing_api_reference_v0.4.22.md`), updated the voltage
guessing user manual with robustness notes, added voltage CLI examples to
this README, and introduced `CHANGELOG.md`.


## v0.4.27 Voltage Guessing cell/NTC mask refinements

Voltage Guessing now strips trailing `+` / `-` polarity markers during normalized rule matching, so names such as `stack_cell10+` and `stack_cell10-` are treated as `STACK_CELL10` and assigned from the configurable max-cell-voltage formula.

Additional deterministic masks were added:

- `Cell0`, `Cell0+`, `STACK_CELL0+` → `GND`, `0 V`, approved.
- `BMIC_NTC3+`, `BMIC_PCB_NTC1+`, and other nets with an `NTC` token → `IO_ANALOG`, `5.5 V max`, needs review.

## v0.4.26 Voltage Guessing configurable cell voltage

Voltage Guessing now includes a **Max cell voltage, V** field on the Overview
tab. The default is **4.3 V/cell**. It is used by cumulative battery cell-count
rules, for example `BAT_4S = 4 × Max cell voltage` and `Cell3 = 3 × Max cell
voltage`.

The value is saved in the project/settings JSON under
`settings.voltage_guessing.max_cell_voltage_v` and in the voltage assignment
project store JSON under `settings.max_cell_voltage_v`, so reopening or loading
a project restores the same rule assumption.

## v0.4.25 Voltage Guessing bulk assignment editing

The All Assignments tab now supports bulk manual edits. Select multiple net rows
with Shift/Ctrl, set the desired Class/Voltage/Review/Notes once, and click
**Apply manual override to selected**. The edit is saved as one undoable
`manual_bulk_edit` operation. Mixed selections show explicit placeholder values
so the user must choose a final class/review state and either enter or clear the
voltage before applying.



## v0.4.33 Pair voltage difference correction

For same-zone and local net-pair checks, the analyzer now uses the actual pair voltage difference:

```text
voltage_difference_v = abs(net_a_voltage_v - net_b_voltage_v)
```

Examples:

- Net A = 10 V, Net B = 21 V → `voltage_difference_v = 11 V`
- Net A = 10 V, Net B = 0 V or common GND net name → `voltage_difference_v = 10 V`

This pair-difference value is also the local `required_voltage_v` for same-zone pairs. Cross-zone Zone 1 ↔ Zone 2 pairs still use the higher-priority configured zone working voltage for `required_voltage_v`, while `voltage_difference_v` remains visible as diagnostic data.

## v0.4.32 OK/NOK voltage compliance columns

Main clearance reports now include an explicit **OK/NOK** voltage screening column.

- `standard_voltage_status` is `OK` when the hierarchy-resolved `required_voltage_v` is less than or equal to the calculated `effective_max_voltage_v`.
- It is `NOK` when the required/actual voltage is higher than the calculated maximum supported voltage from the active standard settings.
- It is `UNKNOWN` when either the required voltage or calculated supported voltage is unavailable.
- `voltage_margin_v = effective_max_voltage_v - required_voltage_v`; positive margin is OK, negative margin is NOK.

This check uses the final voltage hierarchy result, so Zone 1 ↔ Zone 2 voltage priority is respected.


## v0.4.31 Assigned voltage report export and voltage difference

This release improves report traceability for voltage-based clearance review.

- The automatic report package now includes `net_voltage_assignments.csv`.
- The Excel report now includes an **Assigned voltages** sheet.
- The Markdown report now includes an **Assigned Voltages** preview section.
- Main clearance CSV/Excel/Markdown outputs now include `voltage_difference_v`, calculated as `abs(Net A assigned voltage - Net B assigned voltage)` when both assigned voltages are known.
- The large `net_to_net_effective_air_gap_matrix.csv` also includes the voltage difference column, alongside final required voltage/source/zone hierarchy columns.

`voltage_difference_v` is diagnostic information. The final spacing check should still use `required_voltage_v`, because cross-zone pairs intentionally use the higher-priority Zone 1 ↔ Zone 2 working voltage.

## v0.4.30 Geometry Viewer startup fix

- Fixed Geometry Viewer crash when opened from Overview, Critical Pairs, Per-Net Minimum, Effective Net-to-Net, or Debug rows.
- The **Voltage assignment** button callback now belongs to `GeometryViewer` itself, so the viewer finishes constructing its canvas and scrollbars correctly.
- Added a Tk smoke regression test that opens the viewer with the Voltage Assignment callback enabled.

## v0.4.29 Voltage Guessing galvanic zones

Voltage Guessing now has a two-zone galvanic model for isolation-style review:

- Assign selected nets to **Zone 1** or **Zone 2** in the **All Assignments** tab. Shift/Ctrl multi-select is supported for bulk edits.
- Set **Zone 1 ↔ Zone 2 voltage, V** in the Voltage Guessing Overview tab or in the All Assignments detail panel. The default is **1000 V**.
- Press **Apply zone-to-zone voltage** to validate and save the setting to the project assignment JSON. This can be done before any nets are assigned.
- JSON exports include both `galvanic_zone_voltage_v` and the clearer alias `zone_to_zone_voltage_v`; either key is accepted on import/load.
- The zone voltage is treated as a higher-level voltage requirement for any measured pair where one net belongs to Zone 1 and the other belongs to Zone 2.
- Exports include `galvanic_zone_spacing.csv` when analysis measurements and Zone 1/Zone 2 assignments are available. Rows include clearance, required zone voltage, supported effective max voltage, margin, and PASS/FAIL/UNKNOWN status.
- Project assignment JSON, voltage assignment JSON/CSV, CSV import, and settings profile JSON preserve `galvanic_zone` and `galvanic_zone_voltage_v`.


## v0.4.29 Voltage Requirement Hierarchy

Voltage Guessing now resolves one required spacing voltage per measured net pair using a deterministic hierarchy:

1. **Different galvanic zones** → use **Zone 1 ↔ Zone 2 working voltage**.
2. **Same galvanic zone** → use local net/manual/class voltage.
3. **Missing zone assignment** → use local net/manual/class voltage and mark a review warning.

The local voltage resolver is intentionally conservative: it uses the maximum of net A voltage, net B voltage, and the absolute voltage difference. This prevents equal-voltage signal classes such as `3V3` ↔ `3V3` from being treated as `0 V`.

Main spacing CSV/Excel/Markdown reports now include:

- `required_voltage_v`
- `voltage_source`
- `zone_a` / `zone_b`
- `zone_voltage_v`
- `local_voltage_v`
- `net_a_voltage_v` / `net_b_voltage_v`
- `warning`

In the **All Assignments** tab, use **Apply galvanic zone only to selected** or **Clear galvanic zone from selected** to safely assign Zone 1/Zone 2 without overwriting voltage class, voltage value, review state, or notes.

