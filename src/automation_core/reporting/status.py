from __future__ import annotations

from typing import Any

PASSED_STATUS = "passed"
FAILED_STATUS = "failed"
BROKEN_STATUS = "broken"
ERROR_STATUS = "error"
SKIPPED_STATUS = "skipped"
UNKNOWN_STATUS = "unknown"

BLOCKING_FAILURE_STATUSES = frozenset({FAILED_STATUS, BROKEN_STATUS, ERROR_STATUS})
MATRIX_STATUSES = (
    PASSED_STATUS,
    FAILED_STATUS,
    BROKEN_STATUS,
    ERROR_STATUS,
    SKIPPED_STATUS,
    UNKNOWN_STATUS,
)


def normalized_status(status: Any) -> str:
    return str(status or "").strip().lower()


def is_blocking_failure_status(status: Any) -> bool:
    return normalized_status(status) in BLOCKING_FAILURE_STATUSES
