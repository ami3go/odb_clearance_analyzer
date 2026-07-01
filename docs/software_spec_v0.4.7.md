# ODB++ Clearance Analyzer Software Specification

**Product name:** ODB++ Clearance Analyzer  
**Specification version:** 0.4.7  
**Codebase version:** 0.4.7  
**Primary package:** `odb_clearance_analyzer`  
**Document purpose:** implementation-level software specification for maintenance, review, and future code generation.

---

## 1. Product Purpose

ODB++ Clearance Analyzer is a Python desktop and command-line tool for analyzing **same-layer PCB copper-to-copper net clearance** from ODB++ design exports.

The tool reconstructs copper geometry from ODB++ feature data, calculates same-layer net-to-net spacing, highlights critical pairs below a user-defined threshold, estimates screening voltage columns, and exports traceable engineering reports.

The application is intended for PCB design review and engineering screening. It is **not** a certified IEC, UL, IPC, or safety-agency compliance engine.

---

## 2. Scope

### 2.1 In Scope

The software shall:

1. Read ODB++ ZIP/TGZ/TAR archives and extracted ODB++ directories.
2. Parse PCB steps, signal layers, features, nets, symbols, attributes, and plated drill/via data where available.
3. Reconstruct same-layer copper geometry using Shapely.
4. Measure net-to-net copper clearance on each analyzed copper layer.
5. Identify critical pairs below a configurable threshold.
6. Calculate per-net minimum spacing.
7. Optionally calculate an **Effective Net-to-Net distance** diagnostic.
8. Decode ODB++ feature attributes into reportable rows.
9. Provide a Tkinter GUI with modern themed tabs.
10. Provide a CLI for scripted/automated usage.
11. Export CSV, Excel, Markdown, and ZIP report packages.
12. Provide an interactive geometry viewer with zoom, pan, layer colors, pad/via overlay, and closest-point visualization.
13. Provide screening voltage estimates:
    - IEC 60664-1-style **Effective max voltage V**
    - IPC-2221A/B-style **IPC-2221A max voltage V**
14. Allow voltage columns to be included or omitted from exported files.
15. Allow per-layer IEC and IPC settings to be reviewed and manually overridden.

### 2.2 Out of Scope

The software shall not claim to:

1. Prove formal IEC 60664-1 compliance.
2. Prove formal IPC-2221A/B compliance.
3. Prove UL compliance.
4. Model full 3D creepage paths.
5. Model component-body, connector-body, relay, optocoupler, cable, or enclosure creepage paths.
6. Treat solder mask or conformal coating as certified insulation unless a project-specific safety process qualifies it.
7. Replace safety engineer review.
8. Infer net voltage classes automatically unless future voltage/net-class input is added.
9. Calculate clearance between non-coplanar layers.
10. Calculate creepage along a true routed surface path around obstacles.

---

## 3. Definitions

| Term | Definition |
|---|---|
| ODB++ | PCB manufacturing/design exchange format containing layers, features, nets, matrix and drill data. |
| Signal layer | Copper layer used for electrical copper geometry analysis. |
| Same-layer clearance | Minimum 2D distance between copper geometry of two different nets on the same signal layer. |
| Critical pair | Net pair with clearance below configured threshold. |
| Per-net minimum | Worst/lowest measured clearance for each net against any other net. |
| Effective Net-to-Net distance | Optional diagnostic that takes the closest-point line between two nets and subtracts copper occupied by intermediate nets on that line. |
| Effective max voltage V | IEC 60664-1-style screening estimate based on CTI, pollution degree, altitude and measured/effective spacing. |
| IPC-2221A max voltage V | IPC-2221A/B-style screening estimate based on layer role, altitude class and measured spacing. |
| External layer | Top/bottom/outside PCB copper layer. |
| Internal layer | Inner PCB copper layer. |
| PD | Pollution degree. |
| CTI | Comparative Tracking Index. |

---

## 4. Technology Stack

The application shall use:

| Area | Requirement |
|---|---|
| Language | Python 3.10+ recommended. |
| GUI | Tkinter / ttk. |
| Geometry engine | Shapely. |
| Spreadsheet export | openpyxl. |
| Packaging | Installable Python package with `pyproject.toml`. |
| CLI entry | `odb-clearance-analyzer`. |
| GUI entry | `odb-clearance-analyzer-gui` / `python -m odb_clearance_analyzer`. |
| Tests | pytest. |
| Source layout | Package directory directly at repository root; no `src/` layout. |

---

## 5. Repository / Package Layout

Expected package layout:

```text
odb_clearance_analyzer_pkg/
├── odb_clearance_analyzer/
│   ├── __init__.py
│   ├── __main__.py
│   ├── analyzer.py
│   ├── cli.py
│   ├── geometry.py
│   ├── geometry_viewer.py
│   ├── gui.py
│   ├── layer_rules.py
│   ├── models.py
│   ├── odb_parser.py
│   ├── reports.py
│   ├── run_gui.py
│   ├── theme.py
│   ├── voltage_estimator.py
│   └── assets/
├── docs/
│   ├── architecture.md
│   └── software_spec_v0.4.4.md
├── tests/
├── README.md
└── pyproject.toml
```

---

## 6. Main Data Models

### 6.1 `AnalysisConfig`

`AnalysisConfig` shall contain all analysis, report and voltage settings.

| Field | Type | Default | Description |
|---|---:|---:|---|
| `odb_path` | `Path` | required | ODB++ input archive/folder. |
| `output_dir` | `Path` | required | Output report directory. |
| `threshold_mm` | `float` | `0.15` | Critical clearance threshold. |
| `include_none_net` | `bool` | `False` | Include `$NONE$` net copper in analysis. |
| `layers` | `list[str] \| None` | `None` | Optional layer subset. |
| `top_critical_limit` | `int` | `1000` | Maximum critical rows shown/export-prioritized. |
| `geometry_resolution` | `int` | `16` | Circle/arc approximation resolution. |
| `precision_grid_mm` | `float \| None` | `1e-6` | Geometry snapping precision. |
| `debug_limit` | `int` | `500` | Max debug rows for suspicious critical pairs. |
| `debug_probe_radius_mm` | `float` | `0.002` | Probe radius for geometry debug attribution. |
| `effective_air_gap_matrix` | `bool` | `False` | Enable Effective Net-to-Net matrix. |
| `cti` | `float` | `175.0` | CTI for IEC-style voltage estimate. |
| `pollution_degree` | `int` | `2` | Base/external pollution degree. |
| `altitude_m` | `float` | `5500.0` | Altitude above sea level in meters. |
| `layer_roles` | `dict[str, str]` | `{}` | IPC role per layer: `internal` or `external`. |
| `layer_pollution_degrees` | `dict[str, int]` | `{}` | IEC pollution degree per layer. |
| `external_conformal_coating` | `bool` | `False` | If true, external IEC layers default to PD2. |
| `metallic_particle_size_mm` | `float` | `0.0` | Conservative external-layer spacing reduction. |
| `export_effective_max_voltage` | `bool` | `True` | Include IEC-style voltage column in exported files. |
| `export_ipc2221a_max_voltage` | `bool` | `True` | Include IPC-style voltage column in exported files. |

### 6.2 `MeasurementRecord`

Represents one measured same-layer net pair.

| Field | Description |
|---|---|
| `layer` | Signal layer name. |
| `net_a`, `net_b` | Net names. |
| `clearance_mm` | Direct same-layer copper-to-copper clearance. |
| `x_a_mm`, `y_a_mm` | Closest point on Net A. |
| `x_b_mm`, `y_b_mm` | Closest point on Net B. |
| `effective_max_voltage_v` | IEC 60664-1-style screening voltage estimate. |
| `ipc2221a_max_voltage_v` | IPC-2221A/B-style screening voltage estimate. |

### 6.3 `PerNetMinimum`

Represents the worst clearance for a net.

| Field | Description |
|---|---|
| `net` | Net name. |
| `min_clearance_mm` | Minimum measured clearance for this net. |
| `layer` | Layer where minimum was found. |
| `other_net` | Opposing net. |
| `x_this_mm`, `y_this_mm` | Point on this net. |
| `x_other_mm`, `y_other_mm` | Point on other net. |
| `effective_max_voltage_v` | IEC-style estimate at this minimum. |
| `ipc2221a_max_voltage_v` | IPC-style estimate at this minimum. |

### 6.4 `EffectiveAirGapRecord`

Represents optional Effective Net-to-Net diagnostic row.

| Field | Description |
|---|---|
| `layer` | Signal layer. |
| `net_a`, `net_b` | Net names. |
| `direct_clearance_mm` | Normal geometric clearance. |
| `effective_air_gap_mm` | Closest-line length minus intermediate copper. |
| `copper_blocked_length_mm` | Amount of line blocked by other copper. |
| `copper_on_path` | True when intermediate copper intersects closest-line path. |
| `blocker_nets` | Nets intersecting the path. |
| `effective_max_voltage_v` | IEC-style voltage estimate based on effective gap. |
| `ipc2221a_max_voltage_v` | IPC-style voltage estimate based on effective gap. |
| `x_a_mm`, `y_a_mm`, `x_b_mm`, `y_b_mm` | Closest points. |

### 6.5 `AnalysisResult`

Contains complete output:

- `config`
- `job`
- `measurements`
- `per_net_minimum`
- `critical_measurements`
- `layer_net_counts`
- `geometry_debug_records`
- `effective_air_gap_records`
- `skipped_features`
- `warnings`
- `report_files`
- `net_geometry_by_layer`
- `via_geometry_by_layer`

---

## 7. ODB++ Input Requirements

### 7.1 Supported Input Forms

The software shall accept:

- `.zip`
- `.tgz`
- `.tar.gz`
- `.tar`
- extracted ODB++ folder

### 7.2 ODB++ Metadata Read

The GUI shall provide **Read ODB++** buttons in relevant tabs.

When pressed, software shall parse metadata without requiring full report analysis and populate:

- source name
- step name
- number of signal layers
- signal layer names
- approximate PCB bounding-box size
- net count
- plated drill layers
- ODB++ matrix / stackup rows when present
- default IPC layer roles
- default IEC layer pollution degrees

### 7.3 Approximate PCB Size

Approximate PCB size shall be calculated from parsed signal-layer feature geometry bounding boxes.

It is a geometry bounding-box estimate and not a formal board-outline parser unless the ODB++ input provides such data and future code explicitly uses it.

---

## 8. Layer Role Auto-Detection

Layer-role detection is implemented in `layer_rules.py`.

### 8.1 Role Values

Each signal layer shall be assigned one of:

- `external`
- `internal`

### 8.2 Default Detection Rules

The software shall recognize common naming patterns:

| Layer name pattern | Default role |
|---|---|
| `Top`, `F.CU`, `F_CU`, `Front`, `TopCopper`, `Signal1`, `L1`, `Layer1` | `external` |
| `Bottom`, `B.CU`, `B_CU`, `Back`, `Bot`, last signal layer | `external` |
| `Inner1`, `Inner2`, `Internal`, `In1`, `Plane`, middle `SignalN`, middle `LayerN` | `internal` |

Fallback rule for stack order:

- two-layer board: both layers external
- multilayer board: first and last signal layers external, middle layers internal

### 8.3 User Overrides

The GUI shall allow the user to:

- auto-detect roles
- set selected rows as external
- set selected rows as internal
- double-click a row to toggle internal/external

The CLI shall support:

```bash
--layer-role F.CU=external
--layer-role Inner1=internal
```

---

## 9. IEC 60664-1 Tab Requirements

The **IEC 60664-1** tab replaces the earlier generic Settings tab.

### 9.1 Visible Controls

The IEC tab shall visibly show all IEC-style voltage estimate controls without hiding them in a collapsed panel:

- CTI
- External/base pollution degree
- External conformal coating checkbox
- Metallic particles size in mm
- Export Effective max voltage V checkbox
- Current IEC settings preview
- Read ODB++
- Auto-assign IEC PD
- Set selected PD1
- Set selected PD2
- Set selected PD3
- Set selected PD4
- Recalculate voltage columns
- Layer pollution-degree table

### 9.2 IEC Layer Pollution-Degree Table

The table shall be visible below the controls. Columns:

| Column | Description |
|---|---|
| `#` | Layer order. |
| `Layer` | Signal layer name. |
| `Role` | `external` or `internal`, derived from IPC-2221A layer-role table. |
| `IEC pollution degree` | PD1, PD2, PD3 or PD4. |
| `External particle correction mm` | Particle correction applied to external layer. |
| `Default/override reason` | Auto/manual reason text. |

Before ODB++ metadata is loaded, the table shall show a placeholder row:

```text
Read ODB++ to populate layer table
```

### 9.3 IEC Auto-Assignment Rules

IEC pollution-degree assignment shall use IPC layer roles as input:

| Condition | Default IEC pollution degree |
|---|---|
| internal layer | PD1 |
| external layer, no conformal coating | selected external/base pollution degree |
| external layer, conformal coating present | PD2 |

The user can override each layer manually to PD1, PD2, PD3 or PD4.

### 9.4 Conformal Coating Behavior

When **External conformal coating** is enabled:

- external layers are automatically assigned PD2
- internal layer PD assignments remain unchanged
- user may still manually override rows if needed

This is a screening behavior and not a claim that a coating is certified as insulation.

### 9.5 Metallic Particle Size

The IEC tab shall provide:

```text
Metallic particles, mm
```

For external layers only, before calculating `Effective max voltage V`, the software shall apply:

```text
effective_spacing_mm = max(0, measured_spacing_mm - metallic_particle_size_mm)
```

For internal layers:

```text
effective_spacing_mm = measured_spacing_mm
```

### 9.6 IEC Recalculation

The GUI **Recalculate voltage columns** button shall update displayed voltage columns after settings changes.

It shall update:

- full measurement records
- critical measurement records
- per-net minimum records
- effective net-to-net records
- in-memory `AnalysisConfig`

To regenerate CSV/XLSX/Markdown files with updated settings, user shall rerun the analysis.

---

## 10. IPC-2221A Tab Requirements

The **IPC-2221A** tab shall contain settings used by IPC-style voltage estimate.

### 10.1 Visible Controls

The tab shall include:

- Altitude above sea level, m
- Export IPC-2221A max voltage V checkbox
- Read ODB++
- Auto-detect layer roles
- Set selected external
- Set selected internal
- Recalculate voltage columns
- Layer role table

### 10.2 Layer Role Table

Columns:

| Column | Description |
|---|---|
| `#` | Layer order. |
| `Layer` | Signal layer name. |
| `Role` | `external` or `internal`. |
| `IPC-2221A class` | Internal/external/high-altitude class. |
| `Default/override reason` | Auto/manual reason text. |

### 10.3 IPC Altitude Behavior

For IPC-style estimate:

- `internal` layer maps to internal conductor class.
- `external` layer maps to external low-altitude class at altitude <= 3050 m.
- `external` layer maps to external high-altitude class at altitude > 3050 m.

---

## 11. Voltage Estimate Models

### 11.1 General Disclaimer

Both voltage columns are engineering screening estimates. They shall not be presented as formal standards compliance.

Reports shall include warnings/limitations explaining this.

### 11.2 Effective max voltage V

`Effective max voltage V` is an IEC 60664-1-style screening estimate.

Inputs:

- measured or effective spacing in mm
- CTI
- material group from CTI
- per-layer pollution degree
- altitude
- external-layer metallic-particle correction

The estimate shall be:

```text
min(clearance_limited_voltage, creepage_limited_voltage)
```

Where:

- clearance estimate uses altitude-corrected spacing
- creepage estimate uses CTI/material group and pollution degree

#### 11.2.1 CTI Material Group Mapping

| CTI | Material group |
|---:|---|
| >= 600 | I |
| >= 400 | II |
| >= 175 | IIIa |
| >= 100 | IIIb |
| < 100 | below IIIb |

#### 11.2.2 Pollution Degree Scaling

The current screening model uses:

| Pollution degree | Scale |
|---:|---:|
| PD1 | 0.55 |
| PD2 | 1.00 |
| PD3 | 1.65 |
| PD4 | 2.40 |

#### 11.2.3 Material Scaling

| Material group | Scale |
|---|---:|
| I | 0.70 |
| II | 0.85 |
| IIIa | 1.00 |
| IIIb | 1.12 |
| below IIIb | 1.35 |

#### 11.2.4 Altitude Correction Table

| Altitude m | Factor |
|---:|---:|
| 0 | 1.00 |
| 2000 | 1.00 |
| 3000 | 1.14 |
| 4000 | 1.29 |
| 5000 | 1.48 |
| 6000 | 1.70 |
| 7000 | 1.95 |
| 8000 | 2.25 |
| 10000 | 2.90 |

Values between points shall be linearly interpolated.

### 11.3 IPC-2221A max voltage V

`IPC-2221A max voltage V` is an IPC-2221A/B-style conductor-spacing screening estimate.

Inputs:

- measured spacing in mm
- layer role: internal or external
- altitude

Layer class:

- internal -> B1-style internal class
- external <= 3050 m -> B2-style external class
- external > 3050 m -> B3-style external high-altitude class

The current implementation uses discrete IPC-style spacing ranges up to 500 V and per-volt increments above 500 V. The estimate is capped at 5000 V.

### 11.4 Export Control

Voltage columns shall be calculated in memory, but exported only when enabled:

| Checkbox / CLI | Exported column |
|---|---|
| Include Effective max voltage V / `--export-effective-max-voltage` | `effective_max_voltage_v` |
| Include IPC-2221A max voltage V / `--export-ipc2221a-max-voltage` | `ipc2221a_max_voltage_v` |

CLI negative forms:

```bash
--no-export-effective-max-voltage
--no-export-ipc2221a-max-voltage
```

---

## 12. Geometry Reconstruction Requirements

### 12.1 Shape Support

The ODB++ parser/geometry layer shall support common feature geometries including:

- lines/traces
- arcs where supported
- pads
- circular/oval approximations
- polygons/surfaces
- rectangular and rounded rectangular pads using conservative approximations
- plated drill/via features projected across applicable span layers

Unsupported or malformed features shall be counted and reported as skipped/warnings rather than crashing analysis.

### 12.2 Geometry Union

For each layer/net, parsed copper features shall be combined into a Shapely geometry.

The analysis shall measure between unioned per-net geometries, not individual raw features, so the measured distance reflects copper belonging to the net.

### 12.3 Precision

The software shall support geometry precision snapping via `precision_grid_mm`.

Default:

```text
1e-6 mm
```

### 12.4 Measurement

For each signal layer:

1. Build dictionary of net -> geometry.
2. Remove empty geometries.
3. Optionally remove `$NONE$` unless `include_none_net` is true.
4. Measure pairwise distances between nets.
5. Store clearance and closest points.
6. Add voltage estimates.
7. Sort results by clearance.

### 12.5 Critical Pair Identification

A pair is critical when:

```text
clearance_mm < threshold_mm
```

Default threshold:

```text
0.15 mm
```

### 12.6 Per-Net Minimum

For each net, software shall store the lowest clearance where the net appears as Net A or Net B.

---

## 13. Effective Net-to-Net Distance Diagnostic

When enabled, the analyzer shall calculate an additional matrix.

For each measured net pair:

1. Take the closest-point line between the two nets.
2. Identify copper from other nets intersecting the line.
3. Calculate copper-blocked length.
4. Calculate:

```text
effective_air_gap_mm = max(0, direct_clearance_mm - copper_blocked_length_mm)
```

5. Record blocker nets.
6. Estimate voltage columns using the effective air gap.

This feature is diagnostic only. It is not a true routed creepage solver.

The CLI flag is:

```bash
--effective-air-gap-matrix
```

The GUI label is:

```text
Effective Net-to-Net distance
```

---

## 14. GUI Specification

### 14.1 Main Window

The GUI shall show:

- software version in main window title
- software version in main header
- app icon where available
- modern Material-like theme
- light/dark theme toggle
- compact, collapsible **Input and output** section
- compact, collapsible **Analysis** section
- full-width Reports and diagnostics notebook

### 14.2 Top Sections

#### Input and output

Fields/buttons:

- ODB++ path
- Browse
- Read ODB++
- Output directory
- Browse

#### Analysis

Controls:

- threshold mm
- include `$NONE$`
- effective net-to-net matrix
- debug limit
- run analysis
- cancel analysis
- open output folder/report where supported

### 14.3 Report and Diagnostic Tab Order

The main notebook shall use this tab order:

1. IEC 60664-1
2. IPC-2221A
3. Summary
4. Critical pairs
5. Per-net minimum
6. Effective Net-to-Net distance
7. Feature attributes
8. Debug zero/overlap
9. Log

### 14.4 Table Sorting

All GUI tables shall support click-to-sort by column header.

Behavior:

- first click sorts ascending
- second click reverses
- numeric columns sort numerically
- row colors/tags stay with rows
- geometry-view row links remain correct after sorting

### 14.5 Critical Pairs Tab

Columns:

- Layer
- Net A
- Net B
- Clearance mm
- Effective max voltage V
- IPC-2221A max voltage V
- Point A mm
- Point B mm

Features:

- View selected geometry
- double-click row opens geometry viewer
- clearance gradient coloring option from main GUI

### 14.6 Per-Net Minimum Tab

Columns:

- Net
- Minimum clearance mm
- Effective max voltage V
- IPC-2221A max voltage V
- Layer
- Other net
- This point
- Other point

Features:

- View selected geometry
- double-click row opens geometry viewer

### 14.7 Effective Net-to-Net Distance Tab

Columns:

- Layer
- Net A
- Net B
- Direct clearance mm
- Effective Net-to-Net distance mm
- Effective max voltage V
- IPC-2221A max voltage V
- Copper blocked mm
- Copper on path
- Blocker nets
- Point A
- Point B

Features:

- View selected geometry
- double-click row opens geometry viewer

### 14.8 Feature Attributes Tab

Shall list decoded ODB++ feature attributes with raw traceability.

### 14.9 Debug Zero/Overlap Tab

Shall show suspicious zero/overlap rows and geometry diagnostic information.

### 14.10 Log Tab

Shall show progress, warnings and status messages.

---

## 15. Geometry Viewer Specification

### 15.1 Purpose

The Geometry Viewer shall allow visual inspection of reconstructed copper geometry used by the analysis engine.

### 15.2 Required Features

The viewer shall support:

- layer selection
- filtered Net A / Net B selection
- click copper to select Net A and Net B
- swap nets
- show all nets
- show/hide other nets
- show/hide component pads
- show/hide vias
- show/hide measurement points
- zoom with mouse wheel
- pan with mouse drag
- fit to layer
- fit to selection
- closest-point line and distance label
- overlap/touch visualization
- coordinate/status display

### 15.3 Automatic Layer Colors

The viewer shall assign deterministic high-contrast colors to each signal layer.

Typical defaults:

| Layer | Color |
|---|---|
| Top / F.CU / Signal1 / L1 | red |
| Bottom / B.CU / last signal layer | blue |
| Inner layers | green, yellow/gold, orange, violet, cyan, magenta, lime, rotating |

The active layer color shall be shown beside the layer selector.

Non-selected copper, component pads and vias shall use the active layer color.

Net A and Net B shall keep special highlight colors for clear selected-pair inspection.

### 15.4 Component Pad Overlay

The viewer shall draw component pad features over merged net copper so individual pads remain visible.

### 15.5 Via Overlay

The viewer shall draw plated-via pad geometry as overlay on active layers when available.

---

## 16. Report Export Specification

### 16.1 Output Directory

Output directory defaults to:

```text
clearance_report
```

### 16.2 Generated Files

The report writer shall generate:

| File | Description |
|---|---|
| `net_to_net_measurements_full.csv` | All measured pairs. |
| `net_to_net_critical_under_<threshold>mm.csv` | Critical rows below threshold. |
| `net_to_net_per_net_minimum.csv` | Per-net minimum table. |
| `net_to_net_effective_air_gap_matrix.csv` | Effective Net-to-Net distance rows when enabled. |
| `odb_feature_attributes.csv` | Decoded ODB++ attributes. |
| `geometry_debug_critical_pairs.csv` | Debug geometry diagnostics. |
| `net_to_net_clearance_report.md` | Human-readable report. |
| `net_to_net_clearance_report.xlsx` | Excel workbook. |
| `net_to_net_report_package.zip` | ZIP containing report files. |

### 16.3 Conditional Voltage Columns

When `export_effective_max_voltage` is false, exports shall omit:

```text
effective_max_voltage_v
```

When `export_ipc2221a_max_voltage` is false, exports shall omit:

```text
ipc2221a_max_voltage_v
```

GUI may still display calculated voltage values.

### 16.4 Markdown Report

Markdown report shall include:

- generation timestamp
- source file
- step
- signal layers
- threshold
- `$NONE$` inclusion
- effective net-to-net enabled state
- IEC settings
- IEC per-layer pollution degrees
- conformal coating state
- metallic particle size
- IPC layer roles
- voltage export flags
- summary counts
- layer net counts
- most critical measurements
- geometry debug
- effective net-to-net section when available
- feature attribute decoding section
- limitations and warnings

### 16.5 Excel Workbook

Excel workbook shall include sheets:

- Summary
- Critical
- All measurements
- Per net minimum
- Effective Net-to-Net distance when available
- Geometry debug
- Feature attributes
- Warnings

---

## 17. CLI Specification

Command:

```bash
odb-clearance-analyzer <odb_path> [options]
```

### 17.1 Positional Argument

| Argument | Description |
|---|---|
| `odb_path` | ODB++ archive or extracted directory. |

### 17.2 Options

| Option | Default | Description |
|---|---:|---|
| `-o`, `--output` | `clearance_report` | Output directory. |
| `-t`, `--threshold` | `0.6` | Critical threshold in mm. |
| `--include-none` | false | Include `$NONE$` copper. |
| `--cti` | `175` | CTI for Effective max voltage estimate. |
| `--pollution-degree` | `2` | Base/external pollution degree. |
| `--altitude-m` | `5500` | Altitude in meters. |
| `--external-conformal-coating` | false | Auto-assign external IEC layers as PD2. |
| `--metallic-particle-size-mm` | `0` | Subtract particle size from external-layer spacing. |
| `--layer-pollution-degree LAYER=1\|2\|3\|4` | repeatable | Override IEC PD by layer. |
| `--layers LAYER...` | all | Layer subset. |
| `--geometry-resolution` | `16` | Circle/oval approximation resolution. |
| `--debug-limit` | `500` | Max geometry debug records. |
| `--effective-air-gap-matrix` | false | Enable Effective Net-to-Net matrix. |
| `--layer-role LAYER=internal\|external` | repeatable | Override IPC layer role. |
| `--export-effective-max-voltage` / `--no-export-effective-max-voltage` | true | Export IEC-style voltage column. |
| `--export-ipc2221a-max-voltage` / `--no-export-ipc2221a-max-voltage` | true | Export IPC-style voltage column. |

### 17.3 CLI Example

```bash
odb-clearance-analyzer board_odb.zip \
  --output clearance_report \
  --threshold 0.6 \
  --cti 175 \
  --pollution-degree 2 \
  --altitude-m 5500 \
  --external-conformal-coating \
  --metallic-particle-size-mm 0.1 \
  --layer-role F.CU=external \
  --layer-role Inner1=internal \
  --layer-pollution-degree F.CU=2 \
  --effective-air-gap-matrix
```

---

## 18. Error Handling Requirements

The software shall:

1. Report parser warnings without stopping analysis when possible.
2. Skip unsupported features and count them by layer.
3. Avoid crashing on malformed optional attributes.
4. Allow cancellation from GUI.
5. Restore GUI run buttons after analysis/cancellation/error.
6. Display errors using message boxes in GUI.
7. Return non-zero exit code in CLI on failure.
8. Always close temporary extraction folders/parsers.

---

## 19. Performance Requirements

The software should:

1. Avoid unnecessary repeated ODB++ parsing where possible.
2. Use write-only Excel mode for large jobs.
3. Limit displayed GUI rows to practical counts, typically first 1000.
4. Keep long analysis in worker thread so GUI remains responsive.
5. Provide progress messages during parsing, geometry building, measuring and export.
6. Allow optional Effective Net-to-Net matrix because it can be expensive.

---

## 20. Validation Requirements

Minimum validation shall include:

1. Unit tests for geometry/symbol parsing.
2. Tests for plated drill/via projection.
3. Tests for rounded rectangle pad behavior.
4. Import smoke test for GUI.
5. CLI `--help` smoke test.
6. Report export validation for:
   - voltage columns enabled
   - voltage columns disabled
   - only one voltage column enabled
7. Analysis smoke test on representative ODB++ file.
8. Geometry Viewer import smoke test.
9. Static GUI check for required tabs and visible IEC controls.

Current validation status for v0.4.4:

```text
18 tests passed
GUI import smoke test passed
IEC controls visible
IEC table placeholder present
```

---

## 21. Known Limitations

1. The analysis is same-layer 2D copper-to-copper geometry.
2. True creepage path over PCB surface is not solved.
3. Component/connector body creepage is not included.
4. Solder mask is not treated as qualified insulation.
5. Conformal coating behavior is a configurable screening assumption, not certification.
6. Metallic particle input is a conservative user-specified subtraction model.
7. IPC and IEC voltage estimates are approximate screening estimates.
8. Rounded pads and symbols depend on ODB++ feature/symbol data quality.
9. Large designs can take significant time due to pairwise distance calculations.
10. Effective Net-to-Net distance is diagnostic, not a full physical insulation path model.

---

## 22. Future Improvement Candidates

Recommended future enhancements:

1. Add voltage/net-class input table.
2. Add pass/fail rules by net class instead of only measured clearance.
3. Add project-specific rule profiles.
4. Replace screening voltage curves with verified project-approved tables.
5. Add board outline extraction.
6. Add true creepage path solver over non-copper areas.
7. Add solder mask / coating qualification metadata model.
8. Add GUI persistence for settings.
9. Add packaging recipe for Windows executable.
10. Add multi-processing acceleration for large net-pair calculations.
11. Add DRC-style export for EDA back-annotation.
12. Add graphical PDF report.

---

## 23. Acceptance Criteria

The codebase satisfies this specification when:

1. GUI launches and shows version in header/title.
2. Main tab order matches specification.
3. IEC 60664-1 tab shows CTI, base PD, conformal coating, metallic particle size, export checkbox, settings preview and visible layer table.
4. IPC-2221A tab shows altitude, IPC export checkbox and layer role table.
5. Read ODB++ populates metadata, layer roles and IEC PD rows.
6. Full analysis generates all required tables.
7. Sorting works in every table.
8. View selected geometry works after table sorting.
9. Geometry Viewer uses automatic layer colors.
10. Reports are exported with voltage columns according to checkbox/CLI flags.
11. CLI supports all specified options.
12. Tests pass.
13. Limitations are visible in reports/documentation.

---

## 24. Safety / Compliance Statement

This tool is for engineering screening and design investigation. Results shall be reviewed by a qualified engineer before being used for safety decisions. The software shall not label any design as IEC, IPC, UL, CE or regulatory-compliant without an external qualification process and project-specific rule approval.



## 25. v0.4.5 Maintenance Fix

Fixed missing `ClearanceAnalyzer._default_iec_pollution_degree` helper used during IEC per-layer default assignment at analysis startup.


## v0.4.6 Maintenance Update

Default critical threshold changed to 0.15 mm. ODB++ PCB outline/profile is parsed into job geometry and shown in the Geometry Viewer as a high-contrast overlay. Primary source is `steps/<step>/profile`; fallback sources include common mechanical outline layers such as `edge.cuts`, `outline`, and `board_outline`.


## v0.4.7 Compact Header Status Panel

The main header is divided into a left identity section and a right live status/statistics section. The right section contains status text, an indeterminate progress bar and compact key statistics such as layer count, net count, PCB size, measured pairs, critical count and minimum clearance. The previous separate status/progress rows below the analysis controls are removed.
