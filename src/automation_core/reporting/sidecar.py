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
from automation_core.reporting.insights import ReportInsightConfig, build_enterprise_insights
from automation_core.reporting.models import Artifact, RunReport, TestCaseReport, to_jsonable
from automation_core.reporting.quality import QualityGate, QualityGateConfig, evaluate_quality_gates
from automation_core.reporting.redaction import redact_payload, redact_report, redaction_manifest
from automation_core.reporting.traversal import collect_action_retries, collect_test_artifacts, iter_steps

FAILED_STATUSES = {"failed", "broken", "error"}
EMPTY_FAILURE_SUMMARY = {"category": "", "title": "", "detail": ""}


def build_report_data(
    report: RunReport,
    *,
    history_entries: list[dict[str, Any]] | None = None,
    timeline_events: list[ReportingEvent] | None = None,
    details: dict[str, str] | None = None,
    quality_gates: QualityGateConfig
    | list[QualityGate | dict[str, Any]]
    | tuple[QualityGate | dict[str, Any], ...]
    | None = None,
    insight_config: ReportInsightConfig | dict[str, Any] | None = None,
    safe_share: bool = True,
    redaction: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the machine-readable product report sidecar."""

    if safe_share:
        report, redaction = redact_report(report)
    elif redaction is None:
        redaction = redaction_manifest(False)

    history = history_entries or []
    timeline = timeline_events if timeline_events is not None else build_timeline_events(report)
    summary = summarize_run(report)
    speed = fastest_slowest_tests(report, limit=10)
    test_index = _test_index(report, details or {})
    aggregates = _aggregates(report, test_index)
    signals = _signal_counts(report)
    run_comparison = _run_comparison(summary, history, signals)
    failure_transitions = _failure_transitions(test_index, history, summary)
    insights = build_enterprise_insights(
        report,
        summary=summary,
        test_index=test_index,
        signals=signals,
        failure_transitions=failure_transitions,
        history_entries=history,
        run_comparison=run_comparison,
        config=insight_config,
    )

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
            "run_comparison": _run_comparison_chart(run_comparison),
            "quality_score_components": insights["quality_score"]["components"],
            "compare_metrics": insights["compare"]["metrics"],
        },
        "top_slow_tests": _test_refs(speed["slowest"]),
        "failure_clusters": _failure_clusters(report),
        "flaky": {
            "items": flaky_analysis(report),
            "breakdown": _flaky_breakdown(report),
        },
        "signals": signals,
        "risk_signals": _risk_signals(report, test_index),
        "quality_score": insights["quality_score"],
        "risk_signal": insights["risk_signal"],
        "quality": evaluate_quality_gates(report, quality_gates).to_dict(),
        "default_gate_status": insights["default_gate_status"],
        "failure_transitions": failure_transitions,
        "run_comparison": run_comparison,
        "compare": insights["compare"],
        "stability": insights["stability"],
        "recovery": insights["recovery"],
        "resource_efficiency": insights["resource_efficiency"],
        "ui_metadata": insights["ui_metadata"],
        "report_config": insights["config"],
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
        "sharing": {
            "safe_share": redaction,
            "exports": _default_export_links(),
        },
    }
    if safe_share:
        payload, payload_redaction = redact_payload(payload)
        payload["sharing"]["safe_share"] = _merge_redaction(redaction, payload_redaction)
    return to_jsonable(payload)


def _default_export_links() -> dict[str, str]:
    return {
        "sidecar_json": "report-data.json",
        "run_report_json": "data/run-report.json",
        "test_index_csv": "exports/test-index.csv",
        "test_index_xlsx": "exports/test-index.xlsx",
        "executive_summary_docx": "exports/executive-summary.docx",
        "share_card_svg": "exports/share-card.svg",
        "report_bundle_json": "exports/report-bundle.json",
        "share_manifest_json": "exports/share-manifest.json",
        "print_summary_html": "print-summary.html",
        "full_report_entry": "index.html",
    }


def _merge_redaction(primary: dict[str, Any] | None, secondary: dict[str, Any] | None) -> dict[str, Any]:
    primary = primary or redaction_manifest(True)
    secondary = secondary or redaction_manifest(True)
    counts: Counter[str] = Counter()
    counts.update(primary.get("redacted_counts", {}))
    counts.update(secondary.get("redacted_counts", {}))
    patterns = list(primary.get("patterns", []))
    for pattern in secondary.get("patterns", []):
        if pattern not in patterns:
            patterns.append(pattern)
    return {
        "enabled": bool(primary.get("enabled") or secondary.get("enabled")),
        "replacement": primary.get("replacement") or secondary.get("replacement") or "[redacted]",
        "patterns": patterns,
        "redacted_categories": sorted(counts),
        "redacted_counts": dict(sorted(counts.items())),
    }


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
        summary = _failure_summary_for_index(test)
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


def _failure_summary_for_index(test: TestCaseReport) -> dict[str, str]:
    if _has_failure_details(test):
        return failure_summary(test)
    return dict(EMPTY_FAILURE_SUMMARY)


def _has_failure_details(test: TestCaseReport) -> bool:
    if _is_failure_status(test.status):
        return True
    if test.failure_message or test.failure_trace:
        return True
    for key in ("error", "failure_reason", "failure_category"):
        if test.metadata.get(key):
            return True
    return False


def _aggregates(report: RunReport, test_index: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(_status_group(test.status) for test in report.tests)
    duration_buckets = Counter(item["duration_bucket"] for item in test_index)
    failure_counter = Counter(
        item["failure"]["category"]
        for item in test_index
        if _is_failure_status(item.get("status")) and item.get("failure", {}).get("category")
    )
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
    failed = [item for item in test_index if _is_failure_status(item["status"])]
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


def _failure_transitions(
    test_index: list[dict[str, Any]],
    history_entries: list[dict[str, Any]],
    summary: dict[str, Any],
) -> dict[str, Any]:
    previous = _previous_history_entry(summary, history_entries)
    empty = {
        "previous_run_id": "",
        "new_failures": [],
        "known_failures": [],
        "resolved_failures": [],
        "counts": {"new": 0, "known": 0, "resolved": 0},
    }
    if not previous:
        return empty

    current_by_identity = {
        _test_identity_from_index(item): item for item in test_index if _test_identity_from_index(item)
    }
    current_failed = {
        identity: item for identity, item in current_by_identity.items() if _is_failure_status(item.get("status"))
    }
    previous_failed = {
        _test_identity_from_history(item): item
        for item in previous.get("failed_tests", [])
        if isinstance(item, dict) and _test_identity_from_history(item)
    }

    new_failures = [
        _failure_transition_current_ref(identity, item)
        for identity, item in current_failed.items()
        if identity not in previous_failed
    ]
    known_failures = [
        _failure_transition_current_ref(identity, item)
        for identity, item in current_failed.items()
        if identity in previous_failed
    ]
    resolved_failures: list[dict[str, Any]] = []
    for identity, previous_item in previous_failed.items():
        if identity in current_failed:
            continue
        current_item = current_by_identity.get(identity)
        if current_item is None or current_item.get("status") == "passed":
            resolved_failures.append(_resolved_failure_ref(identity, previous_item, current_item))

    return {
        "previous_run_id": previous.get("run_id", ""),
        "new_failures": new_failures,
        "known_failures": known_failures,
        "resolved_failures": resolved_failures,
        "counts": {
            "new": len(new_failures),
            "known": len(known_failures),
            "resolved": len(resolved_failures),
        },
    }


def _run_comparison(
    summary: dict[str, Any],
    history_entries: list[dict[str, Any]],
    signals: dict[str, Any],
) -> dict[str, Any]:
    previous = _previous_history_entry(summary, history_entries)
    if not previous:
        return {}

    metrics = {
        "total": (summary.get("total", 0), previous.get("total", 0)),
        "passed": (summary.get("passed", 0), previous.get("passed", 0)),
        "pass_rate": (summary.get("pass_rate", 0), previous.get("pass_rate", 0)),
        "failed_broken": (
            summary.get("failed", 0) + summary.get("broken", 0),
            previous.get("failed", 0) + previous.get("broken", 0),
        ),
        "skipped": (summary.get("skipped", 0), previous.get("skipped", 0)),
        "flaky": (summary.get("flaky", 0), previous.get("flaky", 0)),
        "duration_ms": (summary.get("duration_ms", 0), previous.get("duration_ms", 0)),
        "test_retry_count": (signals.get("test_retry_count", 0), _previous_signal(previous, "test_retry_count")),
        "action_retry_count": (
            signals.get("action_retry_count", 0),
            _previous_signal(previous, "action_retry_count"),
        ),
        "healing_event_count": (
            signals.get("healing_event_count", 0),
            _previous_signal(previous, "healing_event_count"),
        ),
        "artifact_count": (signals.get("artifact_count", 0), _previous_signal(previous, "artifact_count")),
    }
    values = {
        metric: {
            "current": current,
            "previous": previous_value,
            "delta": _numeric_delta(current, previous_value),
        }
        for metric, (current, previous_value) in metrics.items()
    }
    return {
        "current_run_id": summary.get("run_id", ""),
        "previous_run_id": previous.get("run_id", ""),
        "values": values,
        "deltas": {metric: item["delta"] for metric, item in values.items()},
    }


def _run_comparison_chart(comparison: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"metric": metric, **values}
        for metric, values in comparison.get("values", {}).items()
        if metric
        in {
            "total",
            "passed",
            "pass_rate",
            "failed_broken",
            "skipped",
            "flaky",
            "test_retry_count",
            "action_retry_count",
        }
    ]


def _test_identity_from_index(item: dict[str, Any]) -> str:
    return str(item.get("test_id") or item.get("full_name") or item.get("name") or "")


def _test_identity_from_history(item: dict[str, Any]) -> str:
    return str(item.get("identity") or item.get("test_id") or item.get("full_name") or item.get("name") or "")


def _failure_transition_current_ref(identity: str, item: dict[str, Any]) -> dict[str, Any]:
    failure = item.get("failure", {})
    return {
        "identity": identity,
        "test_id": item.get("test_id", ""),
        "name": item.get("name", ""),
        "full_name": item.get("full_name", ""),
        "status": item.get("status", ""),
        "detail_href": item.get("detail_href", ""),
        "failure_category": failure.get("category", ""),
        "failure_title": failure.get("title", ""),
    }


def _resolved_failure_ref(
    identity: str,
    previous_item: dict[str, Any],
    current_item: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "identity": identity,
        "test_id": (current_item or previous_item).get("test_id", ""),
        "name": (current_item or previous_item).get("name", ""),
        "full_name": (current_item or previous_item).get("full_name", ""),
        "previous_status": previous_item.get("status", ""),
        "current_status": current_item.get("status", "absent") if current_item else "absent",
        "detail_href": current_item.get("detail_href", "") if current_item else "",
        "failure_category": previous_item.get("failure_category", ""),
    }


def _previous_signal(previous: dict[str, Any], key: str) -> Any:
    signals = previous.get("signals", {})
    if isinstance(signals, dict):
        return signals.get(key, 0)
    return 0


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
        if not _is_failure_status(test.status):
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


def _is_failure_status(status: Any) -> bool:
    return str(status or "").lower() in FAILED_STATUSES


def _status_group(status: str) -> str:
    if status == "passed":
        return "passed"
    if _is_failure_status(status):
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
        if _is_failure_status(item.get("status")) and item.get("failure", {}).get("category"):
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
