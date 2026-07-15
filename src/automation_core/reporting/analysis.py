from __future__ import annotations

from collections import Counter
from typing import Any

from automation_core.reporting.models import RunReport, TestCaseReport
from automation_core.reporting.traversal import collect_action_retries

FAILED_STATUSES = {"failed", "broken"}
PASSED_STATUS = "passed"
SKIPPED_STATUS = "skipped"
DEFAULT_SLOW_THRESHOLD_MS = 30_000
MATRIX_STATUSES = ("passed", "failed", "broken", "skipped", "unknown")

FAILURE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("appium_server_unreachable", ("appium server unreachable", "appium", "connection refused", "could not connect")),
    ("app_not_installed", ("app not installed", "application is not installed", "install_failed")),
    ("webview_context_missing", ("webview context", "webview", "context missing", "context not found")),
    ("api_contract_mismatch", ("contract mismatch", "schema validation", "jsonschema", "contract validation")),
    ("locator_not_found", ("locator not found", "no such element", "element not found", "strict mode violation")),
    ("auth_config_issue", ("unauthorized", "forbidden", "401", "403", "auth", "missing environment", "config")),
    ("timeout", ("timeout", "timed out")),
    ("assertion_mismatch", ("assert", "expected", "actual", "mismatch")),
)

FAILURE_SUMMARIES: dict[str, dict[str, str]] = {
    "locator_not_found": {
        "title": "Locator not found",
        "detail": "Inspect the selector, page state, screenshots, and source snapshots for a missing or changed element.",
    },
    "timeout": {
        "title": "Timeout",
        "detail": "Check waits, service readiness, device/browser responsiveness, and the nearest timeline events.",
    },
    "assertion_mismatch": {
        "title": "Assertion mismatch",
        "detail": "Compare expected and actual values, then inspect related logs, payloads, or screenshots.",
    },
    "api_contract_mismatch": {
        "title": "API contract mismatch",
        "detail": "Review schema or contract validation output and sanitized request/response artifacts.",
    },
    "appium_server_unreachable": {
        "title": "Appium server unreachable",
        "detail": "Check server availability, endpoint configuration, logs, and capability setup.",
    },
    "app_not_installed": {
        "title": "App not installed",
        "detail": "Inspect app installation steps, app path, package or bundle identifiers, and device state.",
    },
    "webview_context_missing": {
        "title": "Webview context missing",
        "detail": "Check context discovery, hybrid app readiness, platform capabilities, and context switch timing.",
    },
    "auth_config_issue": {
        "title": "Auth or configuration issue",
        "detail": "Review credentials, environment selection, configuration values, and authorization responses.",
    },
    "unknown": {
        "title": "Unknown failure",
        "detail": "Inspect the failure message, trace, timeline, logs, artifacts, and adapter metadata.",
    },
}


def summarize_run(report: RunReport) -> dict[str, Any]:
    total = len(report.tests)
    passed = sum(1 for test in report.tests if test.status == PASSED_STATUS)
    failed = sum(1 for test in report.tests if test.status == "failed")
    broken = sum(1 for test in report.tests if test.status == "broken")
    skipped = sum(1 for test in report.tests if test.status == SKIPPED_STATUS)
    flaky = sum(1 for test in report.tests if is_test_flaky(test) or has_action_flaky(test))
    duration_ms = report.duration_ms or sum(test.duration_ms for test in report.tests)
    pass_rate = round((passed / total) * 100, 2) if total else 0
    status = "passed" if total and failed + broken == 0 else "failed"
    if total == 0:
        status = "unknown"

    return {
        "run_id": report.run_id,
        "project_name": report.project_name,
        "framework": report.framework,
        "latest_run": report.generated_at.isoformat(),
        "status": status,
        "total": total,
        "passed": passed,
        "failed": failed,
        "broken": broken,
        "skipped": skipped,
        "flaky": flaky,
        "duration_ms": duration_ms,
        "pass_rate": pass_rate,
        "profiles": sorted(_non_empty(test.profile for test in report.tests)),
        "environments": sorted(_non_empty(test.environment for test in report.tests)),
        "browsers": sorted(_non_empty(_metadata_value(test, "browser") for test in report.tests)),
        "devices": sorted(_non_empty(_metadata_value(test, "device_name") for test in report.tests)),
    }


def fastest_slowest_tests(report: RunReport, *, limit: int = 5) -> dict[str, list[TestCaseReport]]:
    finished_tests = [test for test in report.tests if test.duration_ms is not None]
    fastest = sorted(finished_tests, key=lambda test: test.duration_ms)[:limit]
    slowest = sorted(finished_tests, key=lambda test: test.duration_ms, reverse=True)[:limit]
    return {"fastest": fastest, "slowest": slowest}


def flaky_analysis(
    report: RunReport,
    *,
    slow_threshold_ms: float = DEFAULT_SLOW_THRESHOLD_MS,
) -> list[dict[str, Any]]:
    analysis: list[dict[str, Any]] = []
    for test in report.tests:
        category = ""
        reason = ""
        if is_test_flaky(test):
            category = "test_retry_flaky"
            reason = "failed/broken attempt eventually passed"
        elif has_action_flaky(test):
            category = "action_retry_flaky"
            reason = "action retry failed then passed"
        elif test.status in FAILED_STATUSES:
            category = "always_failing"
            reason = classify_failure(test)
        elif test.status == PASSED_STATUS and test.duration_ms >= slow_threshold_ms:
            category = "slow_but_passing"
            reason = f"duration >= {slow_threshold_ms:.0f} ms"

        if category:
            analysis.append(
                {
                    "test_id": test.id,
                    "name": test.name,
                    "full_name": test.full_name,
                    "status": test.status,
                    "category": category,
                    "reason": reason,
                    "duration_ms": test.duration_ms,
                }
            )
    return analysis


def failure_categories(report: RunReport) -> dict[str, int]:
    counter = Counter(classify_failure(test) for test in report.tests if test.status in FAILED_STATUSES)
    return dict(sorted(counter.items()))


def failure_summary(test: TestCaseReport) -> dict[str, str]:
    category = classify_failure(test)
    template = FAILURE_SUMMARIES.get(category)
    if template is None:
        return {
            "category": category,
            "title": _humanize_category(category),
            "detail": "Review the failure message, trace, artifacts, and adapter metadata for this category.",
        }
    return {"category": category, "title": template["title"], "detail": template["detail"]}


def classify_failure(test: TestCaseReport) -> str:
    explicit = test.metadata.get("failure_category")
    if isinstance(explicit, str) and explicit:
        return explicit

    text = " ".join(
        str(part)
        for part in (
            test.failure_message,
            test.failure_trace,
            test.metadata.get("error"),
            test.metadata.get("failure_reason"),
        )
        if part
    ).lower()
    if not text:
        return "unknown"

    for category, patterns in FAILURE_RULES:
        if _matches_rule(text, patterns):
            return category
    return "unknown"


def is_test_flaky(test: TestCaseReport) -> bool:
    if test.status != PASSED_STATUS:
        return False
    retry_statuses = [retry.status for retry in test.retries]
    return any(status in FAILED_STATUSES for status in retry_statuses)


def has_action_flaky(test: TestCaseReport) -> bool:
    action_retries = collect_action_retries(test)
    if not action_retries:
        return False
    statuses = [retry.status for retry in action_retries]
    return any(status in FAILED_STATUSES for status in statuses) and statuses[-1] == PASSED_STATUS


def matrix_summary(report: RunReport) -> dict[str, dict[str, dict[str, Any]]]:
    summary: dict[str, dict[str, dict[str, Any]]] = {}
    for dimension in report.matrix_dimensions:
        values: dict[str, dict[str, Any]] = {}
        for test in report.tests:
            for value in _dimension_values(test, dimension):
                bucket = values.setdefault(
                    str(value),
                    {"total": 0, "passed": 0, "failed": 0, "broken": 0, "skipped": 0, "unknown": 0},
                )
                bucket["total"] += 1
                bucket[test.status if test.status in MATRIX_STATUSES else "unknown"] += 1
                if test.status in FAILED_STATUSES:
                    categories = bucket.setdefault("failure_categories", {})
                    category = classify_failure(test)
                    categories[category] = categories.get(category, 0) + 1
        for bucket in values.values():
            bucket["pass_rate"] = round((bucket["passed"] / bucket["total"]) * 100, 2) if bucket["total"] else 0
        if values:
            summary[dimension] = values
    return summary


def _matches_rule(text: str, patterns: tuple[str, ...]) -> bool:
    if len(patterns) == 1:
        return patterns[0] in text
    if patterns[0] in text:
        return True
    return any(pattern in text for pattern in patterns[1:])


def _humanize_category(category: str) -> str:
    return " ".join(part.capitalize() for part in category.replace("-", "_").split("_") if part) or "Unknown failure"


def _metadata_value(test: TestCaseReport, key: str) -> Any:
    if key in test.metadata:
        return test.metadata[key]
    return test.capabilities.get(key)


def _dimension_values(test: TestCaseReport, dimension: str) -> list[Any]:
    value = _dimension_value(test, dimension)
    if value in (None, ""):
        return []
    if isinstance(value, (list, tuple, set)):
        return [item for item in value if item not in (None, "")]
    return [value]


def _dimension_value(test: TestCaseReport, dimension: str) -> Any:
    if dimension in {"id", "name", "status", "full_name", "suite", "domain", "profile", "environment"}:
        return getattr(test, dimension)
    if dimension in test.metadata:
        return test.metadata[dimension]
    if dimension in test.capabilities:
        return test.capabilities[dimension]
    if dimension in test.labels:
        return test.labels[dimension]
    return None


def _non_empty(values) -> set[str]:
    return {str(value) for value in values if value not in (None, "")}
