from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from automation_core.reporting.models import to_jsonable, utc_timestamp


class HealingMode(StrEnum):
    DISABLED = "disabled"
    SUGGEST = "suggest"
    APPLY = "apply"


class HealingDecision(StrEnum):
    DISABLED = "disabled"
    SKIPPED = "skipped"
    REJECTED = "rejected"
    SUGGESTED = "suggested"
    APPLIED = "applied"


@dataclass(frozen=True)
class LocatorDescriptor:
    strategy: str
    value: str
    category: str = "locator"
    action: str = ""
    label: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class CandidateDescriptor:
    strategy: str
    value: str
    category: str = "locator"
    label: str = ""
    source: str = ""
    signals: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    unique: bool = True

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class CandidateScore:
    candidate: CandidateDescriptor
    score: float
    reasons: list[str] = field(default_factory=list)
    rejected_reasons: list[str] = field(default_factory=list)

    @property
    def rejected(self) -> bool:
        return bool(self.rejected_reasons)

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class HealingConfig:
    mode: HealingMode | str = HealingMode.DISABLED
    min_score: float = 0.78
    ambiguity_delta: float = 0.05
    max_candidates: int = 10
    allowed_actions: tuple[str, ...] = ()
    allowed_categories: tuple[str, ...] = ("locator", "element", "control", "screen")
    allow_patterns: tuple[str, ...] = ()
    deny_patterns: tuple[str, ...] = ()
    signal_weights: dict[str, float] = field(default_factory=dict)

    def normalized_mode(self) -> HealingMode:
        return self.mode if isinstance(self.mode, HealingMode) else HealingMode(str(self.mode).strip().lower())

    def action_allowed(self, action: str) -> bool:
        return not self.allowed_actions or action in self.allowed_actions

    def category_allowed(self, category: str) -> bool:
        return not self.allowed_categories or category in self.allowed_categories

    def text_allowed(self, value: str) -> bool:
        if self.deny_patterns and any(re.search(pattern, value) for pattern in self.deny_patterns):
            return False
        if self.allow_patterns and not any(re.search(pattern, value) for pattern in self.allow_patterns):
            return False
        return True

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class HealingResult:
    mode: HealingMode
    decision: HealingDecision
    original: LocatorDescriptor
    candidates: list[CandidateScore] = field(default_factory=list)
    selected: CandidateScore | None = None
    reason: str = ""
    action: str = ""
    test_id: str = ""
    timestamp: datetime = field(default_factory=utc_timestamp)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def applied(self) -> bool:
        return self.decision == HealingDecision.APPLIED

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)
