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
odb-clearance-analyzer-gui
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
0.4.14
```

Recent additions:

- IEC 61558 / IEC 62368 isolation tab.
- Isolated-side net group screening.
- JSON settings export for isolation variables.
- Geometry Viewer Fast mode.
- Zoom min 2/3 button.
- Blocker-dot visualization.
- Compact input/output/analysis controls.
- Accurate dense ground-pour rendering.

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
