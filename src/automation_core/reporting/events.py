from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from automation_core.reporting.models import Artifact, RunReport, StepRecord, TestCaseReport, to_jsonable


@dataclass
class ReportingEvent:
    event_type: str
    title: str
    timestamp: datetime
    test_id: str | None = None
    test_name: str | None = None
    status: str | None = None
    duration_ms: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


def build_timeline_events(report: RunReport) -> list[ReportingEvent]:
    events: list[ReportingEvent] = []
    fallback_time = report.started_at or report.generated_at

    for test in report.tests:
        started_at = test.started_at or fallback_time
        events.append(
            ReportingEvent(
                event_type="test_started",
                title=f"Started {test.name}",
                timestamp=started_at,
                test_id=test.id,
                test_name=test.name,
                status=test.status,
                metadata=_test_context(test),
            )
        )
        for retry in test.retries:
            events.append(
                ReportingEvent(
                    event_type=f"{retry.retry_type}_retry",
                    title=f"{retry.retry_type.title()} retry attempt {retry.attempt}",
                    timestamp=retry.started_at or started_at,
                    test_id=test.id,
                    test_name=test.name,
                    status=retry.status,
                    duration_ms=retry.duration_ms,
                    metadata={"reason": retry.reason, **retry.metadata},
                )
            )
        for retry in test.action_retries:
            events.append(
                ReportingEvent(
                    event_type="action_retry",
                    title=f"Action retry attempt {retry.attempt}: {retry.action or 'action'}",
                    timestamp=retry.started_at or started_at,
                    test_id=test.id,
                    test_name=test.name,
                    status=retry.status,
                    duration_ms=retry.duration_ms,
                    metadata={"reason": retry.reason, **retry.metadata},
                )
            )
        for step in test.steps:
            _append_step_events(events, test, step, started_at)
        for artifact in test.artifacts:
            _append_artifact_event(events, test, artifact, test.ended_at or started_at)
        events.append(
            ReportingEvent(
                event_type="test_finished",
                title=f"Finished {test.name}",
                timestamp=test.ended_at or started_at,
                test_id=test.id,
                test_name=test.name,
                status=test.status,
                duration_ms=test.duration_ms,
                metadata=_test_context(test),
            )
        )

    return sorted(events, key=lambda event: event.timestamp)


def _append_step_events(
    events: list[ReportingEvent],
    test: TestCaseReport,
    step: StepRecord,
    fallback_time: datetime,
) -> None:
    events.append(
        ReportingEvent(
            event_type="step",
            title=step.name,
            timestamp=step.started_at or fallback_time,
            test_id=test.id,
            test_name=test.name,
            status=step.status,
            duration_ms=step.duration_ms,
            metadata=step.metadata,
        )
    )
    for retry in step.retries:
        events.append(
            ReportingEvent(
                event_type="action_retry",
                title=f"Action retry attempt {retry.attempt}: {retry.action or step.name}",
                timestamp=retry.started_at or step.started_at or fallback_time,
                test_id=test.id,
                test_name=test.name,
                status=retry.status,
                duration_ms=retry.duration_ms,
                metadata={"reason": retry.reason, **retry.metadata},
            )
        )
    for artifact in step.artifacts:
        _append_artifact_event(events, test, artifact, step.ended_at or step.started_at or fallback_time)
    for child in step.children:
        _append_step_events(events, test, child, step.started_at or fallback_time)


def _append_artifact_event(
    events: list[ReportingEvent],
    test: TestCaseReport,
    artifact: Artifact,
    fallback_time: datetime,
) -> None:
    events.append(
        ReportingEvent(
            event_type="artifact",
            title=f"Artifact captured: {artifact.name}",
            timestamp=artifact.created_at or fallback_time,
            test_id=test.id,
            test_name=test.name,
            metadata={"artifact_type": artifact.artifact_type, "path": artifact.path, "href": artifact.href},
        )
    )


def _test_context(test: TestCaseReport) -> dict[str, Any]:
    return {
        "domain": test.domain,
        "profile": test.profile,
        "environment": test.environment,
        "browser": test.metadata.get("browser"),
        "device_name": test.metadata.get("device_name"),
    }
