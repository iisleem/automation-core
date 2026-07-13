from __future__ import annotations

from collections.abc import Iterable, Iterator

from automation_core.reporting.models import Artifact, RetryAttempt, StepRecord, TestCaseReport


def iter_steps(steps: Iterable[StepRecord]) -> Iterator[StepRecord]:
    for step in steps:
        yield step
        yield from iter_steps(step.children)


def collect_step_artifacts(test: TestCaseReport) -> list[Artifact]:
    return [artifact for step in iter_steps(test.steps) for artifact in step.artifacts]


def collect_test_artifacts(test: TestCaseReport) -> list[Artifact]:
    return [*test.artifacts, *collect_step_artifacts(test)]


def collect_step_retries(test: TestCaseReport) -> list[RetryAttempt]:
    return [retry for step in iter_steps(test.steps) for retry in step.retries]


def collect_action_retries(test: TestCaseReport) -> list[RetryAttempt]:
    return [*test.action_retries, *collect_step_retries(test)]
