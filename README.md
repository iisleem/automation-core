# automation-core

`automation-core` is the shared, domain-neutral Python package for the web, mobile, and API automation frameworks.

It intentionally does **not** include Selenium, Playwright page objects, Appium/device logic, API clients, schemas, or framework-specific pytest fixtures. Those stay in their standalone repositories.

## Repository Role

`automation-core` is a shared package, not a starter template repository. Start user-facing automation suites from the web, mobile, or API framework template repositories, then consume `automation-core` as a pinned dependency.

Keep browser, device, app, request/client, and other environment-specific code in the framework repositories. Core should contain reusable domain-neutral helpers, reporting models, events, artifacts, and utilities.

See [Template Repository Strategy](docs/template_strategy.md) for the product-family template model and validation expectations.

## Install

From GitHub after the repository is published:

```bash
pip install "automation-core @ git+https://github.com/iisleem/automation-core.git@v0.11.2"
```

For local development:

```bash
python -m pip install -e ".[dev]"
pytest
```

## Included

- Config loading for YAML/JSON, environment interpolation, environment selection, and `deep_get`.
- Logging setup with optional file logging.
- Shared reporting product with neutral models/events/artifacts, visual dashboard charts, executive summary, quality gates, run comparison, share/export center, searchable Tests Explore, test details, timeline, flaky analysis, matrix heatmaps, artifacts viewer, history, machine-readable sidecar data, plus Allure result parsing and fallback HTML summaries.
- Runtime auto-healing foundation with neutral locator/candidate models, scoring, safety gates, JSONL audit events, and report metadata helpers.
- Optional Allure debug attachments with graceful no-op behavior when Allure is unavailable.
- Wait, polling, and retry helpers.
- Data, file, structured file, text, URL, date/time, secrets, cleanup, soft assertion, security, and response timing helpers.

## Version Notes

`0.11.2` improves long-label readability in report charts and test tables while keeping the shared
design-system shell consistent across retained portfolio pages and per-run reports.

`0.11.1` aligns the static report shell with the shared design system, adds portfolio/run hero
insight cards, improves matrix heatmap status coloring and long-name handling, and removes the
legacy duplicated report CSS from the product and portfolio renderers.

`0.11.0` redesigns the static enterprise report visual system across retained portfolio pages and
single-run reports. It adds a consistent sidebar/mobile drawer shell, system-default theme with
light/dark overrides, portfolio Compare, quality score, risk signal, default informational gate
status, stability, recovery, resource-efficiency, and chart-ready comparison data while preserving
existing `report-data.json` keys.

`0.10.0` introduced the first retained-report portfolio redesign and comparison data foundation.

`0.9.1` improves small-screen report readability by turning wide run-detail tables into labeled
mobile cards. `0.9.0` adds retained timestamped report runs and a portfolio dashboard. The shared
finalizer now stores each core report under `reports/automation-report/runs/<timestamp>-<run-id>/`,
keeps older run folders, archives a pre-existing root report instead of overwriting it, and writes
cross-run `index.html`, `reports.html`, and `portfolio-data.json` pages at the report root.

`0.8.0` adds an enterprise export pack for the static reporting product: Word executive summary, Excel test index workbook, and an SVG share card generated without extra runtime dependencies.

`0.7.0` adds neutral report quality gates, new/known/resolved failure comparison against history, run-to-run comparison sidecar data, and a dedicated Quality page in the static reporting product.

`0.6.0` adds the first enterprise sharing slice for the static reporting product: Executive Summary, Share And Export center, printable summary, CSV/JSON export artifacts, share manifest, stakeholder views, and safe-sharing redaction for generated report outputs by default.

`0.5.0` upgrades the static reporting product with enterprise-style dashboard charts, a searchable Tests Explore page, page-level filters, matrix heatmaps, richer test detail search, and expanded chart-ready `report-data.json` data.

`0.4.1` polishes the reporting product dashboard, test detail pages, matrix/history pages, and writes `report-data.json` for validation and downstream tooling.

`0.4.0` adds the neutral runtime auto-healing foundation. It provides models, scoring, safety gates, audit serialization, and reporting hooks only. Web and mobile adapters own actual selector discovery and application.

## Boundaries

Domain-specific code remains in the framework repositories:

- Web: browser/page helpers, screenshots, Playwright/Selenium storage, visual browser assertions, browser performance APIs.
- Mobile: Appium drivers, capabilities, devices, contexts, gestures, permissions, deep links, app install helpers.
- API: HTTP clients, auth providers, schema validation, contract files, service objects, API demo payloads.

See `docs/audit.md`, `docs/design.md`, and `docs/migration_plan.md` for the extraction audit and wrapper plan.

## Reporting Product

Core owns the neutral reporting engine. Frameworks provide adapter data:

- Web adapters enrich tests with browser, viewport, trace/video/screenshot links, console errors, and network failures.
- Mobile adapters enrich tests with device, platform, Appium driver, context switches, orientation, and app install/start timings.
- API adapters enrich tests with request/response summaries, status code, latency, schema/contract validation, and sanitized payload links.

The core package stores only serializable metadata and never imports Selenium, Appium, Playwright, requests, httpx, or framework clients.

## Runtime Auto-Healing Foundation

Core provides the environment-neutral pieces for runtime auto-healing:

- `LocatorDescriptor` and `CandidateDescriptor` describe the original locator and adapter-discovered alternatives.
- `HealingConfig` controls `disabled`, `suggest`, and `apply` modes, minimum score, ambiguity handling, allowed actions/categories, and allow/deny patterns.
- `evaluate_healing(...)` ranks candidates from adapter-supplied signals and returns a JSON-safe `HealingResult`.
- `append_healing_event(...)` writes JSONL audit records.
- `add_healing_result(...)` attaches healing metadata to `TestCaseReport` so the product report timeline and test details can show attempts.

The default mode is `disabled` so existing tests do not change behavior silently. Frameworks should enable `suggest`
or `apply` explicitly in their own configuration. Core does not inspect DOM, XML, accessibility trees, drivers,
sessions, pages, or devices.

```python
from automation_core.healing import (
    CandidateDescriptor,
    HealingConfig,
    LocatorDescriptor,
    add_healing_result,
    evaluate_healing,
)

original = LocatorDescriptor(strategy="css", value="[data-test='login']", action="click")
candidate = CandidateDescriptor(
    strategy="css",
    value="[data-test='sign-in']",
    signals={"stable_id": 1.0, "text": 0.8},
)
result = evaluate_healing(
    original,
    [candidate],
    HealingConfig(mode="suggest", min_score=0.75),
    action="click",
    test_id="login",
)
add_healing_result(test_report, result)
```

Generate the product report from Allure results:

```bash
automation-core-report \
  --results reports/allure-results \
  --output reports/automation-report \
  --project-name web-automation-framework \
  --framework pytest-playwright \
  --run-id local-run-001 \
  --history-dir reports/history
```

Use `--summary` when you only need the legacy one-page Allure summary. Use `--both` when you want the core
product report plus the official Allure HTML report if the Allure CLI is available. The official Allure report is
optional; missing or failing Allure CLI generation does not block the core report.

Frameworks can call the same finalizer directly:

```python
from automation_core.reporting import finalize_allure_reporting

result = finalize_allure_reporting(
    results_dir="reports/allure-results",
    output_dir="reports/automation-report",
    project_name="web-automation-framework",
    framework="pytest-playwright",
    run_id="local-run-001",
    history_dir="reports/history",
    report_kind="core",  # core, summary, allure, or both
    open_report=False,
)

if not result.ok:
    raise RuntimeError(result.to_dict())
```

The returned object includes per-report statuses, generated paths, warnings, errors, and open status so framework
wrappers can make clear decisions without parsing console output.

When frameworks use `finalize_allure_reporting(...)`, the report root becomes a retained report portfolio:

- `reports/automation-report/index.html`: portfolio dashboard with search, filters, charts, health signals, and coverage across retained runs.
- `reports/automation-report/reports.html`: report gallery with cards/table view and links into each saved run.
- `reports/automation-report/runs/<timestamp>-<run-id>/index.html`: overview page for one execution.
- `reports/automation-report/portfolio-data.json`: machine-readable index of all saved report runs.

`result.core.path` points to the portfolio dashboard. `result.core.run_path` points to the current timestamped run's
`index.html`.

By default, local artifact files are bundled under the generated report's `artifacts/` directory when possible. External URLs are preserved.

Each timestamped run report writes `report-data.json` next to that run's `index.html`. It contains JSON-safe run
summary data, test index records with detail links, chart-ready aggregates, failure clusters, flaky breakdown,
matrix rows, timeline counts/events, history comparison points, risk signals, quality score, stability/recovery,
resource-efficiency when worker metadata is available, coverage metadata, and an artifact index with bundled hrefs.
Framework validation can read this file instead of scraping HTML.

Quality gates are opt-in and domain-neutral. Callers can pass `quality_gates=QualityGateConfig(...)` to
`generate_reporting_product(...)` or `build_report_data(...)` to evaluate thresholds such as minimum pass rate,
maximum failed/broken tests, skipped tests, flaky tests, retries, duration, and failure categories. When history is
available, the sidecar and `quality.html` classify current failures as new or known and list resolved failures from
the previous run.

Enterprise insight defaults are informational and conservative. The report derives quality score, risk level,
default gate status, retry-recovered stability, mean recovery time, and run comparison from neutral run/test/history
data. Use `ReportInsightConfig(...)` with `generate_reporting_product(...)`, `build_report_data(...)`, or
`finalize_allure_reporting(...)` to tune slow-test thresholds, risk thresholds, default informational gates, quality
score weights, stability window, or worker-count metadata keys.

Generated reports are safe-sharing enabled by default. Values under sensitive keys or names such as `token`,
`secret`, `password`, `authorization`, `cookie`, `api_key`, `bearer`, and `session` are replaced with `[redacted]`
in public-facing HTML, `report-data.json`, `data/run-report.json`, CSV/XLSX/DOCX/SVG exports, and JSON export
bundles. Normal metadata values are preserved. Call `generate_reporting_product(..., safe_share=False)` or
`build_report_data(..., safe_share=False)` only for internal raw diagnostics.

The report also writes:

- `executive.html`: management-ready readiness, blockers, trend, quality, retry, and coverage summary.
- `quality.html`: quality gate status, new/known/resolved failures, and run comparison.
- `compare.html`: current-vs-previous run deltas, failure movement, stability, recovery, and resource-efficiency.
- `share.html`: export center with stakeholder views and links to the generated artifacts.
- `print-summary.html`: printable HTML summary suitable for browser PDF printing.
- `exports/test-index.csv`: flat test index for spreadsheet workflows.
- `exports/test-index.xlsx`: Excel workbook version of the test index.
- `exports/executive-summary.docx`: Word executive summary for stakeholder handoff.
- `exports/share-card.svg`: shareable visual status card for messages, dashboards, or release notes.
- `exports/report-bundle.json`: compact JSON bundle for downstream validation.
- `exports/share-manifest.json`: package manifest with safe-sharing status and report entry points.

## Recording Events

Framework adapters can build neutral report data with `EventRecorder`:

```python
from automation_core.reporting import EventRecorder, generate_reporting_product

recorder = EventRecorder(run_id="local-run", project_name="mobile-automation-framework")
test = recorder.start_test(
    "login",
    "test_login",
    domain="mobile",
    profile="ios",
    metadata={"device_name": "iPhone 15", "platform_version": "17.5"},
)
step = recorder.add_step(test, "Tap login", status="passed")
recorder.add_action_retry(test, attempt=1, status="failed", action="tap login", step=step)
recorder.add_action_retry(test, attempt=2, status="passed", action="tap login", step=step)
recorder.add_artifact(test, name="source", artifact_type="source", path="source.xml", step=step)
recorder.finish_test(test, status="passed")

generate_reporting_product(recorder.report, "reports/automation-report")
```

Before generating or publishing adapter data, validate it:

```python
from automation_core.reporting import assert_valid_report

assert_valid_report(recorder.report)
```
