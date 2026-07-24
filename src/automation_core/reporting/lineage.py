"""Test-content lineage: group and compare runs by *what they tested*.

A run's identity is the set of fully-qualified test ids it executed — not a
manual "system" label and not the framework repo name. Two runs belong to the
same *lineage* when their test sets overlap enough (see :func:`same_lineage`),
so a run's trend is built only from prior runs of the *same* tests and
comparisons stay apples-to-apples.

Everything here is pure and deterministic so it can be unit-tested with
fixtures before any UI exists. The fully-qualified id is an internal matching
key; user-facing surfaces show friendly names and the plain-language diff from
:func:`diff_tests`, never the raw id.

Design decisions (see ``docs/lineage-model.md``):
- Matching uses the **containment coefficient** ``|A∩B| / min(|A|,|B|)`` with a
  default threshold of ``0.6``. Containment (not Jaccard) means a small smoke
  run that is a subset of a full run counts as the same lineage automatically.
- Lineages are assigned chronologically; each run matches against the
  *most-recent* run of existing lineages (no transitive chaining).
- ``pairwise_delta`` compares over the exact **intersection**; ``trend_series``
  plots each run's raw pass rate restricted to its lineage plus a coverage
  badge (a deliberate v1 simplification — see the doc's backlog).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

DEFAULT_LINEAGE_THRESHOLD = 0.6
PASSED_STATUSES = frozenset({"passed"})


# --------------------------------------------------------------------------- #
# Run views: a normalized, comparable projection of a run.
# --------------------------------------------------------------------------- #


class RunView:
    """A run reduced to what lineage math needs: an id, a time, and per-test
    fully-qualified ids with their statuses."""

    __slots__ = ("run_id", "generated_at", "statuses")

    def __init__(self, run_id: str, generated_at: Any, statuses: Mapping[str, str]):
        self.run_id = run_id
        self.generated_at = generated_at
        # fully-qualified id -> status (last write wins for duplicate ids).
        self.statuses: dict[str, str] = dict(statuses)

    @property
    def signature(self) -> frozenset[str]:
        return frozenset(self.statuses)

    @property
    def size(self) -> int:
        return len(self.statuses)

    def pass_rate_over(self, ids: Iterable[str]) -> float:
        """Pass rate (0–100) over the given ids that this run actually ran."""
        present = [i for i in ids if i in self.statuses]
        if not present:
            return 0.0
        passed = sum(1 for i in present if self.statuses[i] in PASSED_STATUSES)
        return round(passed / len(present) * 100, 2)

    @property
    def pass_rate(self) -> float:
        """Raw pass rate over this run's whole signature."""
        return self.pass_rate_over(self.statuses)


def fq_id(test: Any) -> str:
    """Best-available stable, cross-run identity for one test.

    Precedence: explicit node id in metadata -> full name -> ``suite::name`` ->
    name -> id. Names alone can collide across apps, so callers that want strict
    separation should populate a node id / full name.
    """

    def get(key: str) -> Any:
        if isinstance(test, Mapping):
            return test.get(key)
        return getattr(test, key, None)

    metadata = get("metadata") or {}
    if isinstance(metadata, Mapping):
        for key in ("nodeid", "node_id", "fq_id", "fqid"):
            value = metadata.get(key)
            if value:
                return str(value)

    full_name = get("full_name")
    if full_name:
        return str(full_name)

    name = get("name") or ""
    suite = get("suite") or ""
    if suite and name:
        return f"{suite}::{name}"
    if name:
        return str(name)
    return str(get("id") or get("test_id") or "")


def _status_of(test: Any) -> str:
    if isinstance(test, Mapping):
        return str(test.get("status", "unknown"))
    return str(getattr(test, "status", "unknown"))


def run_view(run_id: str, generated_at: Any, tests: Sequence[Any]) -> RunView:
    """Build a :class:`RunView` from any sequence of test-like objects."""
    statuses: dict[str, str] = {}
    for test in tests:
        key = fq_id(test)
        if key:
            statuses[key] = _status_of(test)
    return RunView(run_id, generated_at, statuses)


def run_view_from_report(report: Any) -> RunView:
    """Build a view from a :class:`~automation_core.reporting.RunReport`."""
    return run_view(report.run_id, getattr(report, "generated_at", None), report.tests)


def run_view_from_report_data(report_data: Mapping[str, Any]) -> RunView:
    """Build a view from a neutral report-data sidecar (its ``test_index``)."""
    run = report_data.get("run", {}) or {}
    run_id = run.get("run_id") or report_data.get("run_id") or ""
    generated_at = run.get("generated_at") or report_data.get("generated_at")
    return run_view(run_id, generated_at, report_data.get("test_index", []) or [])


def run_view_from_history_entry(entry: Mapping[str, Any]) -> RunView:
    """Build a view from a stored history entry (its ``test_statuses``).

    Each status entry carries a precomputed ``fq_id`` (falling back to identity
    fields) so the id matches what :func:`run_view_from_report` produced.
    """
    statuses: dict[str, str] = {}
    for item in entry.get("test_statuses", []) or []:
        key = item.get("fq_id") or fq_id(item)
        if key:
            statuses[str(key)] = str(item.get("status", "unknown"))
    run_id = entry.get("run_id", "")
    generated_at = entry.get("latest_run") or entry.get("generated_at")
    return RunView(run_id, generated_at, statuses)


# --------------------------------------------------------------------------- #
# Set-similarity primitives.
# --------------------------------------------------------------------------- #


def containment(a: Iterable[str], b: Iterable[str]) -> float:
    """Overlap coefficient ``|A∩B| / min(|A|,|B|)`` in ``[0, 1]``.

    Unlike Jaccard this is ``1.0`` when one set is a subset of the other, so a
    smoke subset of a full run is recognised as the same suite.
    """
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / min(len(sa), len(sb))


def jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    """``|A∩B| / |A∪B|`` — reported for context, not used for matching."""
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def same_lineage(a: RunView, b: RunView, *, threshold: float = DEFAULT_LINEAGE_THRESHOLD) -> bool:
    """True when two runs share enough tests to belong to the same lineage."""
    return containment(a.signature, b.signature) >= threshold


# --------------------------------------------------------------------------- #
# Lineage assignment.
# --------------------------------------------------------------------------- #


def _chrono_key(view: RunView) -> tuple[str, str]:
    # Sort by time then run id; str() keeps datetimes and ISO strings comparable
    # within a consistent input and stays deterministic for ties.
    return (str(view.generated_at), str(view.run_id))


def assign_lineages(views: Sequence[RunView], *, threshold: float = DEFAULT_LINEAGE_THRESHOLD) -> dict[str, str]:
    """Map each ``run_id`` to a lineage id (the anchor run's id).

    Runs are processed oldest-first; each joins the existing lineage whose
    most-recent run it best matches (containment ≥ threshold), else it starts a
    new lineage anchored on itself.
    """
    lineages: list[dict[str, Any]] = []  # {"id": anchor_run_id, "latest": RunView}
    result: dict[str, str] = {}
    for view in sorted(views, key=_chrono_key):
        best: dict[str, Any] | None = None
        best_score = 0.0
        for lineage in lineages:
            score = containment(view.signature, lineage["latest"].signature)
            if score >= threshold and score > best_score:
                best, best_score = lineage, score
        if best is not None:
            result[view.run_id] = best["id"]
            best["latest"] = view
        else:
            lineages.append({"id": view.run_id, "latest": view})
            result[view.run_id] = view.run_id
    return result


def lineage_members(
    target: RunView, views: Sequence[RunView], *, threshold: float = DEFAULT_LINEAGE_THRESHOLD
) -> list[RunView]:
    """All runs in ``target``'s lineage, oldest-first (includes ``target``)."""
    by_id = {v.run_id: v for v in views}
    by_id.setdefault(target.run_id, target)
    all_views = list(by_id.values())
    assignment = assign_lineages(all_views, threshold=threshold)
    target_lineage = assignment.get(target.run_id, target.run_id)
    members = [v for v in all_views if assignment.get(v.run_id) == target_lineage]
    return sorted(members, key=_chrono_key)


# --------------------------------------------------------------------------- #
# Diff, coverage, comparison, trend.
# --------------------------------------------------------------------------- #


def diff_tests(base: RunView, other: RunView) -> dict[str, Any]:
    """What changed going from ``base`` to ``other``.

    ``added`` are ids in ``other`` but not ``base``; ``removed`` the reverse.
    Lists are sorted for deterministic, presentable output.
    """
    a, b = base.signature, other.signature
    shared = a & b
    return {
        "shared": len(shared),
        "base_total": len(a),
        "other_total": len(b),
        "added": sorted(b - a),
        "removed": sorted(a - b),
    }


def coverage(view: RunView, members: Sequence[RunView]) -> dict[str, Any]:
    """How much of its lineage's largest run this run covered.

    ``reference`` is the biggest signature seen in the lineage; a run smaller
    than that is ``partial`` (e.g. a smoke subset of a full regression run).
    """
    reference = max((m.size for m in members), default=view.size)
    reference = max(reference, view.size)
    ratio = round(view.size / reference * 100, 2) if reference else 0.0
    return {
        "covered": view.size,
        "reference": reference,
        "ratio": ratio,
        "partial": view.size < reference,
    }


def pairwise_delta(base: RunView, other: RunView) -> dict[str, Any]:
    """Compare two runs over the exact **intersection** of their tests.

    Pass rates are computed only over the shared ids so the delta is fair even
    when the suites differ; the non-shared tests are reported via the diff.
    """
    shared_ids = base.signature & other.signature
    base_rate = base.pass_rate_over(shared_ids)
    other_rate = other.pass_rate_over(shared_ids)
    return {
        "shared": len(shared_ids),
        "base_pass_rate": base_rate,
        "other_pass_rate": other_rate,
        "pass_rate_delta": round(other_rate - base_rate, 2),
        "comparable": bool(shared_ids),
        "diff": diff_tests(base, other),
    }


def build_lineage_view(
    current: RunView,
    history_views: Sequence[RunView],
    *,
    threshold: float = DEFAULT_LINEAGE_THRESHOLD,
) -> dict[str, Any]:
    """Assemble the render-ready lineage view-model for ``current``.

    Combines the current run's own view with prior runs (``history_views``) and
    returns the lineage trend, the diff against the previous run in the same
    lineage, coverage, and the lineage size — everything a report needs to draw
    the lineage surfaces, with no rendering assumptions baked in.
    """
    by_id: dict[str, RunView] = {v.run_id: v for v in history_views}
    by_id[current.run_id] = current  # the live run is authoritative
    views = list(by_id.values())

    members = lineage_members(current, views, threshold=threshold)
    trend = trend_series(current, views, threshold=threshold)
    cov = coverage(current, members)

    member_ids = [m.run_id for m in members]
    index = member_ids.index(current.run_id)
    previous = members[index - 1] if index > 0 else None
    if previous is not None:
        diff = diff_tests(previous, current)
    else:
        diff = {
            "shared": 0,
            "base_total": 0,
            "other_total": current.size,
            "added": sorted(current.signature),
            "removed": [],
        }

    return {
        "trend": trend,
        "lineage_size": len(members),
        "coverage": cov,
        "partial": cov["partial"],
        "previous_run_id": previous.run_id if previous else None,
        "diff_vs_previous": diff,
    }


def trend_series(
    target: RunView, views: Sequence[RunView], *, threshold: float = DEFAULT_LINEAGE_THRESHOLD
) -> list[dict[str, Any]]:
    """The lineage trend for ``target``: one point per run in its lineage.

    Each point carries the run's raw pass rate and its coverage badge, oldest
    first. (v1: raw per-run pass rate restricted to the lineage; making each
    point intersection-based is a tracked backlog item.)
    """
    members = lineage_members(target, views, threshold=threshold)
    points: list[dict[str, Any]] = []
    for member in members:
        cov = coverage(member, members)
        points.append(
            {
                "run_id": member.run_id,
                "generated_at": member.generated_at,
                "pass_rate": member.pass_rate,
                "total": member.size,
                "coverage_ratio": cov["ratio"],
                "partial": cov["partial"],
                "is_target": member.run_id == target.run_id,
            }
        )
    return points
