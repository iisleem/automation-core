from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from automation_core.reporting.models import Artifact, RetryAttempt, RunReport, StepRecord, TestCaseReport

ReportEnricher = Callable[[RunReport], RunReport | None]
TestMetadata = Mapping[str, Mapping[str, Any]]


def apply_enrichers(report: RunReport, enrichers: list[ReportEnricher] | None = None) -> RunReport:
    for enricher in enrichers or []:
        updated = enricher(report)
        if updated is not None:
            report = updated
    return report


def run_report_from_allure_results(
    results_dir: str | Path,
    *,
    run_id: str | None = None,
    project_name: str = "",
    framework: str = "",
    metadata: dict[str, Any] | None = None,
    test_metadata: TestMetadata | None = None,
    enrichers: list[ReportEnricher] | None = None,
    missing_ok: bool = False,
) -> RunReport:
    results_path = Path(results_dir)
    if not results_path.exists():
        if missing_ok:
            return RunReport(run_id=run_id or _default_run_id(), project_name=project_name, framework=framework)
        raise FileNotFoundError(f"Allure results directory not found: {results_path}")

    grouped: dict[str, list[dict[str, Any]]] = {}
    for path in sorted(results_path.glob("*-result.json")):
        with path.open("r", encoding="utf-8") as file:
            result = json.load(file)
        result["_path"] = path
        grouped.setdefault(_history_key(result), []).append(result)

    tests = [_test_from_allure_group(key, values, results_path, test_metadata or {}) for key, values in grouped.items()]
    started_at = min((test.started_at for test in tests if test.started_at), default=None)
    ended_at = max((test.ended_at for test in tests if test.ended_at), default=None)
    duration_ms = (
        _duration_between(started_at, ended_at) if started_at and ended_at else sum(test.duration_ms for test in tests)
    )
    report = RunReport(
        run_id=run_id or _default_run_id(),
        project_name=project_name,
        framework=framework,
        started_at=started_at,
        ended_at=ended_at,
        duration_ms=duration_ms,
        tests=sorted(tests, key=lambda test: (test.started_at or datetime.min.replace(tzinfo=UTC), test.name)),
        metadata=metadata or {},
    )
    return apply_enrichers(report, enrichers)


def _test_from_allure_group(
    key: str,
    results: list[dict[str, Any]],
    results_dir: Path,
    test_metadata: TestMetadata,
) -> TestCaseReport:
    ordered = sorted(results, key=lambda result: (result.get("start", 0), result.get("stop", 0)))
    final = ordered[-1]
    retries = [_retry_from_allure(index, result) for index, result in enumerate(ordered, start=1)]
    labels = _labels(final)
    test = TestCaseReport(
        id=key,
        name=final.get("name", key),
        full_name=final.get("fullName", ""),
        suite=labels.get("suite", labels.get("parentSuite", "")),
        status=final.get("status", "unknown"),
        started_at=_from_millis(final.get("start")),
        ended_at=_from_millis(final.get("stop")),
        duration_ms=_duration_ms(final),
        failure_message=final.get("statusDetails", {}).get("message", ""),
        failure_trace=final.get("statusDetails", {}).get("trace", ""),
        labels=labels,
        retries=retries,
        steps=[_step_from_allure(step, results_dir) for step in final.get("steps", [])],
        artifacts=[_artifact_from_allure(attachment, results_dir) for attachment in final.get("attachments", [])],
        metadata={},
    )
    for metadata_key in (test.id, test.full_name, test.name):
        if metadata_key in test_metadata:
            _merge_test_metadata(test, dict(test_metadata[metadata_key]))
    _derive_common_fields(test)
    return test


def _retry_from_allure(attempt: int, result: dict[str, Any]) -> RetryAttempt:
    status_details = result.get("statusDetails", {})
    return RetryAttempt(
        attempt=attempt,
        status=result.get("status", "unknown"),
        retry_type="test",
        started_at=_from_millis(result.get("start")),
        ended_at=_from_millis(result.get("stop")),
        duration_ms=_duration_ms(result),
        reason=status_details.get("message", ""),
    )


def _step_from_allure(step: dict[str, Any], results_dir: Path) -> StepRecord:
    return StepRecord(
        name=step.get("name", "step"),
        status=step.get("status", "unknown"),
        started_at=_from_millis(step.get("start")),
        ended_at=_from_millis(step.get("stop")),
        duration_ms=_duration_ms(step),
        artifacts=[_artifact_from_allure(attachment, results_dir) for attachment in step.get("attachments", [])],
        children=[_step_from_allure(child, results_dir) for child in step.get("steps", [])],
    )


def _artifact_from_allure(attachment: dict[str, Any], results_dir: Path) -> Artifact:
    source = attachment.get("source")
    path = str(results_dir / source) if source else None
    mime_type = attachment.get("type")
    artifact_type = _infer_artifact_type(attachment.get("name", ""), source or "", mime_type or "")
    size_bytes = Path(path).stat().st_size if path and Path(path).exists() else None
    return Artifact(
        name=attachment.get("name", source or "artifact"),
        artifact_type=artifact_type,
        path=path,
        mime_type=mime_type,
        size_bytes=size_bytes,
    )


def _labels(result: dict[str, Any]) -> dict[str, str]:
    labels: dict[str, str] = {}
    for label in result.get("labels", []):
        name = label.get("name")
        value = label.get("value")
        if name and value:
            labels[str(name)] = str(value)
    return labels


def _merge_test_metadata(test: TestCaseReport, metadata: dict[str, Any]) -> None:
    test.domain = str(metadata.pop("domain", test.domain) or "")
    test.profile = str(metadata.pop("profile", test.profile) or "")
    test.environment = str(metadata.pop("environment", test.environment) or "")
    capabilities = metadata.pop("capabilities", None)
    if isinstance(capabilities, dict):
        test.capabilities.update(capabilities)
    artifacts = metadata.pop("artifacts", None)
    if isinstance(artifacts, list):
        test.artifacts.extend(Artifact(**item) if isinstance(item, dict) else item for item in artifacts)
    action_retries = metadata.pop("action_retries", None)
    if isinstance(action_retries, list):
        test.action_retries.extend(RetryAttempt(**item) if isinstance(item, dict) else item for item in action_retries)
    test.metadata.update(metadata)


def _derive_common_fields(test: TestCaseReport) -> None:
    parameters = test.labels
    test.environment = test.environment or parameters.get("env", "") or parameters.get("environment", "")
    test.profile = test.profile or parameters.get("profile", "") or parameters.get("browser", "")
    if "browser" in parameters and "browser" not in test.metadata:
        test.metadata["browser"] = parameters["browser"]
    if "device" in parameters and "device_name" not in test.metadata:
        test.metadata["device_name"] = parameters["device"]


def _history_key(result: dict[str, Any]) -> str:
    return result.get("historyId") or result.get("fullName") or result.get("name") or result.get("uuid") or "unknown"


def _from_millis(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    return datetime.fromtimestamp(float(value) / 1000, tz=UTC)


def _duration_ms(result: dict[str, Any]) -> float:
    start = result.get("start", 0)
    stop = result.get("stop", start)
    return max(0, float(stop) - float(start))


def _duration_between(started_at: datetime, ended_at: datetime) -> float:
    return max(0, (ended_at - started_at).total_seconds() * 1000)


def _default_run_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def _infer_artifact_type(name: str, source: str, mime_type: str) -> str:
    value = f"{name} {source} {mime_type}".lower()
    if any(part in value for part in ("png", "jpg", "jpeg", "screenshot", "image/")):
        return "screenshot"
    if any(part in value for part in ("mp4", "webm", "video/")):
        return "video"
    if "trace" in value or source.endswith(".zip"):
        return "trace"
    if any(part in value for part in ("xml", "page source", "source")):
        return "source"
    if "log" in value or "text/plain" in value:
        return "log"
    if "request" in value:
        return "request"
    if "response" in value:
        return "response"
    if "json" in value:
        return "json"
    return "other"
