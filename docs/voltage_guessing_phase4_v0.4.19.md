# Voltage Guessing Phase 4 — v0.4.19

This release implements the Phase 4 UX/productivity layer on top of the deterministic Voltage Guessing Phase 1–3 engine.

Implemented items:

- Batch review actions with dry-run previews:
  - approve selected
  - accept unknown
  - set class/voltage
  - waive selected
- Batch approve safety rule: Warning and Critical severity nets are never batch-approved.
- Review Needed keyboard shortcuts:
  - A = approve
  - U = accept unknown
  - W = waive
  - E = edit/focus selected net details
  - S = skip in the review session
  - Enter or ? = show Why? explanation
- Inline Why? explanation for a selected assignment.
- Rule sandbox in Advanced tab.
- Correction-to-rule workflow that writes project-local `project_local_corrections.csv` rules.
- Similar-net suggestion helper for applying a manual fix to related nets.
- Persistent review-session state updates.
- Assignment diff viewer against an imported previous assignment file.
- Copyable review summary.
- Geometry Viewer launch from a selected voltage assignment.

Still intentionally not implemented in this phase:

- Full bidirectional Geometry Viewer context menu back into Voltage Guessing.
- Full GUI table virtualization.
- Full CLI Phase 5 report integration.

No LLM, local AI model, cloud API, Ollama, llama.cpp, GPT4All, OpenAI-compatible backend, or probabilistic classifier is implemented.
