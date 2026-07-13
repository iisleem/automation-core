from __future__ import annotations

from datetime import datetime
from typing import Any

from automation_core.reporting.models import (
    Artifact,
    RetryAttempt,
    RunReport,
    StepRecord,
    TestCaseReport,
    utc_timestamp,
)


class EventRecorder:
    """Domain-neutral helper for building reporting data during framework runs."""

    def __init__(
        self,
        report: RunReport | None = None,
        *,
        run_id: str | None = None,
        project_name: str = "",
        framework: str = "",
    ) -> None:
        self.report = report or RunReport(
            run_id=run_id or utc_timestamp().strftime("%Y%m%dT%H%M%S%fZ"),
            project_name=project_name,
            framework=framework,
            started_at=utc_timestamp(),
        )

    def start_test(
        self,
        test_id: str,
        name: str,
        *,
        full_name: str = "",
        suite: str = "",
        domain: str = "",
        profile: str = "",
        environment: str = "",
        metadata: dict[str, Any] | None = None,
        capabilities: dict[str, Any] | None = None,
    ) -> TestCaseReport:
        test = self.get_test(test_id)
        if test is None:
            test = TestCaseReport(id=test_id, name=name)
            self.report.tests.append(test)
        test.name = name
        test.full_name = full_name or test.full_name
        test.suite = suite or test.suite
        test.domain = domain or test.domain
        test.profile = profile or test.profile
        test.environment = environment or test.environment
        test.started_at = test.started_at or utc_timestamp()
        if metadata:
            test.metadata.update(metadata)
        if capabilities:
            test.capabilities.update(capabilities)
        return test

    def finish_test(
        self,
        test: TestCaseReport | str,
        *,
        status: str,
        failure_message: str = "",
        failure_trace: str = "",
        ended_at: datetime | None = None,
        duration_ms: float | None = None,
    ) -> TestCaseReport:
        test_case = self.require_test(test)
        test_case.status = status
        test_case.failure_message = failure_message or test_case.failure_message
        test_case.failure_trace = failure_trace or test_case.failure_trace
        test_case.ended_at = ended_at or utc_timestamp()
        if duration_ms is not None:
            test_case.duration_ms = duration_ms
        elif test_case.started_at and test_case.ended_at:
            test_case.duration_ms = max(0, (test_case.ended_at - test_case.started_at).total_seconds() * 1000)
        return test_case

    def add_step(
        self,
        test: TestCaseReport | str,
        name: str,
        *,
        status: str = "unknown",
        parent: StepRecord | None = None,
        duration_ms: float = 0,
        metadata: dict[str, Any] | None = None,
    ) -> StepRecord:
        test_case = self.require_test(test)
        step = StepRecord(
            name=name,
            status=status,
            started_at=utc_timestamp(),
            duration_ms=duration_ms,
            metadata=metadata or {},
        )
        if parent is None:
            test_case.steps.append(step)
        else:
            parent.children.append(step)
        return step

    def add_action_retry(
        self,
        test: TestCaseReport | str,
        *,
        attempt: int,
        status: str,
        action: str = "",
        reason: str = "",
        step: StepRecord | None = None,
        duration_ms: float = 0,
        metadata: dict[str, Any] | None = None,
    ) -> RetryAttempt:
        retry = RetryAttempt(
            attempt=attempt,
            status=status,
            retry_type="action",
            action=action,
            reason=reason,
            duration_ms=duration_ms,
            metadata=metadata or {},
        )
        if step is None:
            self.require_test(test).action_retries.append(retry)
        else:
            step.retries.append(retry)
        return retry

    def add_artifact(
        self,
        test: TestCaseReport | str,
        *,
        name: str,
        artifact_type: str = "other",
        path: str | None = None,
        href: str | None = None,
        mime_type: str | None = None,
        step: StepRecord | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Artifact:
        artifact = Artifact(
            name=name,
            artifact_type=artifact_type,
            path=path,
            href=href,
            mime_type=mime_type,
            created_at=utc_timestamp(),
            metadata=metadata or {},
        )
        if step is None:
            self.require_test(test).artifacts.append(artifact)
        else:
            step.artifacts.append(artifact)
        return artifact

    def update_metadata(
        self,
        target: RunReport | TestCaseReport | StepRecord | str,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        values = {**(metadata or {}), **kwargs}
        if isinstance(target, str):
            self.require_test(target).metadata.update(values)
        elif isinstance(target, RunReport | TestCaseReport | StepRecord):
            target.metadata.update(values)

    def get_test(self, test_id: str) -> TestCaseReport | None:
        return next((test for test in self.report.tests if test.id == test_id), None)

    def require_test(self, test: TestCaseReport | str) -> TestCaseReport:
        if isinstance(test, TestCaseReport):
            return test
        existing = self.get_test(test)
        if existing is None:
            raise KeyError(f"Unknown test id: {test}")
        return existing
