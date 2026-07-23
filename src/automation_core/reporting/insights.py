from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from automation_core.reporting.models import RunReport
from automation_core.reporting.quality import QualityGateConfig
from automation_core.reporting.status import PASSED_STATUS, is_blocking_failure_status, normalized_status


@dataclass(frozen=True)
class QualityScoreWeights:
    failure_penalty: float = 8.0
    flaky_penalty: float = 4.0
    retry_penalty: float = 1.5
    action_retry_penalty: float = 1.0
    slow_penalty: float = 2.0
    max_total_penalty: float = 70.0


@dataclass(frozen=True)
class RiskThresholds:
    medium_failed: int = 1
    high_failed: int = 3
    medium_flaky: int = 2
    high_flaky: int = 5
    medium_new_failures: int = 1
    high_new_failures: int = 3
    medium_retries: int = 3
    high_retries: int = 8


@dataclass(frozen=True)
class ReportInsightConfig:
    quality_weights: QualityScoreWeights = field(default_factory=QualityScoreWeights)
    risk_thresholds: RiskThresholds = field(default_factory=RiskThresholds)
    slow_test_threshold_ms: float = 30_000
    stability_history_window: int = 10
    default_min_pass_rate: float = 80.0
    default_duration_budget_ms: float = 60_000.0
    default_max_failed_broken: int = 0
    default_max_flaky: int = 2
    default_max_skipped: int = 20
    default_max_test_retries: int = 3
    default_max_action_retries: int = 5
    worker_count_metadata_keys: tuple[str, ...] = ("worker_count", "workers", "parallel_workers")
    # Feature/domain names expected to have automated coverage. Any listed
    # feature with zero tests in a run is flagged as a coverage gap. Empty means
    # only the features actually present are shown (no gap detection).
    expected_features: tuple[str, ...] = ()

    @classmethod
    def from_value(cls, value: ReportInsightConfig | dict[str, Any] | None) -> ReportInsightConfig:
        if value is None:
            return cls()
        if isinstance(value, cls):
            return value
        defaults = cls()
        weights = value.get("quality_weights", {})
        thresholds = value.get("risk_thresholds", {})
        return cls(
            quality_weights=QualityScoreWeights(**weights) if isinstance(weights, dict) else QualityScoreWeights(),
            risk_thresholds=RiskThresholds(**thresholds) if isinstance(thresholds, dict) else RiskThresholds(),
            slow_test_threshold_ms=float(value.get("slow_test_threshold_ms", defaults.slow_test_threshold_ms)),
            stability_history_window=int(value.get("stability_history_window", defaults.stability_history_window)),
            default_min_pass_rate=float(value.get("default_min_pass_rate", defaults.default_min_pass_rate)),
            default_duration_budget_ms=float(
                value.get("default_duration_budget_ms", defaults.default_duration_budget_ms)
            ),
            default_max_failed_broken=int(value.get("default_max_failed_broken", defaults.default_max_failed_broken)),
            default_max_flaky=int(value.get("default_max_flaky", defaults.default_max_flaky)),
            default_max_skipped=int(value.get("default_max_skipped", defaults.default_max_skipped)),
            default_max_test_retries=int(value.get("default_max_test_retries", defaults.default_max_test_retries)),
            default_max_action_retries=int(
                value.get("default_max_action_retries", defaults.default_max_action_retries)
            ),
            worker_count_metadata_keys=tuple(
                value.get("worker_count_metadata_keys", defaults.worker_count_metadata_keys)
            ),
            expected_features=tuple(value.get("expected_features", defaults.expected_features)),
        )

    def default_gate_config(self) -> QualityGateConfig:
        return QualityGateConfig(
            min_pass_rate=self.default_min_pass_rate,
            max_failed_broken=self.default_max_failed_broken,
            max_flaky=self.default_max_flaky,
            max_skipped=self.default_max_skipped,
            max_test_retries=self.default_max_test_retries,
            max_action_retries=self.default_max_action_retries,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_enterprise_insights(
    report: RunReport,
    *,
    summary: dict[str, Any],
    test_index: list[dict[str, Any]],
    signals: dict[str, Any],
    failure_transitions: dict[str, Any],
    history_entries: list[dict[str, Any]],
    run_comparison: dict[str, Any],
    config: ReportInsightConfig | dict[str, Any] | None = None,
) -> dict[str, Any]:
    active_config = ReportInsightConfig.from_value(config)
    quality_score = _quality_score(summary, test_index, signals, active_config)
    risk_signal = _risk_signal(summary, signals, failure_transitions, test_index, active_config)
    stability = _stability(test_index, history_entries, active_config)
    recovery = _recovery(history_entries, active_config)
    adjusted_pass_rate = _adjusted_pass_rate(test_index)
    default_gates = _design_gate_status(summary, test_index, failure_transitions, adjusted_pass_rate, active_config)
    health_score = _health_score(adjusted_pass_rate, stability)
    return {
        "quality_score": quality_score,
        "adjusted_pass_rate": adjusted_pass_rate,
        "health_score": health_score,
        "risk_signal": risk_signal,
        "default_gate_status": {
            **default_gates,
            "enforced": False,
            "description": "Default gates are informational unless a framework or CI workflow enforces them.",
        },
        "stability": stability,
        "recovery": recovery,
        "resource_efficiency": _resource_efficiency(report, test_index, active_config),
        "compare": _compare(run_comparison, failure_transitions),
        "ui_metadata": {
            "visual_system": "enterprise-redesign",
            "pages": [
                "index.html",
                "executive.html",
                "quality.html",
                "compare.html",
                "explore.html",
                "timeline.html",
                "flaky.html",
                "matrix.html",
                "history.html",
                "share.html",
            ],
        },
        "config": active_config.to_dict(),
    }


def _is_quarantined(item: dict[str, Any]) -> bool:
    metadata = item.get("metadata") or {}
    return bool(metadata.get("quarantined") or metadata.get("known_issue") or item.get("quarantined"))


def _adjusted_pass_rate(test_index: list[dict[str, Any]]) -> float:
    """Pass rate excluding quarantined tests from the denominator.

    ``adjusted pass rate = passed(non-quarantined) / total(non-quarantined)``.
    A run with only quarantined tests (or no tests) reports 100 so it never
    blocks purely on chronically-excluded work.
    """

    considered = [item for item in test_index if not _is_quarantined(item)]
    if not considered:
        return 100.0
    passed = sum(1 for item in considered if str(item.get("status", "")).lower() in {"passed", "pass"})
    return round(passed / len(considered) * 100, 2)


def _new_unresolved_failures(
    test_index: list[dict[str, Any]], failure_transitions: dict[str, Any]
) -> list[dict[str, Any]]:
    quarantined = {item.get("test_id") for item in test_index if _is_quarantined(item)}
    known = {item.get("test_id") for item in test_index if (item.get("metadata") or {}).get("known_issue")}
    excluded = quarantined | known
    return [
        failure
        for failure in failure_transitions.get("new_failures", []) or []
        if failure.get("test_id") not in excluded and not failure.get("known_issue")
    ]


def _design_gate_status(
    summary: dict[str, Any],
    test_index: list[dict[str, Any]],
    failure_transitions: dict[str, Any],
    adjusted_pass_rate: float,
    config: ReportInsightConfig,
) -> dict[str, Any]:
    """The three default release gates from the design system.

    1. Minimum adjusted pass rate (quarantined excluded).
    2. Zero new unresolved failures vs the previous run (known/quarantined excluded).
    3. Duration budget.

    Thresholds are configurable via :class:`ReportInsightConfig`.
    """

    duration_ms = float(summary.get("duration_ms", 0) or 0)
    new_unresolved = len(_new_unresolved_failures(test_index, failure_transitions))

    def result(name: str, metric: str, expected: str, actual: Any, ok: bool) -> dict[str, Any]:
        return {
            "name": name,
            "metric": metric,
            "expected": expected,
            "actual": actual,
            "status": "passed" if ok else "failed",
            "severity": "failed",
            "message": "",
            "category": "",
        }

    results = [
        result(
            "Minimum Pass Rate (adjusted)",
            "adjusted_pass_rate",
            f">= {config.default_min_pass_rate:g}%",
            f"{adjusted_pass_rate:g}%",
            adjusted_pass_rate >= config.default_min_pass_rate,
        ),
        result(
            "Zero New Unresolved Failures",
            "new_unresolved_failures",
            "0",
            str(new_unresolved),
            new_unresolved == 0,
        ),
        result(
            "Duration Budget",
            "duration",
            f"<= {config.default_duration_budget_ms / 1000:g}s",
            f"{duration_ms / 1000:g}s",
            duration_ms <= config.default_duration_budget_ms,
        ),
    ]
    passed = all(item["status"] == "passed" for item in results)
    return {
        "status": "passed" if passed else "failed",
        "configured": True,
        "results": results,
        "adjusted_pass_rate": adjusted_pass_rate,
        "new_unresolved_failures": new_unresolved,
        "quarantined_count": sum(1 for item in test_index if _is_quarantined(item)),
    }


def _health_score(adjusted_pass_rate: float, stability: dict[str, Any]) -> int:
    """Design health score: 60% adjusted pass rate + 40% average stability."""

    stability_score = stability.get("score")
    avg_stability = float(stability_score) if isinstance(stability_score, (int, float)) else adjusted_pass_rate
    return int(round(adjusted_pass_rate * 0.6 + avg_stability * 0.4))


def _quality_score(
    summary: dict[str, Any],
    test_index: list[dict[str, Any]],
    signals: dict[str, Any],
    config: ReportInsightConfig,
) -> dict[str, Any]:
    total = int(summary.get("total", 0) or 0)
    pass_rate = float(summary.get("pass_rate", 0) or 0)
    failed_broken = _blocking_failure_count(summary)
    flaky = int(summary.get("flaky", 0) or 0)
    test_retries = int(signals.get("test_retry_count", 0) or 0)
    action_retries = int(signals.get("action_retry_count", 0) or 0)
    slow_tests = sum(
        1 for item in test_index if float(item.get("duration_ms", 0) or 0) >= config.slow_test_threshold_ms
    )
    weights = config.quality_weights
    penalties = {
        "failure_penalty": failed_broken * weights.failure_penalty,
        "flaky_penalty": flaky * weights.flaky_penalty,
        "retry_penalty": test_retries * weights.retry_penalty,
        "action_retry_penalty": action_retries * weights.action_retry_penalty,
        "slow_penalty": slow_tests * weights.slow_penalty,
    }
    total_penalty = min(sum(penalties.values()), weights.max_total_penalty)
    score = round(max(0.0, min(100.0, pass_rate - total_penalty)), 2) if total else None
    return {
        "score": score,
        "grade": _quality_grade(score),
        "status": _quality_status(score),
        "components": {
            "base_pass_rate": pass_rate,
            **{key: round(value, 2) for key, value in penalties.items()},
            "total_penalty": round(total_penalty, 2),
            "slow_tests": slow_tests,
        },
        "message": "No tests were captured." if score is None else f"Quality score {score:g}/100.",
    }


def _risk_signal(
    summary: dict[str, Any],
    signals: dict[str, Any],
    failure_transitions: dict[str, Any],
    test_index: list[dict[str, Any]],
    config: ReportInsightConfig,
) -> dict[str, Any]:
    thresholds = config.risk_thresholds
    failed_broken = _blocking_failure_count(summary)
    flaky = int(summary.get("flaky", 0) or 0)
    retries = int(signals.get("test_retry_count", 0) or 0) + int(signals.get("action_retry_count", 0) or 0)
    new_failures = int(failure_transitions.get("counts", {}).get("new", 0) or 0)
    slow_tests = sum(
        1 for item in test_index if float(item.get("duration_ms", 0) or 0) >= config.slow_test_threshold_ms
    )
    severe_categories = {
        item.get("failure", {}).get("category", "")
        for item in test_index
        if is_blocking_failure_status(item.get("status"))
        and item.get("failure", {}).get("category", "")
        in {"appium_server_unreachable", "auth_config_issue", "api_contract_mismatch"}
    }
    reasons: list[dict[str, Any]] = []
    _add_risk_reason(reasons, failed_broken, thresholds.medium_failed, thresholds.high_failed, "Blocking failures")
    _add_risk_reason(reasons, flaky, thresholds.medium_flaky, thresholds.high_flaky, "Flaky signals")
    _add_risk_reason(
        reasons,
        new_failures,
        thresholds.medium_new_failures,
        thresholds.high_new_failures,
        "New failures",
    )
    _add_risk_reason(reasons, retries, thresholds.medium_retries, thresholds.high_retries, "Retry signals")
    if slow_tests:
        reasons.append({"level": "medium", "label": "Slow tests", "value": slow_tests})
    if severe_categories:
        reasons.append(
            {
                "level": "high",
                "label": "Severe failure categories",
                "value": len(severe_categories),
                "categories": sorted(severe_categories),
            }
        )
    level = "high" if any(reason["level"] == "high" for reason in reasons) else "medium" if reasons else "low"
    return {
        "level": level,
        "reasons": reasons,
        "summary": "No material risk signals." if level == "low" else f"{level.capitalize()} risk from run signals.",
        "thresholds": asdict(thresholds),
    }


def _stability(
    test_index: list[dict[str, Any]],
    history_entries: list[dict[str, Any]],
    config: ReportInsightConfig,
) -> dict[str, Any]:
    window = history_entries[-config.stability_history_window :]
    entries_with_statuses = [entry for entry in window if isinstance(entry.get("test_statuses"), list)]
    retry_recovered = sum(
        1
        for item in test_index
        if "test_retry_flaky" in item.get("flaky_categories", [])
        or "action_retry_flaky" in item.get("flaky_categories", [])
    )
    if len(entries_with_statuses) < 2:
        return {
            "status": "insufficient_history",
            "score": None,
            "window_size": config.stability_history_window,
            "available_runs": len(entries_with_statuses),
            "retry_recovered_count": retry_recovered,
            "unstable_tests": [],
            "message": "At least two retained runs with test status history are required.",
        }
    by_identity: dict[str, list[dict[str, Any]]] = {}
    for entry in entries_with_statuses:
        for item in entry.get("test_statuses", []):
            identity = str(
                item.get("identity") or item.get("test_id") or item.get("full_name") or item.get("name") or ""
            )
            if identity:
                by_identity.setdefault(identity, []).append(
                    {"run_id": entry.get("run_id", ""), "status": item.get("status", "unknown")}
                )
    unstable: list[dict[str, Any]] = []
    changes = 0
    for identity, statuses in by_identity.items():
        identity_changes = sum(
            1
            for previous, current in zip(statuses, statuses[1:], strict=False)
            if previous.get("status") != current.get("status")
        )
        if identity_changes:
            changes += identity_changes
            unstable.append({"identity": identity, "changes": identity_changes, "statuses": statuses})
    score = round(max(0, 100 - changes * 10 - retry_recovered * 2), 2)
    return {
        "status": "available",
        "score": score,
        "window_size": config.stability_history_window,
        "available_runs": len(entries_with_statuses),
        "retry_recovered_count": retry_recovered,
        "unstable_tests": sorted(unstable, key=lambda item: (-item["changes"], item["identity"]))[:20],
        "message": f"Stability score {score:g}/100 across {len(entries_with_statuses)} retained runs.",
    }


def _recovery(history_entries: list[dict[str, Any]], config: ReportInsightConfig) -> dict[str, Any]:
    entries = [entry for entry in history_entries[-config.stability_history_window :] if entry.get("test_statuses")]
    if len(entries) < 2:
        return {
            "status": "insufficient_history",
            "mean_recovery_ms": None,
            "recovered_tests": [],
            "message": "At least two retained runs with test status history are required.",
        }
    open_failures: dict[str, dict[str, Any]] = {}
    recovered: list[dict[str, Any]] = []
    for entry in entries:
        run_time = _parse_time(entry.get("latest_run"))
        for item in entry.get("test_statuses", []):
            identity = str(
                item.get("identity") or item.get("test_id") or item.get("full_name") or item.get("name") or ""
            )
            if not identity or run_time is None:
                continue
            status = str(item.get("status", "unknown"))
            if is_blocking_failure_status(status) and identity not in open_failures:
                open_failures[identity] = {"run_id": entry.get("run_id", ""), "time": run_time, "status": status}
            elif normalized_status(status) == PASSED_STATUS and identity in open_failures:
                started = open_failures.pop(identity)
                duration_ms = max(0, (run_time - started["time"]).total_seconds() * 1000)
                recovered.append(
                    {
                        "identity": identity,
                        "failed_run_id": started["run_id"],
                        "recovered_run_id": entry.get("run_id", ""),
                        "recovery_ms": round(duration_ms, 2),
                    }
                )
    if not recovered:
        return {
            "status": "not_available",
            "mean_recovery_ms": None,
            "recovered_tests": [],
            "message": "No failure-to-pass recovery was visible in retained history.",
        }
    mean = round(sum(item["recovery_ms"] for item in recovered) / len(recovered), 2)
    return {
        "status": "available",
        "mean_recovery_ms": mean,
        "recovered_tests": recovered,
        "message": f"Mean recovery time is {_format_duration(mean)} across {len(recovered)} recovered tests.",
    }


def _resource_efficiency(
    report: RunReport,
    test_index: list[dict[str, Any]],
    config: ReportInsightConfig,
) -> dict[str, Any]:
    worker_count = _worker_count(report, config)
    wall_clock_ms = float(report.duration_ms or 0)
    total_test_duration = sum(float(item.get("duration_ms", 0) or 0) for item in test_index)
    if not worker_count or not wall_clock_ms:
        return {
            "status": "not_available",
            "efficiency_percent": None,
            "message": "Worker count and wall-clock run duration are required.",
        }
    efficiency = round((total_test_duration / (wall_clock_ms * worker_count)) * 100, 2)
    return {
        "status": "available",
        "efficiency_percent": efficiency,
        "worker_count": worker_count,
        "wall_clock_duration_ms": wall_clock_ms,
        "total_test_duration_ms": round(total_test_duration, 2),
        "message": f"Resource efficiency is {efficiency:g}%.",
    }


def _compare(run_comparison: dict[str, Any], failure_transitions: dict[str, Any]) -> dict[str, Any]:
    values = run_comparison.get("values", {})
    metrics = [
        {
            "metric": metric,
            "label": _humanize(metric),
            "current": item.get("current", 0),
            "previous": item.get("previous", 0),
            "delta": item.get("delta", 0),
            "direction": _delta_direction(float(item.get("delta", 0) or 0)),
        }
        for metric, item in values.items()
    ]
    return {
        "previous_run_id": run_comparison.get("previous_run_id", ""),
        "current_run_id": run_comparison.get("current_run_id", ""),
        "metrics": metrics,
        "failure_transitions": failure_transitions.get("counts", {}),
    }


def _add_risk_reason(reasons: list[dict[str, Any]], value: int, medium: int, high: int, label: str) -> None:
    if value >= high:
        reasons.append({"level": "high", "label": label, "value": value, "threshold": high})
    elif value >= medium:
        reasons.append({"level": "medium", "label": label, "value": value, "threshold": medium})


def _blocking_failure_count(summary: dict[str, Any]) -> int:
    return int(
        summary.get(
            "blocking_failures",
            int(summary.get("failed", 0) or 0) + int(summary.get("broken", 0) or 0) + int(summary.get("error", 0) or 0),
        )
        or 0
    )


def _quality_grade(score: float | None) -> str:
    if score is None:
        return "n/a"
    if score >= 90:
        return "excellent"
    if score >= 75:
        return "good"
    if score >= 60:
        return "watch"
    return "at_risk"


def _quality_status(score: float | None) -> str:
    if score is None:
        return "unknown"
    if score >= 75:
        return "passed"
    if score >= 60:
        return "warning"
    return "failed"


def _worker_count(report: RunReport, config: ReportInsightConfig) -> int | None:
    for key in config.worker_count_metadata_keys:
        value = report.metadata.get(key)
        if isinstance(value, int | float) and value > 0:
            return int(value)
        if isinstance(value, str) and value.isdigit() and int(value) > 0:
            return int(value)
    return None


def _parse_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _delta_direction(delta: float) -> str:
    if delta > 0:
        return "up"
    if delta < 0:
        return "down"
    return "flat"


def _humanize(value: str) -> str:
    return " ".join(part.capitalize() for part in value.replace("-", "_").split("_") if part)


def _format_duration(duration_ms: float) -> str:
    seconds = round(duration_ms / 1000, 2)
    if seconds < 60:
        return f"{seconds:g}s"
    minutes = int(seconds // 60)
    remaining = round(seconds % 60, 2)
    return f"{minutes}m {remaining:g}s"
