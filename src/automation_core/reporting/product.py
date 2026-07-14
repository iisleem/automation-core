from __future__ import annotations

import html
import json
import os
import re
from pathlib import Path
from shutil import copy2
from typing import Any
from urllib.parse import urlparse

from automation_core.reporting.analysis import (
    failure_summary,
    fastest_slowest_tests,
    flaky_analysis,
    matrix_summary,
    summarize_run,
)
from automation_core.reporting.events import ReportingEvent, build_timeline_events
from automation_core.reporting.history import load_history, trend_points, update_history
from automation_core.reporting.models import Artifact, RunReport, StepRecord, TestCaseReport, to_jsonable
from automation_core.reporting.traversal import collect_action_retries, collect_test_artifacts
from automation_core.reporting.validation import assert_valid_report

TEXT_ARTIFACT_TYPES = {"log", "source", "xml", "json", "request", "response", "payload", "text"}
IMAGE_ARTIFACT_TYPES = {"screenshot", "image"}
VIDEO_ARTIFACT_TYPES = {"video"}


def generate_reporting_product(
    report: RunReport,
    output_dir: str | Path,
    *,
    history_dir: str | Path | None = None,
    update_history_file: bool = True,
    history_limit: int = 20,
    bundle_artifacts: bool = True,
    validate: bool = True,
) -> Path:
    output_path = Path(output_dir)
    tests_dir = output_path / "tests"
    data_dir = output_path / "data"
    tests_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    if bundle_artifacts:
        _bundle_report_artifacts(report, output_path)
    if validate:
        assert_valid_report(report)

    details = _write_test_pages(report, tests_dir, output_path)
    history_entries = _history_entries(report, history_dir, update_history_file, history_limit)
    timeline = build_timeline_events(report)

    (data_dir / "run-report.json").write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    (output_path / "timeline.html").write_text(_render_timeline_page(report, timeline), encoding="utf-8")
    (output_path / "flaky.html").write_text(_render_flaky_page(report), encoding="utf-8")
    (output_path / "matrix.html").write_text(_render_matrix_page(report), encoding="utf-8")
    (output_path / "history.html").write_text(_render_history_page(report, history_entries), encoding="utf-8")
    index_path = output_path / "index.html"
    index_path.write_text(_render_dashboard(report, details, history_entries), encoding="utf-8")
    return index_path


def _bundle_report_artifacts(report: RunReport, output_dir: Path) -> None:
    artifacts_dir = output_dir / "artifacts"
    index = 0
    for test in report.tests:
        for artifact in collect_test_artifacts(test):
            if _is_external_href(artifact.href):
                continue
            if not artifact.path:
                continue
            source = Path(artifact.path)
            if not source.exists() or not source.is_file():
                continue
            index += 1
            artifacts_dir.mkdir(parents=True, exist_ok=True)
            destination = _artifact_destination(artifacts_dir, artifact, source, index)
            try:
                if source.resolve() != destination.resolve():
                    copy2(source, destination)
                artifact.metadata.setdefault("original_path", str(source))
                artifact.metadata["bundled"] = True
                artifact.path = str(destination)
                artifact.href = f"artifacts/{destination.name}"
                artifact.size_bytes = destination.stat().st_size
            except OSError as error:
                artifact.metadata["bundle_error"] = str(error)


def _artifact_destination(artifacts_dir: Path, artifact: Artifact, source: Path, index: int) -> Path:
    stem = _slug(artifact.name or source.stem)
    suffix = source.suffix
    destination = artifacts_dir / f"{index:04d}-{stem}{suffix}"
    collision = 1
    while destination.exists():
        destination = artifacts_dir / f"{index:04d}-{stem}-{collision}{suffix}"
        collision += 1
    return destination


def _history_entries(
    report: RunReport,
    history_dir: str | Path | None,
    update_history_file: bool,
    history_limit: int,
) -> list[dict[str, Any]]:
    if not history_dir:
        return []
    if update_history_file:
        return update_history(report, history_dir, max_entries=history_limit)
    return load_history(history_dir, limit=history_limit)


def _write_test_pages(report: RunReport, tests_dir: Path, report_root: Path) -> dict[str, str]:
    details: dict[str, str] = {}
    for index, test in enumerate(report.tests, start=1):
        filename = f"{index:04d}-{_slug(test.id or test.name)}.html"
        (tests_dir / filename).write_text(_render_test_page(report, test, tests_dir, report_root), encoding="utf-8")
        details[test.id] = f"tests/{filename}"
    return details


def _render_dashboard(
    report: RunReport,
    details: dict[str, str],
    history_entries: list[dict[str, Any]],
) -> str:
    summary = summarize_run(report)
    speed = fastest_slowest_tests(report)
    flaky = flaky_analysis(report)
    trend = trend_points(history_entries)
    rows = "\n".join(_test_row(test, details.get(test.id, "#")) for test in report.tests)

    return _page(
        "Automation Report",
        f"""
<header class="hero">
  <div>
    <p class="eyebrow">{_e(report.project_name or "automation")}</p>
    <h1>Automation Report</h1>
    <p>{_e(report.framework or "shared reporting")} · {_e(summary["latest_run"])}</p>
  </div>
  <span class="status {summary["status"]}">{_e(summary["status"])}</span>
</header>
<nav class="tabs">
  <a href="index.html">Dashboard</a>
  <a href="timeline.html">Timeline</a>
  <a href="flaky.html">Flaky</a>
  <a href="matrix.html">Matrix</a>
  <a href="history.html">History</a>
</nav>
<section class="metrics">
  {_metric("Total", summary["total"])}
  {_metric("Passed", summary["passed"])}
  {_metric("Failed", summary["failed"] + summary["broken"])}
  {_metric("Skipped", summary["skipped"])}
  {_metric("Flaky", summary["flaky"])}
  {_metric("Duration", _format_duration(summary["duration_ms"]))}
</section>
<section class="grid two">
  <article>
    <h2>Run Context</h2>
    {
            _key_values(
                {
                    "Run ID": report.run_id,
                    "Profiles": ", ".join(summary["profiles"]) or "-",
                    "Environments": ", ".join(summary["environments"]) or "-",
                    "Browsers": ", ".join(summary["browsers"]) or "-",
                    "Devices": ", ".join(summary["devices"]) or "-",
                    "Pass Rate": f"{summary['pass_rate']}%",
                }
            )
        }
  </article>
  <article>
    <h2>Trend</h2>
    {_trend_bars(trend)}
  </article>
</section>
<section class="grid three">
  <article>
    <h2>Fastest Tests</h2>
    {_test_list(speed["fastest"], details)}
  </article>
  <article>
    <h2>Slowest Tests</h2>
    {_test_list(speed["slowest"], details)}
  </article>
  <article>
    <h2>Failure Summary</h2>
    {_failure_summary_list(report)}
  </article>
</section>
<section>
  <h2>Flaky Signals</h2>
  {_analysis_table(flaky)}
</section>
<section>
  <h2>Tests</h2>
  <table>
    <thead><tr><th>Status</th><th>Test</th><th>Profile</th><th>Duration</th><th>Failure</th></tr></thead>
    <tbody>{rows or '<tr><td colspan="5">No tests found.</td></tr>'}</tbody>
  </table>
</section>
""",
    )


def _render_test_page(report: RunReport, test: TestCaseReport, page_dir: Path, report_root: Path) -> str:
    action_retries = collect_action_retries(test)
    artifacts = collect_test_artifacts(test)
    timeline = [
        event
        for event in build_timeline_events(RunReport(run_id=report.run_id, tests=[test]))
        if event.test_id == test.id
    ]
    return _page(
        test.name,
        f"""
<header class="hero compact">
  <div>
    <p class="eyebrow">{_e(test.suite or test.domain or report.project_name or "test")}</p>
    <h1>{_e(test.name)}</h1>
    <p>{_e(test.full_name or test.id)}</p>
  </div>
  <span class="status {test.status}">{_e(test.status)}</span>
</header>
<nav class="tabs"><a href="../index.html">Dashboard</a><a href="../timeline.html">Timeline</a><a href="../flaky.html">Flaky</a><a href="../matrix.html">Matrix</a></nav>
<section class="metrics">
  {_metric("Duration", _format_duration(test.duration_ms))}
  {_metric("Retries", len(test.retries))}
  {_metric("Action Retries", len(action_retries))}
  {_metric("Artifacts", len(artifacts))}
</section>
<section class="grid two">
  <article>
    <h2>Failure Reason</h2>
    {_failure_reason(test)}
  </article>
  <article>
    <h2>Context</h2>
    {_key_values(_test_context_values(test))}
  </article>
</section>
<section class="grid two">
  <article>
    <h2>Capabilities</h2>
    {_json_block(test.capabilities or {})}
  </article>
  <article>
    <h2>Metadata</h2>
    {_json_block(test.metadata or {})}
  </article>
</section>
<section>
  <h2>Steps</h2>
  {_steps_view(test.steps)}
</section>
<section class="grid two">
  <article>
    <h2>Retries</h2>
    {_retry_table(test.retries)}
  </article>
  <article>
    <h2>Action Retries</h2>
    {_retry_table(action_retries)}
  </article>
</section>
<section>
  <h2>Artifacts</h2>
  {_artifacts_view(artifacts, page_dir, report_root)}
</section>
<section>
  <h2>Timeline</h2>
  {_timeline_table(timeline)}
</section>
""",
    )


def _render_timeline_page(report: RunReport, events: list[ReportingEvent]) -> str:
    return _page(
        "Timeline",
        f"""
<header class="hero compact"><div><p class="eyebrow">{_e(report.run_id)}</p><h1>Timeline</h1></div></header>
<nav class="tabs"><a href="index.html">Dashboard</a><a href="flaky.html">Flaky</a><a href="matrix.html">Matrix</a><a href="history.html">History</a></nav>
<section>{_timeline_table(events)}</section>
""",
    )


def _render_flaky_page(report: RunReport) -> str:
    return _page(
        "Flaky Analysis",
        f"""
<header class="hero compact"><div><p class="eyebrow">{_e(report.run_id)}</p><h1>Flaky Analysis</h1></div></header>
<nav class="tabs"><a href="index.html">Dashboard</a><a href="timeline.html">Timeline</a><a href="matrix.html">Matrix</a><a href="history.html">History</a></nav>
<section>{_analysis_table(flaky_analysis(report))}</section>
""",
    )


def _render_matrix_page(report: RunReport) -> str:
    summary = matrix_summary(report)
    sections = "\n".join(
        f"<article><h2>{_e(dimension)}</h2>{_matrix_table(values)}</article>" for dimension, values in summary.items()
    )
    return _page(
        "Matrix",
        f"""
<header class="hero compact"><div><p class="eyebrow">{_e(report.run_id)}</p><h1>Matrix</h1></div></header>
<nav class="tabs"><a href="index.html">Dashboard</a><a href="timeline.html">Timeline</a><a href="flaky.html">Flaky</a><a href="history.html">History</a></nav>
<section class="grid two">{sections or "<article>No matrix metadata found.</article>"}</section>
""",
    )


def _render_history_page(report: RunReport, history_entries: list[dict[str, Any]]) -> str:
    rows = "\n".join(
        f"<tr><td>{_e(entry.get('latest_run', ''))}</td><td>{_e(entry.get('run_id', ''))}</td>"
        f"<td>{entry.get('pass_rate', 0)}%</td><td>{entry.get('flaky', 0)}</td>"
        f"<td>{entry.get('failed', 0) + entry.get('broken', 0)}</td><td>{_format_duration(entry.get('duration_ms', 0))}</td></tr>"
        for entry in history_entries
    )
    return _page(
        "History",
        f"""
<header class="hero compact"><div><p class="eyebrow">{_e(report.run_id)}</p><h1>History</h1></div></header>
<nav class="tabs"><a href="index.html">Dashboard</a><a href="timeline.html">Timeline</a><a href="flaky.html">Flaky</a><a href="matrix.html">Matrix</a></nav>
<section>
  <h2>Pass Rate Trend</h2>
  {_trend_bars(trend_points(history_entries))}
</section>
<section>
  <h2>Runs</h2>
  <table><thead><tr><th>Run Time</th><th>Run ID</th><th>Pass Rate</th><th>Flaky</th><th>Failed</th><th>Duration</th></tr></thead><tbody>{rows or '<tr><td colspan="6">No history yet.</td></tr>'}</tbody></table>
</section>
""",
    )


def _page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_e(title)}</title>
  <style>
    :root {{ color-scheme: light; --ink:#172033; --muted:#5b6472; --line:#dde3ea; --panel:#ffffff; --bg:#f6f7f9; --accent:#0f766e; }}
    body {{ margin:0; font-family: Arial, sans-serif; color:var(--ink); background:var(--bg); }}
    .hero {{ background:#102033; color:#fff; padding:28px 36px; display:flex; justify-content:space-between; gap:18px; align-items:flex-start; }}
    .hero.compact {{ padding:22px 36px; }}
    h1 {{ margin:0 0 8px; font-size:30px; letter-spacing:0; }}
    h2 {{ margin:0 0 14px; font-size:18px; letter-spacing:0; }}
    p {{ margin:0; color:inherit; }}
    .eyebrow {{ color:#b7c7d7; font-size:12px; text-transform:uppercase; letter-spacing:0; margin-bottom:7px; }}
    .tabs {{ display:flex; gap:8px; flex-wrap:wrap; padding:14px 36px; background:#fff; border-bottom:1px solid var(--line); }}
    .tabs a {{ color:#0f5b99; font-weight:700; text-decoration:none; }}
    section {{ margin:24px 36px; }}
    article {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:16px; }}
    .metrics {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(130px,1fr)); gap:12px; }}
    .metric {{ background:#fff; border:1px solid var(--line); border-radius:8px; padding:14px; }}
    .metric strong {{ display:block; font-size:26px; margin-bottom:4px; }}
    .grid {{ display:grid; gap:16px; }}
    .grid.two {{ grid-template-columns:repeat(auto-fit,minmax(320px,1fr)); }}
    .grid.three {{ grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); }}
    table {{ border-collapse:collapse; width:100%; background:#fff; border:1px solid var(--line); }}
    th,td {{ border-bottom:1px solid #e9edf2; padding:10px; text-align:left; vertical-align:top; }}
    th {{ background:#eef2f6; }}
    pre {{ white-space:pre-wrap; overflow:auto; background:#f4f6f8; border:1px solid #e1e6ed; border-radius:6px; padding:10px; }}
    .status {{ display:inline-block; padding:5px 9px; border-radius:999px; font-size:12px; font-weight:700; text-transform:uppercase; }}
    .passed {{ color:#047857; background:#dff7ed; }}
    .failed,.broken {{ color:#b91c1c; background:#fee2e2; }}
    .skipped {{ color:#92400e; background:#fef3c7; }}
    .unknown {{ color:#4b5563; background:#e5e7eb; }}
    .bar {{ height:9px; background:#e5e7eb; border-radius:999px; overflow:hidden; min-width:90px; }}
    .bar span {{ display:block; height:100%; background:var(--accent); }}
    img.preview {{ max-width:100%; border:1px solid var(--line); border-radius:6px; }}
    video {{ max-width:100%; }}
    a {{ color:#0f5b99; }}
    .muted {{ color:var(--muted); }}
  </style>
  <script>
    function filterLog(input) {{
      const target = document.getElementById(input.dataset.target);
      if (!target) return;
      const query = input.value.toLowerCase();
      for (const line of target.querySelectorAll('[data-line]')) {{
        line.hidden = query && !line.textContent.toLowerCase().includes(query);
      }}
    }}
  </script>
</head>
<body>
{body}
</body>
</html>
"""


def _metric(label: str, value: Any) -> str:
    return f'<div class="metric"><strong>{_e(value)}</strong>{_e(label)}</div>'


def _test_row(test: TestCaseReport, href: str) -> str:
    profile = (
        test.profile or test.environment or test.metadata.get("browser") or test.metadata.get("device_name") or "-"
    )
    return (
        f'<tr><td><span class="status {test.status}">{_e(test.status)}</span></td>'
        f'<td><a href="{_e(href)}">{_e(test.name)}</a><br><span class="muted">{_e(test.full_name)}</span></td>'
        f"<td>{_e(profile)}</td>"
        f"<td>{_format_duration(test.duration_ms)}</td><td>{_e(_failure_cell(test))}</td></tr>"
    )


def _test_list(tests: list[TestCaseReport], details: dict[str, str]) -> str:
    if not tests:
        return "<p>No tests.</p>"
    items = "".join(
        f'<li><a href="{_e(details.get(test.id, "#"))}">{_e(test.name)}</a> · {_format_duration(test.duration_ms)}</li>'
        for test in tests
    )
    return f"<ul>{items}</ul>"


def _counter_list(counter: dict[str, int]) -> str:
    if not counter:
        return "<p>No failures.</p>"
    return "<ul>" + "".join(f"<li>{_e(key)}: {value}</li>" for key, value in counter.items()) + "</ul>"


def _failure_summary_list(report: RunReport) -> str:
    summaries: dict[str, dict[str, Any]] = {}
    for test in report.tests:
        if test.status not in {"failed", "broken"}:
            continue
        summary = failure_summary(test)
        bucket = summaries.setdefault(
            summary["category"],
            {"count": 0, "title": summary["title"], "detail": summary["detail"]},
        )
        bucket["count"] += 1
    if not summaries:
        return "<p>No failures.</p>"
    items = "".join(
        f"<li><strong>{_e(item['title'])}</strong>: {item['count']}"
        f'<br><span class="muted">{_e(item["detail"])}</span></li>'
        for item in summaries.values()
    )
    return f"<ul>{items}</ul>"


def _failure_reason(test: TestCaseReport) -> str:
    if test.status not in {"failed", "broken"} and not test.failure_message:
        return "<pre>No failure message.</pre>"
    summary = failure_summary(test)
    return (
        f"{_key_values({'Category': summary['category'], 'Probable Cause': summary['title'], 'Inspection Hint': summary['detail']})}"
        f"<pre>{_e(test.failure_message or 'No failure message.')}</pre>"
    )


def _failure_cell(test: TestCaseReport) -> str:
    if test.status not in {"failed", "broken"} and not test.failure_message:
        return ""
    summary = failure_summary(test)
    if test.failure_message:
        return f"{summary['title']} · {test.failure_message[:180]}"
    return summary["title"]


def _analysis_table(items: list[dict[str, Any]]) -> str:
    rows = "\n".join(
        f"<tr><td>{_e(item['category'])}</td><td>{_e(item['name'])}</td><td>{_e(item['status'])}</td>"
        f"<td>{_format_duration(item['duration_ms'])}</td><td>{_e(item['reason'])}</td></tr>"
        for item in items
    )
    empty_row = '<tr><td colspan="5">No flaky signals found.</td></tr>'
    return (
        "<table><thead><tr><th>Category</th><th>Test</th><th>Status</th><th>Duration</th><th>Reason</th></tr></thead>"
        f"<tbody>{rows or empty_row}</tbody></table>"
    )


def _timeline_table(events: list[ReportingEvent]) -> str:
    rows = "\n".join(
        f"<tr><td>{_e(event.timestamp.isoformat())}</td><td>{_e(event.event_type)}</td><td>{_e(event.test_name or '')}</td>"
        f"<td>{_e(event.title)}</td><td>{_e(event.status or '')}</td><td>{_format_duration(event.duration_ms or 0)}</td></tr>"
        for event in events
    )
    empty_row = '<tr><td colspan="6">No timeline events.</td></tr>'
    return (
        "<table><thead><tr><th>Time</th><th>Event</th><th>Test</th><th>Title</th><th>Status</th><th>Duration</th></tr></thead>"
        f"<tbody>{rows or empty_row}</tbody></table>"
    )


def _matrix_table(values: dict[str, dict[str, int]]) -> str:
    rows = "\n".join(
        f"<tr><td>{_e(name)}</td><td>{counts['total']}</td><td>{counts['passed']}</td>"
        f"<td>{counts['failed'] + counts['broken']}</td><td>{counts['skipped']}</td></tr>"
        for name, counts in values.items()
    )
    return (
        "<table><thead><tr><th>Name</th><th>Total</th><th>Passed</th><th>Failed</th><th>Skipped</th></tr></thead><tbody>"
        + rows
        + "</tbody></table>"
    )


def _steps_view(steps: list[StepRecord]) -> str:
    if not steps:
        return "<p>No steps captured.</p>"
    return "<ol>" + "".join(_step_item(step) for step in steps) + "</ol>"


def _step_item(step: StepRecord) -> str:
    children = "<ol>" + "".join(_step_item(child) for child in step.children) + "</ol>" if step.children else ""
    return (
        f'<li><span class="status {step.status}">{_e(step.status)}</span> {_e(step.name)} '
        f'<span class="muted">{_format_duration(step.duration_ms)}</span>{children}</li>'
    )


def _retry_table(retries: list[Any]) -> str:
    rows = "\n".join(
        f"<tr><td>{retry.attempt}</td><td>{_e(retry.retry_type)}</td><td>{_e(retry.action or '')}</td>"
        f"<td>{_e(retry.status)}</td><td>{_format_duration(retry.duration_ms)}</td><td>{_e(retry.reason)}</td></tr>"
        for retry in retries
    )
    empty_row = '<tr><td colspan="6">No retries.</td></tr>'
    return (
        "<table><thead><tr><th>Attempt</th><th>Type</th><th>Action</th><th>Status</th><th>Duration</th><th>Reason</th></tr></thead>"
        f"<tbody>{rows or empty_row}</tbody></table>"
    )


def _artifacts_view(artifacts: list[Artifact], page_dir: Path, report_root: Path) -> str:
    if not artifacts:
        return "<p>No artifacts captured.</p>"
    return "\n".join(
        _artifact_panel(artifact, page_dir, report_root, index) for index, artifact in enumerate(artifacts, start=1)
    )


def _artifact_panel(artifact: Artifact, page_dir: Path, report_root: Path, index: int) -> str:
    href = _artifact_href(artifact, page_dir, report_root)
    link = f'<p><a href="{_e(href)}">{_e(href)}</a></p>' if href else ""
    preview = _artifact_preview(artifact, href, page_dir, index)
    return f'<article><h3>{_e(artifact.name)} <span class="muted">{_e(artifact.artifact_type)}</span></h3>{link}{preview}</article>'


def _artifact_preview(artifact: Artifact, href: str, page_dir: Path, index: int) -> str:
    if artifact.artifact_type in IMAGE_ARTIFACT_TYPES and href:
        return f'<img class="preview" src="{_e(href)}" alt="{_e(artifact.name)}">'
    if artifact.artifact_type in VIDEO_ARTIFACT_TYPES and href:
        return f'<video controls src="{_e(href)}"></video>'
    if artifact.artifact_type in TEXT_ARTIFACT_TYPES:
        text = _read_artifact_text(artifact)
        if text is None:
            return ""
        log_id = f"log-{index}"
        lines = "".join(f"<span data-line>{_e(line)}</span>\n" for line in text.splitlines())
        return (
            f'<input data-target="{log_id}" oninput="filterLog(this)" placeholder="Search artifact">'
            f'<pre id="{log_id}">{lines}</pre>'
        )
    return _json_block(artifact.metadata) if artifact.metadata else ""


def _read_artifact_text(artifact: Artifact, *, max_bytes: int = 200_000) -> str | None:
    if not artifact.path:
        return None
    path = Path(artifact.path)
    if not path.exists() or not path.is_file() or path.stat().st_size > max_bytes:
        return None
    return path.read_text(encoding="utf-8", errors="replace")


def _artifact_href(artifact: Artifact, page_dir: Path, report_root: Path) -> str:
    if artifact.href:
        if _is_external_href(artifact.href):
            return artifact.href
        href_path = Path(artifact.href)
        if href_path.is_absolute():
            return href_path.as_uri() if href_path.exists() else str(href_path)
        return os.path.relpath(report_root / href_path, page_dir)
    if not artifact.path:
        return ""
    path = Path(artifact.path)
    if not path.is_absolute():
        return path.as_posix()
    if path.exists():
        try:
            return os.path.relpath(path, page_dir)
        except ValueError:
            return path.as_uri()
    return str(path)


def _is_external_href(href: str | None) -> bool:
    if not href:
        return False
    parsed = urlparse(href)
    return bool(parsed.scheme and parsed.scheme != "file")


def _trend_bars(points: list[dict[str, Any]]) -> str:
    if not points:
        return "<p>No history yet.</p>"
    rows = "".join(
        f'<tr><td>{_e(point["run_id"])}</td><td><div class="bar"><span style="width:{point["pass_rate"]}%"></span></div></td>'
        f"<td>{point['pass_rate']}%</td><td>{point['flaky']}</td><td>{point['failed']}</td></tr>"
        for point in points[-8:]
    )
    return (
        "<table><thead><tr><th>Run</th><th>Pass Rate</th><th>%</th><th>Flaky</th><th>Failed</th></tr></thead><tbody>"
        + rows
        + "</tbody></table>"
    )


def _key_values(values: dict[str, Any]) -> str:
    rows = "".join(f"<tr><th>{_e(key)}</th><td>{_e(value)}</td></tr>" for key, value in values.items())
    return f"<table>{rows}</table>"


def _test_context_values(test: TestCaseReport) -> dict[str, Any]:
    return {
        "Domain": test.domain or "-",
        "Profile": test.profile or "-",
        "Environment": test.environment or "-",
        "Browser": test.metadata.get("browser", "-"),
        "Device": test.metadata.get("device_name", "-"),
        "Platform": test.metadata.get("platform", "-"),
        "Status Code": test.metadata.get("status_code", "-"),
        "Latency": _format_duration(test.metadata.get("latency_ms", 0)) if test.metadata.get("latency_ms") else "-",
    }


def _json_block(value: Any) -> str:
    return f"<pre>{_e(json.dumps(to_jsonable(value), indent=2, default=str))}</pre>"


def _format_duration(duration_ms: float | int) -> str:
    seconds = round(float(duration_ms) / 1000, 2)
    if seconds < 60:
        return f"{seconds}s"
    minutes = int(seconds // 60)
    remaining = round(seconds % 60, 2)
    return f"{minutes}m {remaining}s"


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-").lower() or "test"


def _e(value: Any) -> str:
    return html.escape(str(value), quote=True)
