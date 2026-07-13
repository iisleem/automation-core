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
        generator.py
        history.py
        models.py
        opener.py
        product.py
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
- `tests/*.html`: test details.
- `timeline.html`: chronological events.
- `flaky.html`: flaky/slow/failing analysis.
- `matrix.html`: profile/browser/device/environment comparison.
- `history.html`: history/trend من `reports/history`.
- `data/run-report.json`: neutral JSON للـ run الحالي.

Local artifacts are bundled by default under `artifacts/` inside the generated report:

```python
generate_reporting_product(report, "reports/automation-report", bundle_artifacts=True)
```

External URLs stay untouched. If a local file cannot be copied, the original link/path is kept and a `bundle_error` entry is added to artifact metadata.

### Adapter/enricher flow

الفريموركات تغذي core هكذا:

```python
from automation_core.reporting.adapters import run_report_from_allure_results
from automation_core.reporting.product import generate_reporting_product

report = run_report_from_allure_results(
    "reports/allure-results",
    project_name="mobile-automation-framework",
    framework="pytest-appium",
)

for test in report.tests:
    test.metadata.update(mobile_metadata_by_test.get(test.full_name, {}))

generate_reporting_product(report, "reports/core-report", history_dir="reports/history")
```

هكذا mobile يرسل device/context/app timings كـ data، web يرسل browser/trace/video/console/network كـ data، وAPI يرسل request/response/schema/latency كـ data.

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

الـ history في core لا يحتاج DB ولا service خارجي؛ مجرد files قابلة للـ gitignore أو upload كـ CI artifact.

## Boundaries

أي code يحتاج object من Selenium/Playwright/Appium/httpx client/schema validator لا يدخل core. المقبول فقط هو function تعمل على data عادية، paths، strings، dicts، lists، أو protocols واسعة مثل object لديه `headers` أو `elapsed`.
