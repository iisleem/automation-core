from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
T = TypeVar("T")


def retry_action(
    action: Callable[[], T],
    *,
    attempts: int = 3,
    delay_seconds: float = 0,
    backoff: float = 1,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
    retry_if: Callable[[BaseException], bool] | None = None,
    on_retry: Callable[[BaseException, int], None] | None = None,
) -> T:
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    if delay_seconds < 0:
        raise ValueError("delay_seconds must be 0 or greater")
    if backoff < 1:
        raise ValueError("backoff must be at least 1")

    delay = delay_seconds
    last_error: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            return action()
        except exceptions as error:
            last_error = error
            should_retry = retry_if(error) if retry_if else True
            if not should_retry or attempt == attempts:
                raise
            if on_retry:
                on_retry(error, attempt)
            if delay:
                time.sleep(delay)
                delay *= backoff

    raise RuntimeError("retry_action exhausted without returning or raising") from last_error


def retry(
    *,
    attempts: int = 3,
    delay_seconds: float = 0,
    backoff: float = 1,
    exceptions: Iterable[type[BaseException]] = (Exception,),
    retry_if: Callable[[BaseException], bool] | None = None,
    on_retry: Callable[[BaseException, int], None] | None = None,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    exception_tuple = tuple(exceptions)

    def decorator(function: Callable[P, T]) -> Callable[P, T]:
        def wrapped(*args: P.args, **kwargs: P.kwargs) -> T:
            return retry_action(
                lambda: function(*args, **kwargs),
                attempts=attempts,
                delay_seconds=delay_seconds,
                backoff=backoff,
                exceptions=exception_tuple,
                retry_if=retry_if,
                on_retry=on_retry,
            )

        return wrapped

    return decorator
