from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SoftAssertionFailure:
    description: str
    message: str


class SoftAssert:
    """Collect assertion failures and fail once with a grouped message."""

    def __init__(self) -> None:
        self.failures: list[SoftAssertionFailure] = []

    def __enter__(self) -> SoftAssert:
        return self

    def __exit__(self, exc_type: type[BaseException] | None, *_: object) -> None:
        if exc_type is None:
            self.assert_all()

    @property
    def has_failures(self) -> bool:
        return bool(self.failures)

    def check(self, description_or_condition: str | bool, assertion_or_message: Callable[[], None] | str) -> None:
        if callable(assertion_or_message):
            description = str(description_or_condition)
            try:
                assertion_or_message()
            except AssertionError as error:
                self._add_failure(description, str(error) or description)
            return

        if not bool(description_or_condition):
            self._add_failure(str(assertion_or_message), str(assertion_or_message))

    def assert_true(self, condition: bool, message: str) -> None:
        if not condition:
            self._add_failure(message, message)

    def assert_equal(self, actual: Any, expected: Any, message: str = "") -> None:
        if actual != expected:
            failure_message = message or f"Expected {expected!r}, got {actual!r}"
            self._add_failure(failure_message, failure_message)

    def assert_contains(self, actual: Any, expected_member: Any, message: str = "") -> None:
        if expected_member not in actual:
            failure_message = message or f"Expected {actual!r} to contain {expected_member!r}"
            self._add_failure(failure_message, failure_message)

    def assert_in(self, member: Any, container: Any, message: str = "") -> None:
        if member not in container:
            failure_message = message or f"Expected {member!r} to exist in {container!r}"
            self._add_failure(failure_message, failure_message)

    def equals(self, actual: Any, expected: Any, message: str | None = None) -> None:
        self.assert_equal(actual, expected, message or "")

    def contains(self, container: Any, item: Any, message: str | None = None) -> None:
        self.assert_contains(container, item, message or "")

    def assert_all(self) -> None:
        assert not self.failures, self.format_failures()

    def format_failures(self) -> str:
        lines = [f"Soft assertion failures ({len(self.failures)}):"]
        for index, failure in enumerate(self.failures, start=1):
            lines.append(f"{index}. {failure.description}: {failure.message}")
        return "\n".join(lines)

    def _add_failure(self, description: str, message: str) -> None:
        self.failures.append(SoftAssertionFailure(description=description, message=message))


def soft_assert() -> SoftAssert:
    return SoftAssert()
