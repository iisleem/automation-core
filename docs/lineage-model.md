# Test-content lineage model

## Why

Reports must be compared and trended by **what tests a run actually executed**,
not by a manual label and not by the framework repo name. `project_name` only
identifies the framework (`web/mobile/api-automation-framework`), so it cannot
tell an e-commerce run from a magazine run. Feeding two different apps into one
portfolio would otherwise average unrelated suites into one meaningless number.

The lineage model derives a run's identity from its test content, so runs of
the *same* tests trend together and everything else stays separate —
automatically, with no user-declared "system".

Implemented in [`automation_core/reporting/lineage.py`](../src/automation_core/reporting/lineage.py),
covered by [`tests/test_reporting_lineage.py`](../tests/test_reporting_lineage.py).
All functions are pure and deterministic: the behaviour is QA-able with
fixtures before any UI exists.

## Definitions

- **Signature** — the set of *fully-qualified test ids* a run executed
  (`metadata.nodeid` → `full_name` → `suite::name` → `name`). The id is an
  internal matching key; users never see it.
- **Containment** — `|A ∩ B| / min(|A|, |B|)`. Chosen over Jaccard because a
  small smoke run that is a subset of a full run yields `1.0` and is recognised
  as the same suite. (Jaccard would score that pair ~0.05 and split them.)
- **Lineage** — a chain of runs of the same evolving suite over time.

## Rules (agreed)

1. **Matching:** two runs are the same lineage when
   `containment ≥ threshold` (default **0.6**, configurable per call). This one
   rule subsumes the subset/smoke case.
2. **Assignment:** runs are processed oldest-first; each joins the existing
   lineage whose **most-recent** run it best matches, else it anchors a new
   lineage. No transitive chaining, so slow drift keeps one lineage while an
   abrupt change forks a new one.
3. **Comparison (pairwise):** `pairwise_delta` compares two runs over the exact
   **intersection** of their tests, so the delta is fair even when suites
   differ. Non-shared tests are surfaced as the diff.
4. **Diff:** explicit and tiered — counts always (`shares N of M · +X · −Y`),
   with the full added/removed lists available for drill-down.
5. **Coverage / partial:** `coverage` compares a run's size to the largest run
   in its lineage; anything smaller is `partial` (e.g. `partial · 10/200`) so a
   smoke run's high pass rate is not misread as full-suite health.
6. **Two levels, two roles:**
   - *Single report* → per-lineage trend (same test set over time).
   - *Portfolio* → per-platform (web/mobile/api) bird's-eye average.

## v1 simplification

`trend_series` plots each run's **raw pass rate restricted to its lineage**
plus a coverage badge, rather than recomputing every trend point over a shared
core. The precise intersection comparison lives in `pairwise_delta` (run vs
run), which is where fairness matters most.

## Backlog / deferred

- [ ] **Intersection-based trend line.** Make each `trend_series` point compare
  over a stable common core (e.g. the intersection across the lineage, or a
  rolling shared set) instead of the v1 raw-per-run-restricted-to-lineage
  approach. Deferred until the initial lineage feature ships so the trend and
  the pairwise compare use the exact same fairness basis. Do not lose this.

## Not yet wired

This is the logic layer only. Integration points still to come (separately):
sidecar exposure of the signature, portfolio/report rendering of lineage
trends and diffs, and the Claude Design pass for the experience — intentionally
**last**, after the logic is locked and tested.
