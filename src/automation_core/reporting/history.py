from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from automation_core.reporting.analysis import failure_categories, fastest_slowest_tests, flaky_analysis, summarize_run
from automation_core.reporting.models import RunReport, to_jsonable

INDEX_FILE = "index.json"


def history_entry_from_report(report: RunReport) -> dict[str, Any]:
    summary = summarize_run(report)
    speed = fastest_slowest_tests(report, limit=10)
    return {
        **summary,
        "failure_categories": failure_categories(report),
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
            "failed": entry.get("failed", 0) + entry.get("broken", 0),
            "duration_ms": entry.get("duration_ms", 0),
        }
        for entry in history_entries
    ]


def _safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-") or "run"
