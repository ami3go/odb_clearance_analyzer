# ODB++ Clearance Analyzer v0.4.58

Release date: 2026-09-10
Target branch: `main`

## Summary

This release packages the recent GUI and Voltage Guessing work from v0.4.38 through v0.4.58.  The main focus is multi-zone voltage management, zone-aware report calculation, zone visualization in Geometry Viewer, and cleanup of the main header controls.

## Highlights

### Multi-zone Voltage Guessing

- Added a dedicated **Voltage Guessing → Zones** subtab.
- Extended galvanic-zone assignment from two zones to **Zone 1 … Zone 10**.
- Added a **10×10 zone voltage matrix**.
- Matrix values define the required working voltage between any two zones.
- Diagonal cells are fixed at `0 V`.
- The matrix is stored symmetrically and used by the voltage requirement resolver.

### Matrix usability

- Added vertical scrolling to the Zones tab for smaller displays.
- Added configurable **Reset voltage, V** textbox.
- Added **Reset all to value** button for filling all off-diagonal matrix cells with any positive finite voltage.
- Masked duplicate matrix fields so each zone pair is edited only once.
- Changed masking orientation so the upper/top triangle is masked and the lower triangle is editable.
- Fixed lower-triangle source-of-truth handling so visible edits are saved symmetrically and are used by reports.

### Report integration

- The report voltage resolver now uses the multi-zone voltage matrix for cross-zone pairs.
- `required_voltage_v`, `zone_voltage_v`, OK/NOK status, and voltage-margin calculations are resolved from the stored matrix values.
- Added regression coverage to verify that lower-triangle matrix edits reach the resolver and report path.

### Geometry Viewer zone visualization

- Added **Show zones** action to the main GUI header.
- Added **Show zones** action inside Geometry Viewer.
- The zone view opens/fits the full-board geometry view and colors nets by assigned galvanic zone.
- Zone 1 … Zone 10 use distinct high-contrast colors.
- Unassigned nets are shown in neutral grey.
- Added an on-canvas zone legend with per-zone net counts.

### Header and button cleanup

- Moved/kept main analysis actions in the application header.
- Combined Run/Stop into one visible button that changes state depending on analysis state.
- Normalized header button styling so **Run analysis**, **Open output**, **Geometry viewer**, and **Show zones** use the same visible style.
- Removed the version number from the large in-app header title.
- Kept the version number in the operating-system/window title bar only.

### Debug tab fix

- Fixed the nested Debug tab implementation so Log, Feature attributes, and Debug zero content is rebuilt into live nested panes rather than reparented after creation.
- Added regression coverage to verify that debug widgets are live descendants of the nested Debug notebook.

### Import-hook stability

- Fixed recursive import-hook failures in multi-zone support.
- Fixed recursive import-hook failures in zone visualization support.
- Added re-entrancy guards and regression tests around partial GUI-module imports.

## Version

- Package version: `0.4.58`
- `odb_clearance_analyzer.__version__`: `0.4.58`

## Local update

```bash
git pull
python -m pip install -e .
odb-clearance-gui
```

## Manual GitHub release command

The ChatGPT GitHub connector available in this session does not expose a release-creation mutation. To publish the actual GitHub Release object from a local checkout, run:

```bash
git pull
git tag -a v0.4.58 -m "Release v0.4.58"
git push origin v0.4.58
gh release create v0.4.58 \
  --title "v0.4.58" \
  --notes-file RELEASE_NOTES_v0.4.58.md
```
