from __future__ import annotations

from automation_core.healing.audit import append_healing_event, append_healing_events
from automation_core.healing.models import (
    CandidateDescriptor,
    CandidateScore,
    HealingConfig,
    HealingDecision,
    HealingMode,
    HealingResult,
    LocatorDescriptor,
)
from automation_core.healing.reporting import add_healing_result, healing_events_for_test
from automation_core.healing.scoring import evaluate_healing, rank_candidates, score_candidate

__all__ = [
    "CandidateDescriptor",
    "CandidateScore",
    "HealingConfig",
    "HealingDecision",
    "HealingMode",
    "HealingResult",
    "LocatorDescriptor",
    "add_healing_result",
    "append_healing_event",
    "append_healing_events",
    "evaluate_healing",
    "healing_events_for_test",
    "rank_candidates",
    "score_candidate",
]
