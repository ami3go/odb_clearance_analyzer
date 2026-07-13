# Voltage Guessing — Crash hardening (v0.4.21)

Findings from an adversarial defect inspection of v0.4.20 (static lint +
runtime probes with hostile inputs), and their fixes.

## Crashes fixed

1. Invalid regex in a user-editable rule file crashed auto-detect.
   Project-local correction files load without full validation, and
   rule_engine compiled patterns directly. re.error propagated into the
   GUI callback. Fix: _compiled_regex compiles defensively — an invalid
   pattern logs one warning and degrades to a never-matching regex;
   all other rules keep working.

2. One net name with control/format characters aborted auto-detect for
   the entire board (ValueError from strict Rev C 9.5 normalization).
   Fix: guess_net_voltage catches the rejection per net and returns an
   explicit UNKNOWN / Needs review assignment whose reason says the
   name could not be normalized.

3. A corrupted store file whose top level is a JSON array crashed
   project open with AttributeError, escaping the GUI's
   (ValueError, OSError) handler. Fix: load_assignment_store validates
   the top-level type and raises ValueError.

4. Follow-on from fix 2: control-char nets can now legitimately exist in
   the store, and six downstream consumers (exports, similar-net
   suggestions, correction rule-id derivation, revision matching in
   both directions) all crashed on them via strict normalization.
   Fix: normalization gains normalize_net_name_safe / net_tokens_safe
   (identical algorithm, strips instead of raising); exports, phase4,
   and revision_matcher use the tolerant variants. The strict variant
   remains the guessing engine's contract.

## Probed and confirmed safe (no change needed)
- Hostile net names (Tk-special characters, 5000-char names, unicode,
  a net literally named "__created__" vs the undo sentinel) through
  guessing, store round-trip, and undo.
- CSV import with quoted commas/newlines; duplicate imported objects;
  empty imported list through match/apply/delta export.
- Repeated undo on an empty stack; unknown gate mode string (falls back
  to warn); invalid waiver scope (ValueError by design, unreachable
  from the GUI's combobox).
- GUI batch waive already guards the empty-reason ValueError with an
  early return; manual override guards the KeyError path.

## Known remaining weaknesses (accepted, documented)
- Long operations run on the Tk main thread (freeze risk on huge
  boards, no crash); the 13.1 worker-queue pattern is Phase 5 scope.
- Obsolete (missing-in-new-revision) Critical nets count toward the
  block gate; policy decision pending.
- Conflict candidates are recovered by parsing the human-readable
  detail string; breaks (mis-lists, not crash) if a net name contains
  ", ". Structured field planned.
- Tk UI changes are syntax- and service-tested only in this headless
  environment.

Tests: 69 passed (65 prior + 4 crash-hardening regressions).
