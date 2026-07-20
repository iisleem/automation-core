from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import UTC, datetime
from typing import Any, ClassVar


def utc_timestamp() -> datetime:
    return datetime.now(UTC)


@dataclass
class Artifact:
    name: str
    artifact_type: str = "other"
    path: str | None = None
    href: str | None = None
    mime_type: str | None = None
    created_at: datetime | None = None
    size_bytes: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass
class RetryAttempt:
    attempt: int
    status: str
    retry_type: str = "test"
    started_at: datetime | None = None
    ended_at: datetime | None = None
    duration_ms: float = 0
    reason: str = ""
    action: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass
class StepRecord:
    name: str
    status: str = "unknown"
    started_at: datetime | None = None
    ended_at: datetime | None = None
    duration_ms: float = 0
    retries: list[RetryAttempt] = field(default_factory=list)
    artifacts: list[Artifact] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    children: list[StepRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass
class TestCaseReport:
    __test__: ClassVar[bool] = False

    id: str
    name: str
    status: str = "unknown"
    full_name: str = ""
    suite: str = ""
    domain: str = ""
    profile: str = ""
    environment: str = ""
    started_at: datetime | None = None
    ended_at: datetime | None = None
    duration_ms: float = 0
    failure_message: str = ""
    failure_trace: str = ""
    labels: dict[str, Any] = field(default_factory=dict)
    capabilities: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    retries: list[RetryAttempt] = field(default_factory=list)
    action_retries: list[RetryAttempt] = field(default_factory=list)
    steps: list[StepRecord] = field(default_factory=list)
    artifacts: list[Artifact] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass
class RunReport:
    run_id: str
    project_name: str = ""
    framework: str = ""
    generated_at: datetime = field(default_factory=utc_timestamp)
    started_at: datetime | None = None
    ended_at: datetime | None = None
    duration_ms: float = 0
    tests: list[TestCaseReport] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    matrix_dimensions: list[str] = field(
        default_factory=lambda: ["profile", "api_profile", "domain", "component", "platform", "context", "owner"]
    )

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


def to_jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value):
        return {key: to_jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    return value
