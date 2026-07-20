from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from automation_core.reporting.analysis import (
    classify_failure,
    failure_categories,
    fastest_slowest_tests,
    flaky_analysis,
    summarize_run,
)
from automation_core.reporting.models import RunReport, TestCaseReport, to_jsonable
from automation_core.reporting.platforms import platform_breakdown
from automation_core.reporting.status import is_blocking_failure_status
from automation_core.reporting.traversal import collect_action_retries, collect_test_artifacts

INDEX_FILE = "index.json"


def _platform_records(report: RunReport) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for test in report.tests:
        metadata = test.metadata if isinstance(test.metadata, dict) else {}
        records.append(
            {
                "status": test.status,
                "duration_ms": test.duration_ms,
                "domain": test.domain,
                "suite": test.suite,
                "platform_type": metadata.get("platform_type"),
                "browser": metadata.get("browser"),
                "device_name": metadata.get("device_name"),
                "api_profile": metadata.get("api_profile"),
                "context": metadata.get("context"),
                "platform": metadata.get("platform"),
                "flaky_categories": [],
                "metadata": metadata,
            }
        )
    return records


def history_entry_from_report(report: RunReport) -> dict[str, Any]:
    summary = summarize_run(report)
    speed = fastest_slowest_tests(report, limit=10)
    framework_hint = f"{report.framework} {report.project_name}".strip()
    return {
        **summary,
        "platforms": dict(platform_breakdown(_platform_records(report), framework_hint=framework_hint)),
        "failure_categories": failure_categories(report),
        "failed_tests": [_failed_test_entry(test) for test in report.tests if is_blocking_failure_status(test.status)],
        "test_statuses": [_test_status_entry(test) for test in report.tests],
        "flaky_tests": flaky_analysis(report),
        "slow_tests": [
            {
                "test_id": test.id,
                "name": test.name,
                "duration_ms": test.duration_ms,
                "status": test.status,
            }
            for test in speed["slowest"]
        ],
        "signals": {
            "artifact_count": sum(len(collect_test_artifacts(test)) for test in report.tests),
            "action_retry_count": sum(len(collect_action_retries(test)) for test in report.tests),
            "test_retry_count": sum(len(test.retries) for test in report.tests),
            "healing_event_count": sum(_healing_event_count(test) for test in report.tests),
        },
    }


def update_history(
    report: RunReport,
    history_dir: str | Path,
    *,
    max_entries: int = 50,
) -> list[dict[str, Any]]:
    history_path = Path(history_dir)
    history_path.mkdir(parents=True, exist_ok=True)
    entry = history_entry_from_report(report)
    entry_path = history_path / f"{_safe_filename(report.run_id)}.json"
    entry_path.write_text(json.dumps(to_jsonable(entry), indent=2), encoding="utf-8")

    entries = load_history(history_path)
    by_run_id = {item["run_id"]: item for item in entries}
    by_run_id[entry["run_id"]] = entry
    entries = sorted(by_run_id.values(), key=lambda item: item.get("latest_run", ""))[-max_entries:]
    (history_path / INDEX_FILE).write_text(json.dumps(to_jsonable(entries), indent=2), encoding="utf-8")
    return entries


def load_history(history_dir: str | Path, *, limit: int | None = None) -> list[dict[str, Any]]:
    history_path = Path(history_dir)
    if not history_path.exists():
        return []
    index_path = history_path / INDEX_FILE
    if index_path.exists():
        entries = json.loads(index_path.read_text(encoding="utf-8"))
    else:
        entries = []
        for path in sorted(history_path.glob("*.json")):
            if path.name == INDEX_FILE:
                continue
            entries.append(json.loads(path.read_text(encoding="utf-8")))
    entries = sorted(entries, key=lambda item: item.get("latest_run", ""))
    return entries[-limit:] if limit else entries


def trend_points(history_entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "run_id": entry.get("run_id", ""),
            "latest_run": entry.get("latest_run", ""),
            "pass_rate": entry.get("pass_rate", 0),
            "flaky": entry.get("flaky", 0),
            "failed": entry.get(
                "blocking_failures",
                entry.get("failed", 0) + entry.get("broken", 0) + entry.get("error", 0),
            ),
            "duration_ms": entry.get("duration_ms", 0),
            "platforms": entry.get("platforms", {}),
        }
        for entry in history_entries
    ]


def _failed_test_entry(test: TestCaseReport) -> dict[str, Any]:
    return {
        "identity": _test_identity(test),
        "test_id": test.id,
        "name": test.name,
        "full_name": test.full_name,
        "status": test.status,
        "failure_category": classify_failure(test),
        "failure_message": test.failure_message[:300],
    }


def _test_status_entry(test: TestCaseReport) -> dict[str, Any]:
    return {
        "identity": _test_identity(test),
        "test_id": test.id,
        "name": test.name,
        "full_name": test.full_name,
        "status": test.status,
    }


def _test_identity(test: TestCaseReport) -> str:
    return test.id or test.full_name or test.name


def _healing_event_count(test: TestCaseReport) -> int:
    events = test.metadata.get("healing_events", [])
    return len(events) if isinstance(events, list) else 0


def _safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-") or "run"
