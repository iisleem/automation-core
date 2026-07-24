"""Deterministic fixture tests for the test-content lineage model.

These pin the agreed logic (containment >= 0.6, subset handling, intersection
comparison, coverage/partial, added/removed diff) with plain fixtures and no
UI — the feature is QA-able before any design work.
"""

from __future__ import annotations

from automation_core.reporting import lineage
from automation_core.reporting.lineage import (
    RunView,
    assign_lineages,
    containment,
    coverage,
    diff_tests,
    fq_id,
    jaccard,
    lineage_members,
    pairwise_delta,
    run_view,
    same_lineage,
    trend_series,
)


def _view(run_id: str, day: int, tests: dict[str, str]) -> RunView:
    """A run view from {fq_id: status}."""
    return RunView(run_id, f"2026-07-{day:02d}T00:00:00Z", tests)


def _passed(ids: list[str]) -> dict[str, str]:
    return {i: "passed" for i in ids}


# --------------------------------------------------------------------------- #
# Identity / signatures
# --------------------------------------------------------------------------- #


def test_fq_id_precedence_prefers_stable_identifiers():
    assert fq_id({"metadata": {"nodeid": "tests/a.py::test_x"}, "name": "test_x"}) == "tests/a.py::test_x"
    assert fq_id({"full_name": "pkg.mod.test_x", "name": "test_x"}) == "pkg.mod.test_x"
    assert fq_id({"suite": "auth", "name": "test_login"}) == "auth::test_login"
    assert fq_id({"name": "test_login"}) == "test_login"


def test_run_view_signature_and_pass_rate():
    view = run_view(
        "r1",
        "2026-07-01",
        [
            {"suite": "auth", "name": "test_login", "status": "passed"},
            {"suite": "auth", "name": "test_logout", "status": "failed"},
        ],
    )
    assert view.signature == frozenset({"auth::test_login", "auth::test_logout"})
    assert view.pass_rate == 50.0


# --------------------------------------------------------------------------- #
# Similarity primitives
# --------------------------------------------------------------------------- #


def test_containment_is_one_for_subset_but_jaccard_is_small():
    smoke = {"a", "b", "c"}
    full = {f"t{i}" for i in range(197)} | smoke  # 200 tests, smoke ⊂ full
    assert containment(smoke, full) == 1.0
    assert jaccard(smoke, full) < 0.05
    assert containment(set(), full) == 0.0


def test_same_lineage_threshold_boundary():
    base = _view("b", 1, _passed(["a", "b", "c", "d", "e"]))  # 5
    keep3 = _view("k", 2, _passed(["a", "b", "c", "x", "y"]))  # shares 3 -> 3/5 = 0.6
    keep2 = _view("k2", 2, _passed(["a", "b", "x", "y", "z"]))  # shares 2 -> 0.4
    assert same_lineage(base, keep3) is True
    assert same_lineage(base, keep2) is False


# --------------------------------------------------------------------------- #
# Lineage assignment
# --------------------------------------------------------------------------- #


def test_smoke_and_full_runs_share_one_lineage():
    full1 = _view("full-1", 1, _passed([f"t{i}" for i in range(200)]))
    smoke = _view("smoke", 2, _passed([f"t{i}" for i in range(10)]))
    full2 = _view("full-2", 3, _passed([f"t{i}" for i in range(200)]))
    assignment = assign_lineages([full1, smoke, full2])
    # All three collapse into the anchor lineage of the earliest run.
    assert set(assignment.values()) == {"full-1"}


def test_different_apps_form_separate_lineages():
    ecom = _view("ecom", 1, _passed([f"ecom::t{i}" for i in range(20)]))
    mag = _view("mag", 2, _passed([f"magazine::t{i}" for i in range(20)]))
    assignment = assign_lineages([ecom, mag])
    assert assignment["ecom"] != assignment["mag"]
    assert len(set(assignment.values())) == 2


def test_evolving_suite_stays_one_lineage_until_it_drifts_too_far():
    r1 = _view("r1", 1, _passed([f"t{i}" for i in range(100)]))
    # keeps 80, drops 20, adds 20 -> containment vs r1 = 80/100 = 0.8
    r2_ids = [f"t{i}" for i in range(20, 100)] + [f"n{i}" for i in range(20)]
    r2 = _view("r2", 2, _passed(r2_ids))
    # a hard fork: shares only 30 with r2 -> 30/100 = 0.3
    r3_ids = [f"t{i}" for i in range(20, 50)] + [f"z{i}" for i in range(70)]
    r3 = _view("r3", 3, _passed(r3_ids))
    assignment = assign_lineages([r1, r2, r3])
    assert assignment["r1"] == assignment["r2"] == "r1"
    assert assignment["r3"] == "r3"


def test_lineage_members_are_chronological_and_scoped():
    a1 = _view("a1", 1, _passed(["a", "b", "c"]))
    other = _view("x", 2, _passed(["p", "q", "r"]))
    a2 = _view("a2", 3, _passed(["a", "b", "c"]))
    members = lineage_members(a2, [a1, other, a2])
    assert [m.run_id for m in members] == ["a1", "a2"]


# --------------------------------------------------------------------------- #
# Diff / coverage / comparison
# --------------------------------------------------------------------------- #


def test_diff_reports_added_and_removed():
    base = _view("b", 1, _passed(["a", "b", "c"]))
    other = _view("o", 2, _passed(["b", "c", "d", "e"]))
    diff = diff_tests(base, other)
    assert diff["shared"] == 2
    assert diff["added"] == ["d", "e"]
    assert diff["removed"] == ["a"]


def test_coverage_flags_partial_runs():
    full = _view("full", 1, _passed([f"t{i}" for i in range(200)]))
    smoke = _view("smoke", 2, _passed([f"t{i}" for i in range(10)]))
    members = [full, smoke]
    assert coverage(full, members)["partial"] is False
    smoke_cov = coverage(smoke, members)
    assert smoke_cov["partial"] is True
    assert smoke_cov["covered"] == 10
    assert smoke_cov["reference"] == 200
    assert smoke_cov["ratio"] == 5.0


def test_pairwise_delta_compares_over_intersection_only():
    # base: a,b,c,d all passed. other: a,b pass, c fail, plus new e (ignored in
    # the rate because e is not shared). Shared = {a,b,c}.
    base = RunView("b", 1, {"a": "passed", "b": "passed", "c": "passed", "d": "passed"})
    other = RunView("o", 2, {"a": "passed", "b": "passed", "c": "failed", "e": "passed"})
    delta = pairwise_delta(base, other)
    assert delta["shared"] == 3
    assert delta["base_pass_rate"] == 100.0
    assert round(delta["other_pass_rate"]) == 67  # 2/3 over the shared set
    assert delta["pass_rate_delta"] < 0
    assert delta["diff"]["added"] == ["e"]
    assert delta["diff"]["removed"] == ["d"]


def test_pairwise_delta_marks_incomparable_when_no_overlap():
    a = _view("a", 1, _passed(["x", "y"]))
    b = _view("b", 2, _passed(["p", "q"]))
    delta = pairwise_delta(a, b)
    assert delta["comparable"] is False
    assert delta["shared"] == 0


# --------------------------------------------------------------------------- #
# Trend
# --------------------------------------------------------------------------- #


def test_trend_series_is_lineage_scoped_with_coverage_and_target_flag():
    full1 = RunView("full-1", "2026-07-01", {**_passed([f"t{i}" for i in range(9)]), "t9": "failed"})  # 90%
    smoke = RunView("smoke", "2026-07-02", _passed(["t0", "t1"]))  # 100% of 2
    unrelated = _view("other", 2, _passed(["z0", "z1", "z2"]))
    full2 = RunView("full-2", "2026-07-03", _passed([f"t{i}" for i in range(10)]))  # 100%

    series = trend_series(full2, [full1, smoke, unrelated, full2])
    ids = [p["run_id"] for p in series]
    assert ids == ["full-1", "smoke", "full-2"]  # unrelated excluded, chronological
    by_id = {p["run_id"]: p for p in series}
    assert by_id["full-1"]["pass_rate"] == 90.0
    assert by_id["smoke"]["partial"] is True
    assert by_id["full-2"]["partial"] is False
    assert by_id["full-2"]["is_target"] is True
    assert by_id["smoke"]["is_target"] is False


def test_threshold_is_configurable():
    base = _view("b", 1, _passed(["a", "b", "c", "d", "e"]))
    other = _view("o", 2, _passed(["a", "b", "x", "y", "z"]))  # containment 0.4
    assert same_lineage(base, other, threshold=0.4) is True
    assert same_lineage(base, other, threshold=0.6) is False


def test_default_threshold_constant():
    assert lineage.DEFAULT_LINEAGE_THRESHOLD == 0.6


def test_build_lineage_view_assembles_trend_diff_and_coverage():
    prev = RunView("prev", "2026-07-01", _passed([f"t{i}" for i in range(10)]))  # 100% of 10
    # current: same suite minus t9, plus a new t10, with one failure.
    current_ids = [f"t{i}" for i in range(9)] + ["t10"]
    current_statuses = _passed(current_ids)
    current_statuses["t0"] = "failed"
    current = RunView("cur", "2026-07-02", current_statuses)

    vm = lineage.build_lineage_view(current, [prev])
    assert vm["lineage_size"] == 2
    assert [p["run_id"] for p in vm["trend"]] == ["prev", "cur"]
    assert vm["previous_run_id"] == "prev"
    # Diff vs previous: dropped t9, added t10.
    assert vm["diff_vs_previous"]["added"] == ["t10"]
    assert vm["diff_vs_previous"]["removed"] == ["t9"]
    assert vm["coverage"]["partial"] is False  # same size as reference


def test_build_lineage_view_first_run_has_no_previous():
    current = RunView("only", "2026-07-01", _passed(["a", "b"]))
    vm = lineage.build_lineage_view(current, [])
    assert vm["lineage_size"] == 1
    assert vm["previous_run_id"] is None
    assert vm["diff_vs_previous"]["added"] == ["a", "b"]
    assert vm["diff_vs_previous"]["removed"] == []


def test_run_view_from_history_entry_uses_stored_fq_id():
    entry = {
        "run_id": "r1",
        "latest_run": "2026-07-01T00:00:00Z",
        "test_statuses": [
            {"fq_id": "auth::test_login", "status": "passed"},
            {"fq_id": "auth::test_logout", "status": "failed"},
            {"name": "test_fallback", "status": "passed"},  # no fq_id -> derived
        ],
    }
    view = lineage.run_view_from_history_entry(entry)
    assert view.signature == frozenset({"auth::test_login", "auth::test_logout", "test_fallback"})
    assert view.pass_rate == round(2 / 3 * 100, 2)
