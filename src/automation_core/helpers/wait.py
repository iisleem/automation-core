from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


def wait_until(
    condition: Callable[[], T | None | bool],
    timeout_seconds: float = 30,
    interval_seconds: float = 1,
    failure_message: str = "Condition was not met before timeout.",
    ignore_exceptions: bool = False,
) -> T:
    deadline = time.monotonic() + timeout_seconds
    last_value = None
    last_error: Exception | None = None

    while time.monotonic() <= deadline:
        try:
            last_value = condition()
        except Exception as error:
            if not ignore_exceptions:
                raise
            last_error = error
            last_value = None
        else:
            if last_value:
                return last_value
        time.sleep(interval_seconds)

    message = f"{failure_message} Last value: {last_value!r}"
    if last_error is not None:
        message += f" Last error: {type(last_error).__name__}: {last_error}"
    raise TimeoutError(message)


def poll_until(
    action: Callable[[], T],
    predicate: Callable[[T], bool],
    timeout_seconds: float = 30,
    interval_seconds: float = 1,
    message: str = "Condition was not met before timeout",
) -> T:
    deadline = time.monotonic() + timeout_seconds
    last_result = action()

    while time.monotonic() <= deadline:
        if predicate(last_result):
            return last_result
        time.sleep(interval_seconds)
        last_result = action()

    raise AssertionError(f"{message}. Last value: {last_result!r}")
