from __future__ import annotations

from collections import Counter
from typing import Any

from automation_core.reporting.analysis import (
    failure_summary,
    fastest_slowest_tests,
    flaky_analysis,
    matrix_summary,
    summarize_run,
)
from automation_core.reporting.events import ReportingEvent, build_timeline_events
from automation_core.reporting.history import trend_points
from automation_core.reporting.models import Artifact, RunReport, TestCaseReport, to_jsonable
from automation_core.reporting.traversal import collect_action_retries, collect_test_artifacts, iter_steps

FAILED_STATUSES = {"failed", "broken"}


def build_report_data(
    report: RunReport,
    *,
    history_entries: list[dict[str, Any]] | None = None,
    timeline_events: list[ReportingEvent] | None = None,
    details: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build the machine-readable product report sidecar."""

    history = history_entries or []
    timeline = timeline_events if timeline_events is not None else build_timeline_events(report)
    summary = summarize_run(report)
    speed = fastest_slowest_tests(report, limit=10)
    test_index = _test_index(report, details or {})
    aggregates = _aggregates(report, test_index)

    payload = {
        "run": {
            "summary": summary,
            "health": _run_health(summary, history),
        },
        "test_index": test_index,
        "aggregates": aggregates,
        "charts": {
            "status_distribution": aggregates["status_distribution"],
            "duration_buckets": aggregates["duration_buckets"],
            "failure_categories": aggregates["failure_categories"],
            "retry_signals": aggregates["retry_signals"],
            "artifact_types": aggregates["artifact_types"],
            "coverage": aggregates["coverage"],
        },
        "top_slow_tests": _test_refs(speed["slowest"]),
        "failure_clusters": _failure_clusters(report),
        "flaky": {
            "items": flaky_analysis(report),
            "breakdown": _flaky_breakdown(report),
        },
        "signals": _signal_counts(report),
        "risk_signals": _risk_signals(report, test_index),
        "matrix": matrix_summary(report),
        "timeline": {
            "event_counts": dict(sorted(Counter(event.event_type for event in timeline).items())),
            "events": [event.to_dict() for event in timeline],
        },
        "history": {
            "trend_points": trend_points(history),
            "comparison": _history_comparison(summary, history),
        },
        "artifacts": _artifact_index(report),
    }
    return to_jsonable(payload)


def _test_index(report: RunReport, details: dict[str, str]) -> list[dict[str, Any]]:
    flaky_items = flaky_analysis(report)
    flaky_by_test: dict[str, list[dict[str, Any]]] = {}
    for item in flaky_items:
        flaky_by_test.setdefault(item["test_id"], []).append(item)

    index: list[dict[str, Any]] = []
    for test in report.tests:
        artifacts = collect_test_artifacts(test)
        action_retries = collect_action_retries(test)
        healing_events = _healing_events_for_test(test)
        summary = failure_summary(test)
        artifact_types = sorted({artifact.artifact_type for artifact in artifacts if artifact.artifact_type})
        record = {
            "test_id": test.id,
            "name": test.name,
            "full_name": test.full_name,
            "suite": test.suite,
            "status": test.status,
            "domain": test.domain,
            "profile": test.profile,
            "environment": test.environment,
            "duration_ms": test.duration_ms,
            "duration_bucket": _duration_bucket(test.duration_ms),
            "detail_href": details.get(test.id, ""),
            "failure": summary,
            "failure_message": test.failure_message[:500],
            "browser": _metadata_value(test, "browser"),
            "device_name": _metadata_value(test, "device_name"),
            "platform": _metadata_value(test, "platform"),
            "platform_version": _metadata_value(test, "platform_version"),
            "context": _metadata_value(test, "context"),
            "api_profile": _metadata_value(test, "api_profile"),
            "flaky_categories": sorted({item["category"] for item in flaky_by_test.get(test.id, [])}),
            "retry_count": len(test.retries),
            "action_retry_count": len(action_retries),
            "healing_event_count": len(healing_events),
            "artifact_count": len(artifacts),
            "artifact_types": artifact_types,
            "artifact_names": [artifact.name for artifact in artifacts],
            "step_count": sum(1 for _ in iter_steps(test.steps)),
            "has_test_retries": bool(test.retries),
            "has_action_retries": bool(action_retries),
            "has_healing": bool(healing_events),
            "has_artifacts": bool(artifacts),
            "metadata": test.metadata,
            "capabilities": test.capabilities,
        }
        record["search_text"] = _search_text(record)
        index.append(record)
    return index


def _aggregates(report: RunReport, test_index: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(_status_group(test.status) for test in report.tests)
    duration_buckets = Counter(item["duration_bucket"] for item in test_index)
    failure_counter = Counter(item["failure"]["category"] for item in test_index if item["status"] in FAILED_STATUSES)
    artifact_types: Counter[str] = Counter()
    for item in test_index:
        artifact_types.update(item["artifact_types"])

    return {
        "status_distribution": {
            "passed": status_counts.get("passed", 0),
            "failed_broken": status_counts.get("failed_broken", 0),
            "skipped": status_counts.get("skipped", 0),
            "unknown": status_counts.get("unknown", 0),
        },
        "raw_statuses": dict(sorted(Counter(test.status or "unknown" for test in report.tests).items())),
        "duration_buckets": {bucket: duration_buckets.get(bucket, 0) for bucket in _duration_bucket_order()},
        "failure_categories": dict(sorted(failure_counter.items())),
        "retry_signals": _signal_counts(report),
        "artifact_types": dict(sorted(artifact_types.items())),
        "coverage": _coverage_dimensions(test_index),
        "filter_options": _filter_options(test_index),
    }


def _risk_signals(report: RunReport, test_index: list[dict[str, Any]]) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []
    failed = [item for item in test_index if item["status"] in FAILED_STATUSES]
    flaky = [item for item in test_index if item["flaky_categories"]]
    high_retries = [item for item in test_index if item["retry_count"] + item["action_retry_count"] >= 3]
    slow = sorted(test_index, key=lambda item: item["duration_ms"], reverse=True)[:3]
    missing_steps = [item for item in test_index if item["step_count"] == 0]
    missing_artifacts = [item for item in failed if not item["has_artifacts"]]

    if failed:
        risks.append({"severity": "high", "title": "Failing tests", "count": len(failed), "tests": _risk_tests(failed)})
    if flaky:
        risks.append({"severity": "medium", "title": "Flaky signals", "count": len(flaky), "tests": _risk_tests(flaky)})
    if high_retries:
        risks.append(
            {
                "severity": "medium",
                "title": "High retry count",
                "count": len(high_retries),
                "tests": _risk_tests(high_retries),
            }
        )
    if slow and report.tests:
        risks.append({"severity": "low", "title": "Slowest tests", "count": len(slow), "tests": _risk_tests(slow)})
    if missing_artifacts:
        risks.append(
            {
                "severity": "medium",
                "title": "Failed tests without artifacts",
                "count": len(missing_artifacts),
                "tests": _risk_tests(missing_artifacts),
            }
        )
    if missing_steps and len(missing_steps) == len(test_index) and test_index:
        risks.append({"severity": "low", "title": "No steps captured", "count": len(missing_steps), "tests": []})
    return risks


def _run_health(summary: dict[str, Any], history_entries: list[dict[str, Any]]) -> dict[str, Any]:
    previous = _previous_history_entry(summary, history_entries)
    failed_total = summary.get("failed", 0) + summary.get("broken", 0)
    health = {
        "pass_rate": summary.get("pass_rate", 0),
        "failed_total": failed_total,
        "flaky": summary.get("flaky", 0),
        "duration_ms": summary.get("duration_ms", 0),
        "previous_run_id": previous.get("run_id") if previous else "",
        "pass_rate_delta": None,
        "failed_delta": None,
        "flaky_delta": None,
        "duration_delta_ms": None,
    }
    if not previous:
        return health

    health["pass_rate_delta"] = _numeric_delta(summary.get("pass_rate", 0), previous.get("pass_rate", 0))
    health["failed_delta"] = _numeric_delta(failed_total, previous.get("failed", 0) + previous.get("broken", 0))
    health["flaky_delta"] = _numeric_delta(summary.get("flaky", 0), previous.get("flaky", 0))
    health["duration_delta_ms"] = _numeric_delta(summary.get("duration_ms", 0), previous.get("duration_ms", 0))
    return health


def _history_comparison(summary: dict[str, Any], history_entries: list[dict[str, Any]]) -> dict[str, Any]:
    previous = _previous_history_entry(summary, history_entries)
    if not previous:
        return {}
    return {
        "current_run_id": summary.get("run_id", ""),
        "previous_run_id": previous.get("run_id", ""),
        "current_pass_rate": summary.get("pass_rate", 0),
        "previous_pass_rate": previous.get("pass_rate", 0),
        "pass_rate_delta": _numeric_delta(summary.get("pass_rate", 0), previous.get("pass_rate", 0)),
        "failed_delta": _numeric_delta(
            summary.get("failed", 0) + summary.get("broken", 0),
            previous.get("failed", 0) + previous.get("broken", 0),
        ),
        "flaky_delta": _numeric_delta(summary.get("flaky", 0), previous.get("flaky", 0)),
        "duration_delta_ms": _numeric_delta(summary.get("duration_ms", 0), previous.get("duration_ms", 0)),
    }


def _previous_history_entry(summary: dict[str, Any], history_entries: list[dict[str, Any]]) -> dict[str, Any] | None:
    current_run_id = summary.get("run_id")
    for entry in reversed(history_entries):
        if entry.get("run_id") != current_run_id:
            return entry
    return None


def _numeric_delta(current: Any, previous: Any) -> float:
    return round(float(current or 0) - float(previous or 0), 2)


def _failure_clusters(report: RunReport) -> list[dict[str, Any]]:
    clusters: dict[str, dict[str, Any]] = {}
    for test in report.tests:
        if test.status not in FAILED_STATUSES:
            continue
        summary = failure_summary(test)
        cluster = clusters.setdefault(
            summary["category"],
            {
                "category": summary["category"],
                "title": summary["title"],
                "detail": summary["detail"],
                "count": 0,
                "tests": [],
            },
        )
        cluster["count"] += 1
        cluster["tests"].append(_test_ref(test, include_failure=True))
    return sorted(clusters.values(), key=lambda item: (-item["count"], item["category"]))


def _flaky_breakdown(report: RunReport) -> dict[str, int]:
    counter = Counter(item["category"] for item in flaky_analysis(report))
    return {
        "test_retry_flaky": counter.get("test_retry_flaky", 0),
        "action_retry_flaky": counter.get("action_retry_flaky", 0),
        "always_failing": counter.get("always_failing", 0),
        "slow_but_passing": counter.get("slow_but_passing", 0),
    }


def _signal_counts(report: RunReport) -> dict[str, Any]:
    healing_decisions: Counter[str] = Counter()
    healing_total = 0
    for test in report.tests:
        for event in _healing_events_for_test(test):
            healing_total += 1
            healing_decisions[str(event.get("decision") or "unknown")] += 1

    return {
        "artifact_count": sum(len(collect_test_artifacts(test)) for test in report.tests),
        "action_retry_count": sum(len(collect_action_retries(test)) for test in report.tests),
        "test_retry_count": sum(len(test.retries) for test in report.tests),
        "healing_event_count": healing_total,
        "healing_decisions": dict(sorted(healing_decisions.items())),
    }


def _artifact_index(report: RunReport) -> list[dict[str, Any]]:
    indexed: list[dict[str, Any]] = []
    for test in report.tests:
        for artifact in collect_test_artifacts(test):
            indexed.append(_artifact_ref(test, artifact))
    return indexed


def _healing_events_for_test(test: TestCaseReport) -> list[dict[str, Any]]:
    events = test.metadata.get("healing_events", [])
    if not isinstance(events, list):
        return []
    return [event for event in events if isinstance(event, dict)]


def _artifact_ref(test: TestCaseReport, artifact: Artifact) -> dict[str, Any]:
    return {
        "test_id": test.id,
        "test_name": test.name,
        "name": artifact.name,
        "artifact_type": artifact.artifact_type,
        "href": artifact.href,
        "path": artifact.path,
        "mime_type": artifact.mime_type,
        "size_bytes": artifact.size_bytes,
        "bundled": bool(artifact.metadata.get("bundled")),
        "metadata": artifact.metadata,
    }


def _test_refs(tests: list[TestCaseReport]) -> list[dict[str, Any]]:
    return [_test_ref(test) for test in tests]


def _test_ref(test: TestCaseReport, *, include_failure: bool = False) -> dict[str, Any]:
    item: dict[str, Any] = {
        "test_id": test.id,
        "name": test.name,
        "full_name": test.full_name,
        "status": test.status,
        "duration_ms": test.duration_ms,
        "domain": test.domain,
        "profile": test.profile,
        "environment": test.environment,
    }
    if include_failure:
        item["failure_message"] = test.failure_message[:300]
    return item


def _status_group(status: str) -> str:
    if status == "passed":
        return "passed"
    if status in FAILED_STATUSES:
        return "failed_broken"
    if status == "skipped":
        return "skipped"
    return "unknown"


def _duration_bucket(duration_ms: float | int) -> str:
    duration = float(duration_ms or 0)
    if duration < 1_000:
        return "<1s"
    if duration < 5_000:
        return "1-5s"
    if duration < 15_000:
        return "5-15s"
    if duration < 30_000:
        return "15-30s"
    return "30s+"


def _duration_bucket_order() -> tuple[str, ...]:
    return ("<1s", "1-5s", "5-15s", "15-30s", "30s+")


def _coverage_dimensions(test_index: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    dimensions = ("domain", "profile", "environment", "browser", "device_name", "platform", "context", "api_profile")
    coverage: dict[str, dict[str, int]] = {}
    for dimension in dimensions:
        counter: Counter[str] = Counter()
        for item in test_index:
            for value in _values(item.get(dimension)):
                counter[value] += 1
        if counter:
            coverage[dimension] = dict(sorted(counter.items()))
    return coverage


def _filter_options(test_index: list[dict[str, Any]]) -> dict[str, list[str]]:
    options: dict[str, set[str]] = {
        "status": set(),
        "domain": set(),
        "profile": set(),
        "environment": set(),
        "browser": set(),
        "device_name": set(),
        "platform": set(),
        "context": set(),
        "failure_category": set(),
        "flaky_category": set(),
        "artifact_type": set(),
        "duration_bucket": set(),
    }
    for item in test_index:
        for key in ("status", "domain", "profile", "environment", "browser", "device_name", "platform", "context"):
            options[key].update(_values(item.get(key)))
        options["failure_category"].add(item["failure"]["category"])
        options["duration_bucket"].add(item["duration_bucket"])
        options["flaky_category"].update(item["flaky_categories"])
        options["artifact_type"].update(item["artifact_types"])
    return {key: sorted(value for value in values if value) for key, values in options.items()}


def _risk_tests(items: list[dict[str, Any]], *, limit: int = 5) -> list[dict[str, Any]]:
    return [
        {
            "test_id": item["test_id"],
            "name": item["name"],
            "status": item["status"],
            "duration_ms": item["duration_ms"],
            "detail_href": item["detail_href"],
        }
        for item in items[:limit]
    ]


def _metadata_value(test: TestCaseReport, key: str) -> Any:
    if key in test.metadata:
        return test.metadata[key]
    if key in test.capabilities:
        return test.capabilities[key]
    if key in test.labels:
        return test.labels[key]
    return ""


def _values(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, list | tuple | set):
        return [str(item) for item in value if item not in (None, "")]
    return [str(value)]


def _search_text(record: dict[str, Any]) -> str:
    parts: list[str] = []
    keys = (
        "test_id",
        "name",
        "full_name",
        "suite",
        "status",
        "domain",
        "profile",
        "environment",
        "browser",
        "device_name",
        "platform",
        "context",
        "api_profile",
        "failure_message",
    )
    for key in keys:
        parts.extend(_values(record.get(key)))
    parts.extend(_values(record["failure"].get("category")))
    parts.extend(_values(record["failure"].get("title")))
    parts.extend(record["artifact_names"])
    parts.extend(record["artifact_types"])
    parts.extend(record["flaky_categories"])
    parts.append(_json_text(record.get("metadata", {})))
    parts.append(_json_text(record.get("capabilities", {})))
    return " ".join(parts).lower()


def _json_text(value: Any) -> str:
    return str(to_jsonable(value)).replace("<", "").replace(">", "")
