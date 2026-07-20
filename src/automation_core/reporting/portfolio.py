from __future__ import annotations

import html
import json
import os
import re
from datetime import datetime
from pathlib import Path
from shutil import move
from typing import Any

from automation_core.reporting import portfolio_render
from automation_core.reporting.design_system import report_design_styles
from automation_core.reporting.models import to_jsonable

RUNS_DIR = "runs"
PORTFOLIO_DATA_FILE = "portfolio-data.json"

PRODUCT_REPORT_ENTRIES = {
    "artifacts",
    "compare.html",
    "data",
    "executive.html",
    "explore.html",
    "exports",
    "flaky.html",
    "history.html",
    "index.html",
    "matrix.html",
    "print-summary.html",
    "quality.html",
    "report-data.json",
    "share.html",
    "tests",
    "timeline.html",
}


def prepare_timestamped_report_dir(
    output_dir: str | Path,
    *,
    run_id: str,
    generated_at: datetime | str | None = None,
) -> Path:
    """Create a retained run directory under the report portfolio root."""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    archive_legacy_report_if_needed(output_path)

    runs_dir = output_path / RUNS_DIR
    runs_dir.mkdir(parents=True, exist_ok=True)
    folder_name = _run_folder_name(run_id, generated_at)
    report_dir = _unique_child_dir(runs_dir, folder_name)
    report_dir.mkdir(parents=True, exist_ok=False)
    return report_dir


def archive_legacy_report_if_needed(output_dir: str | Path) -> Path | None:
    """Move a pre-portfolio report from the root into the retained runs folder."""

    output_path = Path(output_dir)
    report_data_path = output_path / "report-data.json"
    if not report_data_path.exists():
        return None

    report_data = _read_json(report_data_path) or {}
    summary = _summary_from_report_data(report_data)
    run_id = str(summary.get("run_id") or "legacy-report")
    generated_at = summary.get("latest_run") or _file_timestamp(report_data_path)

    runs_dir = output_path / RUNS_DIR
    runs_dir.mkdir(parents=True, exist_ok=True)
    archive_dir = _unique_child_dir(runs_dir, _run_folder_name(run_id, generated_at))
    archive_dir.mkdir(parents=True, exist_ok=False)

    for name in sorted(PRODUCT_REPORT_ENTRIES):
        source = output_path / name
        if source.exists():
            move(str(source), str(archive_dir / name))

    return archive_dir


def generate_report_portfolio(output_dir: str | Path, *, current_report_dir: str | Path | None = None) -> Path:
    """Write portfolio dashboard pages for all retained reports."""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    reports = collect_report_runs(output_path)
    portfolio_data = build_portfolio_data(reports, output_path, current_report_dir=current_report_dir)

    (output_path / PORTFOLIO_DATA_FILE).write_text(json.dumps(to_jsonable(portfolio_data), indent=2), encoding="utf-8")
    (output_path / "reports.html").write_text(portfolio_render.render_reports(portfolio_data), encoding="utf-8")
    (output_path / "compare.html").write_text(portfolio_render.render_compare(portfolio_data), encoding="utf-8")
    index_path = output_path / "index.html"
    index_path.write_text(portfolio_render.render_dashboard(portfolio_data), encoding="utf-8")
    return index_path


def collect_report_runs(output_dir: str | Path) -> list[dict[str, Any]]:
    output_path = Path(output_dir)
    runs_dir = output_path / RUNS_DIR
    if not runs_dir.exists():
        return []

    reports: list[dict[str, Any]] = []
    for report_data_path in sorted(runs_dir.glob("*/report-data.json")):
        report_data = _read_json(report_data_path)
        if not isinstance(report_data, dict):
            continue
        run_dir = report_data_path.parent
        reports.append(_report_entry(output_path, run_dir, report_data))

    return sorted(reports, key=lambda item: item.get("generated_at", ""), reverse=True)


def build_portfolio_data(
    reports: list[dict[str, Any]],
    output_dir: str | Path,
    *,
    current_report_dir: str | Path | None = None,
) -> dict[str, Any]:
    output_path = Path(output_dir)
    current_path = Path(current_report_dir).resolve() if current_report_dir else None
    current = ""
    if current_path is not None:
        for report in reports:
            if (output_path / report["run_dir"]).resolve() == current_path:
                current = report["run_dir"]
                break

    return {
        "generated_at": datetime.now().astimezone().isoformat(),
        "generated_display": _format_datetime(datetime.now().astimezone()),
        "current_run_dir": current,
        "summary": _portfolio_summary(reports),
        "filter_options": _filter_options(reports),
        "reports": reports,
    }


def _report_entry(output_path: Path, run_dir: Path, report_data: dict[str, Any]) -> dict[str, Any]:
    summary = _summary_from_report_data(report_data)
    charts = report_data.get("charts", {}) if isinstance(report_data.get("charts"), dict) else {}
    signals = report_data.get("signals", {}) if isinstance(report_data.get("signals"), dict) else {}
    quality = report_data.get("quality", {}) if isinstance(report_data.get("quality"), dict) else {}
    quality_score = report_data.get("quality_score", {}) if isinstance(report_data.get("quality_score"), dict) else {}
    risk_signal = report_data.get("risk_signal", {}) if isinstance(report_data.get("risk_signal"), dict) else {}
    transitions = (
        report_data.get("failure_transitions", {}) if isinstance(report_data.get("failure_transitions"), dict) else {}
    )
    transition_counts = transitions.get("counts", {}) if isinstance(transitions.get("counts"), dict) else {}
    compare = report_data.get("compare", {}) if isinstance(report_data.get("compare"), dict) else {}
    stability = report_data.get("stability", {}) if isinstance(report_data.get("stability"), dict) else {}
    recovery = report_data.get("recovery", {}) if isinstance(report_data.get("recovery"), dict) else {}
    resource = (
        report_data.get("resource_efficiency", {}) if isinstance(report_data.get("resource_efficiency"), dict) else {}
    )
    health = report_data.get("run", {}).get("health", {}) if isinstance(report_data.get("run"), dict) else {}
    platforms = report_data.get("platforms", {}) if isinstance(report_data.get("platforms"), dict) else {}
    gate = report_data.get("default_gate_status", {}) if isinstance(report_data.get("default_gate_status"), dict) else {}
    failed_total = _blocking_failure_count(summary)
    run_dir_href = os.path.relpath(run_dir, output_path)
    generated_at = str(summary.get("latest_run") or "")
    entry = {
        "run_id": summary.get("run_id", ""),
        "project_name": summary.get("project_name", ""),
        "framework": summary.get("framework", ""),
        "status": summary.get("status", "unknown"),
        "generated_at": generated_at,
        "generated_display": _format_datetime(generated_at),
        "run_dir": run_dir_href,
        "entry_href": f"{run_dir_href}/index.html",
        "executive_href": f"{run_dir_href}/executive.html",
        "compare_href": f"{run_dir_href}/compare.html",
        "tests_href": f"{run_dir_href}/explore.html",
        "share_href": f"{run_dir_href}/share.html",
        "total": int(summary.get("total", 0) or 0),
        "passed": int(summary.get("passed", 0) or 0),
        "failed": int(summary.get("failed", 0) or 0),
        "broken": int(summary.get("broken", 0) or 0),
        "error": int(summary.get("error", 0) or 0),
        "blocking_failures": failed_total,
        "failed_total": failed_total,
        "skipped": int(summary.get("skipped", 0) or 0),
        "flaky": int(summary.get("flaky", 0) or 0),
        "pass_rate": float(summary.get("pass_rate", 0) or 0),
        "duration_ms": float(summary.get("duration_ms", 0) or 0),
        "duration_display": _format_duration(summary.get("duration_ms", 0) or 0),
        "profiles": summary.get("profiles", []),
        "environments": summary.get("environments", []),
        "browsers": summary.get("browsers", []),
        "devices": summary.get("devices", []),
        "quality_status": quality.get("status", "not_configured") if quality.get("configured") else "not_configured",
        "quality_configured": bool(quality.get("configured")),
        "quality_message": quality.get("message", ""),
        "quality_score": quality_score.get("score"),
        "quality_grade": quality_score.get("grade", "n/a"),
        "quality_score_status": quality_score.get("status", "unknown"),
        "risk_level": risk_signal.get("level", "low"),
        "risk_summary": risk_signal.get("summary", ""),
        "risk_count": len(report_data.get("risk_signals", []) or []),
        "new_failure_count": int(transition_counts.get("new", 0) or 0),
        "known_failure_count": int(transition_counts.get("known", 0) or 0),
        "resolved_failure_count": int(transition_counts.get("resolved", 0) or 0),
        "compare_previous_run_id": compare.get("previous_run_id", ""),
        "compare_metrics": compare.get("metrics", []),
        "stability_status": stability.get("status", "not_available"),
        "stability_score": stability.get("score"),
        "recovery_status": recovery.get("status", "not_available"),
        "mean_recovery_ms": recovery.get("mean_recovery_ms"),
        "resource_status": resource.get("status", "not_available"),
        "resource_efficiency_percent": resource.get("efficiency_percent"),
        "artifact_count": int(signals.get("artifact_count", 0) or 0),
        "test_retry_count": int(signals.get("test_retry_count", 0) or 0),
        "action_retry_count": int(signals.get("action_retry_count", 0) or 0),
        "healing_event_count": int(signals.get("healing_event_count", 0) or 0),
        "failure_categories": charts.get("failure_categories", {}),
        "status_distribution": charts.get("status_distribution", {}),
        "duration_buckets": charts.get("duration_buckets", {}),
        "pass_rate_delta": health.get("pass_rate_delta"),
        "failed_delta": health.get("failed_delta"),
        "flaky_delta": health.get("flaky_delta"),
        "duration_delta_ms": health.get("duration_delta_ms"),
        "platforms": platforms,
        "platform_names": [name.capitalize() for name in platforms],
    }
    gate_passed = str(gate.get("status", "")).lower() == "passed"
    entry["readiness"] = "ready" if gate_passed else "blocked"
    entry["readiness_label"] = "Ready" if gate_passed else "Blocked"
    entry["search_text"] = _search_text(entry)
    return entry


def _portfolio_summary(reports: list[dict[str, Any]]) -> dict[str, Any]:
    latest = reports[0] if reports else {}
    failing_runs = [report for report in reports if report.get("failed_total", 0)]
    flaky_runs = [report for report in reports if report.get("flaky", 0)]
    return {
        "total_reports": len(reports),
        "projects": sorted({str(report.get("project_name")) for report in reports if report.get("project_name")}),
        "frameworks": sorted({str(report.get("framework")) for report in reports if report.get("framework")}),
        "latest_run_id": latest.get("run_id", ""),
        "latest_generated": latest.get("generated_display", ""),
        "latest_pass_rate": latest.get("pass_rate", 0),
        "latest_quality_score": latest.get("quality_score"),
        "latest_risk_level": latest.get("risk_level", "low"),
        "latest_status": latest.get("status", "unknown"),
        "failing_runs": len(failing_runs),
        "flaky_runs": len(flaky_runs),
        "high_risk_runs": sum(1 for report in reports if report.get("risk_level") == "high"),
        "medium_risk_runs": sum(1 for report in reports if report.get("risk_level") == "medium"),
        "new_failures": sum(int(report.get("new_failure_count", 0) or 0) for report in reports),
        "resolved_failures": sum(int(report.get("resolved_failure_count", 0) or 0) for report in reports),
        "total_tests": sum(int(report.get("total", 0) or 0) for report in reports),
        "total_failed": sum(int(report.get("failed_total", 0) or 0) for report in reports),
        "total_flaky": sum(int(report.get("flaky", 0) or 0) for report in reports),
        "total_duration_ms": sum(float(report.get("duration_ms", 0) or 0) for report in reports),
    }


def _filter_options(reports: list[dict[str, Any]]) -> dict[str, list[str]]:
    return {
        "project_name": _sorted_options(report.get("project_name") for report in reports),
        "framework": _sorted_options(report.get("framework") for report in reports),
        "status": _sorted_options(report.get("status") for report in reports),
        "quality_status": _sorted_options(report.get("quality_status") for report in reports),
        "risk_level": _sorted_options(report.get("risk_level") for report in reports),
    }


def _render_dashboard_page(data: dict[str, Any]) -> str:
    return _page(
        "Portfolio Dashboard",
        f"""
<header class="hero">
  <div>
    <p class="eyebrow">Report portfolio</p>
    <h1>Portfolio Dashboard</h1>
    <p>History and health across every retained run — web, mobile, and API.</p>
  </div>
  <div class="hero-actions">
    <a class="button inverse" href="reports.html">Browse Reports</a>
  </div>
</header>
{_portfolio_nav("dashboard")}
{_portfolio_toolbar("portfolio")}
{_portfolio_hero(data)}
<section class="metrics" id="portfolio-metrics"></section>
<section class="grid two">
  <article><h2>Pass Rate Trend</h2><div id="portfolio-pass-trend"></div></article>
  <article><h2>Run Outcomes</h2><div id="portfolio-status-chart"></div></article>
</section>
<section class="grid two">
  <article><h2>Quality Score Trend</h2><div id="portfolio-quality-chart"></div></article>
  <article><h2>Risk Levels</h2><div id="portfolio-risk-chart"></div></article>
</section>
<section class="grid two">
  <article><h2>Failure Categories</h2><div id="portfolio-failure-chart"></div></article>
  <article><h2>Framework Health</h2><div id="portfolio-framework-chart"></div></article>
</section>
<section class="grid two">
  <article><h2>Runs Needing Attention</h2><div id="portfolio-attention"></div></article>
  <article><h2>Coverage Footprint</h2><div id="portfolio-coverage"></div></article>
</section>
<script type="application/json" id="portfolio-data-json">{_json_for_script(data)}</script>
""",
        "dashboard",
    )


def _portfolio_hero(data: dict[str, Any]) -> str:
    summary = data.get("summary", {})
    total = int(summary.get("total_reports", 0) or 0)
    blocked = int(summary.get("failing_runs", 0) or 0)
    ready = max(total - blocked, 0)
    latest_pass_rate = float(summary.get("latest_pass_rate", 0) or 0)
    quality = summary.get("latest_quality_score")
    health = int(quality if isinstance(quality, (int, float)) else round(latest_pass_rate))
    status = "failed" if blocked else "passed"
    ring_color = "var(--fail)" if blocked else "var(--pass)"
    status_text = f"{blocked} Runs Blocked" if blocked else "All Runs Ready"
    sentence = (
        f"{blocked} of {total} retained run(s) need attention before release."
        if blocked
        else f"All {total} retained run(s) are currently release-ready."
    )
    return f"""
<section class="grid two overview-hero">
  <article class="health-card">
    <div class="health-card-main">
      <div class="score-ring status-{_e(status)}" style="background:conic-gradient({ring_color} 0 {health:g}%, var(--surfaceAlt) {health:g}% 100%)">
        <strong>{health}</strong>
        <span>Health</span>
      </div>
      <div>
        <span class="status {status}">{_e(status_text)}</span>
        <p class="muted">{_e(sentence)}</p>
      </div>
    </div>
    {_portfolio_status_segments(ready, blocked)}
  </article>
  <article class="pass-card">
    <div class="card-label">Latest Pass Rate</div>
    <div class="hero-number">{latest_pass_rate:g}%</div>
    {_portfolio_sparkline(data.get("reports", []), latest_pass_rate)}
    <div class="mini-stat-row">
      <span><strong>{total}</strong>Runs</span>
      <span class="failed-stat"><strong>{blocked}</strong>Blocked</span>
      <span class="flaky-stat"><strong>{summary.get("total_flaky", 0)}</strong>Flaky</span>
      <span><strong>{_e(_format_duration(summary.get("total_duration_ms", 0)))}</strong>Duration</span>
    </div>
  </article>
</section>
<section class="grid two insight-pair">
  <article class="insight-card key-wins">
    <h2>Key Wins</h2>
    <ul>{"".join(f"<li>{_e(item)}</li>" for item in _portfolio_wins(summary))}</ul>
  </article>
  <article class="insight-card focus-areas">
    <h2>Focus Areas</h2>
    <ul>{"".join(f"<li>{_e(item)}</li>" for item in _portfolio_focus(summary))}</ul>
  </article>
</section>
"""


def _portfolio_status_segments(ready: int, blocked: int) -> str:
    total = ready + blocked
    if not total:
        return '<p class="empty-state">No retained runs yet.</p>'
    ready_width = (ready / total) * 100 if ready else 0
    blocked_width = (blocked / total) * 100 if blocked else 0
    segments = (f'<span class="segment segment-passed" style="width:{ready_width:.3f}%"></span>' if ready else "") + (
        f'<span class="segment segment-failed" style="width:{blocked_width:.3f}%"></span>' if blocked else ""
    )
    return (
        f'<div class="status-segments">{segments}</div>'
        f'<div class="legend segment-legend"><span><i class="swatch segment-passed"></i>Ready {ready}</span>'
        f'<span><i class="swatch segment-failed"></i>Blocked {blocked}</span></div>'
    )


def _portfolio_sparkline(reports: list[dict[str, Any]], fallback: float) -> str:
    series = [float(report.get("pass_rate", 0) or 0) for report in reversed(reports[:8])]
    if not series:
        series = [fallback]
    width = 260
    height = 58
    if len(series) == 1:
        x_values = [width / 2]
    else:
        x_values = [(index / (len(series) - 1)) * (width - 24) + 12 for index in range(len(series))]
    y_values = [height - 8 - (value / 100) * (height - 16) for value in series]
    path = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(x_values, y_values, strict=False))
    return (
        f'<svg class="mini-sparkline" viewBox="0 0 {width} {height}" role="img" aria-label="Latest pass-rate trend">'
        f'<polyline points="{path}" fill="none" stroke="var(--pass)" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>'
        "</svg>"
    )


def _portfolio_wins(summary: dict[str, Any]) -> list[str]:
    wins: list[str] = []
    ready = int(summary.get("total_reports", 0) or 0) - int(summary.get("failing_runs", 0) or 0)
    if ready > 0:
        wins.append(f"{ready} retained run(s) are release-ready.")
    if int(summary.get("resolved_failures", 0) or 0):
        wins.append(f"{summary.get('resolved_failures')} failure(s) resolved across retained runs.")
    if int(summary.get("total_tests", 0) or 0):
        wins.append(f"{summary.get('total_tests')} total test result(s) are indexed for traceability.")
    return wins or ["No retained run has produced a positive release signal yet."]


def _portfolio_focus(summary: dict[str, Any]) -> list[str]:
    focus: list[str] = []
    if int(summary.get("failing_runs", 0) or 0):
        focus.append(f"{summary.get('failing_runs')} run(s) are blocked by failures.")
    if int(summary.get("total_flaky", 0) or 0):
        focus.append(f"{summary.get('total_flaky')} flaky test signal(s) need review.")
    if int(summary.get("high_risk_runs", 0) or 0):
        focus.append(f"{summary.get('high_risk_runs')} run(s) are marked high risk.")
    if int(summary.get("new_failures", 0) or 0):
        focus.append(f"{summary.get('new_failures')} new failure(s) appeared across retained runs.")
    return focus or ["No retained runs currently need attention."]


def _render_reports_page(data: dict[str, Any]) -> str:
    return _page(
        "Reports",
        f"""
<header class="hero compact">
  <div>
    <p class="eyebrow">Retained runs</p>
    <h1>Reports</h1>
    <p>Choose a saved report and open the exact run details, executive view, tests, or share package.</p>
  </div>
</header>
{_portfolio_nav("reports")}
{_portfolio_toolbar("gallery")}
<section class="result-strip">
  <strong id="gallery-count">0 reports</strong>
  <label>View
    <select id="gallery-view">
      <option value="cards">Cards</option>
      <option value="table">Table</option>
    </select>
  </label>
</section>
<section id="report-gallery" class="report-card-grid"></section>
<script type="application/json" id="portfolio-data-json">{_json_for_script(data)}</script>
""",
        "reports",
    )


def _render_compare_page(data: dict[str, Any]) -> str:
    return _page(
        "Compare Reports",
        f"""
<header class="hero compact">
  <div>
    <p class="eyebrow">Report portfolio</p>
    <h1>Compare Reports</h1>
    <p>Select retained runs and compare release signals side by side.</p>
  </div>
</header>
{_portfolio_nav("compare")}
<section class="toolbar compare-toolbar">
  <label>Baseline
    <select id="compare-baseline"></select>
  </label>
  <label>Compare With
    <select id="compare-target"></select>
  </label>
  <button type="button" id="compare-latest">Latest Pair</button>
</section>
<section class="result-strip">
  <strong id="compare-selection-count">0 selected</strong>
  <span class="muted">Deltas use the baseline run as the reference.</span>
</section>
<section id="portfolio-compare-cards" class="report-card-grid"></section>
<section class="grid three">
  <article><h2>Pass Rate</h2><div id="compare-pass-rate"></div></article>
  <article><h2>Duration</h2><div id="compare-duration"></div></article>
  <article><h2>Failures</h2><div id="compare-failures"></div></article>
</section>
<section>
  <article><h2>Deltas vs Baseline</h2><div id="compare-deltas" class="table-wrap wide"></div></article>
</section>
<section>
  <article><h2>Feature Impact Across Selected Runs</h2><div id="compare-impact"></div></article>
</section>
<script type="application/json" id="portfolio-data-json">{_json_for_script(data)}</script>
""",
        "compare",
    )


def _portfolio_toolbar(scope: str) -> str:
    return f"""
<section class="toolbar" data-portfolio-scope="{_e(scope)}">
  <label class="search-box">Search
    <input type="search" data-portfolio-search placeholder="Run id, project, framework, status, profile, environment">
  </label>
  <label>Project
    <select data-portfolio-filter="project_name"><option value="">All</option></select>
  </label>
  <label>Framework
    <select data-portfolio-filter="framework"><option value="">All</option></select>
  </label>
  <label>Status
    <select data-portfolio-filter="status"><option value="">All</option></select>
  </label>
  <label>Quality
    <select data-portfolio-filter="quality_status"><option value="">All</option></select>
  </label>
  <label>Risk
    <select data-portfolio-filter="risk_level"><option value="">All</option></select>
  </label>
  <button type="button" data-portfolio-reset>Reset</button>
</section>
"""


def _portfolio_nav(active: str) -> str:
    links = (
        ("dashboard", "Portfolio", "index.html"),
        ("reports", "Reports", "reports.html"),
        ("compare", "Compare", "compare.html"),
    )
    return (
        '<div class="nav-shell" data-nav-shell>'
        '<button type="button" class="mobile-nav-toggle" data-nav-toggle '
        'aria-controls="portfolio-navigation" aria-expanded="false">Menu</button>'
        '<nav class="app-nav" id="portfolio-navigation" aria-label="Report portfolio navigation">'
        '<a class="nav-brand" href="index.html"><span class="nav-logo">A</span>'
        "<span><strong>Automation Core</strong><small>Report Portfolio</small></span></a>"
        + "".join(
            f'<a class="{"active" if key == active else ""}" href="{href}">{label}</a>' for key, label, href in links
        )
        + _theme_controls()
        + "</nav></div>"
    )


def _page(title: str, body: str, page_kind: str) -> str:
    return f"""<!doctype html>
<html lang="en" data-theme="system">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_e(title)}</title>
  <script>{_theme_bootstrap_script()}</script>
  <style>{report_design_styles()}</style>
  <script>{_portfolio_script(page_kind)}</script>
</head>
<body data-visual-system="enterprise-redesign" data-theme-default="system">
{body}
</body>
</html>
"""


def _theme_bootstrap_script() -> str:
    return """(function() {
  try {
    var mode = localStorage.getItem('automation-report-theme') || 'system';
    if (!/^(system|light|dark)$/.test(mode)) mode = 'system';
    document.documentElement.dataset.theme = mode;
  } catch (error) {
    document.documentElement.dataset.theme = 'system';
  }
})();"""


def _theme_controls() -> str:
    return (
        '<div class="theme-panel" aria-label="Appearance">'
        '<span class="theme-label">Appearance</span>'
        '<div class="theme-options" role="group" aria-label="Appearance theme">'
        '<button type="button" data-theme-choice="system" aria-pressed="true" class="active">System</button>'
        '<button type="button" data-theme-choice="light" aria-pressed="false">Light</button>'
        '<button type="button" data-theme-choice="dark" aria-pressed="false">Dark</button>'
        "</div></div>"
    )


def _portfolio_script(page_kind: str) -> str:
    return f"""
function setupTheme() {{
  const allowed = new Set(['system', 'light', 'dark']);
  const storageKey = 'automation-report-theme';
  const saved = (() => {{
    try {{ return localStorage.getItem(storageKey) || 'system'; }}
    catch (error) {{ return 'system'; }}
  }})();
  const apply = (mode) => {{
    const theme = allowed.has(mode) ? mode : 'system';
    document.documentElement.dataset.theme = theme;
    document.body.dataset.theme = theme;
    document.querySelectorAll('[data-theme-choice]').forEach((button) => {{
      const active = button.dataset.themeChoice === theme;
      button.classList.toggle('active', active);
      button.setAttribute('aria-pressed', active ? 'true' : 'false');
    }});
    try {{ localStorage.setItem(storageKey, theme); }} catch (error) {{}}
  }};
  document.querySelectorAll('[data-theme-choice]').forEach((button) => {{
    button.addEventListener('click', () => apply(button.dataset.themeChoice));
  }});
  apply(saved);
}}
function setupNavigation() {{
  const shell = document.querySelector('[data-nav-shell]');
  if (!shell) return;
  const toggle = shell.querySelector('[data-nav-toggle]');
  const setOpen = (open) => {{
    shell.classList.toggle('open', open);
    if (toggle) toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
  }};
  if (toggle) toggle.addEventListener('click', () => setOpen(!shell.classList.contains('open')));
  shell.querySelectorAll('.app-nav a').forEach((link) => {{
    link.addEventListener('click', () => {{
      if (window.matchMedia('(max-width: 900px)').matches) setOpen(false);
    }});
  }});
  window.addEventListener('keydown', (event) => {{
    if (event.key === 'Escape') setOpen(false);
  }});
  window.matchMedia('(min-width: 901px)').addEventListener('change', () => setOpen(false));
}}
function portfolioData() {{
  const node = document.getElementById('portfolio-data-json');
  return node ? JSON.parse(node.textContent) : {{reports: [], filter_options: {{}}}};
}}
function escapeHtml(value) {{
  const text = value === null || value === undefined ? '' : String(value);
  return text.replace(/[&<>"']/g, (char) => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[char]));
}}
function escapeAttr(value) {{
  return escapeHtml(value);
}}
function classToken(value, fallback = 'unknown') {{
  const token = String(value || fallback).toLowerCase().replace(/[^a-z0-9_-]+/g, '_');
  return token || fallback;
}}
function safeHref(value, fallback = '#') {{
  const text = value === null || value === undefined ? '' : String(value).trim();
  if (!text || /^(javascript|data|vbscript):/i.test(text) || /[\\u000d\\u000a]/.test(text)) return fallback;
  return escapeAttr(text);
}}
function num(value, fallback = 0) {{
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}}
function optionLabel(value) {{ return escapeHtml(value || '-'); }}
function populateFilters(data) {{
  document.querySelectorAll('[data-portfolio-filter]').forEach((select) => {{
    const field = select.dataset.portfolioFilter;
    const selected = select.value;
    select.innerHTML = '<option value="">All</option>' + (data.filter_options[field] || []).map((value) => `<option value="${{escapeAttr(value)}}">${{optionLabel(value)}}</option>`).join('');
    select.value = selected;
  }});
}}
function filteredReports(data) {{
  const query = (document.querySelector('[data-portfolio-search]')?.value || '').toLowerCase();
  const filters = Array.from(document.querySelectorAll('[data-portfolio-filter]'));
  return (data.reports || []).filter((report) => {{
    const queryMatch = !query || (report.search_text || '').includes(query);
    const filterMatch = filters.every((select) => !select.value || String(report[select.dataset.portfolioFilter] || '') === select.value);
    return queryMatch && filterMatch;
  }});
}}
function metric(label, value) {{
  return `<div class="metric"><strong>${{escapeHtml(value)}}</strong>${{escapeHtml(label)}}</div>`;
}}
function statusClass(status) {{ return classToken(status); }}
function sum(items, field) {{ return items.reduce((total, item) => total + Number(item[field] || 0), 0); }}
function countBy(items, field) {{
  return items.reduce((acc, item) => {{
    const value = item[field] || 'unknown';
    acc[value] = (acc[value] || 0) + 1;
    return acc;
  }}, {{}});
}}
function mergeCounters(items, field) {{
  return items.reduce((acc, item) => {{
    Object.entries(item[field] || {{}}).forEach(([key, value]) => {{
      acc[key] = (acc[key] || 0) + Number(value || 0);
    }});
    return acc;
  }}, {{}});
}}
function barChart(values, empty = 'No data.') {{
  const entries = Object.entries(values).filter(([, value]) => Number(value || 0));
  if (!entries.length) return `<p class="empty-state">${{escapeHtml(empty)}}</p>`;
  const max = Math.max(...entries.map(([, value]) => Number(value || 0)), 1);
  return entries.sort((a, b) => b[1] - a[1]).slice(0, 12).map(([key, value]) => `<div class="hbar-row"><div class="hbar-label" title="${{escapeAttr(key)}}">${{escapeHtml(key)}}</div><div class="hbar-track"><span class="hbar-fill" style="width:${{Math.max(4, Math.round((num(value) / max) * 100))}}%"></span></div><strong>${{escapeHtml(value)}}</strong></div>`).join('');
}}
function trendChart(items) {{
  const reports = [...items].reverse().slice(-14);
  if (!reports.length) return '<p class="empty-state">No retained runs yet.</p>';
  const width = 640, height = 190;
  const x = reports.length === 1 ? [width / 2] : reports.map((_, index) => 30 + index * ((width - 60) / (reports.length - 1)));
  const y = reports.map((report) => height - 32 - (Number(report.pass_rate || 0) / 100) * (height - 64));
  const points = x.map((value, index) => `${{value.toFixed(1)}},${{y[index].toFixed(1)}}`).join(' ');
  const dots = reports.map((report, index) => `<circle cx="${{x[index].toFixed(1)}}" cy="${{y[index].toFixed(1)}}" r="4"><title>${{escapeHtml(report.run_id)}}: ${{escapeHtml(report.pass_rate)}}%</title></circle>`).join('');
  const labelStep = Math.max(1, Math.floor(reports.length / 6));
  const labels = reports.map((report, index) => {{
    if (index % labelStep !== 0 && index !== reports.length - 1) return '';
    return `<text x="${{x[index].toFixed(1)}}" y="${{height - 8}}" text-anchor="middle" font-size="10">${{escapeHtml(String(report.run_id || '').slice(0, 8))}}</text>`;
  }}).join('');
  return `<svg viewBox="0 0 ${{width}} ${{height}}" role="img" aria-label="Pass rate trend"><line x1="30" y1="18" x2="30" y2="${{height - 32}}" stroke="#cbd5e1"/><line x1="30" y1="${{height - 32}}" x2="${{width - 30}}" y2="${{height - 32}}" stroke="#cbd5e1"/><polyline points="${{points}}" fill="none" stroke="#0f766e" stroke-width="3"/><g fill="#0f766e">${{dots}}</g><g fill="#64748b">${{labels}}</g></svg>`;
}}
function renderDashboard() {{
  const data = portfolioData();
  populateFilters(data);
  const items = filteredReports(data);
  const latest = items[0] || {{}};
  const metrics = document.getElementById('portfolio-metrics');
  if (metrics) metrics.innerHTML = [
    metric('Reports', items.length),
    metric('Latest Pass Rate', latest.pass_rate !== undefined ? `${{latest.pass_rate}}%` : '-'),
    metric('Latest Quality', qualityScore(latest)),
    metric('Risk', latest.risk_level || '-'),
    metric('Failing Runs', items.filter((item) => item.failed_total).length),
    metric('Flaky Tests', sum(items, 'flaky')),
    metric('Total Tests', sum(items, 'total')),
    metric('Duration', formatDuration(sum(items, 'duration_ms')))
  ].join('');
  setHtml('portfolio-pass-trend', trendChart(items));
  setHtml('portfolio-status-chart', barChart(countBy(items, 'status'), 'No runs match the filters.'));
  setHtml('portfolio-quality-chart', qualityTrend(items));
  setHtml('portfolio-risk-chart', barChart(countBy(items, 'risk_level'), 'No risk signal data.'));
  setHtml('portfolio-failure-chart', barChart(mergeCounters(items, 'failure_categories'), 'No failures in the filtered runs.'));
  setHtml('portfolio-framework-chart', frameworkHealth(items));
  setHtml('portfolio-attention', attentionList(items));
  setHtml('portfolio-coverage', coverageCloud(items));
}}
function frameworkHealth(items) {{
  const groups = {{}};
  items.forEach((item) => {{
    const key = item.framework || 'unknown';
    groups[key] = groups[key] || {{runs: 0, failed: 0, tests: 0, passRate: 0}};
    groups[key].runs += 1;
    groups[key].failed += Number(item.failed_total || 0);
    groups[key].tests += Number(item.total || 0);
    groups[key].passRate += Number(item.pass_rate || 0);
  }});
  const rows = Object.entries(groups).map(([name, value]) => [name, Math.round(value.passRate / Math.max(value.runs, 1)), value]);
  return barChart(Object.fromEntries(rows.map(([name, passRate]) => [name, passRate])), 'No framework data.') + rows.map(([name, passRate, value]) => `<p class="muted">${{escapeHtml(name)}}: ${{num(value.runs)}} runs, ${{num(value.tests)}} tests, ${{num(value.failed)}} failed, avg ${{escapeHtml(passRate)}}%</p>`).join('');
}}
function attentionList(items) {{
  const attention = items.filter((item) => item.failed_total || item.flaky || item.quality_status === 'failed' || item.risk_level === 'high').slice(0, 8);
  if (!attention.length) return '<p class="empty-state">No failing, flaky, or failed-quality runs in the filtered set.</p>';
  return `<div class="attention-list">${{attention.map((item) => `<div class="attention-item"><strong><a href="${{safeHref(item.entry_href)}}">${{escapeHtml(item.run_id)}}</a></strong><br><span class="muted">${{escapeHtml(item.generated_display)}} · ${{escapeHtml(item.framework || '-')}}</span><p>${{num(item.failed_total)}} failed · ${{num(item.flaky)}} flaky · ${{escapeHtml(item.pass_rate)}}% pass rate · ${{escapeHtml(item.risk_level || 'low')}} risk</p></div>`).join('')}}</div>`;
}}
function coverageCloud(items) {{
  const tags = new Map();
  items.forEach((item) => {{
    ['project_name','framework'].forEach((field) => {{ if (item[field]) tags.set(`${{field}}:${{item[field]}}`, item[field]); }});
    [...(item.profiles || []), ...(item.environments || []), ...(item.browsers || []), ...(item.devices || [])].forEach((value) => tags.set(value, value));
  }});
  if (!tags.size) return '<p class="empty-state">No project, framework, profile, environment, browser, or device metadata found.</p>';
  return `<div class="tag-cloud">${{Array.from(tags.values()).slice(0, 40).map((value) => `<span class="tag">${{escapeHtml(value)}}</span>`).join('')}}</div>`;
}}
function hydrateResponsiveTables(scope = document) {{
  scope.querySelectorAll('.table-wrap.wide table').forEach((table) => {{
    const headers = Array.from(table.querySelectorAll('thead th')).map((header) => header.textContent.trim());
    table.querySelectorAll('tbody tr').forEach((row) => {{
      Array.from(row.children).forEach((cell, index) => {{
        if (cell.tagName === 'TD' && !cell.dataset.label) cell.dataset.label = headers[index] || '';
      }});
    }});
  }});
}}
function renderGallery() {{
  const data = portfolioData();
  populateFilters(data);
  const items = filteredReports(data);
  const count = document.getElementById('gallery-count');
  if (count) count.textContent = `${{items.length}} reports`;
  const root = document.getElementById('report-gallery');
  if (!root) return;
  const view = document.getElementById('gallery-view')?.value || 'cards';
  if (view === 'table') {{
    root.className = 'table-wrap wide';
    root.innerHTML = `<table><thead><tr><th>Status</th><th>Run</th><th>Framework</th><th>Generated</th><th>Tests</th><th>Pass Rate</th><th>Quality</th><th>Signals</th><th>Open</th></tr></thead><tbody>${{items.map(reportTableRow).join('') || '<tr><td colspan="9">No reports match the filters.</td></tr>'}}</tbody></table>`;
    hydrateResponsiveTables(root);
    return;
  }}
  root.className = 'report-card-grid';
  root.innerHTML = items.map(reportCard).join('') || '<p class="empty-state">No reports match the filters.</p>';
}}
function setupCompareOptions(data) {{
  const reports = data.reports || [];
  const options = reports.map((item, index) => `<option value="${{index}}">${{escapeHtml(item.run_id || item.generated_display || `Run ${{index + 1}}`)}}</option>`).join('');
  const baseline = document.getElementById('compare-baseline');
  const target = document.getElementById('compare-target');
  if (!baseline || !target) return;
  if (!baseline.dataset.ready) {{
    baseline.innerHTML = options;
    target.innerHTML = options;
    baseline.value = reports.length > 1 ? '1' : '0';
    target.value = '0';
    baseline.dataset.ready = 'true';
    target.dataset.ready = 'true';
  }}
}}
function selectedCompareReports(data) {{
  const reports = data.reports || [];
  const baselineIndex = Number(document.getElementById('compare-baseline')?.value || 0);
  const targetIndex = Number(document.getElementById('compare-target')?.value || 0);
  const selected = [reports[baselineIndex], reports[targetIndex]].filter(Boolean);
  return selected.filter((item, index) => selected.findIndex((candidate) => candidate.run_dir === item.run_dir) === index);
}}
function renderCompare() {{
  const data = portfolioData();
  setupCompareOptions(data);
  const selected = selectedCompareReports(data);
  const count = document.getElementById('compare-selection-count');
  if (count) count.textContent = `${{selected.length}} selected`;
  setHtml('portfolio-compare-cards', selected.map(reportCard).join('') || '<p class="empty-state">No retained runs available.</p>');
  setHtml('compare-pass-rate', barChart(Object.fromEntries(selected.map((item) => [item.run_id, item.pass_rate])), 'No pass-rate data.'));
  setHtml('compare-duration', barChart(Object.fromEntries(selected.map((item) => [item.run_id, Math.round(num(item.duration_ms) / 1000)])), 'No duration data.'));
  setHtml('compare-failures', barChart(Object.fromEntries(selected.map((item) => [item.run_id, item.failed_total])), 'No failures in selected runs.'));
  setHtml('compare-deltas', compareDeltaTable(selected));
  setHtml('compare-impact', compareImpact(selected));
  hydrateResponsiveTables(document.getElementById('compare-deltas') || document);
}}
function compareDeltaTable(selected) {{
  if (selected.length < 2) return '<p class="empty-state">Select two retained runs to calculate deltas.</p>';
  const baseline = selected[0];
  const target = selected[1];
  const rows = [
    ['Pass Rate', `${{target.pass_rate}}%`, `${{baseline.pass_rate}}%`, deltaLabel(num(target.pass_rate) - num(baseline.pass_rate), '%')],
    ['Failures', target.failed_total, baseline.failed_total, deltaLabel(num(target.failed_total) - num(baseline.failed_total))],
    ['Flaky', target.flaky, baseline.flaky, deltaLabel(num(target.flaky) - num(baseline.flaky))],
    ['Duration', target.duration_display, baseline.duration_display, formatDuration(num(target.duration_ms) - num(baseline.duration_ms))]
  ];
  return `<table><thead><tr><th>Metric</th><th>Compare</th><th>Baseline</th><th>Delta</th></tr></thead><tbody>${{rows.map((row) => `<tr><td>${{escapeHtml(row[0])}}</td><td>${{escapeHtml(row[1])}}</td><td>${{escapeHtml(row[2])}}</td><td>${{escapeHtml(row[3])}}</td></tr>`).join('')}}</tbody></table>`;
}}
function compareImpact(selected) {{
  if (!selected.length) return '<p class="empty-state">No selected runs.</p>';
  const categories = new Map();
  selected.forEach((item) => {{
    Object.entries(item.failure_categories || {{}}).forEach(([category, count]) => {{
      if (!Number(count || 0)) return;
      const runs = categories.get(category) || [];
      runs.push(`${{item.run_id}} · ${{count}}`);
      categories.set(category, runs);
    }});
  }});
  if (!categories.size) return '<p class="empty-state">No failure categories across selected runs.</p>';
  return `<div class="impact-list">${{Array.from(categories.entries()).map(([category, runs]) => `<div class="impact-item"><strong>${{escapeHtml(category)}}</strong><div class="impact-runs">${{runs.map((label) => `<span class="impact-pill">${{escapeHtml(label)}}</span>`).join('')}}</div></div>`).join('')}}</div>`;
}}
function reportCard(item) {{
  const scope = (item.profiles || []).join(', ') || (item.environments || []).join(', ') || '-';
  return `<article class="report-card"><div class="card-head"><div><span class="status ${{statusClass(item.status)}}">${{escapeHtml(item.status)}}</span><h3><a href="${{safeHref(item.entry_href)}}">${{escapeHtml(item.run_id || 'run')}}</a></h3><p class="muted">${{escapeHtml(item.generated_display)}} · ${{escapeHtml(item.framework || '-')}}</p></div><div class="score-line"><strong>${{escapeHtml(qualityScore(item))}}</strong><span class="status ${{statusClass(item.risk_level)}}">${{escapeHtml(item.risk_level || 'low')}}</span></div></div><div class="mini-metrics"><span><strong>${{num(item.total)}}</strong><br>Tests</span><span><strong>${{num(item.failed_total)}}</strong><br>Failures</span><span><strong>${{num(item.flaky)}}</strong><br>Flaky</span><span><strong>${{escapeHtml(item.duration_display)}}</strong><br>Duration</span></div><p class="muted">${{escapeHtml(item.project_name || '-')}} · ${{escapeHtml(scope)}}</p><p class="muted">New ${{num(item.new_failure_count)}} · Known ${{num(item.known_failure_count)}} · Resolved ${{num(item.resolved_failure_count)}} · Pass delta ${{escapeHtml(deltaLabel(item.pass_rate_delta, '%'))}}</p><div class="card-actions"><a class="button" href="${{safeHref(item.entry_href)}}">Dashboard</a><a class="button" href="${{safeHref(item.executive_href)}}">Executive</a><a class="button" href="${{safeHref(item.compare_href)}}">Compare</a><a class="button" href="${{safeHref(item.tests_href)}}">Tests</a><a class="button" href="${{safeHref(item.share_href)}}">Share</a></div></article>`;
}}
function reportTableRow(item) {{
  return `<tr><td><span class="status ${{statusClass(item.status)}}">${{escapeHtml(item.status)}}</span></td><td>${{escapeHtml(item.run_id)}}</td><td>${{escapeHtml(item.framework || '-')}}</td><td>${{escapeHtml(item.generated_display)}}</td><td>${{num(item.total)}}</td><td>${{escapeHtml(item.pass_rate)}}%</td><td>${{escapeHtml(qualityScore(item))}} · <span class="status ${{statusClass(item.risk_level)}}">${{escapeHtml(item.risk_level || 'low')}}</span></td><td>${{num(item.failed_total)}} failed · ${{num(item.flaky)}} flaky · ${{num(item.new_failure_count)}} new · ${{num(item.artifact_count)}} artifacts</td><td><a href="${{safeHref(item.entry_href)}}">Open</a> · <a href="${{safeHref(item.compare_href)}}">Compare</a></td></tr>`;
}}
function qualityScore(item) {{
  return item && item.quality_score !== null && item.quality_score !== undefined ? `${{item.quality_score}}` : 'N/A';
}}
function deltaLabel(value, suffix = '') {{
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-';
  const number = Number(value);
  const sign = number > 0 ? '+' : '';
  return `${{sign}}${{number}}${{suffix}}`;
}}
function qualityTrend(items) {{
  const values = Object.fromEntries(items.slice(0, 12).map((item) => [item.run_id || item.generated_display, Number(item.quality_score || 0)]));
  return barChart(values, 'No quality score data.');
}}
function setHtml(id, value) {{ const node = document.getElementById(id); if (node) node.innerHTML = value; }}
function formatDuration(ms) {{
  const value = Number(ms || 0);
  if (value >= 60000) return `${{(value / 60000).toFixed(1)}}m`;
  if (value >= 1000) return `${{(value / 1000).toFixed(1)}}s`;
  return `${{Math.round(value)}}ms`;
}}
function setupPortfolio() {{
  setupTheme();
  setupNavigation();
  const data = portfolioData();
  populateFilters(data);
  const rerender = () => {{
    if ('{page_kind}' === 'reports') renderGallery();
    else if ('{page_kind}' === 'compare') renderCompare();
    else renderDashboard();
  }};
  document.querySelectorAll('[data-portfolio-search],[data-portfolio-filter],#gallery-view,#compare-baseline,#compare-target').forEach((node) => {{
    node.addEventListener('input', rerender);
    node.addEventListener('change', rerender);
  }});
  const latest = document.getElementById('compare-latest');
  if (latest) latest.addEventListener('click', () => {{
    const baseline = document.getElementById('compare-baseline');
    const target = document.getElementById('compare-target');
    if (baseline) baseline.value = (data.reports || []).length > 1 ? '1' : '0';
    if (target) target.value = '0';
    rerender();
  }});
  document.querySelectorAll('[data-portfolio-reset]').forEach((node) => node.addEventListener('click', () => {{
    document.querySelectorAll('[data-portfolio-search]').forEach((input) => input.value = '');
    document.querySelectorAll('[data-portfolio-filter]').forEach((select) => select.value = '');
    rerender();
  }}));
  rerender();
}}
document.addEventListener('DOMContentLoaded', setupPortfolio);
"""


def _summary_from_report_data(report_data: dict[str, Any]) -> dict[str, Any]:
    run = report_data.get("run", {})
    if isinstance(run, dict) and isinstance(run.get("summary"), dict):
        return run["summary"]
    return {}


def _blocking_failure_count(summary: dict[str, Any]) -> int:
    return int(
        summary.get(
            "blocking_failures",
            int(summary.get("failed", 0) or 0) + int(summary.get("broken", 0) or 0) + int(summary.get("error", 0) or 0),
        )
        or 0
    )


def _run_folder_name(run_id: str, generated_at: datetime | str | None) -> str:
    timestamp = _folder_timestamp(generated_at)
    slug = _safe_filename(run_id)[:72] or "run"
    return f"{timestamp}-{slug}"


def _folder_timestamp(value: datetime | str | None) -> str:
    dt = _parse_datetime(value)
    if dt is None:
        dt = datetime.now().astimezone()
    return dt.astimezone().strftime("%Y%m%d-%H%M%S")


def _file_timestamp(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat()


def _unique_child_dir(parent: Path, folder_name: str) -> Path:
    candidate = parent / folder_name
    suffix = 2
    while candidate.exists():
        candidate = parent / f"{folder_name}-{suffix}"
        suffix += 1
    return candidate


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _parse_datetime(value: datetime | str | None) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _format_datetime(value: datetime | str | None) -> str:
    dt = _parse_datetime(value)
    if dt is None:
        return "-"
    return dt.astimezone().strftime("%b %d, %Y %H:%M")


def _format_duration(duration_ms: float | int) -> str:
    duration = float(duration_ms or 0)
    if duration >= 60_000:
        return f"{duration / 60_000:.1f}m"
    if duration >= 1_000:
        return f"{duration / 1_000:.1f}s"
    return f"{duration:.0f}ms"


def _search_text(entry: dict[str, Any]) -> str:
    values: list[str] = []
    for key in (
        "run_id",
        "project_name",
        "framework",
        "status",
        "quality_status",
        "quality_grade",
        "quality_score_status",
        "risk_level",
        "risk_summary",
        "compare_previous_run_id",
        "stability_status",
        "recovery_status",
        "resource_status",
        "generated_display",
        "profiles",
        "environments",
        "browsers",
        "devices",
        "failure_categories",
    ):
        values.append(str(entry.get(key, "")))
    return " ".join(values).lower()


def _sorted_options(values) -> list[str]:
    return sorted({str(value) for value in values if value not in (None, "")})


def _safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-") or "run"


def _json_for_script(data: dict[str, Any]) -> str:
    return json.dumps(to_jsonable(data), ensure_ascii=False).replace("</", "<\\/")


def _e(value: Any) -> str:
    return html.escape(str(value), quote=True)
