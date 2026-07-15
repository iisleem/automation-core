from __future__ import annotations

import json

from automation_core.healing import (
    CandidateDescriptor,
    HealingConfig,
    HealingDecision,
    HealingMode,
    LocatorDescriptor,
    add_healing_result,
    append_healing_event,
    evaluate_healing,
    healing_events_for_test,
    rank_candidates,
    score_candidate,
)
from automation_core.reporting import RunReport, TestCaseReport, build_timeline_events, generate_reporting_product


def test_disabled_mode_ranks_but_does_not_apply_candidate():
    original = LocatorDescriptor(strategy="css", value="[data-test='login']", action="click")
    candidate = CandidateDescriptor(strategy="css", value="[data-test='sign-in']", signals={"stable_id": 1.0})

    result = evaluate_healing(original, [candidate])

    assert result.mode == HealingMode.DISABLED
    assert result.decision == HealingDecision.DISABLED
    assert not result.applied
    assert result.candidates[0].score > 0


def test_suggest_mode_returns_best_candidate_without_applying():
    original = LocatorDescriptor(strategy="accessibility_id", value="Login", action="tap")
    candidates = [
        CandidateDescriptor(strategy="accessibility_id", value="Sign in", signals={"accessibility": 0.9}),
        CandidateDescriptor(strategy="xpath", value="//button[1]", signals={"hierarchy": 0.3}),
    ]
    config = HealingConfig(mode="suggest", min_score=0.7)

    result = evaluate_healing(original, candidates, config, action="tap", test_id="login")

    assert result.decision == HealingDecision.SUGGESTED
    assert result.selected is not None
    assert result.selected.candidate.value == "Sign in"
    assert not result.applied
    assert result.test_id == "login"


def test_apply_mode_requires_threshold_and_non_ambiguous_candidate():
    original = LocatorDescriptor(strategy="css", value="#checkout", action="click")
    config = HealingConfig(mode="apply", min_score=0.7, ambiguity_delta=0.05)
    low = CandidateDescriptor(strategy="css", value="#continue", signals={"stable_id": 0.4})
    strong = CandidateDescriptor(strategy="css", value="#checkout-continue", signals={"stable_id": 1.0, "text": 1.0})

    rejected = evaluate_healing(original, [low], config, action="click")
    applied = evaluate_healing(original, [strong], config, action="click")

    assert rejected.decision == HealingDecision.REJECTED
    assert "below threshold" in rejected.reason
    assert applied.decision == HealingDecision.APPLIED
    assert applied.applied


def test_apply_mode_rejects_ambiguous_top_candidates():
    original = LocatorDescriptor(strategy="css", value="#save", action="click")
    candidates = [
        CandidateDescriptor(strategy="css", value="#save-primary", signals={"stable_id": 1.0}),
        CandidateDescriptor(strategy="css", value="#save-secondary", signals={"stable_id": 0.98}),
    ]
    config = HealingConfig(mode="apply", min_score=0.7, ambiguity_delta=0.05)

    result = evaluate_healing(original, candidates, config, action="click")

    assert result.decision == HealingDecision.REJECTED
    assert "ambiguous" in result.reason


def test_safety_gates_reject_disallowed_actions_patterns_and_non_unique_candidates():
    original = LocatorDescriptor(strategy="css", value="#delete", action="click")
    candidate = CandidateDescriptor(
        strategy="css",
        value="#delete-confirm",
        signals={"stable_id": 1.0},
        unique=False,
    )
    config = HealingConfig(
        mode="apply",
        allowed_actions=("type",),
        deny_patterns=("delete",),
        min_score=0.7,
    )

    result = evaluate_healing(original, [candidate], config, action="click")
    score = score_candidate(original, candidate, config)

    assert result.decision == HealingDecision.SKIPPED
    assert "not allowed" in result.reason or "blocked" in result.reason
    assert score.rejected
    assert any("not unique" in reason for reason in score.rejected_reasons)


def test_rank_candidates_limits_and_sorts_by_score():
    original = LocatorDescriptor(strategy="css", value="#login")
    candidates = [
        CandidateDescriptor(strategy="css", value="#third", signals={"text": 0.1}),
        CandidateDescriptor(strategy="css", value="#first", signals={"stable_id": 1.0}),
        CandidateDescriptor(strategy="css", value="#second", signals={"accessibility": 0.8}),
    ]

    ranked = rank_candidates(original, candidates, HealingConfig(max_candidates=2))

    assert [item.candidate.value for item in ranked] == ["#first", "#second"]


def test_healing_result_serializes_and_writes_jsonl_audit(tmp_path):
    original = LocatorDescriptor(strategy="css", value="#login")
    candidate = CandidateDescriptor(strategy="css", value="#sign-in", signals={"stable_id": 1.0})
    result = evaluate_healing(original, [candidate], HealingConfig(mode="suggest"))

    payload = result.to_dict()
    audit = append_healing_event(tmp_path / "healing" / "events.jsonl", result)
    lines = audit.read_text(encoding="utf-8").splitlines()

    assert payload["decision"] == "suggested"
    assert json.loads(lines[0])["selected"]["candidate"]["value"] == "#sign-in"


def test_healing_reporting_metadata_appears_in_timeline_and_product_report(tmp_path):
    test = TestCaseReport(id="login", name="test_login", status="passed")
    original = LocatorDescriptor(strategy="css", value="#login", action="click")
    candidate = CandidateDescriptor(strategy="css", value="#sign-in", signals={"stable_id": 1.0, "text": 1.0})
    result = evaluate_healing(original, [candidate], HealingConfig(mode="apply", min_score=0.7), action="click")

    add_healing_result(test, result)
    report = RunReport(run_id="healing-run", generated_at=result.timestamp, tests=[test])
    events = build_timeline_events(report)

    assert healing_events_for_test(test)[0]["decision"] == "applied"
    assert test.metadata["healing_applied_count"] == 1
    assert any(event.event_type == "healing" and "sign-in" in event.title for event in events)

    generate_reporting_product(report, tmp_path / "report")
    timeline = (tmp_path / "report" / "timeline.html").read_text(encoding="utf-8")
    detail = next((tmp_path / "report" / "tests").glob("*.html")).read_text(encoding="utf-8")
    assert "Healing applied" in timeline
    assert "healing_events" in detail
