# Migration plan

هذه الخطة لا تعدل الفريموركات الثلاثة الآن. الهدف منها تجهيز هجرة تدريجية بدون فقد features وبدون كسر imports القديمة دفعة واحدة.

## المرحلة 1: dependency فقط

في كل repo، أضف dependency بعد نشر GitHub tag:

```text
automation-core @ git+https://github.com/iisleem/automation-core.git@v0.5.0
```

أو لاحقاً إذا تم نشرها كـ package:

```text
automation-core==0.5.0
```

## المرحلة 2: compatibility wrappers

## Reporting migration: shared product أولاً

قبل حذف أي reporting code من web/mobile/api، اعتمد المسار التالي:

1. اترك توليد Allure الحالي كما هو.
2. أضف خطوة finalization مشتركة تولد core product report من نفس `reports/allure-results`.
3. أضف enrichers صغيرة داخل كل framework تجمع metadata الخاصة بالدومين كـ dicts.
4. بعد ثبات التقرير، حوّل dashboard القديم إلى wrapper أو redirect.

مثال عام:

```python
from automation_core.reporting import finalize_allure_reporting

result = finalize_allure_reporting(
    results_dir="reports/allure-results",
    output_dir="reports/automation-report",
    run_id=run_id,
    project_name="web-automation-framework",
    framework="pytest-playwright",
    test_metadata=metadata_by_test,
    history_dir="reports/history",
    report_kind="core",
    open_report=False,
)
```

النتيجة `result` تحتوي `core.path`, `allure.status`, `warnings`, و`errors` حتى لا تحتاج الفريموركات parsing للـ stdout.
إذا احتاج framework تعديل `RunReport` بتفصيل أكبر، يستطيع استخدام `run_report_from_allure_results(...)` ثم
`generate_reporting_product(...)` كمسار advanced، لكن المسار الافتراضي يجب أن يبقى `finalize_allure_reporting(...)`.

### web reporting adapter data

كل test يمكن إثراؤه ببيانات مثل:

```python
metadata_by_test[test_full_name] = {
    "domain": "web",
    "profile": browser_name,
    "browser": browser_name,
    "browser_version": browser_version,
    "viewport": "1440x900",
    "console_errors": console_errors,
    "network_failures": network_failures,
    "artifacts": [
        {"name": "trace", "href": "traces/test.zip", "artifact_type": "trace"},
        {"name": "video", "href": "videos/test.webm", "artifact_type": "video"},
    ],
}
```

### mobile reporting adapter data

```python
metadata_by_test[test_full_name] = {
    "domain": "mobile",
    "profile": profile_name,
    "device_name": device_name,
    "platform": platform_name,
    "platform_version": platform_version,
    "appium_driver": driver_name,
    "orientation": orientation,
    "context_switches": context_switches,
    "native_time_ms": native_time_ms,
    "webview_time_ms": webview_time_ms,
    "app_install_duration_ms": install_ms,
    "app_start_duration_ms": start_ms,
}
```

### API reporting adapter data

```python
metadata_by_test[test_full_name] = {
    "domain": "api",
    "profile": env_name,
    "environment": env_name,
    "method": "POST",
    "url": "/booking",
    "status_code": 201,
    "latency_ms": 184,
    "schema_validation": "passed",
    "contract_validation": "passed",
    "artifacts": [
        {"name": "sanitized request", "href": "artifacts/request.json", "artifact_type": "request"},
        {"name": "sanitized response", "href": "artifacts/response.json", "artifact_type": "response"},
    ],
}
```

### action-level retry attempts

أي framework عنده action retry يمرره كبيانات لا ككود driver:

```python
metadata_by_test[test_full_name] = {
    "action_retries": [
        {
            "attempt": 1,
            "retry_type": "action",
            "action": "tap login",
            "status": "failed",
            "duration_ms": 250,
            "reason": "element not ready",
        },
        {
            "attempt": 2,
            "retry_type": "action",
            "action": "tap login",
            "status": "passed",
            "duration_ms": 120,
        },
    ],
}
```

Core سيصنفها ضمن flaky analysis كـ `action_retry_flaky` إذا فشلت ثم نجحت.

### validation قبل التسليم

قبل توليد التقرير أو في نهاية adapter tests:

```python
from automation_core.reporting import assert_valid_report

assert_valid_report(report)
```

هذا يمنع تمرير driver/client/session objects داخل metadata/capabilities، ويكشف أي قيمة غير قابلة للتحويل إلى JSON.

### matrix dimensions مخصصة

كل framework يستطيع ضبط dimensions حسب الحاجة:

```python
report.matrix_dimensions = ["environment", "profile", "browser", "platform_version", "context"]
```

القيم تُقرأ من fields مباشرة مثل `environment`, `profile`, `domain`, `status`، أو من `metadata`/`capabilities` مثل `browser`, `device_name`, `platform_version`, `context`.

### web-automation-framework

مرشحات wrapper مباشرة:

- `utils/helpers/files/file_helper.py`
- `utils/helpers/files/structured_file_helper.py`
- `utils/helpers/env/secrets.py`
- `utils/helpers/date_time/date_helper.py`
- `utils/helpers/text/extractors.py`
- `utils/helpers/wait/polling.py`
- `utils/helpers/soft_assertions/soft_assertions.py`
- `utils/helpers/url/url_helper.py`
- `utils/helpers/cleanup/cleanup_registry.py`
- `utils/report_generator.py`
- `utils/report_opener.py`
- `utils/allure_cli.py`
- `utils/logger.py`

Reporting wrapper المقترح:

```python
from automation_core.reporting import finalize_allure_reporting

def finalize_reports(results_dir, output_dir, *, run_id=None, open_report=False):
    return finalize_allure_reporting(
        results_dir=results_dir,
        output_dir=output_dir,
        project_name="web-automation-framework",
        framework="pytest-playwright",
        run_id=run_id,
        history_dir="reports/history",
        report_kind="core",
        open_report=open_report,
    )
```

### mobile final reporting wrapper

```python
from automation_core.reporting import finalize_allure_reporting

def finalize_reports(results_dir, output_dir, *, run_id=None, metadata_by_test=None, open_report=False):
    return finalize_allure_reporting(
        results_dir=results_dir,
        output_dir=output_dir,
        project_name="mobile-automation-framework",
        framework="pytest-appium",
        run_id=run_id,
        history_dir="reports/history",
        report_kind="core",
        test_metadata=metadata_by_test or {},
        matrix_dimensions=["environment", "profile", "device_name", "platform", "platform_version", "context"],
        open_report=open_report,
    )
```

### API final reporting wrapper

```python
from automation_core.reporting import finalize_allure_reporting

def finalize_reports(results_dir, output_dir, *, run_id=None, metadata_by_test=None, open_report=False):
    return finalize_allure_reporting(
        results_dir=results_dir,
        output_dir=output_dir,
        project_name="api-automation-framework",
        framework="pytest-api",
        run_id=run_id,
        history_dir="reports/history",
        report_kind="core",
        test_metadata=metadata_by_test or {},
        matrix_dimensions=["environment", "profile", "api_profile", "status"],
        open_report=open_report,
    )
```

مثال wrapper:

```python
from automation_core.helpers.files import *
```

للـ logger، حافظ على ملف log الحالي:

```python
from pathlib import Path
from automation_core.logger import get_logger as _get_logger

PROJECT_ROOT = Path(__file__).resolve().parents[1]

def get_logger(name: str):
    return _get_logger(name, log_file=PROJECT_ROOT / "reports" / "framework.log")
```

للـ security في web:

```python
from automation_core.helpers.security import *
from automation_core.helpers.security import BROWSER_SECURITY_HEADERS

def assert_security_headers(response_or_headers, required_headers=None):
    from automation_core.helpers.security import assert_security_headers as core_assert
    return core_assert(response_or_headers, required_headers or BROWSER_SECURITY_HEADERS)
```

يبقى خارج core في web:

- page/browser helpers
- screenshots/videos/traces
- browser storage security
- browser Performance API helpers
- visual/accessibility/table/form/cookie helpers التي تعتمد على browser objects

### mobile-automation-framework

مرشحات wrapper:

- `utils/helpers/wait/polling.py`
- `utils/helpers/data/generators.py`
- `utils/helpers/files/file_helper.py`
- `utils/helpers/text/extractors.py`
- `utils/helpers/soft_assertions/soft_assertions.py`
- `utils/report_generator.py`
- `utils/report_opener.py`
- `utils/allure_cli.py`
- `utils/logger.py`

Config migration:

```python
from automation_core.config import ConfigReader as CoreConfigReader

class ConfigReader(CoreConfigReader):
    def read_capabilities(self):
        return self.read_yaml("config/capabilities.yaml")

    def load(self, environment: str):
        return super().load(
            environment,
            environment_key="environment",
            environment_config_key="environment_config",
            merge_environment=False,
        )
```

Allure debug mobile signature wrapper:

```python
from automation_core.reporting import attach_json as _attach_json
from automation_core.reporting import attach_text as _attach_text

def attach_text(name: str, value: str) -> None:
    _attach_text(value, name=name)

def attach_json(name: str, value) -> None:
    _attach_json(value, name=name)
```

يبقى خارج core في mobile:

- Appium driver/session management
- capabilities model ومعاني device/profile
- contexts/native/hybrid/webview helpers
- gestures/permissions/deep links/app install
- screenshots/source dumps/recordings artifacts

### api-automation-framework

مرشحات wrapper مباشرة:

- `utils/config_reader.py` مع wrapper صغير لـ `API_ENV`
- `utils/logger.py`
- `utils/report_generator.py`
- `utils/report_opener.py`
- `utils/allure_cli.py`
- `utils/helpers/allure_debug/allure_helper.py`
- `utils/helpers/files/file_helper.py`
- `utils/helpers/files/structured_file_helper.py`
- `utils/helpers/env/secrets.py`
- `utils/helpers/date_time/date_helper.py`
- `utils/helpers/text/extractors.py`
- `utils/helpers/wait/polling.py`
- `utils/helpers/soft_assertions/soft_assertions.py`
- `utils/helpers/url/url_helper.py`
- `utils/helpers/cleanup/cleanup_registry.py`
- generic parts من `utils/helpers/security/security_helper.py`
- generic response timing من `utils/helpers/performance/performance_helper.py`

Config wrapper لـ API:

```python
import os
from pathlib import Path
from typing import Any

from automation_core.config import ConfigReader, deep_get, load_json, load_yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]

def load_settings() -> dict[str, Any]:
    return ConfigReader(PROJECT_ROOT).read_settings()

def load_environments() -> dict[str, Any]:
    return ConfigReader(PROJECT_ROOT).read_environments()

def get_environment_config(env: str | None = None) -> dict[str, Any]:
    reader = ConfigReader(PROJECT_ROOT)
    settings = reader.read_settings()
    env_name = env or os.getenv("API_ENV") or settings["framework"]["default_env"]
    config = dict(reader.get_environment_config(env_name))
    config["name"] = env_name
    return config
```

يبقى خارج core في API:

- `clients/`
- auth providers/redaction rules الخاصة بالـ API client
- schema validator/contracts/services
- `booking_payload` demo generator

## المرحلة 3: tests per framework

بعد وضع wrappers، شغل لكل repo:

```bash
pytest tests/helpers
pytest
```

ثم احذف الكود المنسوخ تدريجياً من wrappers بعد التأكد من parity.

## المرحلة 4: GitHub

بعد اعتماد الحزمة:

1. إنشاء repo عام `iisleem/automation-core`.
2. رفع الكود.
3. عمل release tag ثابت، مثل `v0.5.0`.
4. ربط repo بنفس GitHub Project: `https://github.com/users/iisleem/projects/4`.
5. تحديث dependencies في web/mobile/api إلى tag ثابت.
