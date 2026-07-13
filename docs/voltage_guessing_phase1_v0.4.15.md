# Voltage Guessing Phase 1 — v0.4.15

This release implements the first shippable phase of the deterministic Voltage Guessing task.

Implemented:

- New `Voltage Guessing` main GUI tab.
- Sub-tabs: Overview, Review Needed, All Assignments, Revision Import, Export, Advanced.
- Phase-1 deterministic net-name rule engine.
- Built-in CSV/JSON rule pack under `odb_clearance_analyzer/data/net_voltage_rules/`.
- Single net-name normalization function.
- Numeric voltage parser with false-positive guards for `GPIO12`, `ADC_IN1`, `UART2_TX`, `CH4`, `M2_CS`, and mains aliases such as `L1_SW`.
- All Assignments table.
- Manual override for selected net class/voltage/review state.
- Voltage assignment exports:
  - `net_voltage_guessing.csv`
  - `net_voltage_assignments.json`
  - `net_voltage_assignments.csv`
- Project assignment store with atomic JSON writes.
- `analysis_settings.json` includes `voltage_guessing.assignment_store_path`.
- CLI flags:
  - `--voltage-guess`
  - `--validate-voltage-rule-pack`
- Unit tests for parser, rule engine, false-positive guards, and exports.

Not yet implemented from the full Rev C / Rev 3 task:

- Revision import/matching UI.
- Review Needed queue behavior beyond placeholder tab.
- Batch review actions.
- Correction-to-rule workflow.
- Rule sandbox.
- Assignment diff viewer.
- Geometry Viewer cross-highlighting.
- Full report integration with voltage context columns.
- Full CLI gate modes and revision delta export.

No LLM, AI model, local model, cloud API, Ollama, llama.cpp, GPT4All, or probabilistic classifier is included.
