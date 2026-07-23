from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from automation_core.reporting import shell

STATUS_ORDER = {"failed": 0, "broken": 1, "error": 2, "skipped": 3, "passed": 4}

DISPLAY = "'Manrope',sans-serif"
MONO = "'IBM Plex Mono',monospace"


def _status_tokens(status: str) -> tuple[str, str]:
    """Return (color, soft-background) design tokens for a run status."""
    if status == "passed":
        return "var(--pass)", "var(--passSoft)"
    if status in ("failed", "broken", "error"):
        return "var(--fail)", "var(--failSoft)"
    return "var(--muted)", "var(--surfaceAlt)"


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
    dimension_count_key = f"{dimension_label.lower()}s"

    eyebrow = f"{dimension_label} Matrix"
    header = (
        '<div style="margin-bottom:24px;">'
        '<div style="font-size:12px; font-weight:600; letter-spacing:0.06em; text-transform:uppercase; '
        f'color:var(--faint); margin-bottom:6px;">{html.escape(eyebrow)}</div>'
        f'<h1 style="font-family:{DISPLAY}; font-size:28px; font-weight:800; margin:0 0 6px; color:var(--text); '
        f'letter-spacing:-0.01em; overflow-wrap:anywhere;">{html.escape(title)}</h1>'
        f'<p style="font-size:14px; color:var(--muted); margin:0; max-width:70ch; overflow-wrap:anywhere;">'
        f"{html.escape(description)}</p></div>"
    )

    tiles = "".join(
        _matrix_tile(value, label)
        for value, label in (
            (str(totals[dimension_count_key]), f"{dimension_label}s"),
            (str(totals["total"]), "Total Tests"),
            (str(totals["passed"]), "Passed"),
            (str(_blocking_failure_count(totals)), "Failures"),
            (f"{totals['pass_rate']}%", "Pass Rate"),
            (_format_duration(totals["duration_ms"]), "Total Duration"),
        )
    )
    summary = f'<div style="display:flex; flex-wrap:wrap; gap:14px; margin-bottom:24px;">{tiles}</div>'

    cards = "".join(_render_matrix_card(run, dimension_key) for run in runs) or (
        f'<p style="font-size:13px; color:var(--faint);">No {html.escape(dimension_label.lower())} runs recorded.</p>'
    )
    cards_grid = (
        '<div style="display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:16px; '
        f'margin-bottom:24px;" class="grid-auto">{cards}</div>'
    )

    rows = "".join(_render_matrix_row(run, dimension_key) for run in runs) or (
        f'<tr><td colspan="11" style="padding:22px; color:var(--faint);">No {html.escape(dimension_label.lower())}'
        " runs recorded.</td></tr>"
    )
    heads = "".join(
        f'<th style="padding:12px 14px; text-align:left; font-size:11px; font-weight:700; letter-spacing:0.05em; '
        f'text-transform:uppercase; color:var(--faint); background:var(--surfaceAlt); white-space:nowrap;">{h}</th>'
        for h in (
            dimension_label,
            "Status",
            "Total",
            "Passed",
            "Failed",
            "Broken",
            "Skipped",
            "Pass Rate",
            "Duration",
            "Report",
            "Log",
        )
    )
    table_card = _matrix_card_wrap(
        f'<h2 style="font-family:{DISPLAY}; font-size:16px; font-weight:700; margin:0 0 16px;">'
        f"{html.escape(dimension_label)} Results</h2>"
        '<div class="table-wrap" style="overflow-x:auto; max-width:100%;">'
        '<table style="width:100%; min-width:840px; border-collapse:collapse; table-layout:auto;">'
        f"<thead><tr>{heads}</tr></thead><tbody>{rows}</tbody></table></div>"
    )

    failure_items = "".join(_render_failure_item(run, dimension_key) for run in runs)
    if failure_items:
        attention_body = f'<ul style="margin:0; padding-left:18px; line-height:1.8;">{failure_items}</ul>'
    else:
        attention_body = (
            f'<p style="font-size:13.5px; color:var(--muted); margin:0;">{html.escape(no_failures_message)}</p>'
        )
    attention_card = _matrix_card_wrap(
        f'<h2 style="font-family:{DISPLAY}; font-size:16px; font-weight:700; margin:0 0 14px;">Attention Needed</h2>'
        + attention_body
    )

    main = header + summary + cards_grid + table_card + attention_card
    sidebar_html = shell.sidebar("matrix", active="", run={"label": f"{dimension_label} Matrix", "sub": description})
    return shell.document(title, sidebar_html=sidebar_html, main_html=main)


def _matrix_tile(value: str, label: str) -> str:
    return (
        '<div style="flex:1; min-width:140px; background:var(--surface); border:1px solid var(--border); '
        'border-radius:16px; box-shadow:var(--shadow); padding:18px;">'
        f'<strong style="font-family:{MONO}; display:block; font-size:26px; font-weight:700; color:var(--text);">'
        f"{html.escape(value)}</strong>"
        f'<div style="font-size:12.5px; color:var(--muted); margin-top:6px;">{html.escape(label)}</div></div>'
    )


def _matrix_card_wrap(inner: str) -> str:
    return (
        '<div style="background:var(--surface); border:1px solid var(--border); border-radius:16px; '
        f'box-shadow:var(--shadow); padding:20px; margin-bottom:20px;">{inner}</div>'
    )


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


def _status_pill(status: str) -> str:
    color, soft = _status_tokens(status)
    return (
        '<span style="display:inline-block; padding:3px 10px; border-radius:100px; font-size:11px; '
        f'font-weight:700; letter-spacing:0.02em; text-transform:uppercase; background:{soft}; color:{color};">'
        f"{html.escape(status)}</span>"
    )


def _matrix_link(href: str, label: str) -> str:
    return (
        f'<a href="{html.escape(href)}" style="color:var(--link); font-weight:600; text-decoration:none; '
        f'overflow-wrap:anywhere;">{html.escape(label)}</a>'
    )


def _render_matrix_card(run: dict[str, Any], dimension_key: str) -> str:
    summary = run["summary"]
    color, _ = _status_tokens(summary["status"])
    dimension_value = html.escape(str(run[dimension_key]))
    report_href = run["report_href"]
    log_href = run.get("log_href", "#")
    return (
        '<div style="background:var(--surfaceAlt); border:1px solid var(--border); border-radius:14px; '
        'padding:18px; min-width:0; overflow:hidden;">'
        '<div style="display:flex; align-items:center; justify-content:space-between; gap:10px; margin-bottom:10px;">'
        f'<h3 style="font-family:{MONO}; font-size:15px; font-weight:700; margin:0; overflow-wrap:anywhere; '
        f'min-width:0;">{dimension_value}</h3>{_status_pill(summary["status"])}</div>'
        '<div style="height:9px; background:var(--surface); border-radius:100px; overflow:hidden; margin:12px 0;">'
        f'<span style="display:block; height:100%; width:{summary["pass_rate"]}%; background:{color};"></span></div>'
        f'<p style="font-size:13px; color:var(--muted); margin:0 0 6px;"><strong style="color:var(--text);">'
        f"{summary['pass_rate']}%</strong> pass rate across {summary['total']} tests.</p>"
        f'<p style="font-size:13px; color:var(--muted); margin:0 0 6px;">{summary["passed"]} passed, '
        f"{_blocking_failure_count(summary)} failures, {summary['skipped']} skipped.</p>"
        f'<p style="font-size:13px; color:var(--muted); margin:0 0 12px;">Duration: '
        f"{_format_duration(summary['duration_ms'])}</p>"
        '<div style="display:flex; flex-direction:column; gap:6px; font-size:13px;">'
        f"{_matrix_link(report_href, f'Open {run[dimension_key]} report')}"
        f"{_matrix_link(log_href, 'Open execution log')}</div></div>"
    )


def _render_matrix_row(run: dict[str, Any], dimension_key: str) -> str:
    summary = run["summary"]
    dimension_value = html.escape(str(run[dimension_key]))
    cell = "padding:13px 14px; border-top:1px solid var(--border); font-size:13px; color:var(--text);"
    num = f"{cell} font-family:{MONO}; white-space:nowrap;"
    return (
        "<tr>"
        f'<td style="{cell} font-family:{MONO}; white-space:nowrap;">{dimension_value}</td>'
        f'<td style="{cell} white-space:nowrap;">{_status_pill(summary["status"])}</td>'
        f'<td style="{num}">{summary["total"]}</td>'
        f'<td style="{num}">{summary["passed"]}</td>'
        f'<td style="{num}">{summary["failed"]}</td>'
        f'<td style="{num}">{summary["broken"]}</td>'
        f'<td style="{num}">{summary["skipped"]}</td>'
        f'<td style="{num}">{summary["pass_rate"]}%</td>'
        f'<td style="{num}">{_format_duration(summary["duration_ms"])}</td>'
        f'<td style="{cell} white-space:nowrap;">{_matrix_link(run["report_href"], "Details")}</td>'
        f'<td style="{cell} white-space:nowrap;">{_matrix_link(run.get("log_href", "#"), "Log")}</td>'
        "</tr>"
    )


def _render_failure_item(run: dict[str, Any], dimension_key: str) -> str:
    summary = run["summary"]
    if _blocking_failure_count(summary) == 0:
        return ""
    dimension_value = html.escape(str(run[dimension_key]))
    count = _blocking_failure_count(summary)
    return (
        f'<li style="font-size:13.5px; color:var(--text); margin-bottom:6px; overflow-wrap:anywhere;">'
        f"<strong>{dimension_value}</strong>: {count} failing tests. "
        f"{_matrix_link(run['report_href'], 'Open report')}</li>"
    )


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
