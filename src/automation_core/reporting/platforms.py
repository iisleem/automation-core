"""Neutral platform classification for reporting.

The report design groups tests, trends, coverage and history by *platform type*
-- ``web``, ``mobile`` or ``api`` -- rather than by framework. This module
derives that platform type from neutral, environment-agnostic signals so the
shared reporting engine never needs framework-specific code.

Classification order (first match wins), all configurable by an explicit
``platform_type`` label:

1. **Explicit** -- ``metadata["platform_type"]`` / ``labels["platform_type"]``
   equal to ``web``/``mobile``/``api`` (case-insensitive). Adapters should set
   this; everything else is a best-effort fallback.
2. **API** -- an ``api_profile`` is present, or metadata carries request/
   response/status-code/latency fields, or the suite/domain names "api".
3. **Mobile** -- a ``device_name`` is present, the ``platform`` field is an
   Android/iOS value, or a native/webview ``context`` is recorded.
4. **Web** -- a ``browser`` is present, or web-only signals (viewport, console,
   network, trace/video) exist.
5. **Framework hint** -- a caller-supplied hint (e.g. the repo name) mapping to
   a platform, used only when nothing above matched.
6. **Unknown** -- returned as ``web`` by default so a single-suite run still
   renders; callers may pass ``default`` to override.

None of these rules import framework code; frameworks feed the explicit label
through their adapters.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any

PLATFORMS: tuple[str, ...] = ("web", "mobile", "api")
_VALID = set(PLATFORMS)

_MOBILE_OS = {"android", "ios", "ipados", "androidtv", "tvos"}


def _lower(value: Any) -> str:
    return str(value or "").strip().lower()


def classify_platform(record: dict[str, Any], *, framework_hint: str = "", default: str = "web") -> str:
    """Classify one test-index record into ``web``/``mobile``/``api``."""

    metadata = record.get("metadata") or {}
    explicit = _lower(record.get("platform_type") or metadata.get("platform_type") or metadata.get("platformType"))
    if explicit in _VALID:
        return explicit

    api_profile = _lower(record.get("api_profile"))
    domain = _lower(record.get("domain"))
    suite = _lower(record.get("suite"))
    if (
        api_profile
        or "api" in {domain, suite}
        or any(k in metadata for k in ("status_code", "request", "response", "latency_ms", "endpoint"))
    ):
        return "api"

    device = _lower(record.get("device_name"))
    platform_field = _lower(record.get("platform"))
    context = _lower(record.get("context"))
    if device or platform_field in _MOBILE_OS or context in {"native", "webview"} or "webview" in context:
        return "mobile"

    browser = _lower(record.get("browser"))
    if browser or any(k in metadata for k in ("viewport", "console_errors", "network_failures", "trace", "video")):
        return "web"

    hint = _lower(framework_hint)
    for name in PLATFORMS:
        if name in hint:
            return name

    return default if default in _VALID else "web"


def _blank_bucket() -> dict[str, Any]:
    return {
        "total": 0,
        "passed": 0,
        "failed_broken": 0,
        "skipped": 0,
        "flaky": 0,
        "duration_ms": 0.0,
        "pass_rate": 0.0,
    }


def _is_pass(status: str) -> bool:
    return _lower(status) in {"passed", "pass"}


def _is_failed_broken(status: str) -> bool:
    return _lower(status) in {"failed", "broken", "error"}


def _is_skipped(status: str) -> bool:
    return _lower(status) in {"skipped", "skip"}


def platform_breakdown(
    test_index: list[dict[str, Any]], *, framework_hint: str = ""
) -> OrderedDict[str, dict[str, Any]]:
    """Aggregate a test index into per-platform metrics, ordered web/mobile/api.

    Only platforms that actually have tests are included, so a web-only run does
    not fabricate empty Mobile/API slices.
    """

    buckets: dict[str, dict[str, Any]] = {name: _blank_bucket() for name in PLATFORMS}
    for record in test_index:
        platform = record.get("platform_type") or classify_platform(record, framework_hint=framework_hint)
        bucket = buckets[platform if platform in _VALID else "web"]
        bucket["total"] += 1
        status = record.get("status", "")
        if _is_pass(status):
            bucket["passed"] += 1
        elif _is_failed_broken(status):
            bucket["failed_broken"] += 1
        elif _is_skipped(status):
            bucket["skipped"] += 1
        if record.get("flaky_categories"):
            bucket["flaky"] += 1
        bucket["duration_ms"] += float(record.get("duration_ms") or 0)

    result: OrderedDict[str, dict[str, Any]] = OrderedDict()
    for name in PLATFORMS:
        bucket = buckets[name]
        if bucket["total"] == 0:
            continue
        bucket["pass_rate"] = round(bucket["passed"] / bucket["total"] * 100, 2)
        result[name] = bucket
    return result
