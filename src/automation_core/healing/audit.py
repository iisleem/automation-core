from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from automation_core.healing.models import HealingResult


def append_healing_event(path: str | Path, result: HealingResult) -> Path:
    """Append one JSON-safe healing result to a JSONL audit file."""

    audit_path = Path(path)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    with audit_path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(result.to_dict(), sort_keys=True))
        file.write("\n")
    return audit_path


def append_healing_events(path: str | Path, results: Iterable[HealingResult]) -> Path:
    """Append multiple JSON-safe healing results to a JSONL audit file."""

    audit_path = Path(path)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    with audit_path.open("a", encoding="utf-8") as file:
        for result in results:
            file.write(json.dumps(result.to_dict(), sort_keys=True))
            file.write("\n")
    return audit_path
