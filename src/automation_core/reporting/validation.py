from __future__ import annotations

import json
from dataclasses import is_dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from automation_core.reporting.models import Artifact, RetryAttempt, RunReport, StepRecord

JSON_SCALARS = (str, int, float, bool, type(None))
SUSPICIOUS_OBJECT_KEYS = ("driver", "client", "session")


def validate_report(report: RunReport) -> list[str]:
    problems: list[str] = []
    _validate_metadata_mapping(report.metadata, "report.metadata", problems)

    for test_index, test in enumerate(report.tests):
        test_path = f"report.tests[{test_index}]"
        _validate_metadata_mapping(test.labels, f"{test_path}.labels", problems)
        _validate_metadata_mapping(test.capabilities, f"{test_path}.capabilities", problems)
        _validate_metadata_mapping(test.metadata, f"{test_path}.metadata", problems)
        for retry_index, retry in enumerate(test.retries):
            _validate_retry(retry, f"{test_path}.retries[{retry_index}]", problems)
        for retry_index, retry in enumerate(test.action_retries):
            _validate_retry(retry, f"{test_path}.action_retries[{retry_index}]", problems)
        for artifact_index, artifact in enumerate(test.artifacts):
            _validate_artifact(artifact, f"{test_path}.artifacts[{artifact_index}]", problems)
        for step_index, step in enumerate(test.steps):
            _validate_step(step, f"{test_path}.steps[{step_index}]", problems)

    try:
        json.dumps(report.to_dict())
    except TypeError as error:
        problems.append(f"report is not JSON serializable: {error}")

    return problems


def assert_valid_report(report: RunReport) -> None:
    problems = validate_report(report)
    if problems:
        raise ValueError("Invalid report:\n" + "\n".join(f"- {problem}" for problem in problems))


def _validate_step(step: StepRecord, path: str, problems: list[str]) -> None:
    _validate_metadata_mapping(step.metadata, f"{path}.metadata", problems)
    for retry_index, retry in enumerate(step.retries):
        _validate_retry(retry, f"{path}.retries[{retry_index}]", problems)
    for artifact_index, artifact in enumerate(step.artifacts):
        _validate_artifact(artifact, f"{path}.artifacts[{artifact_index}]", problems)
    for child_index, child in enumerate(step.children):
        _validate_step(child, f"{path}.children[{child_index}]", problems)


def _validate_retry(retry: RetryAttempt, path: str, problems: list[str]) -> None:
    _validate_metadata_mapping(retry.metadata, f"{path}.metadata", problems)


def _validate_artifact(artifact: Artifact, path: str, problems: list[str]) -> None:
    _validate_metadata_mapping(artifact.metadata, f"{path}.metadata", problems)


def _validate_metadata_mapping(value: Any, path: str, problems: list[str]) -> None:
    if not isinstance(value, dict):
        problems.append(f"{path} must be a dict, got {type(value).__name__}")
        return
    _validate_json_value(value, path, problems)


def _validate_json_value(value: Any, path: str, problems: list[str]) -> None:
    if isinstance(value, JSON_SCALARS):
        return
    if isinstance(value, (datetime, date)):
        return
    if isinstance(value, Path):
        problems.append(f"{path} contains Path; use str(path) before adding it to report metadata")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key)
            item_path = f"{path}.{key_text}"
            if _looks_like_driver_client_session(key_text) and not _is_json_safe_scalar_or_collection(item):
                problems.append(f"{item_path} appears to contain a driver/client/session object")
            _validate_json_value(item, item_path, problems)
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _validate_json_value(item, f"{path}[{index}]", problems)
        return
    if is_dataclass(value):
        problems.append(f"{path} contains dataclass object {type(value).__name__}; pass plain dict data instead")
        return
    problems.append(f"{path} contains non-serializable {type(value).__name__}")


def _looks_like_driver_client_session(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in SUSPICIOUS_OBJECT_KEYS)


def _is_json_safe_scalar_or_collection(value: Any) -> bool:
    if isinstance(value, JSON_SCALARS):
        return True
    if isinstance(value, dict):
        return all(_is_json_safe_scalar_or_collection(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return all(_is_json_safe_scalar_or_collection(item) for item in value)
    return False
