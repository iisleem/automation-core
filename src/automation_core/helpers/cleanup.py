from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CleanupAction:
    name: str
    callback: Callable[..., Any]
    args: tuple[Any, ...] = field(default_factory=tuple)
    kwargs: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CleanupResult:
    name: str
    success: bool
    error: Exception | None = None


class CleanupRegistry:
    """Small LIFO cleanup registry for test data and external resources."""

    def __init__(self) -> None:
        self._actions: list[CleanupAction] = []

    @property
    def actions(self) -> tuple[CleanupAction, ...]:
        return tuple(self._actions)

    def add(
        self,
        name: str,
        callback: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> CleanupAction:
        action = CleanupAction(name=name, callback=callback, args=args, kwargs=kwargs)
        self._actions.append(action)
        return action

    def run_all(
        self,
        *,
        reverse: bool = True,
        continue_on_error: bool = True,
        clear: bool = True,
    ) -> list[CleanupResult]:
        actions = list(reversed(self._actions)) if reverse else list(self._actions)
        results: list[CleanupResult] = []

        for action in actions:
            try:
                action.callback(*action.args, **action.kwargs)
                results.append(CleanupResult(name=action.name, success=True))
            except Exception as error:
                results.append(CleanupResult(name=action.name, success=False, error=error))
                if not continue_on_error:
                    break

        if clear:
            self.clear()
        return results

    def clear(self) -> None:
        self._actions.clear()


def assert_cleanup_success(results: list[CleanupResult]) -> None:
    failures = [result for result in results if not result.success]
    assert not failures, _format_cleanup_failures(failures)


def _format_cleanup_failures(failures: list[CleanupResult]) -> str:
    details = [f"{failure.name}: {type(failure.error).__name__}: {failure.error}" for failure in failures]
    return "Cleanup actions failed:\n" + "\n".join(details)
