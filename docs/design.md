# Design

`automation-core` هي package مستقلة، public-ready، واسم التوزيع المقترح لها هو `automation-core` مع import package باسم `automation_core`.

## Structure

```text
automation-core/
  pyproject.toml
  README.md
  docs/
    audit.md
    design.md
    migration_plan.md
  src/
    automation_core/
      config.py
      logger.py
      cli.py
      helpers/
        cleanup.py
        data.py
        date_time.py
        files.py
        performance.py
        retry.py
        secrets.py
        security.py
        soft_assertions.py
        structured_files.py
        text.py
        urls.py
        wait.py
      reporting/
        allure_cli.py
        adapters.py
        analysis.py
        allure_debug.py
        events.py
        finalizer.py
        generator.py
        history.py
        models.py
        opener.py
        product.py
      healing/
        audit.py
        models.py
        reporting.py
        scoring.py
  tests/
```

## Public API style

- استخدم imports مباشرة وواضحة:

```python
from automation_core.config import ConfigReader
from automation_core.helpers import wait_until, soft_assert
from automation_core.reporting import generate_html_report
```

- أبقِ wrappers داخل كل framework إذا أردت الحفاظ على imports القديمة مثل:

```python
from utils.helpers.files.file_helper import wait_for_file
```

الـ wrapper وقتها يستورد من `automation_core` فقط، بدون نسخ الكود.

## Dependency policy

Core يعتمد فقط على:

- Python `>=3.11`
- `PyYAML`

Allure Python package اختيارية:

- دوال `automation_core.reporting.allure_debug` تعمل no-op إذا Allure غير مثبت.
- تثبيت optional dependency ممكن عبر:

```bash
pip install "automation-core[allure]"
```

## Reporting design

Reporting في core له طبقتان:

1. Compatibility/report fallback: قراءة Allure JSON وتوليد HTML summary بسيط، مع wrappers للماتريكس الحالية.
2. Reporting product: static report كامل مبني على neutral models/events/artifacts.

### Neutral models

Core يملك schema مستقل عن الدومين:

```python
from automation_core.reporting.models import Artifact, RunReport, TestCaseReport

report = RunReport(
    run_id="2026-07-13T10-00-00",
    project_name="web-automation-framework",
    tests=[
        TestCaseReport(
            id="login",
            name="test_login",
            status="passed",
            profile="chrome",
            domain="web",
            metadata={"browser": "Chrome", "viewport": "1440x900"},
            artifacts=[Artifact(name="screenshot", path="screenshots/login.png", artifact_type="screenshot")],
        )
    ],
)
```

المسموح في `metadata` هو data قابلة للتسلسل فقط: strings/numbers/bools/lists/dicts. ممنوع تمرير driver/session/client objects.

### Product pages

`generate_reporting_product(report, output_dir)` يكتب:

- `index.html`: dashboard رئيسي.
- `explore.html`: searchable Tests Explore page with filters, sorting, and filtered charts.
- `tests/*.html`: test details.
- `timeline.html`: chronological events.
- `flaky.html`: flaky/slow/failing analysis.
- `matrix.html`: profile/browser/device/environment comparison.
- `history.html`: history/trend من `reports/history`.
- `report-data.json`: JSON-safe sidecar للـ dashboard insights, test index, chart aggregates, clusters, matrix/history, timeline counts, sharing metadata, and artifact index.
- `data/run-report.json`: neutral JSON للـ run الحالي.

Local artifacts are bundled by default under `artifacts/` inside the generated report:

```python
generate_reporting_product(report, "reports/automation-report", bundle_artifacts=True)
```

External URLs stay untouched. If a local file cannot be copied, the original link/path is kept and a `bundle_error` entry is added to artifact metadata.

### Adapter/enricher flow

الفريموركات تغذي core هكذا:

```python
from automation_core.reporting import finalize_allure_reporting

result = finalize_allure_reporting(
    results_dir="reports/allure-results",
    output_dir="reports/automation-report",
    project_name="mobile-automation-framework",
    framework="pytest-appium",
    run_id="local-run",
    history_dir="reports/history",
    report_kind="core",
    test_metadata=metadata_by_test,
    matrix_dimensions=["environment", "profile", "device_name", "platform_version", "context"],
    open_report=False,
)
```

The finalizer returns structured status data:

```python
assert result.core.generated
print(result.core.path)
print(result.warnings)
```

For richer domain metadata, frameworks can still build/enrich the neutral `RunReport` through
`run_report_from_allure_results(...)` or `EventRecorder`, then call `generate_reporting_product(...)` directly.

هكذا mobile يرسل device/context/app timings كـ data، web يرسل browser/trace/video/console/network كـ data، وAPI يرسل request/response/schema/latency كـ data.

### Final reporting flow

`finalize_allure_reporting(...)` is the shared end-of-run orchestration API. It is domain-neutral and coordinates:

- reading Allure result JSON into neutral `RunReport` data
- generating the core product report by default
- optionally generating the legacy summary report
- optionally generating the official Allure HTML report
- optionally opening the selected generated report
- accepting neutral `metadata`, `test_metadata`, `enrichers`, and `matrix_dimensions`
- returning `ReportingFinalizeResult` with paths, statuses, warnings, and errors

Supported `report_kind` values are:

- `core`: default product report
- `summary`: legacy one-page summary
- `allure`: official Allure HTML only
- `both`: core product plus official Allure HTML if the CLI is available

Official Allure generation never imports Allure Python APIs and never installs the CLI unless explicitly requested.
If the CLI is missing or fails during `both`, the core product report remains the primary successful output.

Adapters can also build the neutral model incrementally:

```python
from automation_core.reporting import EventRecorder

recorder = EventRecorder(run_id="local-run", project_name="mobile-automation-framework")
test = recorder.start_test("login", "test_login", domain="mobile", profile="ios")
step = recorder.add_step(test, "Tap login", status="passed")
recorder.add_action_retry(test, attempt=1, status="failed", action="tap login", step=step)
recorder.add_action_retry(test, attempt=2, status="passed", action="tap login", step=step)
recorder.finish_test(test, status="passed")
```

Before writing/publishing report data, validate that adapters did not pass driver/client/session objects:

```python
from automation_core.reporting import assert_valid_report

assert_valid_report(recorder.report)
```

## Runtime auto-healing foundation

`automation_core.healing` is a domain-neutral foundation for web and mobile runtime auto-healing. It deliberately
does not inspect browser DOM, mobile XML/source, accessibility trees, pages, drivers, sessions, or devices.

Core owns:

- `LocatorDescriptor`: original selector/locator data as plain strings and metadata.
- `CandidateDescriptor`: adapter-discovered alternative locator data and scoring signals.
- `HealingConfig`: mode, thresholds, ambiguity tolerance, allowed actions/categories, and allow/deny patterns.
- `evaluate_healing(...)`: ranks candidates, applies safety gates, and returns a JSON-safe `HealingResult`.
- JSONL audit helpers for durable healing attempt records.
- Reporting helpers that add healing events to `TestCaseReport.metadata["healing_events"]`.

Framework adapters own:

- Web DOM/accessibility inspection and candidate generation.
- Mobile native/hybrid/source inspection and candidate generation.
- Actually applying a selected Playwright/Selenium/Appium locator.

Modes:

- `disabled`: default; ranks are available only when an adapter calls the evaluator, but no behavior changes.
- `suggest`: ranks and records suggestions without applying them.
- `apply`: permits adapters to apply only the best candidate when it passes score, ambiguity, action, category, and
  pattern gates.

The reporting timeline reads `healing_events` metadata and renders each healing attempt as a timeline event. Test
detail pages render healing attempts as a first-class table with mode, decision, selected candidate, score, and
reason. The raw metadata remains available for deeper inspection without custom framework-specific report code.

### Matrix generalization

بدل ثلاث دوال منفصلة تحتوي نفس HTML تقريباً:

- `generate_browser_matrix_dashboard`
- `generate_environment_matrix_dashboard`
- `generate_device_matrix_dashboard`

core يحتوي API عام:

```python
generate_matrix_dashboard(
    runs,
    output_dir,
    dimension_key="browser",
    dimension_label="Browser",
    title="Browser Matrix Dashboard",
    description="...",
)
```

ثم يوفر wrappers بنفس الأسماء لتقليل تكلفة الهجرة.

For the product report, matrix dimensions come from `RunReport.matrix_dimensions`:

```python
report.matrix_dimensions = ["environment", "profile", "browser", "platform_version", "context"]
```

Each dimension can resolve from direct `TestCaseReport` fields, `metadata`, `capabilities`, or labels.

Matrix rows include total/pass/fail/skip counts, pass rate, and failure category counts when failed or broken tests
exist in that bucket.

### Smart failure classification

Core يقدم classifier مبدئي rule-based على `failure_message`, `failure_trace`, وmetadata:

- locator not found
- app not installed
- Appium server unreachable
- webview context missing
- assertion mismatch
- timeout
- API contract mismatch
- auth/config issue
- unknown

الفريموركات تستطيع تمرير `failure_category` صريح داخل metadata إذا عندها classifier أدق.

### History

`generate_reporting_product(..., history_dir="reports/history")` يحفظ summary JSON لكل run ويقرأ آخر runs لبناء:

- pass rate trend
- flaky count trend
- slowest tests عبر الوقت
- failure category frequency
- recent run comparison deltas in the HTML report and `report-data.json`

الـ history في core لا يحتاج DB ولا service خارجي؛ مجرد files قابلة للـ gitignore أو upload كـ CI artifact.

### Machine-readable sidecar

`generate_reporting_product(...)` writes `report-data.json` next to `index.html`. This file is intentionally
JSON-safe and can be used by framework smoke checks, documentation screenshot scripts, or CI artifact validation.
It includes:

- run summary and run health deltas from history when available
- test index records with detail hrefs, normalized searchable text, duration buckets, retry/artifact/healing flags, and neutral metadata summaries
- chart-ready aggregates for status distribution, duration buckets, failure categories, retry signals, artifact types, coverage, and filter options
- top slow tests
- failure clusters using `failure_summary(...)`
- flaky breakdown for test retry flaky, action retry flaky, always failing, and slow passing tests
- matrix summary with pass rate and failure category counts
- timeline event counts and event details
- history trend points and recent comparison
- risk signals and environment/execution coverage dimensions when metadata is available
- artifact index with bundled hrefs after local artifact copying
- sharing/export metadata with safe-share redaction status and export paths

### Enterprise static report experience

The product report remains a portable static artifact: `index.html` works from local files or CI artifacts without a
server or external CDN. The shared shell links Dashboard, Executive, Tests, Timeline, Flaky, Matrix, History, and Share consistently.
Pages include self-contained CSS/JavaScript for search, filtering, sorting, charts, and matrix view toggles.

The Dashboard includes status distribution, duration distribution, slowest tests, failure category, retry signal,
artifact type, and history trend charts. The Tests Explore page uses the sidecar test index for global search,
filters, sorting, table/card views, and filtered chart summaries. Matrix pages use overflow-safe full-width sections
with heatmap cards plus tables so long dimension values do not break the layout.

The Executive page summarizes release readiness, top blockers, trend, quality signals, flaky/retry state, and
environment coverage for release stakeholders. The Share page provides stakeholder-oriented links, safe-sharing
status, package guidance, artifact index, and generated exports:

- `exports/test-index.csv`
- `exports/report-bundle.json`
- `exports/share-manifest.json`
- `print-summary.html`

Safe sharing is enabled by default for generated public-facing outputs. Sensitive values matching neutral key/name
patterns such as `token`, `secret`, `password`, `authorization`, `cookie`, `api_key`, `bearer`, and `session` are
replaced with `[redacted]` in HTML, sidecar/search text, `data/run-report.json`, CSV, and JSON export summaries.
The data shape is preserved; values are redacted rather than removing keys. Internal callers can opt out with
`safe_share=False` when raw diagnostics are required.

## Boundaries

أي code يحتاج object من Selenium/Playwright/Appium/httpx client/schema validator لا يدخل core. المقبول فقط هو function تعمل على data عادية، paths، strings، dicts، lists، أو protocols واسعة مثل object لديه `headers` أو `elapsed`.
