from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

STATUS_ORDER = {"failed": 0, "broken": 1, "error": 2, "skipped": 3, "passed": 4}


def generate_html_report(
    results_dir: Path | str,
    output_dir: Path | str,
    *,
    title: str = "Allure Results Summary",
    description: str = "Generated automatically from Allure JSON result files.",
    missing_ok: bool = False,
) -> Path:
    report_data = read_allure_results(results_dir, missing_ok=missing_ok)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    report_path = output_path / "index.html"
    report_path.write_text(_render_html(report_data, title=title, description=description), encoding="utf-8")
    return report_path


def read_allure_results(results_dir: Path | str, *, missing_ok: bool = False) -> list[dict[str, Any]]:
    results_path = Path(results_dir)
    if not results_path.exists():
        if missing_ok:
            return []
        raise FileNotFoundError(f"Allure results directory not found: {results_path}")

    tests: list[dict[str, Any]] = []
    for path in sorted(results_path.glob("*-result.json")):
        with path.open("r", encoding="utf-8") as file:
            result = json.load(file)
        tests.append(
            {
                "name": result.get("name", path.stem),
                "full_name": result.get("fullName", ""),
                "status": result.get("status", "unknown"),
                "duration_ms": _duration_ms(result),
                "message": result.get("statusDetails", {}).get("message", ""),
            }
        )

    return sorted(tests, key=lambda item: (STATUS_ORDER.get(item["status"], 9), item["name"]))


def summarize_results(tests: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {status: sum(1 for test in tests if test["status"] == status) for status in STATUS_ORDER}
    total = len(tests)
    passed = counts.get("passed", 0)
    failed = _blocking_failure_count(counts)
    duration_ms = sum(test["duration_ms"] for test in tests)
    pass_rate = round((passed / total) * 100, 2) if total else 0
    status = "passed" if total and failed == 0 else "failed"
    if total == 0:
        status = "unknown"

    return {
        "total": total,
        "passed": passed,
        "failed": counts.get("failed", 0),
        "broken": counts.get("broken", 0),
        "error": counts.get("error", 0),
        "blocking_failures": failed,
        "skipped": counts.get("skipped", 0),
        "duration_ms": duration_ms,
        "pass_rate": pass_rate,
        "status": status,
    }


def generate_matrix_dashboard(
    runs: list[dict[str, Any]],
    output_dir: Path | str,
    *,
    dimension_key: str,
    dimension_label: str,
    title: str,
    description: str,
    no_failures_message: str | None = None,
) -> Path:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    report_path = output_path / "index.html"
    report_path.write_text(
        _render_matrix_html(
            runs,
            dimension_key=dimension_key,
            dimension_label=dimension_label,
            title=title,
            description=description,
            no_failures_message=no_failures_message or f"No {dimension_label.lower()}-level failures detected.",
        ),
        encoding="utf-8",
    )
    return report_path


def generate_browser_matrix_dashboard(browser_runs: list[dict[str, Any]], output_dir: Path | str) -> Path:
    return generate_matrix_dashboard(
        browser_runs,
        output_dir,
        dimension_key="browser",
        dimension_label="Browser",
        title="Browser Matrix Dashboard",
        description="One dashboard for the full cross-browser automation run, with drill-down reports per browser.",
    )


def generate_environment_matrix_dashboard(environment_runs: list[dict[str, Any]], output_dir: Path | str) -> Path:
    return generate_matrix_dashboard(
        environment_runs,
        output_dir,
        dimension_key="env",
        dimension_label="Environment",
        title="API Environment Matrix Dashboard",
        description=(
            "One dashboard for the full multi-environment API automation run, with drill-down reports per environment."
        ),
    )


def generate_device_matrix_dashboard(device_runs: list[dict[str, Any]], output_dir: Path | str) -> Path:
    return generate_matrix_dashboard(
        device_runs,
        output_dir,
        dimension_key="profile",
        dimension_label="Profile",
        title="Device Matrix Dashboard",
        description="One pytest run per configured mobile capability profile.",
    )


def _duration_ms(result: dict[str, Any]) -> int:
    start = result.get("start", 0)
    stop = result.get("stop", start)
    return max(0, int(stop) - int(start))


def _render_html(tests: list[dict[str, Any]], *, title: str, description: str) -> str:
    summary = summarize_results(tests)
    rows = "\n".join(_render_row(test) for test in tests) or "<tr><td colspan='4'>No Allure results found.</td></tr>"
    escaped_title = html.escape(title)
    escaped_description = html.escape(description)

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{escaped_title}</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 32px; color: #1f2937; }}
    h1 {{ margin-bottom: 8px; }}
    .summary {{ display: flex; gap: 12px; margin: 24px 0; flex-wrap: wrap; }}
    .metric {{ border: 1px solid #d1d5db; border-radius: 6px; padding: 12px 16px; min-width: 110px; }}
    .metric strong {{ display: block; font-size: 24px; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border-bottom: 1px solid #e5e7eb; padding: 10px; text-align: left; vertical-align: top; }}
    th {{ background: #f9fafb; }}
    .passed {{ color: #047857; font-weight: 700; }}
    .failed, .broken {{ color: #b91c1c; font-weight: 700; }}
    .skipped {{ color: #92400e; font-weight: 700; }}
    .unknown {{ color: #6b7280; font-weight: 700; }}
    .message {{ color: #4b5563; white-space: pre-wrap; }}
  </style>
</head>
<body>
  <h1>{escaped_title}</h1>
  <p>{escaped_description}</p>
  <section class="summary">
    <div class="metric"><strong>{summary["total"]}</strong>Total</div>
    <div class="metric"><strong>{summary["passed"]}</strong>Passed</div>
    <div class="metric"><strong>{summary["failed"]}</strong>Failed</div>
    <div class="metric"><strong>{summary["broken"]}</strong>Broken</div>
    <div class="metric"><strong>{summary["skipped"]}</strong>Skipped</div>
    <div class="metric"><strong>{summary["pass_rate"]}%</strong>Pass Rate</div>
  </section>
  <table>
    <thead>
      <tr>
        <th>Status</th>
        <th>Test</th>
        <th>Duration</th>
        <th>Message</th>
      </tr>
    </thead>
    <tbody>
      {rows}
    </tbody>
  </table>
</body>
</html>
"""


def _render_row(test: dict[str, Any]) -> str:
    status = html.escape(test["status"])
    name = html.escape(test["name"])
    full_name = html.escape(test["full_name"])
    duration = f"{test['duration_ms'] / 1000:.2f}s"
    message = html.escape(test["message"])
    return f"""<tr>
  <td class="{status}">{status}</td>
  <td><strong>{name}</strong><br>{full_name}</td>
  <td>{duration}</td>
  <td class="message">{message}</td>
</tr>"""


def _render_matrix_html(
    runs: list[dict[str, Any]],
    *,
    dimension_key: str,
    dimension_label: str,
    title: str,
    description: str,
    no_failures_message: str,
) -> str:
    totals = _matrix_totals(runs, dimension_label)
    cards = "\n".join(_render_matrix_card(run, dimension_key, dimension_label) for run in runs)
    rows = "\n".join(_render_matrix_row(run, dimension_key) for run in runs)
    failures = "\n".join(_render_failure_item(run, dimension_key) for run in runs for _ in [0])
    if not failures:
        failures = f"<li>{html.escape(no_failures_message)}</li>"

    escaped_title = html.escape(title)
    escaped_description = html.escape(description)
    escaped_dimension_label = html.escape(dimension_label)
    dimension_count_key = f"{dimension_label.lower()}s"

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escaped_title}</title>
  <style>
    * {{ box-sizing: border-box; }}
    html, body {{ max-width: 100%; overflow-x: hidden; }}
    body {{ font-family: Arial, sans-serif; margin: 0; color: #172033; background: #f6f7f9; }}
    header {{ background: #102033; color: #ffffff; padding: 28px clamp(18px, 4vw, 36px); }}
    h1 {{ margin: 0 0 8px; overflow-wrap: anywhere; }}
    p, li, h2 {{ overflow-wrap: anywhere; }}
    main {{ padding: 28px clamp(18px, 4vw, 36px); max-width: 100%; }}
    .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 14px; margin-bottom: 24px; }}
    .metric {{ background: #ffffff; border: 1px solid #dde3ea; border-radius: 8px; padding: 16px; min-width: 0; }}
    .metric strong {{ display: block; font-size: 28px; margin-bottom: 4px; }}
    .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 16px; margin: 24px 0; }}
    .card {{ background: #ffffff; border: 1px solid #dde3ea; border-radius: 8px; padding: 18px; min-width: 0; overflow: hidden; }}
    .status {{ display: inline-block; padding: 4px 8px; border-radius: 999px; font-size: 12px; font-weight: 700; text-transform: uppercase; }}
    .passed {{ color: #047857; background: #dff7ed; }}
    .failed {{ color: #b91c1c; background: #fee2e2; }}
    .unknown {{ color: #6b7280; background: #e5e7eb; }}
    .bar {{ height: 9px; background: #e5e7eb; border-radius: 999px; overflow: hidden; margin: 12px 0; }}
    .bar span {{ display: block; height: 100%; background: #0f766e; }}
    .table-wrap {{ width: 100%; max-width: 100%; overflow-x: auto; border-radius: 8px; }}
    table {{ border-collapse: collapse; width: 100%; background: #ffffff; border: 1px solid #dde3ea; }}
    th, td {{ border-bottom: 1px solid #e5e7eb; padding: 11px; text-align: left; overflow-wrap: anywhere; word-break: break-word; }}
    th {{ background: #eef2f6; }}
    a {{ color: #0f5b99; font-weight: 700; overflow-wrap: anywhere; word-break: break-word; }}
    .section {{ margin-top: 28px; }}
    @media (max-width: 640px) {{
      main {{ padding: 20px 16px; }}
      header {{ padding: 22px 16px; }}
      .cards {{ grid-template-columns: 1fr; }}
      .table-wrap table {{ min-width: 760px; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>{escaped_title}</h1>
    <p>{escaped_description}</p>
  </header>
  <main>
    <section class="summary">
      <div class="metric"><strong>{totals[dimension_count_key]}</strong>{html.escape(dimension_label)}s</div>
      <div class="metric"><strong>{totals["total"]}</strong>Total Tests</div>
      <div class="metric"><strong>{totals["passed"]}</strong>Passed</div>
      <div class="metric"><strong>{_blocking_failure_count(totals)}</strong>Failures</div>
      <div class="metric"><strong>{totals["pass_rate"]}%</strong>Pass Rate</div>
      <div class="metric"><strong>{_format_duration(totals["duration_ms"])}</strong>Total Duration</div>
    </section>
    <section class="cards">
      {cards}
    </section>
    <section class="section">
      <h2>{escaped_dimension_label} Results</h2>
      <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>{escaped_dimension_label}</th>
            <th>Status</th>
            <th>Total</th>
            <th>Passed</th>
            <th>Failed</th>
            <th>Broken</th>
            <th>Skipped</th>
            <th>Pass Rate</th>
            <th>Duration</th>
            <th>Report</th>
            <th>Log</th>
          </tr>
        </thead>
        <tbody>
          {rows}
        </tbody>
      </table>
      </div>
    </section>
    <section class="section">
      <h2>Attention Needed</h2>
      <ul>{failures}</ul>
    </section>
  </main>
</body>
</html>
"""


def _matrix_totals(runs: list[dict[str, Any]], dimension_label: str) -> dict[str, Any]:
    dimension_count_key = f"{dimension_label.lower()}s"
    totals = {
        dimension_count_key: len(runs),
        "total": 0,
        "passed": 0,
        "failed": 0,
        "broken": 0,
        "error": 0,
        "skipped": 0,
        "duration_ms": 0,
    }
    for run in runs:
        summary = run["summary"]
        for key in ("total", "passed", "failed", "broken", "error", "skipped", "duration_ms"):
            totals[key] += summary.get(key, 0)
    totals["blocking_failures"] = _blocking_failure_count(totals)
    totals["pass_rate"] = round((totals["passed"] / totals["total"]) * 100, 2) if totals["total"] else 0
    return totals


def _render_matrix_card(run: dict[str, Any], dimension_key: str, dimension_label: str) -> str:
    summary = run["summary"]
    dimension_value = html.escape(str(run[dimension_key]))
    report_href = html.escape(run["report_href"])
    log_href = html.escape(run.get("log_href", "#"))
    status = html.escape(summary["status"])
    return f"""<article class="card">
  <h2>{dimension_value}</h2>
  <span class="status {status}">{status}</span>
  <div class="bar"><span style="width: {summary["pass_rate"]}%"></span></div>
  <p><strong>{summary["pass_rate"]}%</strong> pass rate across {summary["total"]} tests.</p>
  <p>{summary["passed"]} passed, {_blocking_failure_count(summary)} failures, {summary["skipped"]} skipped.</p>
  <p>Duration: {_format_duration(summary["duration_ms"])}</p>
  <a href="{report_href}">Open {dimension_value} report</a>
  <br>
  <a href="{log_href}">Open execution log</a>
</article>"""


def _render_matrix_row(run: dict[str, Any], dimension_key: str) -> str:
    summary = run["summary"]
    dimension_value = html.escape(str(run[dimension_key]))
    report_href = html.escape(run["report_href"])
    log_href = html.escape(run.get("log_href", "#"))
    status = html.escape(summary["status"])
    return f"""<tr>
  <td>{dimension_value}</td>
  <td><span class="status {status}">{status}</span></td>
  <td>{summary["total"]}</td>
  <td>{summary["passed"]}</td>
  <td>{summary["failed"]}</td>
  <td>{summary["broken"]}</td>
  <td>{summary["skipped"]}</td>
  <td>{summary["pass_rate"]}%</td>
  <td>{_format_duration(summary["duration_ms"])}</td>
  <td><a href="{report_href}">Details</a></td>
  <td><a href="{log_href}">Log</a></td>
</tr>"""


def _render_failure_item(run: dict[str, Any], dimension_key: str) -> str:
    summary = run["summary"]
    if _blocking_failure_count(summary) == 0:
        return ""
    dimension_value = html.escape(str(run[dimension_key]))
    report_href = html.escape(run["report_href"])
    count = _blocking_failure_count(summary)
    return f'<li>{dimension_value}: {count} failing tests. <a href="{report_href}">Open report</a></li>'


def _blocking_failure_count(summary: dict[str, Any]) -> int:
    return int(
        summary.get(
            "blocking_failures",
            int(summary.get("failed", 0) or 0) + int(summary.get("broken", 0) or 0) + int(summary.get("error", 0) or 0),
        )
        or 0
    )


def _format_duration(duration_ms: int) -> str:
    seconds = round(duration_ms / 1000, 2)
    if seconds < 60:
        return f"{seconds}s"
    minutes = int(seconds // 60)
    remaining = round(seconds % 60, 2)
    return f"{minutes}m {remaining}s"
