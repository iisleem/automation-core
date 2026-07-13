# automation-core

`automation-core` is the shared, domain-neutral Python package for the web, mobile, and API automation frameworks.

It intentionally does **not** include Selenium, Playwright page objects, Appium/device logic, API clients, schemas, or framework-specific pytest fixtures. Those stay in their standalone repositories.

## Install

From GitHub after the repository is published:

```bash
pip install "automation-core @ git+https://github.com/iisleem/automation-core.git@v0.1.0"
```

For local development:

```bash
python -m pip install -e ".[dev]"
pytest
```

## Included

- Config loading for YAML/JSON, environment interpolation, environment selection, and `deep_get`.
- Logging setup with optional file logging.
- Shared reporting product with neutral models/events/artifacts, dashboard, test details, timeline, flaky analysis, matrix views, artifacts viewer, history, plus Allure result parsing and fallback HTML summaries.
- Optional Allure debug attachments with graceful no-op behavior when Allure is unavailable.
- Wait, polling, and retry helpers.
- Data, file, structured file, text, URL, date/time, secrets, cleanup, soft assertion, security, and response timing helpers.

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

By default, local artifact files are bundled under the generated report's `artifacts/` directory when possible. External URLs are preserved.

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
