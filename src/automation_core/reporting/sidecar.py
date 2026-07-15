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
from automation_core.reporting.traversal import collect_action_retries, collect_test_artifacts

FAILED_STATUSES = {"failed", "broken"}


def build_report_data(
    report: RunReport,
    *,
    history_entries: list[dict[str, Any]] | None = None,
    timeline_events: list[ReportingEvent] | None = None,
) -> dict[str, Any]:
    """Build the machine-readable product report sidecar."""

    history = history_entries or []
    timeline = timeline_events if timeline_events is not None else build_timeline_events(report)
    summary = summarize_run(report)
    speed = fastest_slowest_tests(report, limit=10)

    payload = {
        "run": {
            "summary": summary,
            "health": _run_health(summary, history),
        },
        "top_slow_tests": _test_refs(speed["slowest"]),
        "failure_clusters": _failure_clusters(report),
        "flaky": {
            "items": flaky_analysis(report),
            "breakdown": _flaky_breakdown(report),
        },
        "signals": _signal_counts(report),
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
