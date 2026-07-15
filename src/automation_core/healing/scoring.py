from __future__ import annotations

from typing import Any

from automation_core.healing.models import (
    CandidateDescriptor,
    CandidateScore,
    HealingConfig,
    HealingDecision,
    HealingMode,
    HealingResult,
    LocatorDescriptor,
)

DEFAULT_SIGNAL_WEIGHTS: dict[str, float] = {
    "score": 1.0,
    "exact": 0.8,
    "stable_id": 0.7,
    "accessibility": 0.55,
    "text": 0.25,
    "name": 0.18,
    "type": 0.12,
    "hierarchy": 0.12,
    "context": 0.1,
}


def score_candidate(
    original: LocatorDescriptor,
    candidate: CandidateDescriptor,
    config: HealingConfig | None = None,
) -> CandidateScore:
    active_config = config or HealingConfig()
    weights = {**DEFAULT_SIGNAL_WEIGHTS, **active_config.signal_weights}
    reasons: list[str] = []
    rejected_reasons = _candidate_rejections(original, candidate, active_config)
    score = 0.0

    for signal, raw_value in candidate.signals.items():
        weight = weights.get(signal)
        if weight is None:
            continue
        value = _signal_value(raw_value)
        if value <= 0:
            continue
        score += weight * value
        reasons.append(f"{signal}={value:.2f}")

    if candidate.strategy == original.strategy:
        score += 0.05
        reasons.append("same_strategy=1.00")
    if candidate.value == original.value:
        score += 0.1
        reasons.append("same_value=1.00")
    if not candidate.unique:
        rejected_reasons.append("candidate is not unique")

    return CandidateScore(
        candidate=candidate,
        score=round(min(score, 1.0), 4),
        reasons=reasons,
        rejected_reasons=rejected_reasons,
    )


def rank_candidates(
    original: LocatorDescriptor,
    candidates: list[CandidateDescriptor],
    config: HealingConfig | None = None,
) -> list[CandidateScore]:
    active_config = config or HealingConfig()
    scored = [score_candidate(original, candidate, active_config) for candidate in candidates]
    ranked = sorted(scored, key=lambda item: item.score, reverse=True)
    return ranked[: max(active_config.max_candidates, 0)]


def evaluate_healing(
    original: LocatorDescriptor,
    candidates: list[CandidateDescriptor],
    config: HealingConfig | None = None,
    *,
    action: str = "",
    test_id: str = "",
    metadata: dict[str, Any] | None = None,
) -> HealingResult:
    active_config = config or HealingConfig()
    mode = active_config.normalized_mode()
    action_name = action or original.action
    ranked = rank_candidates(original, candidates, active_config)

    if mode == HealingMode.DISABLED:
        return HealingResult(
            mode=mode,
            decision=HealingDecision.DISABLED,
            original=original,
            candidates=ranked,
            reason="runtime healing is disabled",
            action=action_name,
            test_id=test_id,
            metadata=metadata or {},
        )

    setup_rejection = _setup_rejection(original, active_config, action_name)
    if setup_rejection:
        return HealingResult(
            mode=mode,
            decision=HealingDecision.SKIPPED,
            original=original,
            candidates=ranked,
            reason=setup_rejection,
            action=action_name,
            test_id=test_id,
            metadata=metadata or {},
        )

    viable = [score for score in ranked if not score.rejected]
    if not viable:
        return HealingResult(
            mode=mode,
            decision=HealingDecision.REJECTED,
            original=original,
            candidates=ranked,
            reason="no viable healing candidates",
            action=action_name,
            test_id=test_id,
            metadata=metadata or {},
        )

    selected = viable[0]
    if mode == HealingMode.SUGGEST:
        return HealingResult(
            mode=mode,
            decision=HealingDecision.SUGGESTED,
            original=original,
            candidates=ranked,
            selected=selected,
            reason=_suggest_reason(selected, active_config),
            action=action_name,
            test_id=test_id,
            metadata=metadata or {},
        )

    rejection = _apply_rejection(selected, viable, active_config)
    if rejection:
        return HealingResult(
            mode=mode,
            decision=HealingDecision.REJECTED,
            original=original,
            candidates=ranked,
            selected=selected,
            reason=rejection,
            action=action_name,
            test_id=test_id,
            metadata=metadata or {},
        )

    return HealingResult(
        mode=mode,
        decision=HealingDecision.APPLIED,
        original=original,
        candidates=ranked,
        selected=selected,
        reason=f"selected candidate score {selected.score:.2f} met safety gates",
        action=action_name,
        test_id=test_id,
        metadata=metadata or {},
    )


def _candidate_rejections(
    original: LocatorDescriptor,
    candidate: CandidateDescriptor,
    config: HealingConfig,
) -> list[str]:
    rejected: list[str] = []
    if not config.category_allowed(candidate.category):
        rejected.append(f"category '{candidate.category}' is not allowed")
    if not config.text_allowed(candidate.value):
        rejected.append("candidate value is blocked by allow/deny patterns")
    if candidate.category != original.category and not config.category_allowed(candidate.category):
        rejected.append("candidate category does not match allowed categories")
    return rejected


def _setup_rejection(original: LocatorDescriptor, config: HealingConfig, action: str) -> str:
    if action and not config.action_allowed(action):
        return f"action '{action}' is not allowed for runtime healing"
    if not config.category_allowed(original.category):
        return f"original category '{original.category}' is not allowed for runtime healing"
    if not config.text_allowed(original.value):
        return "original locator is blocked by allow/deny patterns"
    return ""


def _apply_rejection(selected: CandidateScore, viable: list[CandidateScore], config: HealingConfig) -> str:
    if selected.score < config.min_score:
        return f"best candidate score {selected.score:.2f} is below threshold {config.min_score:.2f}"
    if len(viable) > 1 and selected.score - viable[1].score <= config.ambiguity_delta:
        return "best candidate is ambiguous with another candidate"
    return ""


def _suggest_reason(selected: CandidateScore, config: HealingConfig) -> str:
    if selected.score < config.min_score:
        return f"suggesting best candidate below apply threshold {config.min_score:.2f}"
    return "suggesting best candidate without applying it"


def _signal_value(value: Any) -> float:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, int | float):
        return max(0.0, min(float(value), 1.0))
    return 0.0
