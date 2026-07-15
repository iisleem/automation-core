from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from automation_core.reporting.analysis import classify_failure, flaky_analysis, summarize_run
from automation_core.reporting.models import RunReport
from automation_core.reporting.traversal import collect_action_retries

FAILED_STATUSES = {"failed", "broken"}
SUPPORTED_OPERATORS = {"max", "min"}
SUPPORTED_SEVERITIES = {"failed", "warning"}
SUPPORTED_METRICS = {
    "total",
    "passed",
    "pass_rate",
    "failed",
    "broken",
    "failed_broken",
    "skipped",
    "flaky",
    "test_retries",
    "action_retries",
    "duration_ms",
    "failure_category",
}


@dataclass(frozen=True)
class QualityGate:
    name: str
    metric: str
    threshold: float
    operator: str = "max"
    severity: str = "failed"
    category: str = ""
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class QualityGateConfig:
    min_pass_rate: float | None = None
    max_failed: int | None = None
    max_broken: int | None = None
    max_failed_broken: int | None = None
    max_skipped: int | None = None
    max_flaky: int | None = None
    max_test_retries: int | None = None
    max_action_retries: int | None = None
    max_duration_ms: float | None = None
    max_failures_by_category: dict[str, int] = field(default_factory=dict)
    severity: str = "failed"

    def to_gates(self) -> list[QualityGate]:
        gates: list[QualityGate] = []
        if self.min_pass_rate is not None:
            gates.append(
                QualityGate(
                    name="Minimum pass rate",
                    metric="pass_rate",
                    threshold=float(self.min_pass_rate),
                    operator="min",
                    severity=self.severity,
                )
            )
        for field_name, metric, label in (
            ("max_failed", "failed", "Maximum failed"),
            ("max_broken", "broken", "Maximum broken"),
            ("max_failed_broken", "failed_broken", "Maximum failed or broken"),
            ("max_skipped", "skipped", "Maximum skipped"),
            ("max_flaky", "flaky", "Maximum flaky"),
            ("max_test_retries", "test_retries", "Maximum test retries"),
            ("max_action_retries", "action_retries", "Maximum action retries"),
            ("max_duration_ms", "duration_ms", "Maximum duration"),
        ):
            value = getattr(self, field_name)
            if value is not None:
                gates.append(
                    QualityGate(
                        name=label,
                        metric=metric,
                        threshold=float(value),
                        operator="max",
                        severity=self.severity,
                    )
                )
        for category, threshold in sorted(self.max_failures_by_category.items()):
            gates.append(
                QualityGate(
                    name=f"Maximum {category} failures",
                    metric="failure_category",
                    threshold=float(threshold),
                    operator="max",
                    severity=self.severity,
                    category=category,
                )
            )
        return gates


@dataclass(frozen=True)
class QualityGateResult:
    name: str
    metric: str
    status: str
    severity: str
    expected: str
    actual: float
    message: str
    category: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class QualityGateEvaluation:
    status: str
    configured: bool
    results: list[QualityGateResult]
    summary: dict[str, int]
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "configured": self.configured,
            "results": [result.to_dict() for result in self.results],
            "summary": self.summary,
            "message": self.message,
        }


def evaluate_quality_gates(
    report: RunReport,
    gates: QualityGateConfig
    | list[QualityGate | dict[str, Any]]
    | tuple[QualityGate | dict[str, Any], ...]
    | None = None,
) -> QualityGateEvaluation:
    """Evaluate domain-neutral quality gates for a run report."""

    normalized = _normalize_gates(gates)
    if not normalized:
        return QualityGateEvaluation(
            status="passed",
            configured=False,
            results=[],
            summary={"passed": 0, "failed": 0, "warning": 0},
            message="No quality gates configured.",
        )

    metrics = _quality_metrics(report)
    results = [_evaluate_gate(gate, metrics) for gate in normalized]
    failed = sum(1 for result in results if result.status == "failed" and result.severity == "failed")
    warnings = sum(1 for result in results if result.status == "failed" and result.severity == "warning")
    passed = sum(1 for result in results if result.status == "passed")
    if failed:
        status = "failed"
    elif warnings:
        status = "warning"
    else:
        status = "passed"
    return QualityGateEvaluation(
        status=status,
        configured=True,
        results=results,
        summary={"passed": passed, "failed": failed, "warning": warnings},
        message=_quality_message(status, failed, warnings),
    )


def _normalize_gates(
    gates: QualityGateConfig | list[QualityGate | dict[str, Any]] | tuple[QualityGate | dict[str, Any], ...] | None,
) -> list[QualityGate]:
    if gates is None:
        return []
    if isinstance(gates, QualityGateConfig):
        return _quality_config_gates(gates)
    return [_gate_from_value(gate) for gate in gates]


def _gate_from_value(value: QualityGate | dict[str, Any]) -> QualityGate:
    if isinstance(value, QualityGate):
        _validate_gate(value)
        return value
    operator = str(value.get("operator") or ("min" if "min" in value else "max"))
    severity = str(value.get("severity", "failed"))
    gate = QualityGate(
        name=str(value.get("name") or value.get("metric") or "Quality gate"),
        metric=str(value.get("metric", "")),
        threshold=float(value.get("threshold", value.get("max", value.get("min", 0)))),
        operator=operator,
        severity=severity,
        category=str(value.get("category", "")),
        message=str(value.get("message", "")),
    )
    _validate_gate(gate)
    return gate


def _validate_gate(gate: QualityGate) -> None:
    if gate.operator not in SUPPORTED_OPERATORS:
        raise ValueError(f"Unsupported quality gate operator: {gate.operator}")
    if gate.severity not in SUPPORTED_SEVERITIES:
        raise ValueError(f"Unsupported quality gate severity: {gate.severity}")
    if not gate.metric:
        raise ValueError("Quality gate metric is required.")
    if gate.metric not in SUPPORTED_METRICS:
        raise ValueError(f"Unsupported quality gate metric: {gate.metric}")
    if gate.metric == "failure_category" and not gate.category:
        raise ValueError("Quality gate category is required for failure_category metrics.")


def _validated_gates(gates: list[QualityGate]) -> list[QualityGate]:
    for gate in gates:
        _validate_gate(gate)
    return gates


def _quality_config_gates(config: QualityGateConfig) -> list[QualityGate]:
    return _validated_gates(config.to_gates())


def _quality_metrics(report: RunReport) -> dict[str, Any]:
    summary = summarize_run(report)
    categories: dict[str, int] = {}
    for test in report.tests:
        if test.status in FAILED_STATUSES:
            category = classify_failure(test)
            categories[category] = categories.get(category, 0) + 1
    return {
        "total": summary["total"],
        "passed": summary["passed"],
        "pass_rate": summary["pass_rate"],
        "failed": summary["failed"],
        "broken": summary["broken"],
        "failed_broken": summary["failed"] + summary["broken"],
        "skipped": summary["skipped"],
        "flaky": len(flaky_analysis(report)),
        "test_retries": sum(len(test.retries) for test in report.tests),
        "action_retries": sum(len(collect_action_retries(test)) for test in report.tests),
        "duration_ms": summary["duration_ms"],
        "failure_categories": categories,
    }


def _evaluate_gate(gate: QualityGate, metrics: dict[str, Any]) -> QualityGateResult:
    actual = _actual_value(gate, metrics)
    if gate.operator == "min":
        passed = actual >= gate.threshold
        expected = f">= {gate.threshold:g}"
    else:
        passed = actual <= gate.threshold
        expected = f"<= {gate.threshold:g}"
    status = "passed" if passed else "failed"
    message = gate.message or _gate_message(gate, actual, expected, status)
    return QualityGateResult(
        name=gate.name,
        metric=gate.metric,
        status=status,
        severity=gate.severity,
        expected=expected,
        actual=actual,
        message=message,
        category=gate.category,
    )


def _actual_value(gate: QualityGate, metrics: dict[str, Any]) -> float:
    if gate.metric == "failure_category":
        return float(metrics["failure_categories"].get(gate.category, 0))
    return float(metrics.get(gate.metric, 0) or 0)


def _gate_message(gate: QualityGate, actual: float, expected: str, status: str) -> str:
    label = gate.category if gate.metric == "failure_category" else gate.metric
    outcome = "meets" if status == "passed" else "does not meet"
    return f"{label} is {actual:g}; {outcome} expected {expected}."


def _quality_message(status: str, failed: int, warnings: int) -> str:
    if status == "passed":
        return "All configured quality gates passed."
    if status == "warning":
        return f"{warnings} quality gate warning(s) found."
    return f"{failed} quality gate(s) failed."
