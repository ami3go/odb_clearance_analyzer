# ODB++ Clearance Analyzer — User Manual

Version: 0.4.14  
Document type: end-user operating manual

---

## 1. Purpose

ODB++ Clearance Analyzer is a desktop and command-line application for reviewing PCB copper spacing from ODB++ data.

It helps you:

- Load an ODB++ PCB export.
- Reconstruct copper geometry by layer and net.
- Measure same-layer net-to-net copper clearance.
- Find critical copper pairs below a selected threshold.
- Inspect geometry visually.
- Export engineering reports.
- Save and reload project settings.
- Perform screening checks for IPC-2221A, IEC 60664-1, and IEC 61558 / IEC 62368 isolation spacing.

> **Important safety note**  
> This application is an engineering screening tool. It does not certify IEC, UL, IPC, DIN, ANSI, EN, or any other compliance by itself. Final decisions must be checked against the applicable standard edition, product category, certification body, design rules, and lab interpretation.

---

## 2. Supported input files

The application accepts:

- ODB++ `.zip` archive.
- ODB++ `.tgz` or `.tar` archive, if supported by your package version.
- Extracted ODB++ folder.

Typical ODB++ content contains folders such as:

```text
steps/
matrix/
fonts/
symbols/
```

The tool expects copper layer data and net information to be present in the export.

---

## 3. Starting the application

### 3.1 From installed Python package

Run:

```bash
odb-clearance-analyzer-gui
```

Or:

```bash
python -m odb_clearance_analyzer.gui
```

### 3.2 From Windows executable

If you built with PyInstaller `--onedir`, run the executable from inside the generated folder:

```text
dist/
  ODBClearanceAnalyzer/
    ODBClearanceAnalyzer.exe
    _internal/
      python313.dll
      ...
```

Do not copy only the `.exe`. Copy the full `ODBClearanceAnalyzer` folder.

---

## 4. Main window overview

The main window contains:

1. **Input, output and analysis** card.
2. **IEC 60664-1** tab.
3. **IPC-2221A** tab.
4. **IEC 61558 / IEC 62368** tab.
5. **Settings** tab.
6. **Summary** tab.
7. **Critical pairs** tab.
8. **Per-net minimum** tab.
9. **Effective Net-to-Net distance** tab.
10. **Feature attributes** tab.
11. **Debug zero/overlap** tab.
12. **Log** tab.

The top header shows status, progress, and key statistics.

---

## 5. Basic workflow

### Step 1 — Select ODB++ file or folder

In the **Input, output and analysis** card:

1. Click **Browse** next to **ODB++ archive/folder**.
2. Select your ODB++ ZIP archive or extracted folder.
3. Click **Read ODB++**.

The application reads metadata and populates layer-related tables.

### Step 2 — Select output folder

1. Click **Browse** next to **Output folder**.
2. Choose where reports should be written.

Default output folder is usually:

```text
clearance_report
```

### Step 3 — Set critical threshold

Set **Critical threshold, mm**.

Example:

```text
0.15
```

This means any measured same-layer copper spacing below `0.15 mm` is listed as critical.

The threshold field is highlighted in light yellow because it strongly affects result interpretation.

### Step 4 — Select optional analysis settings

Optional checkboxes:

- **Include $NONE$ net**  
  Includes copper features with no resolved net name.

- **Effective Net-to-Net distance**  
  Adds a diagnostic matrix that checks whether other copper lies on the direct line between two nets.

- **Dark theme**  
  Switches the UI theme.

### Step 5 — Run analysis

Click:

```text
Run analysis
```

The application parses the ODB++ geometry, reconstructs copper shapes, measures net spacing, and writes output files.

### Step 6 — Review results

Start with:

- **Summary**
- **Critical pairs**
- **Per-net minimum**
- **Geometry Viewer**

---

## 6. Input, output and analysis controls

### ODB++ archive/folder

Path to the PCB ODB++ export.

### Output folder

Folder where all report files will be generated.

### Critical threshold, mm

The limit used to classify a measured clearance as critical.

Example:

```text
0.15 mm
```

If a pair has:

```text
Measured clearance = 0.12 mm
Threshold = 0.15 mm
```

then it appears in the critical list.

### Include $NONE$ net

ODB++ exports sometimes include copper without a net assignment. Enable this if you want to include those geometries in spacing checks.

Use with care: `$NONE$` may include mechanical or non-electrical copper depending on the ODB++ export.

### Effective Net-to-Net distance

When enabled, the tool calculates additional line-path diagnostics between net pairs.

It checks whether other copper blocks part of the direct air-gap path between two net geometries.

---

## 7. IEC 60664-1 tab

The **IEC 60664-1** tab is used for insulation coordination screening.

### Adjustable parameters

- **CTI**
- **External/base pollution degree**
- **Metallic particles, mm**
- **External conformal coating**
- **Export Effective max voltage V**
- **Per-layer IEC pollution degree**

### Layer pollution-degree table

The table shows each signal layer and the assigned IEC pollution degree.

Typical logic:

- Internal layers can be assigned as pollution degree 1.
- External layers use the selected base pollution degree.
- External layers with conformal coating can be assigned as pollution degree 2.

You can manually override the pollution degree per layer.

### Buttons

- **Read ODB++**  
  Reads ODB++ metadata and updates layer tables.

- **Auto-assign IEC PD**  
  Automatically assigns pollution degrees based on layer role and coating settings.

- **Set selected PD1 / PD2 / PD3 / PD4**  
  Manually changes the selected layer rows.

- **Recalculate voltage columns**  
  Recomputes voltage estimate columns using the current settings.

---

## 8. IPC-2221A tab

The **IPC-2221A** tab is used for PCB spacing screening based on layer roles.

### Adjustable parameters

- **Altitude above sea level, m**
- **Export IPC-2221A max voltage V**
- Layer role assignment:
  - `internal`
  - `external`

### Layer role table

Each copper layer is assigned a role.

Common examples:

```text
F.CU → external
B.CU → external
In1.CU → internal
In2.CU → internal
```

### Buttons

- **Read ODB++**
- **Auto-detect layer roles**
- **Set selected external**
- **Set selected internal**
- **Recalculate voltage columns**

---

## 9. IEC 61558 / IEC 62368 tab

The **IEC 61558 / IEC 62368** tab is used for transformer or isolation-barrier screening.

This tab answers a common question:

```text
Do all nets on the isolated side have enough spacing to every other net?
```

### 9.1 Typical use case

Example:

- Primary side:
  - `L`
  - `N`
  - `PRI_SW`
  - `HV+`
  - `HV-`

- Isolated secondary side:
  - `SEC_GND`
  - `SEC+`
  - `SEC-`

You enter the secondary-side nets as the isolated group. The tool checks those nets against every other net on the PCB on each same copper layer.

### 9.2 Isolated-side nets input

Enter net names separated by new lines, commas, semicolons, or spaces.

Example:

```text
SEC_GND
SEC+
SEC-
```

or:

```text
SEC_GND, SEC+, SEC-
```

### 9.3 Adjustable variables

The tab includes:

- **Standard**
  - IEC 62368-1
  - IEC 61558
  - IEC 62368-1 + IEC 61558 note

- **Insulation type**
  - Functional
  - Basic
  - Supplementary
  - Reinforced

- **Group name**
  - Example: `Isolated side`

- **Overvoltage category**
  - I
  - II
  - III
  - IV

- **Working voltage V RMS/DC**

- **Peak / recurring voltage V**

- **Impulse voltage V**

- **Altitude m**

- **Pollution degree**

- **Material group / CTI class**

- **CTI**

- **Safety factor**

- **Required clearance mm**

- **Required creepage mm**

### 9.4 Required spacing calculation

The tool calculates the governing required spacing as:

```text
required_spacing_mm = max(required_clearance_mm, required_creepage_mm) × safety_factor
```

Example:

```text
required_clearance_mm = 1.0
required_creepage_mm = 1.5
safety_factor = 1.2
```

Result:

```text
required_spacing_mm = max(1.0, 1.5) × 1.2 = 1.8 mm
```

### 9.5 Calculate isolated-side spacing

Click:

```text
Calculate isolated-side spacing
```

The result table shows:

- Group.
- Layer.
- Isolated net.
- Other net.
- Measured mm.
- Required clearance mm.
- Required creepage mm.
- Required spacing mm.
- Margin mm.
- Result.
- Standard.

### 9.6 Pass/fail meaning

Margin is calculated as:

```text
margin_mm = measured_mm - required_spacing_mm
```

If:

```text
margin_mm >= 0
```

then:

```text
PASS
```

If:

```text
margin_mm < 0
```

then:

```text
FAIL
```

### 9.7 Open selected row in Geometry Viewer

Select a row and click:

```text
Open selected in geometry viewer
```

The Geometry Viewer opens the selected isolated net and the selected other net.

### 9.8 Isolation-tab limitations

The isolation tab performs same-layer PCB copper spacing screening.

It does not evaluate:

- Transformer internal construction.
- Bobbin creepage.
- Component body creepage.
- Air distance around component packages.
- Slots unless reflected in geometry.
- Cross-layer dielectric spacing.
- Full IEC 61558 or IEC 62368 table logic.

You must enter the correct required clearance and creepage values from the applicable standard and product context.

---

## 10. Settings tab

The **Settings** tab manages project settings and display diagnostics.

### 10.1 Diagnostics / display

Includes:

- **Clearance gradient**
- **Debug rows**

Clearance gradient is enabled by default.

### 10.2 Load settings JSON

Loads a previously exported settings file.

Click:

```text
Load settings JSON
```

Then select:

```text
analysis_settings.json
```

or another saved settings profile.

### 10.3 Export current settings JSON

Writes the current GUI settings to a JSON file.

Click:

```text
Export current settings JSON
```

### 10.4 Refresh preview

Updates the JSON preview shown in the Settings tab.

### 10.5 Automatic settings export

Every analysis automatically writes:

```text
analysis_settings.json
```

to the output folder.

This file includes:

- Input/output paths.
- Threshold.
- IEC 60664-1 settings.
- IPC-2221A settings.
- Layer role assignments.
- Per-layer pollution-degree assignments.
- IEC 61558 / IEC 62368 isolation settings.
- Export options.

---

## 11. Summary tab

The **Summary** tab shows high-level analysis information:

- ODB++ source.
- Step name.
- Layers.
- Measured pair count.
- Critical count.
- Minimum clearance.
- PCB outline source.
- IEC settings.
- IPC settings.
- Exported report files.
- Output folder.

Use this tab first after each analysis.

---

## 12. Critical pairs tab

The **Critical pairs** tab shows all net pairs below the critical threshold.

Columns include:

- Layer.
- Net A.
- Net B.
- Clearance mm.
- Effective max voltage estimate.
- IPC-2221A max voltage estimate.
- Point A.
- Point B.

### Open critical row in Geometry Viewer

Select a row and use the available geometry-viewer action. The viewer opens focused on that net pair.

---

## 13. Per-net minimum tab

The **Per-net minimum** tab shows the minimum spacing found for each net.

This helps identify the closest neighbor of each net.

Useful for quickly answering:

```text
What is the worst-case spacing for this net?
```

---

## 14. Effective Net-to-Net distance tab

This tab is filled when **Effective Net-to-Net distance** is enabled.

It shows whether another copper object lies on the direct straight-line path between two net geometries.

Columns include:

- Layer.
- Net A.
- Net B.
- Direct clearance mm.
- Effective air gap mm.
- Blocked copper length.
- Copper on path.
- Blocker nets.
- Point A.
- Point B.

This is useful when the nearest straight-line path is interrupted by other copper.

---

## 15. Feature attributes tab

This tab shows decoded ODB++ feature attributes.

It can help debug:

- Net mapping.
- Feature type.
- Symbol name.
- Raw attributes.
- Decoded attributes.

---

## 16. Debug zero/overlap tab

This tab gives extra geometry diagnostics for suspicious cases, especially zero or overlapping clearances.

It can help answer:

- Which features are near the reported point?
- Was there a negative/cutout feature nearby?
- Is the zero clearance caused by real overlap or missing cutout interpretation?

The number of debug rows is controlled in the **Settings** tab.

---

## 17. Log tab

The **Log** tab records analysis progress and warnings.

Use it when:

- Analysis fails.
- A layer is not parsed correctly.
- Geometry reconstruction gives unexpected results.
- Reports are not generated.

---

## 18. Geometry Viewer user guide

### 18.1 Opening the Geometry Viewer

You can open it from:

- Overview button.
- Critical pairs table.
- Per-net minimum table.
- Effective Net-to-Net table.
- Debug table.
- Isolation table.

### 18.2 Basic controls

- Mouse wheel: zoom.
- Left click copper: select Net A or Net B.
- Drag: pan.
- Net filter boxes: search for nets.
- Layer selector: switch copper layer.

### 18.3 Main buttons

#### Redraw

Refreshes the current view.

#### Fit

Fits selected geometry into the view.

#### Zoom min 2/3

Calculates the exact minimum clearance between selected Net A and Net B, centers the view on the exact nearest-point midpoint, and sets the zoom so the clearance line uses about two thirds of the available canvas window length.

Use this when you want to inspect the exact smallest clearance location.

#### Swap

Swaps Net A and Net B.

#### Show all nets

Enables background net display and fits the layer.

### 18.4 Checkboxes

#### Fast mode

Enabled by default.

In Fast mode:

- Background copper is drawn as simplified outlines.
- Selected Net A and Net B remain exact.
- Measurement line and blocker dots remain exact.

Disable Fast mode if you want more exact full-fill background rendering.

#### Other nets

Shows or hides non-selected nets.

#### Component pads

Shows component pad overlays.

#### Show components

Shows component contour outlines and reference designators.

#### Vias

Shows via overlays.

#### PCB outline

Shows board outline/profile.

#### Points

Shows measurement points.

### 18.5 Blocker dots

When the minimum-distance line crosses another copper object, the viewer draws magenta dots on the line.

These dots indicate copper that blocks or interrupts the direct clear path.

---

## 19. Output files

After analysis, the output folder may contain:

```text
analysis_settings.json
geometry_debug_critical_pairs.csv
net_to_net_clearance_report.md
net_to_net_clearance_report.xlsx
net_to_net_critical_under_0p15mm.csv
net_to_net_measurements_full.csv
net_to_net_per_net_minimum.csv
net_to_net_report_package.zip
odb_feature_attributes.csv
```

If Effective Net-to-Net distance is enabled:

```text
net_to_net_effective_air_gap_matrix.csv
```

### 19.1 Report ZIP

The report ZIP bundles the generated report files for easier sharing.

### 19.2 Markdown report

The Markdown report is good for GitHub, issue tracking, or design-review notes.

### 19.3 Excel report

The Excel report is good for filtering and review in a spreadsheet application.

### 19.4 CSV files

CSV files are best for post-processing in Python, Excel, pandas, or another reporting system.

---

## 20. Recommended review process

For a typical PCB review:

1. Load ODB++.
2. Read metadata.
3. Confirm layer roles in **IPC-2221A**.
4. Confirm pollution degree assignments in **IEC 60664-1**.
5. Configure isolation groups in **IEC 61558 / IEC 62368** if relevant.
6. Set critical threshold.
7. Run analysis.
8. Review **Summary**.
9. Review **Critical pairs**.
10. Open suspicious rows in **Geometry Viewer**.
11. Use **Zoom min 2/3** for exact minimum location.
12. Check **Debug zero/overlap** rows if spacing looks wrong.
13. Export/share report ZIP.
14. Save settings JSON with the design review.

---

## 21. Common problems and fixes

### Application starts but no copper appears

Check:

- Correct ODB++ file was selected.
- Signal layers are present.
- Correct layer is selected in Geometry Viewer.
- Net filters are not hiding nets.
- Other nets checkbox is enabled if no Net A/B is selected.

### Geometry looks wrong

Try:

- Disable Fast mode.
- Confirm ODB++ export in CAD viewer.
- Check feature attributes.
- Inspect debug rows.
- Confirm negative/cutout features are exported.

### Executable cannot find `python313.dll`

If built with PyInstaller `--onedir`, copy the entire application folder, not just the `.exe`.

Correct structure:

```text
ODBClearanceAnalyzer/
  ODBClearanceAnalyzer.exe
  _internal/
    python313.dll
```

### Reports are missing

Check:

- Output folder exists and is writable.
- Analysis finished successfully.
- Log tab has no errors.
- Antivirus or corporate file protection did not block writing.

### Isolation tab shows no rows

Check:

- Main analysis was run first.
- Isolated-side net names exactly match net names in ODB++.
- The isolated nets are present on at least one copper layer.
- The nets are not filtered or renamed in the ODB++ export.

---

## 22. Best practices

- Always compare critical findings against the original PCB CAD tool.
- Use exact ODB++ export settings from the manufacturing release.
- Save `analysis_settings.json` with each review.
- Use the same settings file when comparing design revisions.
- Keep notes about which standard edition and table values were used.
- Do not treat voltage estimate columns as formal certification results.
- For isolation barriers, manually enter required spacing values confirmed from the applicable standard.

---

## 23. Glossary

### Clearance

Shortest air distance between conductive parts.

### Creepage

Shortest path along an insulating surface between conductive parts.

### CTI

Comparative tracking index of insulating material.

### Pollution degree

Environmental contamination category used in insulation coordination.

### Isolated side

A user-defined group of nets on one side of an isolation barrier, such as the secondary side of a transformer.

### Critical threshold

User-defined spacing limit below which measured pairs are listed as critical.

### Effective Net-to-Net distance

A diagnostic that considers whether other copper lies on the straight-line path between two nets.

---

## 24. Final compliance note

The analyzer can find layout risks quickly, but final compliance requires engineering judgement and review against the correct standard.

For safety-critical designs, always involve:

- Product safety engineer.
- Certification lab.
- PCB manufacturing engineer.
- Mechanical/enclosure engineer.
- Transformer/component vendor, where applicable.
