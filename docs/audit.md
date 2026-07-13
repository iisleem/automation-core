# Audit: web/mobile/api shared concepts

تاريخ الفحص: 2026-07-13

النطاق المقروء فقط:

- `/Users/ismail/Documents/New project 4/web-automation-framework`
- `/Users/ismail/Documents/New project 4/mobile-automation-framework`
- `/Users/ismail/Documents/New project 4/api-automation-framework`

لم يتم تعديل أي ملف داخل الفريموركات الثلاثة.

## ملخص سريع

- عدد ملفات Python المقروءة تقريباً: web = 122، mobile = 78، api = 68.
- يوجد 56 مسار Python مشترك بالاسم بين repoين أو أكثر.
- لا يوجد ملف Python مطابق تماماً عبر الثلاثة معاً.
- يوجد تطابق كامل واضح بين web و api في helpers عامة:
  - `utils/helpers/date_time/date_helper.py`
  - `utils/helpers/env/secrets.py`
  - `utils/helpers/files/file_helper.py`
  - `utils/helpers/files/structured_file_helper.py`
  - `utils/helpers/soft_assertions/soft_assertions.py`
- mobile يستخدم نفس المفاهيم غالباً، لكن بواجهات أبسط أو بتعديلات Appium/device.

## ما تم اعتباره core

| المجال | القرار | السبب |
| --- | --- | --- |
| config reader/base config | دخل core | YAML/JSON/env interpolation/environment selection بدون domain binding. |
| logger | دخل core | إعداد logging عام مع file logging اختياري. |
| reporting product | دخل core كمرشح رئيسي | web/mobile/api كلهم يحتاجون dashboard/timeline/details/history/flaky analysis، والاختلافات يجب أن تأتي كـ adapter metadata لا كـ dependencies. |
| reporting neutral models/events/artifacts | دخل core | يسمح للفريموركات بتغذية نفس المحرك ببيانات browser/device/API بدون Selenium/Appium/requests. |
| reporting engine القديم | يبقى كـ compatibility layer | قراءة Allure JSON وتوليد HTML summary مفيدة كـ fallback، لكن ليست المنتج النهائي وحدها. |
| matrix dashboards | دخل core | تم تعميم browser/environment/device إلى `generate_matrix_dashboard`، وسيتم توسيعها للمقارنة والفشل المتجمع. |
| report opener | دخل core | فتح report عبر file URL أو local HTTP server عام. |
| Allure CLI | دخل core | discovery/installer لا يعتمد على framework. |
| Allure debug basic attachments | دخل core | `step`, `attach_text`, `attach_json`, `attach_file` عامة وتعمل no-op عند غياب Allure. |
| wait/polling | دخل core | `wait_until` و`poll_until` عامة. |
| retry utilities | دخل core | `retry_action` و decorator عامين كقاعدة action retry. |
| data generators | دخل core | ids/email/username/phone/string عامة. |
| file helpers | دخل core | wait/assert/cleanup/latest file عامة. |
| structured file helpers | دخل core | CSV/JSON helpers عامة. |
| text helpers | دخل core | normalize/extract/OTP/numbers عامة. |
| URL helpers | دخل core | build/query/remove/assert query params عامة. |
| soft assertions | دخل core | دمج web/api feature-set مع دعم context manager المستخدم في mobile. |
| secrets/env | دخل core | require/optional/validate/mask عامة. |
| date/time | دخل core | utc/today/tomorrow/yesterday/format/parse عامة. |
| cleanup registry | دخل core | LIFO cleanup registry عام ومكرر بين web/api. |
| security subset | دخل core | headers/cookies/sensitive text/json عامة. Browser storage بقي خارج core. |
| response timing subset | دخل core | قياس response elapsed عام، بدون API client. |

## ما بقي خارج core

| المجال | السبب |
| --- | --- |
| `conftest.py` | pytest fixtures وartifact hooks مختلفة لكل framework. |
| `framework.py` | CLI orchestration خاص بكل repo: browsers/devices/environments. |
| Selenium/Playwright page objects | web-specific. |
| Appium drivers/capabilities/devices/contexts/gestures/permissions/deep links | mobile-specific. |
| API clients/auth/schema/contracts/services | API-specific ويحتوي httpx/client contracts. |
| `booking_payload` | demo API payload وليس data generator عام. |
| browser storage security helper | يحتاج `page.evaluate` وبالتالي web-specific. |
| browser performance helper | يعتمد على browser Performance API وبالتالي web-specific. |
| screenshot/video/trace/artifact helpers | مرتبطة بمتصفحات أو أجهزة أو pytest hooks. |
| accessibility/visual/browser/table/form/cookie helpers | تحتوي web/mobile driver assumptions. يمكن لاحقاً استخراج أجزاء pure data فقط إذا ظهرت حاجة. |

## Reporting vision داخل core

الـ reporting يجب أن يكون shared product مركزي، وليس مجرد `index.html` مختصر. هذا يجعل core هو المكان الصحيح للآتي:

- Dashboard رئيسي: total/pass/fail/skip/flaky، duration، profiles/devices/browsers، آخر run، trend بسيط، fastest/slowest tests.
- Test details لكل test: steps، test retries، action-level retry attempts، artifacts، logs، capabilities، device/browser/API metadata، failure reason واضح.
- Timeline: بداية ونهاية الاختبارات، duration، retries، artifact capture events.
- Flaky analysis: failed ثم passed بسبب test retry، action failed ثم passed بسبب action retry، always failing، slow but passing.
- Matrix dashboard: Android/iOS/native/hybrid/mobile web، Chrome/Firefox/WebKit، API environments/profiles، مع مقارنة pass/fail/differences/failure clustering.
- Smart failure summary: locator not found، app not installed، Appium server unreachable، webview context missing، assertion mismatch، timeout، API contract mismatch، auth/config issue.
- Artifacts viewer: screenshot preview، XML/source collapsible، searchable logs، embedded videos، sanitized request/response artifacts.
- History في `reports/history`: pass-rate trend، flaky tests، slow tests، failure frequency.

## Reporting adapter boundary

Core يعرّف neutral schema فقط:

- `RunReport`
- `TestCaseReport`
- `StepRecord`
- `RetryAttempt`
- `Artifact`
- `ReportingEvent`

web/mobile/api يضيفون metadata عبر adapters/enrichers، بدون أن يعرف core أي شيء عن Selenium أو Appium أو Playwright أو requests/httpx.

أمثلة adapter metadata المقبولة:

- Mobile: `device_name`, `platform_version`, `appium_driver`, `context_switches`, `native_time_ms`, `webview_time_ms`, `orientation`, `app_install_duration_ms`, `app_start_duration_ms`.
- Web: `browser`, `browser_version`, `viewport`, `trace_href`, `video_href`, `console_errors`, `network_failures`.
- API: `method`, `url`, `status_code`, `latency_ms`, `schema_validation`, `contract_validation`, `sanitized_request_href`, `sanitized_response_href`.

## ملاحظات توافق مهمة

- `read_allure_results` في web/api كان يرمي `FileNotFoundError` إذا النتائج غير موجودة، بينما mobile كان يرجع list فارغة. في core الافتراضي يحافظ على سلوك web/api، ويمكن استخدام `missing_ok=True` لسلوك mobile.
- `soft_assert()` في web/api كان يرجع `SoftAssert` مباشرة، وفي mobile كان context manager. في core `SoftAssert` نفسه يدعم الطريقتين.
- `attach_text` في core يستخدم توقيع web/api: `attach_text(content, name=...)`. mobile يحتاج wrapper بسيط لو بدنا نحافظ على توقيعه القديم `attach_text(name, value)`.
- security headers الافتراضية في core هي التقاطع الآمن بين web/api. web يستطيع استخدام `BROWSER_SECURITY_HEADERS` لإضافة `content-security-policy`.
