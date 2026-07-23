from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import fields, is_dataclass
from typing import Any

from automation_core.reporting.models import RunReport

REDACTED_VALUE = "[redacted]"
SENSITIVE_PATTERN_LABELS = (
    ("token", re.compile(r"token", re.IGNORECASE)),
    ("secret", re.compile(r"secret", re.IGNORECASE)),
    ("password", re.compile(r"password|passwd|pwd", re.IGNORECASE)),
    ("authorization", re.compile(r"authorization|auth[_-]?header", re.IGNORECASE)),
    ("cookie", re.compile(r"cookie", re.IGNORECASE)),
    ("api_key", re.compile(r"api[_-]?key", re.IGNORECASE)),
    ("bearer", re.compile(r"bearer", re.IGNORECASE)),
    ("session", re.compile(r"session", re.IGNORECASE)),
)
# Human-readable identifiers (test names, step names, risk/section titles) are
# authored by engineers and are not secrets, so they are never wholesale
# redacted just because they contain a word like "session" or "token". Only
# explicit artifact file names are content-checked; secret *values* embedded in
# paths, hrefs and free text are still scrubbed by PATH_KEYS / TEXT_SECRET_PATTERN.
NAME_KEYS = {"artifact_name", "file_name", "filename"}
PATH_KEYS = {"path", "href", "original_path", "source"}
ALWAYS_REDACT_KEYS = {"original_path"}
TEXT_SECRET_PATTERN = re.compile(
    r"(?i)(bearer\s+)[^\s,;]+|"
    r"((?:authorization|auth[_-]?header|cookie)[\w .-]*(?:=|:)\s*(?:bearer\s+)?)[^\s,;]+|"
    r"((?:token|secret|password|passwd|pwd|api[_-]?key|session)[\w .-]*(?:=|:)\s*)[^\s,;]+"
)


class RedactionTracker:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    def record(self, label: str) -> None:
        self.counts[label] = self.counts.get(label, 0) + 1

    def manifest(self, *, enabled: bool) -> dict[str, Any]:
        return {
            "enabled": enabled,
            "replacement": REDACTED_VALUE,
            "patterns": [label for label, _ in SENSITIVE_PATTERN_LABELS],
            "redacted_categories": sorted(self.counts),
            "redacted_counts": dict(sorted(self.counts.items())),
        }


def redaction_manifest(enabled: bool) -> dict[str, Any]:
    return RedactionTracker().manifest(enabled=enabled)


def redact_report(report: RunReport, *, enabled: bool = True) -> tuple[RunReport, dict[str, Any]]:
    """Return a report copy with sensitive generated-output values redacted."""

    if not enabled:
        return report, redaction_manifest(False)
    tracker = RedactionTracker()
    copied = deepcopy(report)
    _redact_in_place(copied, tracker, key=None)
    return copied, tracker.manifest(enabled=True)


def redact_payload(value: Any, *, enabled: bool = True) -> tuple[Any, dict[str, Any]]:
    """Return a JSON-like payload copy with sensitive values redacted."""

    if not enabled:
        return value, redaction_manifest(False)
    tracker = RedactionTracker()
    return _redact_value(deepcopy(value), tracker, key=None), tracker.manifest(enabled=True)


def redact_text(text: str, *, enabled: bool = True) -> str:
    if not enabled:
        return text
    return TEXT_SECRET_PATTERN.sub(_replace_text_secret, text)


def is_sensitive_name(value: str) -> bool:
    return _sensitive_label(value) is not None


def _redact_in_place(value: Any, tracker: RedactionTracker, *, key: str | None) -> Any:
    if is_dataclass(value):
        for field in fields(value):
            current = getattr(value, field.name)
            setattr(value, field.name, _redact_value(current, tracker, key=field.name))
        return value
    return _redact_value(value, tracker, key=key)


def _redact_value(value: Any, tracker: RedactionTracker, *, key: str | None) -> Any:
    if isinstance(value, str) and value == REDACTED_VALUE:
        return value

    key_label = _sensitive_label(key or "")
    if key_label:
        tracker.record(key_label)
        return REDACTED_VALUE
    if key in ALWAYS_REDACT_KEYS:
        tracker.record(str(key))
        return REDACTED_VALUE

    if is_dataclass(value):
        return _redact_in_place(value, tracker, key=key)
    if isinstance(value, dict):
        return {
            item_key: _redact_value(item_value, tracker, key=str(item_key)) for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [_redact_value(item, tracker, key=key) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_value(item, tracker, key=key) for item in value)
    if isinstance(value, set):
        return {_redact_value(item, tracker, key=key) for item in value}
    if isinstance(value, str):
        if key in NAME_KEYS or key in PATH_KEYS:
            name_label = _sensitive_label(value)
            if name_label:
                tracker.record(name_label)
                return REDACTED_VALUE
        redacted = TEXT_SECRET_PATTERN.sub(lambda match: _replace_text_secret(match, tracker), value)
        return redacted
    return value


def _replace_text_secret(match: re.Match[str], tracker: RedactionTracker | None = None) -> str:
    text = match.group(0)
    label = _sensitive_label(text) or "secret"
    if tracker:
        tracker.record(label)
    if match.group(1):
        return f"{match.group(1)}{REDACTED_VALUE}"
    if match.group(2):
        return f"{match.group(2)}{REDACTED_VALUE}"
    if match.group(3):
        return f"{match.group(3)}{REDACTED_VALUE}"
    return REDACTED_VALUE


def _sensitive_label(value: str) -> str | None:
    for label, pattern in SENSITIVE_PATTERN_LABELS:
        if pattern.search(value):
            return label
    return None
