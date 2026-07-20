"""Design-faithful renderers for the per-run report pages.

These build the ten single-run pages (Executive, Overview, Quality Gates,
Tests, Timeline, Flaky, Matrix, History, Share and Test Detail) on top of the
shared sidebar shell in report-nav mode. Everything renders from the neutral
``report_data`` sidecar so the engine stays framework-agnostic; colours are
design tokens and long identifiers wrap via a monospace face.
"""

from __future__ import annotations

import json
from datetime import datetime
from html import escape
from typing import Any

from automation_core.reporting import shell

MONO = "'IBM Plex Mono',monospace"
DISPLAY = "'Manrope',sans-serif"
PLATFORM_COLORS = {"web": "var(--accent)", "mobile": "var(--flaky)", "api": "var(--broken)"}
STATUS_COLORS = {
    "passed": ("var(--pass)", "var(--passSoft)"),
    "failed": ("var(--fail)", "var(--failSoft)"),
    "broken": ("var(--broken)", "var(--brokenSoft)"),
    "error": ("var(--fail)", "var(--failSoft)"),
    "skipped": ("var(--skip)", "var(--skipSoft)"),
}


def _e(value: Any) -> str:
    return escape("" if value is None else str(value), quote=True)


def _status_colors(status: str) -> tuple[str, str]:
    return STATUS_COLORS.get(str(status).lower(), ("var(--muted)", "var(--surfaceAlt)"))


def _fmt_ts(value: Any) -> str:
    text = str(value or "")
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return text[:16]


def _fmt_dur(ms: float | int) -> str:
    ms = float(ms or 0)
    if ms < 1000:
        return f"{round(ms)}ms"
    s = ms / 1000
    if s < 60:
        return f"{round(s, 1)}s"
    return f"{round(s / 60, 1)}m"


def _fmt_pct(value: float | int) -> str:
    return f"{round(float(value or 0))}%"


def _title(text: str, size: int = 16) -> str:
    return (
        f'<h2 style="font-family:{DISPLAY}; font-size:{size}px; font-weight:700; margin:0 0 16px; '
        f'color:var(--text);">{_e(text)}</h2>'
    )


def _card(inner: str, *, pad: int = 22, extra: str = "") -> str:
    return (
        f'<div style="background:var(--surface); border:1px solid var(--border); border-radius:16px; '
        f'box-shadow:var(--shadow); padding:{pad}px; {extra}">{inner}</div>'
    )


def _page_header(eyebrow: str, title: str, subtitle: str, *, action: str = "") -> str:
    action_html = f'<div style="margin-left:auto;">{action}</div>' if action else ""
    return (
        '<div style="display:flex; align-items:flex-start; gap:16px; margin-bottom:24px; flex-wrap:wrap;">'
        '<div style="min-width:0;">'
        '<div style="font-size:12px; font-weight:600; letter-spacing:0.06em; text-transform:uppercase; '
        f'color:var(--faint); margin-bottom:6px;">{_e(eyebrow)}</div>'
        f'<h1 style="font-family:{DISPLAY}; font-size:26px; font-weight:800; margin:0 0 6px; '
        f'color:var(--text); letter-spacing:-0.01em; overflow-wrap:anywhere;">{_e(title)}</h1>'
        f'<p style="font-size:14px; color:var(--muted); margin:0; max-width:64ch;">{_e(subtitle)}</p>'
        "</div>"
        f"{action_html}</div>"
    )


def _run_eyebrow(report_data: dict[str, Any]) -> str:
    return str(report_data.get("run", {}).get("summary", {}).get("run_id", ""))


def _run_context(report_data: dict[str, Any]) -> dict[str, Any]:
    summary = report_data.get("run", {}).get("summary", {})
    gate = report_data.get("default_gate_status", {})
    ready = str(gate.get("status", "")).lower() == "passed"
    color, soft = ("var(--pass)", "var(--passSoft)") if ready else ("var(--fail)", "var(--failSoft)")
    return {
        "run_id": summary.get("run_id", ""),
        "status_label": "Ready" if ready else "Blocked",
        "status_color": color,
        "status_soft": soft,
        "timestamp": _fmt_ts(summary.get("latest_run")),
    }


def _document(
    report_data: dict[str, Any], active: str, title: str, main: str, *, prefix: str = "", scripts: str = ""
) -> str:
    sidebar_html = shell.sidebar("report", active=active, prefix=prefix, run=_run_context(report_data))
    return shell.document(
        title,
        sidebar_html=sidebar_html,
        main_html=main,
        extra_scripts=scripts,
        data_json_script=_data_script(report_data),
    )


def _data_script(report_data: dict[str, Any]) -> str:
    payload = json.dumps(report_data, ensure_ascii=False).replace("</", "<\\/")
    return f'<script type="application/json" id="report-data">{payload}</script>'


# --- shared small components ------------------------------------------------


def _stat_tile(value: Any, label: str, *, delta: Any = None, value_color: str = "var(--text)") -> str:
    delta_html = ""
    if delta not in (None, "", 0, "0"):
        text = str(delta)
        pos = text.startswith("+")
        d_color = "var(--fail)" if pos else "var(--pass)"
        d_soft = "var(--failSoft)" if pos else "var(--passSoft)"
        delta_html = (
            f'<span style="display:inline-block; margin-top:8px; padding:2px 8px; border-radius:100px; '
            f'font-family:{MONO}; font-size:10.5px; font-weight:600; background:{d_soft}; color:{d_color};">'
            f"{_e(text)}</span>"
        )
    return (
        '<div style="flex:1; min-width:120px; background:var(--surface); border:1px solid var(--border); '
        'border-radius:16px; box-shadow:var(--shadow); padding:18px;">'
        f'<div style="font-family:{MONO}; font-size:24px; font-weight:600; color:{value_color}; line-height:1;">'
        f"{_e(value)}</div>"
        f'<div style="font-size:12.5px; color:var(--muted); margin-top:8px;">{_e(label)}</div>{delta_html}</div>'
    )


def _pill(label: str, status: str) -> str:
    color, soft = _status_colors(status)
    return (
        f'<span style="display:inline-block; padding:3px 9px; border-radius:100px; font-family:{MONO}; '
        f'font-size:11px; font-weight:700; background:{soft}; color:{color};">{_e(label)}</span>'
    )


def _hbar_row(label: str, value: Any, maximum: float, color: str, *, mono_right: bool = True) -> str:
    width = (float(value or 0) / maximum * 100) if maximum else 0
    right = f"font-family:{MONO};" if mono_right else ""
    return (
        '<div style="display:flex; align-items:center; gap:12px; margin-bottom:12px;">'
        f'<span style="width:96px; font-size:13px; color:var(--muted); overflow:hidden; '
        f'text-overflow:ellipsis; white-space:nowrap;" title="{_e(label)}">{_e(label)}</span>'
        '<div style="flex:1; height:10px; border-radius:100px; background:var(--surfaceAlt); overflow:hidden;">'
        f'<span style="display:block; height:100%; width:{width:.1f}%; background:{color}; border-radius:100px;">'
        "</span></div>"
        f'<strong style="{right} font-size:13px; min-width:24px; text-align:right;">{_e(value)}</strong></div>'
    )


def _area_svg(series: list[float], color: str, *, w: int = 300, h: int = 110, points: bool = True) -> str:
    if not series:
        return ""
    pad, inner_w, inner_h = 12, w - 24, h - 16
    if len(series) == 1:
        xs = [w / 2]
    else:
        xs = [pad + i / (len(series) - 1) * inner_w for i in range(len(series))]
    ys = [h - 8 - (max(0.0, min(100.0, v)) / 100) * inner_h for v in series]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys, strict=False))
    area = f"M{xs[0]:.1f},{h - 8:.1f} L" + line.replace(" ", " L") + f" L{xs[-1]:.1f},{h - 8:.1f} Z"
    dots = ""
    if points:
        dots = "".join(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="{color}"/>' for x, y in zip(xs, ys, strict=False)
        )
    return (
        f'<svg viewBox="0 0 {w} {h}" style="width:100%; height:{h - 14}px;" preserveAspectRatio="none">'
        f'<path d="{area}" fill="{color}" opacity="0.10"/>'
        f'<polyline points="{line}" fill="none" stroke="{color}" stroke-width="2.5" '
        f'stroke-linecap="round" stroke-linejoin="round"/>{dots}</svg>'
    )


def _platform_trend_cards(trend_points: list[dict[str, Any]], *, note: str) -> str:
    cards = []
    for platform in ("web", "mobile", "api"):
        runs = [tp for tp in trend_points if (tp.get("platforms") or {}).get(platform)]
        if not runs:
            continue
        series = [float(tp["platforms"][platform].get("pass_rate", 0)) for tp in runs]
        last = series[-1] if series else 0
        color = PLATFORM_COLORS[platform]
        cards.append(
            '<div style="background:var(--surfaceAlt); border-radius:12px; padding:16px; margin-bottom:14px;">'
            '<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">'
            f'<span style="display:inline-flex; align-items:center; gap:8px; font-size:14px; font-weight:600;">'
            f'<i style="width:9px; height:9px; border-radius:50%; background:{color}; display:inline-block;"></i>'
            f"{platform.capitalize()}</span>"
            f'<strong style="font-family:{MONO}; font-size:18px; color:{color};">{_fmt_pct(last)}</strong></div>'
            f"{_area_svg(series, color, w=300, h=120)}"
            f'<div style="font-size:11.5px; color:var(--faint); margin-top:8px;">{len(runs)} run(s) with '
            f"{platform.capitalize()} tests.</div></div>"
        )
    body = "".join(cards) or '<p style="font-size:13px; color:var(--faint);">No platform trend data yet.</p>'
    return body + f'<p style="font-size:11.5px; color:var(--faint); margin:10px 0 0; line-height:1.5;">{_e(note)}</p>'


def _donut(values: dict[str, int]) -> str:
    entries = [(k, v) for k, v in values.items() if v]
    total = sum(v for _, v in entries)
    if not total:
        return '<p style="font-size:13px; color:var(--faint);">No data.</p>'
    color_map = {
        "passed": "var(--pass)",
        "failed": "var(--fail)",
        "broken": "var(--broken)",
        "skipped": "var(--skip)",
        "unknown": "var(--muted)",
    }
    stops, acc, legend = [], 0.0, []
    for key, value in entries:
        start = acc / total * 100
        acc += value
        end = acc / total * 100
        color = color_map.get(key, "var(--muted)")
        stops.append(f"{color} {start:.2f}% {end:.2f}%")
        legend.append(
            f'<div style="display:flex; align-items:center; gap:8px; font-size:12.5px; margin-bottom:6px;">'
            f'<i style="width:10px; height:10px; border-radius:2px; background:{color};"></i>'
            f"{key.capitalize()} : {value}</div>"
        )
    return (
        '<div style="display:flex; align-items:center; gap:20px;">'
        f'<div style="width:96px; height:96px; border-radius:50%; flex-shrink:0; '
        f'background:conic-gradient({", ".join(stops)});"></div>'
        f"<div>{''.join(legend)}</div></div>"
    )


# ============================ OVERVIEW =====================================


def render_overview(report_data: dict[str, Any]) -> str:
    summary = report_data.get("run", {}).get("summary", {})
    health = report_data.get("run", {}).get("health", {})
    qscore = report_data.get("quality_score", {})
    gate = report_data.get("default_gate_status", {})
    ready = str(gate.get("status", "")).lower() == "passed"
    score = int(round(float(report_data.get("health_score", qscore.get("score", 0)) or 0)))
    ring_color = "var(--pass)" if score >= 80 else ("var(--flaky)" if score >= 60 else "var(--fail)")
    pass_rate = float(summary.get("pass_rate", 0) or 0)
    total = int(summary.get("total", 0) or 0)
    passed = int(summary.get("passed", 0) or 0)
    failed = int(summary.get("failed", 0) or 0) + int(summary.get("broken", 0) or 0)
    skipped = int(summary.get("skipped", 0) or 0)
    flaky = int(summary.get("flaky", 0) or 0)
    dur = _fmt_dur(summary.get("duration_ms", 0))

    if total == 0:
        empty = _card(
            '<div style="text-align:center; padding:48px 24px;">'
            '<div style="width:56px; height:56px; border-radius:14px; background:var(--surfaceAlt); '
            'display:inline-flex; align-items:center; justify-content:center; margin-bottom:16px;">'
            '<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="var(--faint)" '
            'stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 11l3 3L22 4"/>'
            '<path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg></div>'
            f'<h2 style="font-family:{DISPLAY}; font-size:18px; font-weight:800; margin:0 0 6px;">'
            "No tests found</h2>"
            '<p style="font-size:14px; color:var(--muted); margin:0;">This run produced no test results. '
            "Nothing to show yet.</p></div>"
        )
        main = _page_header("Overview", "Automation Report", "pytest run summary and signals for this build.") + empty
        return _document(report_data, "dashboard", "Automation Report — Overview", main)

    verdict_soft = "var(--passSoft)" if ready else "var(--failSoft)"
    verdict_color = "var(--pass)" if ready else "var(--fail)"
    verdict_label = "RELEASE READY" if ready else "RELEASE BLOCKED"
    gate_msg = _gate_sentence(gate, summary)

    # status segment bar
    seg = _status_segment_bar(passed, failed, int(summary.get("broken", 0) or 0), skipped)
    ring = _ring(score, ring_color, "HEALTH")

    delta = health.get("pass_rate_delta")
    delta_txt = _signed(delta, "%") if delta not in (None, 0) else ""
    trend_pts = report_data.get("history", {}).get("trend_points", [])
    spark_series = [float(p.get("pass_rate", 0)) for p in trend_pts] or [pass_rate]

    hero = (
        '<div style="display:grid; grid-template-columns:1.15fr 1fr; gap:20px; margin-bottom:20px;" class="grid-2">'
        + _card(
            '<div style="display:flex; gap:20px; align-items:center; margin-bottom:16px;">'
            + ring
            + f'<div><span style="display:inline-flex; align-items:center; gap:7px; padding:4px 11px; '
            f"border-radius:100px; font-size:12px; font-weight:800; letter-spacing:0.02em; "
            f'background:{verdict_soft}; color:{verdict_color}; font-family:{DISPLAY};">'
            f'<span style="width:7px; height:7px; border-radius:50%; background:{verdict_color};"></span>'
            f"{verdict_label}</span>"
            f'<p style="font-size:13.5px; color:var(--muted); margin:10px 0 0; line-height:1.5;">{_e(gate_msg)}</p>'
            "</div></div>" + seg,
            extra="display:flex; flex-direction:column;",
        )
        + _card(
            '<div style="font-size:11px; font-weight:600; letter-spacing:0.06em; text-transform:uppercase; '
            'color:var(--faint); display:flex; justify-content:space-between;"><span>Pass Rate</span>'
            + (
                f'<span style="color:{"var(--fail)" if (delta or 0) < 0 else "var(--pass)"}; font-family:{MONO};">'
                f"{_e(delta_txt)}</span>"
                if delta_txt
                else ""
            )
            + "</div>"
            + f'<div style="font-family:{MONO}; font-size:44px; font-weight:600; color:var(--text); '
            f'line-height:1.1; margin-top:2px;">{_fmt_pct(pass_rate)}</div>'
            + f'<div style="margin:10px 0;">{_area_svg(spark_series, "var(--pass)", w=320, h=60, points=False)}</div>'
            + '<div style="display:flex; justify-content:space-between; border-top:1px solid var(--border); '
            'padding-top:12px;">'
            + _mini_stat(total, "Tests")
            + _mini_stat(failed, "Failed", "var(--fail)")
            + _mini_stat(flaky, "Flaky", "var(--flaky)")
            + _mini_stat(dur, "Duration", align="right")
            + "</div>"
        )
        + "</div>"
    )

    insights = _insight_pair(report_data)

    tiles = (
        '<div style="display:flex; flex-wrap:wrap; gap:14px; margin-bottom:20px;">'
        + _stat_tile(total, "Total")
        + _stat_tile(passed, "Passed")
        + _stat_tile(failed, "Failed", delta=_signed(health.get("failed_delta")))
        + _stat_tile(skipped, "Skipped")
        + _stat_tile(flaky, "Flaky", delta=_signed(health.get("flaky_delta")))
        + _stat_tile(_fmt_pct(pass_rate), "Pass Rate", delta=_signed(health.get("pass_rate_delta"), "%"))
        + _stat_tile(dur, "Duration", delta=_signed_dur(health.get("duration_delta_ms")))
        + "</div>"
    )

    signals = report_data.get("signals", {})
    chips = _signal_chips(signals)

    trend = _card(
        _title("Pass Rate Trend")
        + _platform_trend_cards(
            trend_pts,
            note="Each line is one platform's pass rate across every run that included it "
            "(not just this run's own history).",
        )
    )
    risks = _card(
        _title("Risk Signals") + _risk_signal_list(report_data.get("risk_signals", [])),
        extra="max-height:640px; overflow:auto;",
    )
    trend_row = (
        '<div style="display:grid; grid-template-columns:1fr 1fr; gap:20px; margin-bottom:20px;" '
        f'class="grid-2">{trend}{risks}</div>'
    )

    breakdown = _breakdown_section(report_data)
    slowest = _slowest_tests_card(report_data)
    coverage = _env_coverage_section(report_data)

    main = (
        _page_header(
            "Overview",
            "Automation Report",
            "pytest run summary and signals for this build.",
            action=_search_open_explore(),
        )
        + hero
        + insights
        + tiles
        + chips
        + trend_row
        + f'<h2 style="font-family:{DISPLAY}; font-size:18px; font-weight:800; margin:8px 0 16px;">Breakdown</h2>'
        + breakdown
        + slowest
        + coverage
    )
    return _document(report_data, "dashboard", "Automation Report — Overview", main)


def _ring(score: int, color: str, label: str) -> str:
    s = max(0, min(100, score))
    return (
        f'<div style="width:118px; height:118px; border-radius:50%; flex-shrink:0; '
        f"background:conic-gradient({color} 0 {s}%, var(--surfaceAlt) {s}% 100%); display:flex; "
        f'align-items:center; justify-content:center;">'
        f'<div style="width:88px; height:88px; border-radius:50%; background:var(--surface); display:flex; '
        f'flex-direction:column; align-items:center; justify-content:center;">'
        f'<strong style="font-family:{MONO}; font-size:26px; font-weight:600; color:{color}; line-height:1;">'
        f"{s}</strong>"
        f'<span style="font-size:10px; font-weight:600; letter-spacing:0.08em; color:var(--faint); '
        f'margin-top:3px;">{_e(label)}</span></div></div>'
    )


def _mini_stat(value: Any, label: str, color: str = "var(--text)", *, align: str = "left") -> str:
    return (
        f'<span style="text-align:{align};"><strong style="font-family:{MONO}; display:block; font-size:16px; '
        f'color:{color};">{_e(value)}</strong>'
        f'<span style="font-size:11.5px; color:var(--faint);">{_e(label)}</span></span>'
    )


def _status_segment_bar(passed: int, failed: int, broken: int, skipped: int) -> str:
    total = passed + failed + broken + skipped
    if not total:
        return ""
    parts = [
        ("Passed", passed, "var(--pass)"),
        ("Failed", failed, "var(--fail)"),
        ("Broken", broken, "var(--broken)"),
        ("Skipped", skipped, "var(--skip)"),
    ]
    segs = "".join(f'<span style="width:{v / total * 100:.2f}%; background:{c};"></span>' for _, v, c in parts if v)
    legend = "".join(
        f'<span style="display:inline-flex; align-items:center; gap:6px;">'
        f'<i style="width:9px; height:9px; border-radius:2px; background:{c}; display:inline-block;"></i>'
        f"{name} {v}</span>"
        for name, v, c in parts
        if v
    )
    return (
        '<div style="display:flex; height:12px; border-radius:100px; overflow:hidden; '
        f'background:var(--surfaceAlt); margin-top:auto;">{segs}</div>'
        f'<div style="display:flex; gap:16px; margin-top:10px; font-size:12px; color:var(--muted); '
        f'flex-wrap:wrap;">{legend}</div>'
    )


def _gate_sentence(gate: dict[str, Any], summary: dict[str, Any]) -> str:
    results = gate.get("results", []) if isinstance(gate.get("results"), list) else []
    total_gates = len(results)
    passed_gates = sum(1 for r in results if str(r.get("status")).lower() == "passed")
    adjusted = gate.get("adjusted_pass_rate")
    pass_rate = _fmt_pct(adjusted if adjusted is not None else summary.get("pass_rate", 0))
    if str(gate.get("status")).lower() == "passed":
        return f"Adjusted pass rate {pass_rate} meets all {total_gates} release gates, with no new unresolved failures."
    failed_gates = total_gates - passed_gates
    return f"{failed_gates} of {total_gates} release gate(s) failing — adjusted pass rate {pass_rate}."


def _signed(value: Any, suffix: str = "") -> str:
    if value in (None, ""):
        return ""
    num = float(value)
    if num == 0:
        return ""
    return f"{'+' if num > 0 else ''}{round(num)}{suffix}"


def _signed_dur(ms: Any) -> str:
    if ms in (None, "", 0):
        return ""
    num = float(ms)
    if num == 0:
        return ""
    return f"{'+' if num > 0 else '-'}{round(abs(num) / 1000, 1)}s"


def _search_open_explore() -> str:
    return (
        '<div style="display:flex; gap:10px; align-items:center; flex-wrap:wrap; justify-content:flex-end;">'
        '<input id="ov-search" type="search" placeholder="Search tests, failures..." '
        'style="padding:9px 14px; border-radius:9px; border:1px solid var(--border); background:var(--surface); '
        'color:var(--text); font-size:13px; flex:1 1 140px; min-width:0; font-family:inherit;">'
        '<a id="ov-explore" href="explore.html" style="padding:10px 16px; border-radius:9px; background:var(--accent); '
        "color:#fff; font-size:13px; font-weight:700; text-decoration:none; font-family:'Manrope',sans-serif; "
        'white-space:nowrap;">Open Explore</a></div>'
    )


def _insight_pair(report_data: dict[str, Any]) -> str:
    wins = _overview_wins(report_data)
    focus = _overview_focus(report_data)

    def block(title: str, items: list[str], bg: str, color: str, icon: str) -> str:
        lis = "".join(
            f'<li style="font-size:13px; color:var(--text); line-height:1.45; padding-left:16px; '
            f'position:relative;"><span style="position:absolute; left:0; color:{color};">•</span>{_e(i)}</li>'
            for i in items
        )
        return (
            f'<div style="background:{bg}; border-radius:16px; padding:20px 22px;">'
            f'<h2 style="font-family:{DISPLAY}; font-size:16px; font-weight:700; margin:0 0 12px; color:{color}; '
            f'display:flex; align-items:center; gap:8px;">{icon}{_e(title)}</h2>'
            f'<ul style="margin:0; padding:0; list-style:none; display:flex; flex-direction:column; gap:9px;">'
            f"{lis}</ul></div>"
        )

    check = (
        '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>'
    )
    warn = (
        '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" '
        'stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 '
        '0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/>'
        '<line x1="12" y1="17" x2="12.01" y2="17"/></svg>'
    )
    return (
        '<div style="display:grid; grid-template-columns:1fr 1fr; gap:20px; margin-bottom:20px;" class="grid-2">'
        + block("Key Wins", wins, "var(--passSoft)", "var(--pass)", check)
        + block("Focus Areas", focus, "var(--failSoft)", "var(--fail)", warn)
        + "</div>"
    )


def _overview_wins(report_data: dict[str, Any]) -> list[str]:
    wins: list[str] = []
    signals = report_data.get("signals", {})
    if int(signals.get("healing_event_count", 0) or 0):
        wins.append(f"{signals['healing_event_count']} failure(s) auto-healed — no manual fix needed.")
    platforms = report_data.get("platforms", {})
    for name, bucket in platforms.items():
        if bucket.get("pass_rate") == 100 and bucket.get("total"):
            wins.append(f"{name.capitalize()} suite is fully green ({bucket['total']} tests).")
            break
    resolved = report_data.get("failure_transitions", {}).get("counts", {}).get("resolved", 0)
    if resolved:
        wins.append(f"{resolved} previously-failing test(s) resolved this run.")
    return wins or ["No positive release signal yet."]


def _overview_focus(report_data: dict[str, Any]) -> list[str]:
    focus: list[str] = []
    flaky = int(report_data.get("run", {}).get("summary", {}).get("flaky", 0) or 0)
    if flaky:
        focus.append(f"{flaky} flaky signal(s) reducing confidence.")
    slow = report_data.get("top_slow_tests", [])
    if slow:
        top = slow[0]
        focus.append(f"Slowest test takes {_fmt_dur(top.get('duration_ms', 0))} — {top.get('name', '')}.")
    new_failures = report_data.get("failure_transitions", {}).get("counts", {}).get("new", 0)
    if new_failures:
        focus.append(f"{new_failures} new unresolved failure(s) since previous run.")
    return focus or ["No material focus areas this run."]


def _signal_chips(signals: dict[str, Any]) -> str:
    chips = [
        (signals.get("artifact_count", 0), "Artifacts"),
        (signals.get("action_retry_count", 0), "Action Retries"),
        (signals.get("test_retry_count", 0), "Test Retries"),
        (signals.get("healing_event_count", 0), "Healing Events"),
    ]
    inner = "".join(
        f'<span style="display:inline-flex; align-items:center; gap:6px; padding:6px 12px; border-radius:100px; '
        f'border:1px solid var(--border); background:var(--surface); font-size:12.5px; color:var(--muted);">'
        f'<strong style="font-family:{MONO}; color:var(--text);">{int(v or 0)}</strong> {name}</span>'
        for v, name in chips
    )
    return f'<div style="display:flex; gap:10px; flex-wrap:wrap; margin-bottom:20px;">{inner}</div>'


def _risk_signal_list(risks: list[dict[str, Any]]) -> str:
    if not risks:
        return '<p style="font-size:13px; color:var(--faint);">No risk signals detected.</p>'
    blocks = []
    for risk in risks:
        color = "var(--fail)" if str(risk.get("severity")) == "high" else "var(--flaky)"
        links = "".join(
            f'<a href="{_e(t.get("detail_href", "#"))}" style="display:block; font-family:{MONO}; font-size:12px; '
            f'color:var(--link); text-decoration:none; overflow-wrap:anywhere; margin:3px 0;">{_e(t.get("name", ""))}</a>'
            for t in risk.get("tests", [])
        )
        blocks.append(
            f'<div style="margin-bottom:14px;"><div style="display:flex; align-items:center; gap:8px; '
            f'font-size:13.5px; font-weight:700; margin-bottom:6px;">'
            f'<span style="width:7px; height:7px; border-radius:50%; background:{color};"></span>'
            f"{_e(risk.get('title', ''))} ({int(risk.get('count', 0) or 0)})</div>{links}</div>"
        )
    return "".join(blocks)


def _breakdown_section(report_data: dict[str, Any]) -> str:
    charts = report_data.get("charts", {})
    status = charts.get("status_distribution", {})
    durations = charts.get("duration_buckets", {})
    failures = charts.get("failure_categories", {})
    dmax = max(list(durations.values()) + [1])
    fmax = max(list(failures.values()) + [1])
    dur_rows = (
        "".join(_hbar_row(k, v, dmax, "var(--accent)") for k, v in durations.items() if v)
        or '<p style="font-size:13px; color:var(--faint);">No data.</p>'
    )
    fail_rows = (
        "".join(_hbar_row(k, v, fmax, "var(--fail)") for k, v in failures.items())
        or '<p style="font-size:13px; color:var(--faint);">No failure categories.</p>'
    )
    return (
        '<div style="display:grid; grid-template-columns:repeat(3,1fr); gap:20px; margin-bottom:20px;" class="grid-3">'
        + _card(_title("Status Distribution", 15) + _donut(status))
        + _card(_title("Duration Distribution", 15) + dur_rows)
        + _card(_title("Failure Categories", 15) + fail_rows)
        + "</div>"
    )


def _slowest_tests_card(report_data: dict[str, Any]) -> str:
    slow = report_data.get("top_slow_tests", [])[:5]
    if not slow:
        return ""
    mx = max([float(t.get("duration_ms", 0)) for t in slow] + [1])
    rows = "".join(
        '<div style="display:flex; align-items:center; gap:14px; margin-bottom:12px;">'
        f'<a href="{_e(t.get("detail_href", "#"))}" style="flex:1; font-family:{MONO}; font-size:12.5px; '
        f'color:var(--link); text-decoration:none; overflow-wrap:anywhere;">{_e(t.get("name", ""))}</a>'
        '<div style="width:200px; height:8px; border-radius:100px; background:var(--surfaceAlt); overflow:hidden; '
        'flex-shrink:0;">'
        f'<span style="display:block; height:100%; width:{float(t.get("duration_ms", 0)) / mx * 100:.1f}%; '
        'background:var(--accent); border-radius:100px;"></span></div>'
        f'<strong style="font-family:{MONO}; font-size:12.5px; width:60px; text-align:right;">'
        f"{_fmt_dur(t.get('duration_ms', 0))}</strong></div>"
        for t in slow
    )
    header = (
        f'<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:16px;">'
        f'<h2 style="font-family:{DISPLAY}; font-size:16px; font-weight:700; margin:0;">Slowest Tests</h2>'
        f'<a href="explore.html" style="font-size:13px; color:var(--link); text-decoration:none;">'
        f"View all tests →</a></div>"
    )
    return _card(header + rows, extra="margin-bottom:20px;")


def _env_coverage_section(report_data: dict[str, Any]) -> str:
    coverage = report_data.get("aggregates", {}).get("coverage", {})
    dims = [(k, v) for k, v in coverage.items() if isinstance(v, dict) and v and k != "platform_type"]
    if not dims:
        return ""
    cards = []
    for dim, values in dims:
        total = sum(values.values())
        mx = max(list(values.values()) + [1])
        rows = "".join(
            '<div style="margin-bottom:10px;"><div style="display:flex; justify-content:space-between; gap:12px; '
            f'font-family:{MONO}; font-size:11.5px; margin-bottom:4px;">'
            f'<span style="overflow-wrap:anywhere; min-width:0;">{_e(name)}</span>'
            f'<span style="color:var(--muted); flex-shrink:0;">{count}</span></div>'
            '<div style="height:6px; border-radius:100px; background:var(--surfaceAlt); overflow:hidden;">'
            f'<span style="display:block; height:100%; width:{count / mx * 100:.1f}%; background:var(--accent); '
            'border-radius:100px;"></span></div></div>'
            for name, count in sorted(values.items(), key=lambda kv: -kv[1])
        )
        label = dim.replace("_", " ").upper()
        cards.append(
            _card(
                f'<div style="display:flex; justify-content:space-between; margin-bottom:12px;">'
                f'<span style="font-size:11px; font-weight:700; letter-spacing:0.06em; color:var(--faint);">{_e(label)}</span>'
                f'<span style="font-size:11px; color:var(--faint);">{len(values)} values · {total} tests</span></div>{rows}',
                pad=18,
            )
        )
    grid = "".join(cards)
    return (
        f'<h2 style="font-family:{DISPLAY}; font-size:18px; font-weight:800; margin:8px 0 16px;">Environment Coverage</h2>'
        f'<div style="display:grid; grid-template-columns:1fr 1fr; gap:20px;" class="grid-2">{grid}</div>'
    )


# ============================ EXECUTIVE ====================================


def render_executive(report_data: dict[str, Any]) -> str:
    summary = report_data.get("run", {}).get("summary", {})
    gate = report_data.get("default_gate_status", {})
    qscore = report_data.get("quality_score", {})
    ready = str(gate.get("status", "")).lower() == "passed"
    score = int(round(float(report_data.get("health_score", qscore.get("score", 0)) or 0)))
    verdict_soft = "var(--passSoft)" if ready else "var(--failSoft)"
    verdict_color = "var(--pass)" if ready else "var(--fail)"
    verdict_label = "RELEASE READY" if ready else "RELEASE BLOCKED"

    verdict = (
        '<div style="display:grid; grid-template-columns:1.7fr 1fr; gap:20px; margin-bottom:20px;" class="grid-2">'
        + f'<div style="background:{verdict_soft}; border-radius:16px; padding:26px 28px; display:flex; '
        f'flex-direction:column; justify-content:center;">'
        f'<div style="display:flex; align-items:center; gap:10px;">'
        f'<span style="width:11px; height:11px; border-radius:50%; background:{verdict_color};"></span>'
        f'<span style="font-family:{DISPLAY}; font-size:24px; font-weight:800; color:{verdict_color};">'
        f"{verdict_label}</span></div>"
        f'<p style="font-size:15px; color:var(--text); margin:14px 0 0; line-height:1.5;">'
        f"{_e(_gate_sentence(gate, summary))}</p></div>"
        + _card(
            f'<div style="text-align:center; padding:14px 0;">'
            f'<div style="font-family:{MONO}; font-size:52px; font-weight:600; color:var(--text); line-height:1;">'
            f"{score}</div>"
            f'<div style="font-size:13px; color:var(--muted); margin-top:8px; border-bottom:1px dotted var(--faint); '
            f'display:inline-block; padding-bottom:1px;">Health Score / 100</div></div>'
        )
        + "</div>"
    )

    platforms = report_data.get("platforms", {})
    pcards = []
    for name in ("web", "mobile", "api"):
        bucket = platforms.get(name)
        if not bucket:
            continue
        color = PLATFORM_COLORS[name]
        rate = float(bucket.get("pass_rate", 0))
        pcards.append(
            _card(
                f'<div style="font-family:{DISPLAY}; font-size:15px; font-weight:700; margin-bottom:8px;">'
                f"{name.capitalize()}</div>"
                f'<div style="display:flex; align-items:baseline; gap:10px;">'
                f'<span style="font-family:{MONO}; font-size:30px; font-weight:600; color:{color};">{_fmt_pct(rate)}</span>'
                f'<span style="font-size:12.5px; color:var(--muted);">{bucket.get("total", 0)} tests · '
                f"{bucket.get('failed_broken', 0)} failed</span></div>"
                '<div style="height:8px; border-radius:100px; background:var(--surfaceAlt); overflow:hidden; margin-top:12px;">'
                f'<span style="display:block; height:100%; width:{rate:.1f}%; background:{color}; border-radius:100px;">'
                "</span></div>",
                pad=18,
            )
        )
    platform_row = (
        (
            '<div style="display:grid; grid-template-columns:repeat(3,1fr); gap:20px; margin-bottom:20px;" '
            f'class="grid-3">{"".join(pcards)}</div>'
        )
        if pcards
        else ""
    )

    known = _known_issues_card(report_data)
    changed = _what_changed_card(report_data)
    ownership = _ownership_card(report_data)
    healing = _self_healing_card(report_data)
    coverage_map = _coverage_map_card(report_data)

    main = (
        _page_header(
            _run_eyebrow(report_data),
            "Executive Summary",
            "Release health at a glance, for managers and stakeholders.",
            action=_print_button(),
        )
        + verdict
        + platform_row
        + '<div style="display:grid; grid-template-columns:1fr 1fr; gap:20px; margin-bottom:20px;" class="grid-2">'
        + known
        + changed
        + "</div>"
        + '<div style="display:grid; grid-template-columns:1fr 1fr; gap:20px; margin-bottom:20px;" class="grid-2">'
        + ownership
        + healing
        + "</div>"
        + coverage_map
    )
    return _document(report_data, "executive", "Executive Summary", main)


def _print_button() -> str:
    return (
        '<a href="print-summary.html" style="padding:11px 18px; border-radius:10px; background:var(--surface); '
        "border:1px solid var(--border); color:var(--text); font-size:14px; font-weight:700; text-decoration:none; "
        "font-family:'Manrope',sans-serif; box-shadow:var(--shadow); white-space:nowrap;\">Print / Export Summary</a>"
    )


def _known_issues_card(report_data: dict[str, Any]) -> str:
    known = report_data.get("failure_transitions", {}).get("known_failures", [])
    if not known:
        body = '<p style="font-size:13px; color:var(--faint);">No known issues tracked this run.</p>'
    else:
        rows = "".join(
            '<div style="display:flex; justify-content:space-between; gap:14px; padding:10px 0; '
            'border-top:1px solid var(--border);">'
            f'<a href="{_e(k.get("detail_href", "#"))}" style="font-family:{MONO}; font-size:12.5px; '
            f'color:var(--link); text-decoration:none; overflow-wrap:anywhere; min-width:0;">{_e(k.get("name", ""))}</a>'
            f'<span style="font-family:{MONO}; font-size:12px; color:var(--muted); flex-shrink:0;">'
            f"{_e(k.get('known_issue', ''))}</span></div>"
            for k in known
        )
        body = rows
    return _card(_title("Known Issues") + body)


def _what_changed_card(report_data: dict[str, Any]) -> str:
    transitions = report_data.get("failure_transitions", {})
    counts = transitions.get("counts", {})
    new = _filtered_new_failures(report_data)
    known = transitions.get("known_failures", [])
    resolved_count = counts.get("resolved", 0)

    def links(items: list[dict[str, Any]]) -> str:
        return "".join(
            f'<a href="{_e(i.get("detail_href", "#"))}" style="display:block; font-family:{MONO}; font-size:12.5px; '
            f'color:var(--link); text-decoration:none; overflow-wrap:anywhere; margin:6px 0;">{_e(i.get("name", ""))}</a>'
            for i in items
        )

    body = (
        f'<div style="font-size:13.5px; font-weight:700; color:var(--fail); margin-bottom:4px;">'
        f"New failures ({len(new)})</div>"
        + links(new)
        + f'<div style="font-size:13.5px; font-weight:700; color:var(--flaky); margin:12px 0 4px;">'
        f"Persistent known issues ({counts.get('known', 0)})</div>"
        + links(known)
        + f'<p style="font-size:13px; color:var(--muted); margin:12px 0 0;">{resolved_count} test(s) fixed since '
        "previous run.</p>"
    )
    return _card(_title("What Changed Since Previous Run") + body)


def _ownership_card(report_data: dict[str, Any]) -> str:
    test_index = report_data.get("test_index", [])
    owners: dict[str, list[dict[str, Any]]] = {}
    for t in test_index:
        owner = (t.get("metadata") or {}).get("owner") or t.get("suite") or "unassigned"
        owners.setdefault(owner, []).append(t)
    if not owners:
        return _card(_title("Ownership") + '<p style="font-size:13px; color:var(--faint);">No ownership data.</p>')
    rows = []
    for owner, tests in sorted(owners.items()):
        total = len(tests)
        passed = sum(1 for t in tests if str(t.get("status")).lower() == "passed")
        rate = passed / total * 100 if total else 0
        color = "var(--pass)" if rate == 100 else ("var(--flaky)" if rate >= 50 else "var(--fail)")
        rows.append(
            '<div style="margin-bottom:14px;"><div style="display:flex; justify-content:space-between; '
            'font-size:13px; margin-bottom:6px;">'
            f'<strong style="overflow-wrap:anywhere;">{_e(owner)}</strong>'
            f'<span style="font-family:{MONO}; color:var(--muted);">{_fmt_pct(rate)} · {total} tests</span></div>'
            '<div style="height:8px; border-radius:100px; background:var(--surfaceAlt); overflow:hidden;">'
            f'<span style="display:block; height:100%; width:{rate:.1f}%; background:{color}; border-radius:100px;">'
            "</span></div></div>"
        )
    return _card(_title("Ownership") + "".join(rows))


def _self_healing_card(report_data: dict[str, Any]) -> str:
    signals = report_data.get("signals", {})
    count = int(signals.get("healing_event_count", 0) or 0)
    if not count:
        body = '<p style="font-size:13px; color:var(--muted);">No self-healing events this run.</p>'
    else:
        healed = [t for t in report_data.get("test_index", []) if t.get("healing_event_count")]
        links = "".join(
            f'<a href="{_e(t.get("detail_href", "#"))}" style="display:block; font-family:{MONO}; font-size:12.5px; '
            f'color:var(--link); text-decoration:none; overflow-wrap:anywhere; margin:8px 0;">{_e(t.get("name", ""))} →</a>'
            for t in healed
        )
        body = (
            f'<p style="font-size:13.5px; color:var(--text); margin:0 0 8px; line-height:1.5;">{count} healing '
            "event(s) this run — automatically resolved, no manual fix needed.</p>" + links
        )
    return _card(_title("Self-Healing Effectiveness") + body)


def _coverage_map_card(report_data: dict[str, Any]) -> str:
    domains: dict[str, int] = {}
    for t in report_data.get("test_index", []):
        d = t.get("domain") or "uncategorized"
        domains[d] = domains.get(d, 0) + 1
    chips = "".join(
        f'<span style="display:inline-block; padding:8px 14px; border-radius:100px; background:var(--surfaceAlt); '
        f'font-size:13px; color:var(--text);">{_e(name)} · {count} tests</span>'
        for name, count in sorted(domains.items())
    )
    return _card(
        _title("Coverage Map")
        + '<p style="font-size:13px; color:var(--muted); margin:-8px 0 14px;">Features with automated tests in this '
        "run.</p>" + f'<div style="display:flex; flex-wrap:wrap; gap:10px;">{chips}</div>'
    )


# ============================ QUALITY GATES ================================


def render_quality(report_data: dict[str, Any]) -> str:
    gate = report_data.get("default_gate_status", {})
    ready = str(gate.get("status", "")).lower() == "passed"
    comparison = report_data.get("run_comparison", {})

    gate_cards = []
    for result in gate.get("results", [])[:3]:
        passed = str(result.get("status")).lower() == "passed"
        gate_cards.append(
            _card(
                '<div style="display:flex; justify-content:space-between; align-items:flex-start; gap:12px;">'
                f'<h3 style="font-family:{DISPLAY}; font-size:16px; font-weight:700; margin:0;">{_e(result.get("name", ""))}</h3>'
                + _pill("PASS" if passed else "FAIL", "passed" if passed else "failed")
                + "</div>"
                f'<div style="font-size:13px; color:var(--muted); margin-top:10px;">Expected {_e(result.get("expected", ""))}</div>'
                f'<div style="font-family:{MONO}; font-size:26px; font-weight:600; margin-top:8px; '
                f'color:{"var(--pass)" if passed else "var(--fail)"};">{_e(result.get("actual", ""))}</div>'
            )
        )
    gates_row = (
        '<div style="display:grid; grid-template-columns:repeat(3,1fr); gap:20px; margin-bottom:20px;" '
        f'class="grid-3">{"".join(gate_cards)}</div>'
    )

    comp_table = _run_comparison_table(comparison, report_data)
    failure_cards = _failure_transition_cards(report_data)

    header_pill = _pill("PASSED" if ready else "FAILED", "passed" if ready else "failed")
    main = (
        f'<div style="display:flex; align-items:center; gap:14px; margin-bottom:8px;">{header_pill}'
        f'<span style="font-family:{MONO}; font-size:13px; color:var(--faint);">{_e(_run_eyebrow(report_data))}</span></div>'
        + _page_header("", "Quality Gates", "Numeric release criteria for this run, checked against the previous run.")
        + gates_row
        + comp_table
        + failure_cards
    )
    return _document(report_data, "quality", "Quality Gates", main)


def _run_comparison_table(comparison: dict[str, Any], report_data: dict[str, Any]) -> str:
    metrics = report_data.get("compare", {}).get("metrics", [])
    rows_data = []
    if metrics:
        for m in metrics:
            rows_data.append(
                (
                    m.get("label", ""),
                    m.get("current", ""),
                    m.get("previous", ""),
                    m.get("delta_display", m.get("delta", "")),
                    m.get("direction", ""),
                )
            )
    if not rows_data:
        return ""
    body = ""
    for label, cur, prev, delta, direction in rows_data:
        good = direction == "up"
        dcolor = (
            "var(--muted)" if not delta or str(delta) in ("0", "0%") else ("var(--pass)" if good else "var(--fail)")
        )
        body += (
            '<tr><td style="padding:14px 16px; font-weight:600; border-top:1px solid var(--border);">'
            f"{_e(label)}</td>"
            f'<td style="padding:14px 16px; text-align:right; font-family:{MONO}; border-top:1px solid var(--border);">'
            f"{_e(cur)}</td>"
            f'<td style="padding:14px 16px; text-align:right; font-family:{MONO}; color:var(--muted); '
            f'border-top:1px solid var(--border);">{_e(prev)}</td>'
            f'<td style="padding:14px 16px; text-align:right; font-family:{MONO}; color:{dcolor}; font-weight:600; '
            f'border-top:1px solid var(--border);">{_e(delta)}</td></tr>'
        )
    head = "".join(
        f'<th style="padding:12px 16px; text-align:{a}; font-size:11px; font-weight:700; letter-spacing:0.05em; '
        f'text-transform:uppercase; color:var(--faint); background:var(--surfaceAlt);">{h}</th>'
        for h, a in (("Metric", "left"), ("Current", "right"), ("Previous", "right"), ("Delta", "right"))
    )
    return _card(
        _title("Run Comparison")
        + '<div style="overflow-x:auto;"><table style="width:100%; border-collapse:collapse; font-size:13.5px;">'
        f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>",
        extra="margin-bottom:20px;",
    )


def _quarantined_test_ids(report_data: dict[str, Any]) -> set:
    ids = set()
    for item in report_data.get("test_index", []):
        metadata = item.get("metadata") or {}
        if metadata.get("quarantined") or metadata.get("known_issue"):
            ids.add(item.get("test_id"))
    return ids


def _filtered_new_failures(report_data: dict[str, Any]) -> list[dict[str, Any]]:
    """New failures excluding known/quarantined tests — matches the release gate."""

    excluded = _quarantined_test_ids(report_data)
    return [
        failure
        for failure in report_data.get("failure_transitions", {}).get("new_failures", []) or []
        if failure.get("test_id") not in excluded and not failure.get("known_issue")
    ]


def _failure_transition_cards(report_data: dict[str, Any]) -> str:
    transitions = report_data.get("failure_transitions", {})

    def col(title: str, items: list[dict[str, Any]], color: str, detail_key: str = "") -> str:
        if not items:
            body = '<p style="font-size:13px; color:var(--faint); font-style:italic;">None.</p>'
        else:
            body = "".join(
                '<div style="padding:10px 0; border-top:1px solid var(--border);">'
                f'<a href="{_e(i.get("detail_href", "#"))}" style="font-family:{MONO}; font-size:12.5px; '
                f'color:var(--link); text-decoration:none; overflow-wrap:anywhere; display:block;">{_e(i.get("name", ""))}</a>'
                + (
                    f'<div style="font-size:12px; color:var(--muted); margin-top:4px;">'
                    f"{_e(i.get('failure_category', ''))}"
                    + (f" · {_e(i.get('failure_message', ''))}" if i.get("failure_message") else "")
                    + "</div>"
                    if i.get("failure_category") or i.get("failure_message")
                    else ""
                )
                + "</div>"
                for i in items
            )
        return _card(
            f'<h2 style="font-family:{DISPLAY}; font-size:16px; font-weight:700; margin:0 0 4px; color:{color};">'
            f"{_e(title)}</h2>{body}"
        )

    return (
        '<div style="display:grid; grid-template-columns:repeat(3,1fr); gap:20px;" class="grid-3">'
        + col("New Unresolved Failures", _filtered_new_failures(report_data), "var(--fail)")
        + col("Known & Tracked Failures", transitions.get("known_failures", []), "var(--flaky)")
        + col("Resolved Since Previous Run", transitions.get("resolved_failures", []), "var(--pass)")
        + "</div>"
    )


# ============================ TESTS EXPLORE ================================


def render_explore(report_data: dict[str, Any]) -> str:
    filters = report_data.get("aggregates", {}).get("filter_options", {})

    def sel(id_: str, label: str, options: list[str]) -> str:
        opts = f'<option value="">{_e(label)}</option>' + "".join(
            f'<option value="{_e(o)}">{_e(o)}</option>' for o in options
        )
        return (
            f'<select id="{id_}" style="padding:11px 14px; border-radius:9px; border:1px solid var(--border); '
            f"background:var(--surface); color:var(--text); font-size:13px; font-family:inherit; cursor:pointer; "
            f'min-width:0;">{opts}</select>'
        )

    toolbar = _card(
        '<input id="ex-search" type="search" placeholder="Name, suite, status, failure..." '
        'style="width:100%; padding:13px 16px; border-radius:10px; border:1px solid var(--border); '
        'background:var(--surface); color:var(--text); font-size:15px; font-family:inherit; margin-bottom:12px;">'
        '<div style="display:grid; grid-template-columns:repeat(5,1fr); gap:12px;" class="grid-5">'
        + sel("ex-status", "All statuses", filters.get("status", []))
        + sel("ex-platform", "All platforms", ["web", "mobile", "api"])
        + sel("ex-domain", "All domains", filters.get("domain", []))
        + sel("ex-profile", "All profiles", filters.get("profile", []))
        + sel("ex-failure", "All failures", filters.get("failure_category", []))
        + sel("ex-flaky", "All flaky", filters.get("flaky_category", []))
        + sel("ex-artifact", "All artifacts", filters.get("artifact_type", []))
        + sel("ex-duration", "All durations", ["<1s", "1-5s", "5-15s", "15-30s", "30s+"])
        + '<select id="ex-sort" style="padding:11px 14px; border-radius:9px; border:1px solid var(--border); '
        'background:var(--surface); color:var(--text); font-size:13px; font-family:inherit; cursor:pointer;">'
        '<option value="status">Sort: Status</option><option value="duration_desc">Sort: Slowest</option>'
        '<option value="duration_asc">Sort: Fastest</option><option value="name">Sort: Name</option></select>'
        '<button type="button" id="ex-reset" style="padding:11px 14px; border-radius:9px; border:1px solid '
        "var(--border); background:var(--surface); color:var(--text); font-size:13px; font-weight:700; "
        'cursor:pointer; font-family:inherit;">Reset</button>'
        "</div>"
    )

    main = (
        _page_header(
            _run_eyebrow(report_data), "Tests Explore", "Search, filter, sort, and inspect every test in this run."
        )
        + toolbar
        + '<div id="ex-count" style="font-size:13px; color:var(--muted); margin:16px 0;"></div>'
        + '<div style="display:grid; grid-template-columns:repeat(3,1fr); gap:20px; margin-bottom:20px;" class="grid-3">'
        + _card(_title("Filtered Status", 15) + '<div id="ex-status-chart"></div>')
        + _card(_title("Filtered Duration", 15) + '<div id="ex-duration-chart"></div>')
        + _card(_title("Filtered Failures", 15) + '<div id="ex-failure-chart"></div>')
        + "</div>"
        + _card('<div id="ex-table" style="overflow-x:auto;"></div>', pad=0, extra="overflow:hidden;")
    )
    return _document(report_data, "explore", "Tests Explore", main, scripts=_EXPLORE_JS)


_EXPLORE_JS = r"""
function rd(){var n=document.getElementById('report-data');return n?JSON.parse(n.textContent):{test_index:[]};}
function esc(v){var t=(v==null?'':String(v));return t.replace(/[&<>"']/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
function fdur(ms){ms=Number(ms)||0;if(ms<1000)return Math.round(ms)+'ms';var s=ms/1000;if(s<60)return (Math.round(s*10)/10)+'s';return (Math.round(s/60*10)/10)+'m';}
function statusColors(s){return {passed:['var(--pass)','var(--passSoft)'],failed:['var(--fail)','var(--failSoft)'],broken:['var(--broken)','var(--brokenSoft)'],skipped:['var(--skip)','var(--skipSoft)']}[String(s).toLowerCase()]||['var(--muted)','var(--surfaceAlt)'];}
function countBy(items,fn){return items.reduce(function(a,x){var k=fn(x);if(!k)return a;a[k]=(a[k]||0)+1;return a;},{});}
function bars(obj,color){var e=Object.entries(obj).filter(function(x){return x[1];});if(!e.length)return '<p style="font-size:13px;color:var(--faint);">No data.</p>';var mx=Math.max.apply(null,e.map(function(x){return x[1];}));
 return e.map(function(x){return '<div style="display:flex;align-items:center;gap:12px;margin-bottom:10px;"><span style="width:130px;font-size:12.5px;color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="'+esc(x[0])+'">'+esc(x[0])+'</span><div style="flex:1;height:10px;border-radius:100px;background:var(--surfaceAlt);overflow:hidden;"><span style="display:block;height:100%;width:'+(x[1]/mx*100)+'%;background:'+color+';border-radius:100px;"></span></div><strong style="font-family:\'IBM Plex Mono\',monospace;font-size:12.5px;min-width:20px;text-align:right;">'+x[1]+'</strong></div>';}).join('');}
function render(){
  var items=rd().test_index||[];
  var q=(document.getElementById('ex-search').value||'').toLowerCase();
  function val(id){return document.getElementById(id).value;}
  var f={status:val('ex-status'),platform:val('ex-platform'),domain:val('ex-domain'),profile:val('ex-profile'),failure:val('ex-failure'),flaky:val('ex-flaky'),artifact:val('ex-artifact'),duration:val('ex-duration')};
  var out=items.filter(function(t){
    return (!q||(t.search_text||'').indexOf(q)>=0)
      &&(!f.status||t.status===f.status)&&(!f.platform||t.platform_type===f.platform)
      &&(!f.domain||t.domain===f.domain)&&(!f.profile||t.profile===f.profile)
      &&(!f.failure||((t.failure||{}).category)===f.failure)
      &&(!f.flaky||(t.flaky_categories||[]).indexOf(f.flaky)>=0)
      &&(!f.artifact||(t.artifact_types||[]).indexOf(f.artifact)>=0)
      &&(!f.duration||t.duration_bucket===f.duration);
  });
  var sort=val('ex-sort');
  out.sort(function(a,b){if(sort==='duration_desc')return b.duration_ms-a.duration_ms;if(sort==='duration_asc')return a.duration_ms-b.duration_ms;if(sort==='name')return String(a.name).localeCompare(b.name);return String(a.status).localeCompare(b.status);});
  document.getElementById('ex-count').textContent=out.length+' test'+(out.length===1?'':'s');
  document.getElementById('ex-status-chart').innerHTML=bars(countBy(out,function(t){return t.status;}),'var(--pass)');
  document.getElementById('ex-duration-chart').innerHTML=bars(countBy(out,function(t){return t.duration_bucket;}),'var(--accent)');
  document.getElementById('ex-failure-chart').innerHTML=bars(countBy(out,function(t){return (t.failure||{}).category;}),'var(--fail)');
  var head=['Status','Test','Platform','Domain','Duration','Failure'].map(function(h){return '<th style="padding:14px 16px;text-align:left;font-size:11px;font-weight:700;letter-spacing:0.05em;text-transform:uppercase;color:var(--faint);background:var(--surfaceAlt);">'+h+'</th>';}).join('');
  var rows=out.map(function(t){var sc=statusColors(t.status);
    var known=(t.metadata||{}).known_issue?'<div style="font-family:\'IBM Plex Mono\',monospace;font-size:11px;color:var(--flaky);margin-top:4px;">Known Issue · '+esc((t.metadata||{}).known_issue)+'</div>':'';
    return '<tr><td style="padding:14px 16px;border-top:1px solid var(--border);vertical-align:top;"><span style="display:inline-block;padding:3px 9px;border-radius:100px;font-family:\'IBM Plex Mono\',monospace;font-size:11px;font-weight:700;background:'+sc[1]+';color:'+sc[0]+';">'+esc(t.status)+'</span></td>'
      +'<td style="padding:14px 16px;border-top:1px solid var(--border);max-width:300px;"><a href="'+esc(t.detail_href||'#')+'" title="'+esc(t.name)+'" style="font-family:\'IBM Plex Mono\',monospace;font-size:12.5px;color:var(--link);text-decoration:none;display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">'+esc(t.name)+'</a><span style="font-family:\'IBM Plex Mono\',monospace;font-size:11.5px;color:var(--faint);">'+esc(t.suite||'')+'</span>'+known+'</td>'
      +'<td style="padding:14px 16px;border-top:1px solid var(--border);font-weight:600;">'+esc((t.platform_type||'').charAt(0).toUpperCase()+(t.platform_type||'').slice(1))+'</td>'
      +'<td style="padding:14px 16px;border-top:1px solid var(--border);font-family:\'IBM Plex Mono\',monospace;font-size:12px;color:var(--muted);max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="'+esc(t.domain||'')+'">'+esc(t.domain||'-')+'</td>'
      +'<td style="padding:14px 16px;border-top:1px solid var(--border);font-family:\'IBM Plex Mono\',monospace;">'+fdur(t.duration_ms)+'</td>'
      +'<td style="padding:14px 16px;border-top:1px solid var(--border);font-size:12.5px;color:var(--muted);max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="'+esc((t.failure||{}).title||'')+'">'+esc((t.failure||{}).title||'—')+'</td></tr>';
  }).join('')||'<tr><td colspan="6" style="padding:40px;text-align:center;color:var(--faint);">No tests match the filters.</td></tr>';
  document.getElementById('ex-table').innerHTML='<table style="width:100%;border-collapse:collapse;font-size:13.5px;"><thead><tr>'+head+'</tr></thead><tbody>'+rows+'</tbody></table>';
}
function setupPage(){
  var ids=['ex-search','ex-status','ex-platform','ex-domain','ex-profile','ex-failure','ex-flaky','ex-artifact','ex-duration','ex-sort'];
  ids.forEach(function(id){var n=document.getElementById(id);if(n){n.addEventListener('input',render);n.addEventListener('change',render);}});
  var params=new URLSearchParams(location.search);if(params.get('q'))document.getElementById('ex-search').value=params.get('q');
  document.getElementById('ex-reset').addEventListener('click',function(){ids.forEach(function(id){var n=document.getElementById(id);if(n)n.value='';});document.getElementById('ex-sort').value='status';render();});
  render();
}
"""


# ============================ TIMELINE =====================================


def render_timeline(report_data: dict[str, Any]) -> str:
    main = (
        _page_header(_run_eyebrow(report_data), "Timeline", "Execution sequence for every test, grouped by test.")
        + _card(
            '<input id="tl-search" type="search" placeholder="Search test or event" '
            'style="width:100%; padding:13px 16px; border-radius:10px; border:1px solid var(--border); '
            'background:var(--surface); color:var(--text); font-size:15px; font-family:inherit;">'
        )
        + '<div id="tl-list" style="margin-top:20px; display:flex; flex-direction:column; gap:16px;"></div>'
    )
    return _document(report_data, "timeline", "Timeline", main, scripts=_TIMELINE_JS)


_TIMELINE_JS = r"""
function rd(){var n=document.getElementById('report-data');return n?JSON.parse(n.textContent):{};}
function esc(v){var t=(v==null?'':String(v));return t.replace(/[&<>"']/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
function fdur(ms){ms=Number(ms)||0;if(ms<1000)return (Math.round(ms/100)/10)+'s';var s=ms/1000;if(s<60)return (Math.round(s*10)/10)+'s';return (Math.round(s/60*10)/10)+'m';}
function statusColor(s){return {passed:'var(--pass)',failed:'var(--fail)',broken:'var(--broken)',skipped:'var(--skip)'}[String(s).toLowerCase()]||'var(--muted)';}
function statusSoft(s){return {passed:'var(--passSoft)',failed:'var(--failSoft)',broken:'var(--brokenSoft)',skipped:'var(--skipSoft)'}[String(s).toLowerCase()]||'var(--surfaceAlt)';}
function evLabel(e){if(e.name)return e.name;var m={test_started:'Started',test_finished:'Finished',started:'Started',finished:'Finished',artifact:'Artifact captured',test_retry:'Retry attempt',action_retry:'Action retry',healing:'Self-healing',step:'Step'};var t=String(e.event_type||'').toLowerCase();return m[t]||(t.replace(/_/g,' ').replace(/\b\w/g,function(c){return c.toUpperCase();}))||'Event';}
function render(){
  var d=rd();var events=(d.timeline||{}).events||[];var tests=d.test_index||[];
  var byId={};tests.forEach(function(t){byId[t.test_id]=t;});
  var groups={};events.forEach(function(e){var k=e.test_id||e.test||'';(groups[k]=groups[k]||[]).push(e);});
  var q=(document.getElementById('tl-search').value||'').toLowerCase();
  var html=tests.map(function(t){
    var evs=groups[t.test_id]||[];
    var hay=(t.name+' '+evs.map(function(e){return e.name||e.event_type;}).join(' ')).toLowerCase();
    if(q&&hay.indexOf(q)<0)return '';
    var col=statusColor(t.status);
    var steps=evs.length?evs:[{name:'Started',event_type:'started'},{name:'Finished',event_type:'finished'}];
    var stepper=steps.map(function(e,i){
      var ec=/fail|error|broken|retry/.test((e.event_type||e.name||'').toLowerCase())?'var(--fail)':(/(artifact|capture)/.test((e.event_type||'').toLowerCase())?'var(--accent)':col);
      var connector=i<steps.length-1?'<div style="flex:1;height:2px;background:var(--border);margin:0 8px;align-self:flex-start;margin-top:6px;"></div>':'';
      var ts=e.offset_ms!=null?fdur(e.offset_ms):(e.timestamp?'':'');
      return '<div style="display:flex;flex-direction:column;align-items:center;text-align:center;min-width:110px;"><span style="width:13px;height:13px;border-radius:50%;background:'+ec+';"></span><strong style="font-size:12.5px;margin-top:8px;">'+esc(evLabel(e))+'</strong><span style="font-family:\'IBM Plex Mono\',monospace;font-size:11.5px;color:var(--faint);margin-top:3px;">'+esc(ts)+'</span></div>'+connector;
    }).join('');
    return '<div style="background:var(--surface);border:1px solid var(--border);border-radius:16px;box-shadow:var(--shadow);padding:22px;">'
      +'<div style="display:flex;align-items:center;gap:12px;margin-bottom:18px;flex-wrap:wrap;"><span style="display:inline-block;padding:3px 9px;border-radius:100px;font-family:\'IBM Plex Mono\',monospace;font-size:11px;font-weight:700;background:'+statusSoft(t.status)+';color:'+col+';">'+esc(t.status)+'</span>'
      +'<a href="'+esc(t.detail_href||'#')+'" style="font-family:\'IBM Plex Mono\',monospace;font-size:14px;font-weight:600;color:var(--link);text-decoration:none;overflow-wrap:anywhere;">'+esc(t.name)+'</a>'
      +'<span style="font-family:\'IBM Plex Mono\',monospace;font-size:12px;color:var(--faint);">'+esc(t.suite||'')+'</span>'
      +'<span style="margin-left:auto;font-family:\'IBM Plex Mono\',monospace;font-size:13px;color:var(--muted);">'+fdur(t.duration_ms)+'</span></div>'
      +'<div style="display:flex;align-items:flex-start;flex-wrap:wrap;gap:4px;">'+stepper+'</div></div>';
  }).join('');
  document.getElementById('tl-list').innerHTML=html||'<p style="font-size:14px;color:var(--faint);padding:40px;text-align:center;">No tests match your search.</p>';
}
function setupPage(){document.getElementById('tl-search').addEventListener('input',render);render();}
"""


# ============================ FLAKY ========================================


def render_flaky(report_data: dict[str, Any]) -> str:
    breakdown = report_data.get("flaky", {}).get("breakdown", {})
    tiles_def = [
        ("test_retry_flaky", "Test Retry Flaky"),
        ("action_retry_flaky", "Action Retry Flaky"),
        ("skipped_flaky", "Skipped"),
        ("always_failing", "Always Failing"),
        ("slow_but_passing", "Slow But Passing"),
    ]
    tiles = "".join(
        '<div style="flex:1; min-width:150px; background:var(--surface); border:1px solid var(--border); '
        'border-radius:16px; box-shadow:var(--shadow); padding:20px;">'
        f'<div style="font-family:{MONO}; font-size:28px; font-weight:600;">{int(breakdown.get(key, 0) or 0)}</div>'
        f'<div style="font-size:12.5px; color:var(--muted); margin-top:6px;">{label}</div></div>'
        for key, label in tiles_def
    )
    quarantined = [t for t in report_data.get("test_index", []) if (t.get("metadata") or {}).get("quarantined")]
    quar_rows = (
        "".join(
            '<div style="display:flex; justify-content:space-between; gap:14px; padding:12px 0; '
            'border-top:1px solid var(--border);">'
            f'<a href="{_e(t.get("detail_href", "#"))}" style="font-family:{MONO}; font-size:13px; color:var(--link); '
            f'text-decoration:none; overflow-wrap:anywhere; min-width:0;">{_e(t.get("name", ""))}</a>'
            f'<span style="font-family:{MONO}; font-size:12px; color:var(--faint); flex-shrink:0;">always_failing</span></div>'
            for t in quarantined
        )
        or '<p style="font-size:13px; color:var(--faint);">No quarantined tests.</p>'
    )
    quar = _card(
        f'<div style="display:flex; justify-content:space-between; align-items:center;">'
        f'<h2 style="font-family:{DISPLAY}; font-size:16px; font-weight:700; margin:0;">Quarantined Tests</h2>'
        f'<span style="font-family:{MONO}; font-size:16px; color:var(--muted);">{len(quarantined)}</span></div>'
        '<p style="font-size:13px; color:var(--muted); margin:6px 0 8px;">Excluded from the release gate\'s pass-rate '
        "calculation until fixed.</p>" + quar_rows,
        extra="margin-bottom:20px;",
    )
    clusters = report_data.get("failure_clusters", [])
    cluster_cards = "".join(
        _card(
            f'<div style="font-family:{DISPLAY}; font-size:15px; font-weight:700; margin-bottom:8px;">'
            f"{_e(c.get('category', ''))} · {int(c.get('count', 0) or 0)}</div>"
            f'<div style="font-family:{MONO}; font-size:13px; color:var(--fail); line-height:1.5; overflow-wrap:anywhere;">'
            f"{_e(c.get('signature', c.get('message', '')))}</div>"
            f'<p style="font-size:13px; color:var(--muted); margin:10px 0 0; line-height:1.5;">'
            f"{_e(c.get('recommendation', 'Review failure output and artifacts.'))}</p>"
        )
        for c in clusters[:2]
    )
    cluster_row = (
        (
            f'<div style="display:grid; grid-template-columns:1fr 1fr; gap:20px; margin-bottom:20px;" '
            f'class="grid-2">{cluster_cards}</div>'
        )
        if cluster_cards
        else ""
    )

    main = (
        _page_header(
            _run_eyebrow(report_data),
            "Flaky Analysis",
            "Flaky signals: retry-based, always-failing, and slow-but-passing.",
        )
        + f'<div style="display:flex; flex-wrap:wrap; gap:14px; margin-bottom:20px;">{tiles}</div>'
        + quar
        + cluster_row
        + _card(
            '<input id="fl-search" type="search" placeholder="Category, test, reason, status" '
            'style="width:100%; padding:13px 16px; border-radius:10px; border:1px solid var(--border); '
            'background:var(--surface); color:var(--text); font-size:15px; font-family:inherit;">',
            extra="margin-bottom:20px;",
        )
        + _card('<div id="fl-table" style="overflow-x:auto;"></div>', pad=0, extra="overflow:hidden;")
    )
    return _document(report_data, "flaky", "Flaky Analysis", main, scripts=_FLAKY_JS)


_FLAKY_JS = r"""
function rd(){var n=document.getElementById('report-data');return n?JSON.parse(n.textContent):{};}
function esc(v){var t=(v==null?'':String(v));return t.replace(/[&<>"']/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
function fdur(ms){ms=Number(ms)||0;if(ms<1000)return (Math.round(ms/100)/10)+'s';var s=ms/1000;if(s<60)return (Math.round(s*10)/10)+'s';return (Math.round(s/60*10)/10)+'m';}
function sc(s){return {passed:['var(--pass)','var(--passSoft)'],failed:['var(--fail)','var(--failSoft)'],broken:['var(--broken)','var(--brokenSoft)'],skipped:['var(--skip)','var(--skipSoft)']}[String(s).toLowerCase()]||['var(--muted)','var(--surfaceAlt)'];}
function render(){
  var d=rd();var items=(d.flaky||{}).items||[];var q=(document.getElementById('fl-search').value||'').toLowerCase();
  var out=items.filter(function(i){return !q||((i.category+' '+i.name+' '+(i.reason||'')+' '+(i.status||'')).toLowerCase().indexOf(q)>=0);});
  var head=['Category','Test','Status','Duration','Reason'].map(function(h){return '<th style="padding:14px 16px;text-align:left;font-size:11px;font-weight:700;letter-spacing:0.05em;text-transform:uppercase;color:var(--faint);background:var(--surfaceAlt);">'+h+'</th>';}).join('');
  var rows=out.map(function(i){var c=sc(i.status);
    return '<tr><td style="padding:14px 16px;border-top:1px solid var(--border);font-family:\'IBM Plex Mono\',monospace;font-size:12px;color:var(--muted);">'+esc(i.category)+'</td>'
      +'<td style="padding:14px 16px;border-top:1px solid var(--border);max-width:280px;"><a href="'+esc(i.detail_href||'#')+'" title="'+esc(i.name)+'" style="display:block;font-family:\'IBM Plex Mono\',monospace;font-size:12.5px;color:var(--link);text-decoration:none;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">'+esc(i.name)+'</a></td>'
      +'<td style="padding:14px 16px;border-top:1px solid var(--border);"><span style="display:inline-block;padding:3px 9px;border-radius:100px;font-family:\'IBM Plex Mono\',monospace;font-size:11px;font-weight:700;background:'+c[1]+';color:'+c[0]+';">'+esc(i.status)+'</span></td>'
      +'<td style="padding:14px 16px;border-top:1px solid var(--border);font-family:\'IBM Plex Mono\',monospace;">'+fdur(i.duration_ms)+'</td>'
      +'<td style="padding:14px 16px;border-top:1px solid var(--border);font-size:12.5px;color:var(--muted);overflow-wrap:anywhere;max-width:280px;">'+esc(i.reason||'')+'</td></tr>';
  }).join('')||'<tr><td colspan="5" style="padding:40px;text-align:center;color:var(--faint);">No flaky signals match.</td></tr>';
  document.getElementById('fl-table').innerHTML='<table style="width:100%;border-collapse:collapse;font-size:13.5px;"><thead><tr>'+head+'</tr></thead><tbody>'+rows+'</tbody></table>';
}
function setupPage(){document.getElementById('fl-search').addEventListener('input',render);render();}
"""


# ============================ MATRIX =======================================


def render_matrix(report_data: dict[str, Any]) -> str:
    main = (
        _page_header(_run_eyebrow(report_data), "Matrix", "Pass rate broken down by dimension.")
        + _card(
            '<input id="mx-search" type="search" placeholder="Search this dimension\'s values or failure categories" '
            'style="width:100%; padding:13px 16px; border-radius:10px; border:1px solid var(--border); '
            'background:var(--surface); color:var(--text); font-size:15px; font-family:inherit;">',
            extra="margin-bottom:20px;",
        )
        + '<div id="mx-tabs" style="display:flex; gap:4px; background:var(--surfaceAlt); padding:5px; '
        'border-radius:12px; margin-bottom:20px; flex-wrap:wrap;"></div>'
        + '<div id="mx-cards" style="display:grid; grid-template-columns:repeat(3,1fr); gap:18px; '
        'margin-bottom:20px;" class="grid-3"></div>'
        + _card('<div id="mx-table" style="overflow-x:auto;"></div>', pad=0, extra="overflow:hidden;")
    )
    return _document(report_data, "matrix", "Matrix", main, scripts=_MATRIX_JS)


_MATRIX_JS = r"""
function rd(){var n=document.getElementById('report-data');return n?JSON.parse(n.textContent):{};}
function esc(v){var t=(v==null?'':String(v));return t.replace(/[&<>"']/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
function rateColor(r){return r>=80?'var(--pass)':(r>=50?'var(--flaky)':'var(--fail)');}
var mxState={dim:'',q:''};
function labelize(k){return k.replace(/_/g,' ').replace(/\b\w/g,function(c){return c.toUpperCase();});}
function render(){
  var d=rd();var matrix=d.matrix||{};var dims=Object.keys(matrix).filter(function(k){return matrix[k]&&Object.keys(matrix[k]).length;});
  if(!dims.length){document.getElementById('mx-tabs').innerHTML='';document.getElementById('mx-cards').innerHTML='';document.getElementById('mx-table').innerHTML='<p style="font-size:14px;color:var(--faint);padding:40px;text-align:center;">No dimension data captured for this run.</p>';return;}
  if(dims.indexOf(mxState.dim)<0)mxState.dim=dims[0];
  document.getElementById('mx-tabs').innerHTML=dims.map(function(k){var on=k===mxState.dim;
    return '<button type="button" data-dim="'+esc(k)+'" style="flex:0 0 auto;padding:9px 16px;border:0;border-radius:8px;font-size:13.5px;font-weight:600;cursor:pointer;font-family:inherit;background:'+(on?'var(--accentSoft)':'transparent')+';color:'+(on?'var(--accent)':'var(--muted)')+';">'+labelize(k)+'</button>';
  }).join('');
  var data=matrix[mxState.dim]||{};
  var entries=Object.entries(data).filter(function(e){var hay=(e[0]+' '+Object.keys(e[1].failure_categories||{}).join(' ')).toLowerCase();return !mxState.q||hay.indexOf(mxState.q)>=0;});
  document.getElementById('mx-cards').innerHTML=entries.slice(0,3).map(function(e){var v=e[1];var rate=v.pass_rate||0;var col=rateColor(rate);var fc=Object.entries(v.failure_categories||{}).map(function(x){return x[0]+': '+x[1];}).join(', ');
    return '<div style="background:var(--surface);border:1px solid var(--border);border-radius:16px;box-shadow:var(--shadow);padding:20px;"><div style="display:flex;justify-content:space-between;gap:12px;align-items:flex-start;"><strong style="font-family:\'Manrope\',sans-serif;font-size:15px;overflow-wrap:anywhere;min-width:0;">'+esc(e[0])+'</strong><span style="font-family:\'IBM Plex Mono\',monospace;font-weight:700;color:'+col+';flex-shrink:0;">'+Math.round(rate)+'%</span></div>'
      +'<div style="height:8px;border-radius:100px;background:var(--surfaceAlt);overflow:hidden;margin:14px 0 12px;"><span style="display:block;height:100%;width:'+rate+'%;background:'+col+';border-radius:100px;"></span></div>'
      +'<div style="font-family:\'IBM Plex Mono\',monospace;font-size:12px;color:var(--muted);">'+v.total+' tests · '+(v.failed+ (v.broken||0))+' failed</div>'
      +'<div style="font-family:\'IBM Plex Mono\',monospace;font-size:11.5px;color:var(--faint);margin-top:4px;overflow-wrap:anywhere;">'+esc(fc||'-')+'</div></div>';
  }).join('');
  var head=['Name','Total','Passed','Failed','Pass Rate','Failure Categories'].map(function(h,i){return '<th style="padding:14px 16px;text-align:'+(i===0||i===5?'left':'center')+';font-size:11px;font-weight:700;letter-spacing:0.05em;text-transform:uppercase;color:var(--faint);background:var(--surfaceAlt);">'+h+'</th>';}).join('');
  var rows=entries.map(function(e){var v=e[1];var rate=v.pass_rate||0;var col=rateColor(rate);var fc=Object.entries(v.failure_categories||{}).map(function(x){return x[0]+': '+x[1];}).join(', ');
    return '<tr><td style="padding:14px 16px;border-top:1px solid var(--border);font-weight:600;overflow-wrap:anywhere;max-width:300px;">'+esc(e[0])+'</td>'
      +'<td style="padding:14px 16px;border-top:1px solid var(--border);text-align:center;font-family:\'IBM Plex Mono\',monospace;">'+v.total+'</td>'
      +'<td style="padding:14px 16px;border-top:1px solid var(--border);text-align:center;font-family:\'IBM Plex Mono\',monospace;">'+v.passed+'</td>'
      +'<td style="padding:14px 16px;border-top:1px solid var(--border);text-align:center;font-family:\'IBM Plex Mono\',monospace;">'+(v.failed+(v.broken||0))+'</td>'
      +'<td style="padding:14px 16px;border-top:1px solid var(--border);text-align:center;font-family:\'IBM Plex Mono\',monospace;font-weight:700;color:'+col+';">'+Math.round(rate)+'%</td>'
      +'<td style="padding:14px 16px;border-top:1px solid var(--border);font-family:\'IBM Plex Mono\',monospace;font-size:12px;color:var(--muted);overflow-wrap:anywhere;max-width:240px;">'+esc(fc||'-')+'</td></tr>';
  }).join('')||'<tr><td colspan="6" style="padding:40px;text-align:center;color:var(--faint);">No values match.</td></tr>';
  document.getElementById('mx-table').innerHTML='<table style="width:100%;border-collapse:collapse;font-size:13.5px;"><thead><tr>'+head+'</tr></thead><tbody>'+rows+'</tbody></table>';
  document.querySelectorAll('[data-dim]').forEach(function(b){b.addEventListener('click',function(){mxState.dim=b.dataset.dim;render();});});
}
function setupPage(){document.getElementById('mx-search').addEventListener('input',function(e){mxState.q=e.target.value.toLowerCase();render();});render();}
"""


# ============================ HISTORY ======================================


def render_history(report_data: dict[str, Any]) -> str:
    trend_pts = report_data.get("history", {}).get("trend_points", [])
    health = report_data.get("run", {}).get("health", {})
    current_id = report_data.get("run", {}).get("summary", {}).get("run_id", "")

    legend = "".join(
        f'<span style="display:inline-flex; align-items:center; gap:7px; font-size:13px; color:var(--muted);">'
        f'<i style="width:9px; height:9px; border-radius:50%; background:{PLATFORM_COLORS[p]}; display:inline-block;"></i>'
        f"{p.capitalize()} · <strong>{_fmt_pct(_last_platform_rate(trend_pts, p))}</strong></span>"
        for p in ("web", "mobile", "api")
        if any((tp.get("platforms") or {}).get(p) for tp in trend_pts)
    )
    trend_cards = "".join(
        f'<div style="background:var(--surfaceAlt); border-radius:12px; padding:16px;">'
        f'<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">'
        f'<span style="display:inline-flex; align-items:center; gap:8px; font-size:14px; font-weight:600;">'
        f'<i style="width:9px; height:9px; border-radius:50%; background:{PLATFORM_COLORS[p]};"></i>{p.capitalize()}</span>'
        f'<strong style="font-family:{MONO}; font-size:18px; color:{PLATFORM_COLORS[p]};">'
        f"{_fmt_pct(_last_platform_rate(trend_pts, p))}</strong></div>"
        f"{_area_svg([float((tp.get('platforms') or {}).get(p, {}).get('pass_rate', 0)) for tp in trend_pts if (tp.get('platforms') or {}).get(p)], PLATFORM_COLORS[p], w=300, h=120)}"
        f'<div style="font-size:11.5px; color:var(--faint); margin-top:8px;">'
        f"{sum(1 for tp in trend_pts if (tp.get('platforms') or {}).get(p))} run(s) with {p.capitalize()} tests.</div></div>"
        for p in ("web", "mobile", "api")
        if any((tp.get("platforms") or {}).get(p) for tp in trend_pts)
    )
    trend_card = _card(
        _title("Pass Rate Trend")
        + f'<div style="display:grid; grid-template-columns:repeat(3,1fr); gap:16px;" class="grid-3">{trend_cards}</div>'
        + f'<div style="display:flex; gap:20px; flex-wrap:wrap; margin-top:16px;">{legend}</div>'
        + f'<p style="font-size:11.5px; color:var(--faint); margin:14px 0 0;">Each line shows one platform\'s pass rate '
        f"across every run that included it, across {len(trend_pts)} recorded run(s) total.</p>",
        extra="margin-bottom:20px;",
    )

    chips = "".join(
        f'<div style="background:var(--surface); border:1px solid var(--border); border-radius:12px; '
        f'box-shadow:var(--shadow); padding:14px 18px; display:flex; align-items:center; gap:10px;">'
        f'<span style="font-size:13px; color:var(--muted);">{label}</span>'
        f'<strong style="font-family:{MONO}; font-size:15px; color:{color};">{val}</strong></div>'
        for label, val, color in [
            (
                "Pass Rate",
                _signed(health.get("pass_rate_delta"), "%") or "0%",
                "var(--fail)" if (health.get("pass_rate_delta") or 0) < 0 else "var(--pass)",
            ),
            (
                "Failed",
                _signed(health.get("failed_delta")) or "0",
                "var(--fail)" if (health.get("failed_delta") or 0) > 0 else "var(--pass)",
            ),
            (
                "Flaky",
                _signed(health.get("flaky_delta")) or "0",
                "var(--fail)" if (health.get("flaky_delta") or 0) > 0 else "var(--pass)",
            ),
            (
                "Duration",
                _signed_dur(health.get("duration_delta_ms")) or "0s",
                "var(--fail)" if (health.get("duration_delta_ms") or 0) > 0 else "var(--pass)",
            ),
        ]
    )

    rows = ""
    for tp in reversed(trend_pts):
        is_here = tp.get("run_id") == current_id
        here_badge = (
            '<span style="display:inline-block; margin-left:10px; padding:2px 8px; border-radius:100px; '
            'font-size:10px; font-weight:700; background:var(--accent); color:#fff;">YOU ARE HERE</span>'
            if is_here
            else ""
        )
        rate = float(tp.get("pass_rate", 0))
        row_bg = "background:var(--accentSoft);" if is_here else ""
        rows += (
            f'<tr style="{row_bg}"><td style="padding:14px 16px; font-family:{MONO}; font-size:12.5px; '
            f'color:var(--muted); border-top:1px solid var(--border);">{_fmt_ts(tp.get("latest_run"))}</td>'
            f'<td style="padding:14px 16px; font-family:{MONO}; font-weight:600; white-space:nowrap; '
            f'border-top:1px solid var(--border);">{_e(tp.get("run_id", ""))}{here_badge}</td>'
            f'<td style="padding:14px 16px; border-top:1px solid var(--border);">'
            '<div style="display:flex; align-items:center; gap:10px;">'
            '<div style="width:110px; height:8px; border-radius:100px; background:var(--surfaceAlt); '
            'overflow:hidden; flex-shrink:0;">'
            f'<span style="display:block; height:100%; width:{rate:.1f}%; background:var(--accent); '
            'border-radius:100px;"></span></div>'
            f'<span style="font-family:{MONO}; font-size:12.5px; white-space:nowrap;">{_fmt_pct(rate)}</span>'
            "</div></td>"
            f'<td style="padding:14px 16px; text-align:right; font-family:{MONO}; border-top:1px solid var(--border);">'
            f"{int(tp.get('flaky', 0) or 0)}</td>"
            f'<td style="padding:14px 16px; text-align:right; font-family:{MONO}; border-top:1px solid var(--border);">'
            f"{int(tp.get('failed', 0) or 0)}</td>"
            f'<td style="padding:14px 16px; text-align:right; font-family:{MONO}; border-top:1px solid var(--border);">'
            f"{_fmt_dur(tp.get('duration_ms', 0))}</td></tr>"
        )
    head = "".join(
        f'<th style="padding:12px 16px; text-align:{a}; font-size:11px; font-weight:700; letter-spacing:0.05em; '
        f'text-transform:uppercase; color:var(--faint); background:var(--surfaceAlt);">{h}</th>'
        for h, a in (
            ("Run Time", "left"),
            ("Run ID", "left"),
            ("Pass Rate", "left"),
            ("Flaky", "right"),
            ("Failed", "right"),
            ("Duration", "right"),
        )
    )
    table = _card(
        '<div style="overflow-x:auto;"><table style="width:100%; border-collapse:collapse; font-size:13.5px;">'
        f"<thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table></div>",
        pad=0,
        extra="overflow:hidden;",
    )

    main = (
        _page_header(
            _run_eyebrow(report_data),
            "History",
            "Pass rate trend and run-over-run comparison, across all recorded runs.",
        )
        + trend_card
        + f'<div style="display:flex; gap:14px; flex-wrap:wrap; margin-bottom:20px;">{chips}</div>'
        + table
    )
    return _document(report_data, "history", "History", main)


def _last_platform_rate(trend_pts: list[dict[str, Any]], platform: str) -> float:
    runs = [tp for tp in trend_pts if (tp.get("platforms") or {}).get(platform)]
    return float(runs[-1]["platforms"][platform].get("pass_rate", 0)) if runs else 0.0


# ============================ SHARE ========================================


def render_share(report_data: dict[str, Any]) -> str:
    exports = report_data.get("sharing", {}).get("exports", {})

    def export_card(title: str, body: str, link_label: str, href: str) -> str:
        btn = (
            (
                f'<a href="{_e(href)}" style="display:inline-block; margin-top:14px; padding:10px 18px; '
                "border-radius:9px; border:1px solid var(--border); background:var(--surface); color:var(--text); "
                f'font-size:13.5px; font-weight:700; text-decoration:none; box-shadow:var(--shadow);">{_e(link_label)}</a>'
            )
            if href
            else ""
        )
        return _card(
            f'<h3 style="font-family:{DISPLAY}; font-size:17px; font-weight:700; margin:0 0 8px;">{_e(title)}</h3>'
            f'<p style="font-size:13.5px; color:var(--muted); margin:0; line-height:1.5;">{_e(body)}</p>{btn}'
        )

    export_row = (
        '<div style="display:grid; grid-template-columns:repeat(3,1fr); gap:20px; margin-bottom:20px;" class="grid-3">'
        + export_card(
            "Export Tests (CSV)",
            "Flat index of every test in this run for spreadsheets.",
            "Download CSV",
            exports.get("test_index_csv", ""),
        )
        + export_card("Copy Share Link", "Direct link to this run for stakeholders.", "", "").replace(
            "</p>",
            '</p><button type="button" data-copy-share-link style="display:inline-block; margin-top:14px; '
            "padding:10px 18px; border-radius:9px; border:1px solid var(--border); background:var(--surface); "
            "color:var(--text); font-size:13.5px; font-weight:700; cursor:pointer; box-shadow:var(--shadow); "
            'font-family:inherit;">Copy Link</button>',
        )
        + export_card(
            "Print / PDF Summary",
            "Print the current page using your browser's print dialog.",
            "Print Summary",
            "print-summary.html",
        )
        + "</div>"
    )

    def stakeholder(title: str, body: str, links: list[tuple[str, str]]) -> str:
        btns = "".join(
            f'<a href="{_e(href)}" style="display:block; text-align:center; padding:11px 0; border:1px solid '
            "var(--border); border-radius:9px; font-size:13.5px; font-weight:700; color:var(--link); "
            f'text-decoration:none; margin-bottom:10px;">{_e(label)}</a>'
            for label, href in links
        )
        return _card(
            f'<h3 style="font-family:{DISPLAY}; font-size:17px; font-weight:700; margin:0 0 8px;">{_e(title)}</h3>'
            f'<p style="font-size:13.5px; color:var(--muted); margin:0 0 14px; line-height:1.5;">{_e(body)}</p>{btns}'
        )

    stake_row = (
        f'<h2 style="font-family:{DISPLAY}; font-size:18px; font-weight:800; margin:8px 0 16px;">Stakeholder Views</h2>'
        '<div style="display:grid; grid-template-columns:repeat(3,1fr); gap:20px; margin-bottom:20px;" class="grid-3">'
        + stakeholder(
            "Executive",
            "Release readiness, health score, and top blockers.",
            [("Executive Summary", "executive.html"), ("Quality Gates", "quality.html")],
        )
        + stakeholder(
            "QA Lead",
            "Failure clusters, flaky analysis, and matrix coverage.",
            [("Tests Explore", "explore.html"), ("Flaky Analysis", "flaky.html"), ("Matrix", "matrix.html")],
        )
        + stakeholder(
            "Developer",
            "Failure detail, timeline events, retries, and artifacts.",
            [("Timeline", "timeline.html"), ("Tests Explore", "explore.html")],
        )
        + "</div>"
    )

    artifacts = report_data.get("artifacts", [])
    art_rows = (
        "".join(
            '<tr><td style="padding:14px 16px; border-top:1px solid var(--border);">'
            f'<a href="{_e(a.get("href") or "#")}" style="font-family:{MONO}; font-size:12.5px; color:var(--link); '
            f'text-decoration:none; overflow-wrap:anywhere;">{_e(a.get("test_name", a.get("name", "")))}</a></td>'
            f'<td style="padding:14px 16px; border-top:1px solid var(--border); font-size:13px; color:var(--muted);">'
            f"{_e(a.get('artifact_type', ''))}</td></tr>"
            for a in artifacts
        )
        or '<tr><td colspan="2" style="padding:24px; color:var(--faint);">No artifacts captured.</td></tr>'
    )
    art_head = "".join(
        f'<th style="padding:12px 16px; text-align:left; font-size:11px; font-weight:700; letter-spacing:0.05em; '
        f'text-transform:uppercase; color:var(--faint); background:var(--surfaceAlt);">{h}</th>'
        for h in ("Test", "Artifact Type")
    )
    art_card = _card(
        _title("Artifact Index") + '<div style="overflow-x:auto;"><table style="width:100%; border-collapse:collapse;">'
        f"<thead><tr>{art_head}</tr></thead><tbody>{art_rows}</tbody></table></div>",
        pad=22,
    )

    main = (
        _page_header(
            _run_eyebrow(report_data), "Share & Export", "Portable exports and stakeholder-specific views for this run."
        )
        + export_row
        + stake_row
        + art_card
    )
    return _document(report_data, "share", "Share & Export", main)


def render_print_summary(report_data: dict[str, Any]) -> str:
    # Reuse the executive layout for printing.
    return render_executive(report_data)


# ============================ TEST DETAIL ==================================


def render_test_detail(report_data: dict[str, Any], test: dict[str, Any], *, prefix: str = "../") -> str:
    status = test.get("status", "")
    color, soft = _status_colors(status)
    metadata = test.get("metadata") or {}
    known = metadata.get("known_issue")
    breadcrumb = " · ".join(
        x
        for x in [
            test.get("suite", ""),
            (test.get("platform_type", "") or "").capitalize(),
            test.get("domain", ""),
            metadata.get("owner", ""),
        ]
        if x
    )

    banner = ""
    if known:
        banner = (
            f'<div style="background:var(--flakySoft); border:1px solid var(--flaky); border-radius:12px; '
            f'padding:14px 18px; margin-bottom:20px; font-size:13.5px; color:var(--text);">'
            f"Known Issue · {_e(known)} — tracked and excluded from the release gate.</div>"
        )

    tiles = (
        '<div style="display:flex; flex-wrap:wrap; gap:14px; margin-bottom:20px;">'
        + _stat_tile(_fmt_dur(test.get("duration_ms", 0)), "Duration")
        + _stat_tile(test.get("retry_count", 0), "Retries")
        + _stat_tile(test.get("action_retry_count", 0), "Action Retries")
        + _stat_tile(test.get("healing_event_count", 0), "Healing Events")
        + _stat_tile(test.get("artifact_count", 0), "Artifacts")
        + "</div>"
    )

    stability = _stability_card(report_data, test)
    failure = test.get("failure", {})
    category = failure.get("category", "")
    category_tag = (
        f'<span style="display:inline-block; margin-bottom:10px; padding:3px 10px; border-radius:100px; '
        f'font-family:{MONO}; font-size:11.5px; background:var(--failSoft); color:var(--fail);">{_e(category)}</span>'
        if category
        else ""
    )
    smart = _card(
        _title("Smart Failure Summary")
        + category_tag
        + (
            f'<div style="background:var(--surfaceAlt); border-radius:10px; padding:16px; font-family:{MONO}; '
            f'font-size:13px; line-height:1.6; color:var(--text); overflow-wrap:anywhere;">'
            f"{_e(test.get('failure_message') or failure.get('detail') or failure.get('title') or 'No failure — test passed.')}</div>"
        )
    )

    context_rows = [
        ("Domain", test.get("domain", "-")),
        ("Profile", test.get("profile", "-")),
        ("Environment", test.get("environment", "-")),
        ("Browser", test.get("browser", "-")),
        ("Device", test.get("device_name", "-")),
        ("Platform", test.get("platform", "-")),
        ("Status Code", metadata.get("status_code", "-")),
        ("Latency", metadata.get("latency_ms", "-")),
    ]
    context = _card(
        _title("Context")
        + "".join(
            f'<div style="display:flex; justify-content:space-between; gap:16px; padding:8px 0; '
            f'border-top:1px solid var(--border);"><span style="font-size:13px; color:var(--muted);">{_e(label)}</span>'
            f'<span style="font-family:{MONO}; font-size:12.5px; text-align:right; overflow-wrap:anywhere; min-width:0;">'
            f"{_e(value or '-')}</span></div>"
            for label, value in context_rows
        )
    )

    metadata_rows = [
        (k, v)
        for k, v in metadata.items()
        if k not in ("platform_type", "quarantined", "known_issue") and not isinstance(v, (dict, list))
    ]
    meta_card = _card(
        _title("Metadata")
        + (
            "".join(
                f'<div style="display:flex; justify-content:space-between; gap:16px; padding:8px 0; '
                f'border-top:1px solid var(--border);"><span style="font-size:13px; color:var(--muted);">{_e(k)}</span>'
                f'<span style="font-family:{MONO}; font-size:12.5px; overflow-wrap:anywhere;">{_e(v)}</span></div>'
                for k, v in metadata_rows
            )
            or '<p style="font-size:13px; color:var(--faint);">No metadata.</p>'
        )
    )

    artifacts = _artifact_detail(report_data, test, prefix=prefix)
    timeline = _test_timeline(report_data, test)
    healing = _healing_detail(test)

    main = (
        '<a href="explore.html" style="display:inline-flex; align-items:center; gap:6px; font-size:13px; '
        'color:var(--link); text-decoration:none; margin-bottom:14px;">← Back to Tests Explore</a>'
        + f'<div style="margin-bottom:10px;">{_pill(status, status)}</div>'
        + f'<h1 style="font-family:{DISPLAY}; font-size:26px; font-weight:800; margin:0 0 6px; '
        f'overflow-wrap:anywhere; line-height:1.2;">{_e(test.get("name", ""))}</h1>'
        + f'<p style="font-family:{MONO}; font-size:13px; color:var(--muted); margin:0 0 20px;">{_e(breadcrumb)}</p>'
        + banner
        + tiles
        + stability
        + '<div style="display:grid; grid-template-columns:1fr 1fr; gap:20px; margin-bottom:20px;" class="grid-2">'
        + smart
        + context
        + "</div>"
        + '<div style="display:grid; grid-template-columns:1fr 1fr; gap:20px; margin-bottom:20px;" class="grid-2">'
        + meta_card
        + _card(
            _title("Capabilities")
            + (
                f'<pre style="font-family:{MONO}; font-size:12px; white-space:pre-wrap; overflow-wrap:anywhere; margin:0; '
                f'color:var(--muted);">{_e(json.dumps(test.get("capabilities") or {}, indent=2))}</pre>'
                if test.get("capabilities")
                else '<p style="font-size:13px; color:var(--faint);">No data captured.</p>'
            )
        )
        + "</div>"
        + healing
        + artifacts
        + timeline
    )
    context_data = _run_context(report_data)
    sidebar_html = shell.sidebar("report", active="explore", prefix=prefix, run=context_data)
    return shell.document(
        f"Test · {test.get('name', '')}", sidebar_html=sidebar_html, main_html=main, data_json_script=""
    )


def _stability_card(report_data: dict[str, Any], test: dict[str, Any]) -> str:
    # Derive a last-N stability strip from history test statuses if available.
    stab_pct = report_data.get("stability", {}).get("score")
    if str(test.get("status")).lower() in ("failed", "broken"):
        dots = [False] * 5
        pct = 0
    else:
        dots = [True] * 5
        pct = 100
    if stab_pct is not None:
        pct = int(round(float(stab_pct)))
    strip = "".join(
        f'<span style="width:28px; height:12px; border-radius:3px; background:{"var(--pass)" if ok else "var(--fail)"}; '
        'display:inline-block; margin-right:6px;"></span>'
        for ok in dots
    )
    return _card(
        '<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:14px;">'
        f'<h2 style="font-family:{DISPLAY}; font-size:16px; font-weight:700; margin:0;">Stability (last 5 runs)</h2>'
        f'<strong style="font-family:{MONO}; font-size:14px; color:{"var(--pass)" if pct >= 80 else "var(--fail)"};">'
        f"{pct}% stable</strong></div>{strip}",
        extra="margin-bottom:20px;",
    )


def _healing_detail(test: dict[str, Any]) -> str:
    events = (test.get("metadata") or {}).get("healing_events", [])
    if not isinstance(events, list) or not events:
        return _card(
            _title("Healing Events") + '<p style="font-size:13px; color:var(--faint);">No healing events captured.</p>',
            extra="margin-bottom:20px;",
        )
    rows = []
    for event in events:
        decision = event.get("decision", "")
        original = (event.get("original") or {}).get("value", "")
        selected_obj = event.get("selected") or {}
        selected = (
            selected_obj.get("value")
            or (selected_obj.get("candidate") or {}).get("value")
            or ((event.get("candidates") or [{}])[0].get("candidate") or {}).get("value", "")
        )
        color = "var(--pass)" if decision == "applied" else "var(--flaky)"
        rows.append(
            '<div style="padding:12px 0; border-top:1px solid var(--border);">'
            f'<span style="display:inline-block; padding:2px 9px; border-radius:100px; font-family:{MONO}; '
            f'font-size:11px; font-weight:700; background:var(--surfaceAlt); color:{color};">{_e(decision)}</span>'
            f'<div style="font-family:{MONO}; font-size:12.5px; margin-top:8px; overflow-wrap:anywhere;">'
            f'{_e(original)} <span style="color:var(--faint);">→</span> '
            f'<strong style="color:var(--text);">{_e(selected)}</strong></div></div>'
        )
    return _card(_title("Healing Events") + "".join(rows), extra="margin-bottom:20px;")


def _artifact_detail(report_data: dict[str, Any], test: dict[str, Any], *, prefix: str = "../") -> str:
    test_id = test.get("test_id")
    entries = [a for a in report_data.get("artifacts", []) if a.get("test_id") == test_id]
    if not entries:
        # Fall back to plain names from the test-index record.
        names = test.get("artifact_names", [])
        if not names:
            return _card(
                _title("Artifacts") + '<p style="font-size:13px; color:var(--faint);">No artifacts captured.</p>',
                extra="margin-bottom:20px;",
            )
        entries = [{"name": name, "artifact_type": "", "href": None} for name in names]

    def artifact_row(entry: dict[str, Any]) -> str:
        name = entry.get("name", "")
        href = entry.get("href") or entry.get("path")
        atype = entry.get("artifact_type", "")
        label = (
            f'<a href="{_e(prefix + href)}" style="font-family:{MONO}; font-size:12.5px; color:var(--link); '
            f'text-decoration:none; overflow-wrap:anywhere;">{_e(name)}</a>'
            if href and str(href) != "[redacted]"
            else f'<span style="font-family:{MONO}; font-size:12.5px; overflow-wrap:anywhere;">{_e(name)}</span>'
        )
        type_html = (
            f'<span style="font-size:12px; color:var(--faint); flex-shrink:0;">{_e(atype)}</span>' if atype else ""
        )
        return (
            '<div style="display:flex; justify-content:space-between; gap:16px; padding:10px 0; '
            f'border-top:1px solid var(--border);">{label}{type_html}</div>'
        )

    rows = "".join(artifact_row(entry) for entry in entries)
    return _card(_title("Artifacts") + rows, extra="margin-bottom:20px;")


_EVENT_LABELS = {
    "test_started": "Started",
    "test_finished": "Finished",
    "started": "Started",
    "finished": "Finished",
    "artifact": "Artifact captured",
    "test_retry": "Retry attempt",
    "action_retry": "Action retry",
    "healing": "Self-healing",
    "step": "Step",
}


def _event_label(event: dict[str, Any]) -> str:
    name = event.get("name")
    if name:
        return str(name)
    event_type = str(event.get("event_type") or "").lower()
    label = _EVENT_LABELS.get(event_type)
    if label:
        return label
    return event_type.replace("_", " ").title() or "Event"


def _event_color(event: dict[str, Any], test_status: str) -> str:
    event_type = str(event.get("event_type") or "").lower()
    if "artifact" in event_type or "capture" in event_type:
        return "var(--accent)"
    if any(token in event_type for token in ("retry", "fail", "error", "broken", "healing")):
        return "var(--fail)" if "retry" in event_type or "fail" in event_type else "var(--broken)"
    # Started/finished reflect the test's overall outcome; steps use their own status.
    status = (
        test_status if event_type in ("test_started", "test_finished", "started", "finished") else event.get("status")
    )
    color, _ = _status_colors(str(status or test_status))
    return color


def _timeline_stepper(events: list[dict[str, Any]], test_status: str) -> str:
    cells = []
    for index, event in enumerate(events):
        color = _event_color(event, test_status)
        connector = (
            '<div style="flex:1 1 20px; height:2px; background:var(--border); margin:6px 6px 0; '
            'align-self:flex-start; min-width:18px;"></div>'
            if index < len(events) - 1
            else ""
        )
        cells.append(
            '<div style="display:flex; flex-direction:column; align-items:center; text-align:center; '
            'min-width:96px; max-width:150px;">'
            f'<span style="width:13px; height:13px; border-radius:50%; background:{color}; flex-shrink:0;"></span>'
            f'<strong style="font-size:12.5px; margin-top:8px; overflow-wrap:anywhere; line-height:1.35;">'
            f"{_e(_event_label(event))}</strong></div>{connector}"
        )
    return f'<div style="display:flex; align-items:flex-start; flex-wrap:wrap;">{"".join(cells)}</div>'


def _test_timeline(report_data: dict[str, Any], test: dict[str, Any]) -> str:
    events = [e for e in report_data.get("timeline", {}).get("events", []) if e.get("test_id") == test.get("test_id")]
    if not events:
        return ""
    return _card(_title("Timeline") + _timeline_stepper(events, str(test.get("status", ""))))
