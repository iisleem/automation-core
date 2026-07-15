from __future__ import annotations

from typing import Any

from automation_core.healing.models import HealingResult
from automation_core.reporting.models import TestCaseReport

HEALING_EVENTS_KEY = "healing_events"


def add_healing_result(test: TestCaseReport, result: HealingResult) -> None:
    """Attach a JSON-safe healing result to a test report."""

    events = test.metadata.setdefault(HEALING_EVENTS_KEY, [])
    if not isinstance(events, list):
        events = []
        test.metadata[HEALING_EVENTS_KEY] = events
    payload = result.to_dict()
    events.append(payload)
    test.metadata["healing_attempt_count"] = len(events)
    if result.applied:
        test.metadata["healing_applied_count"] = int(test.metadata.get("healing_applied_count", 0)) + 1


def healing_events_for_test(test: TestCaseReport) -> list[dict[str, Any]]:
    events = test.metadata.get(HEALING_EVENTS_KEY, [])
    if not isinstance(events, list):
        return []
    return [event for event in events if isinstance(event, dict)]
