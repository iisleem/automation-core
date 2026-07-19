from __future__ import annotations

import html
import json
import os
import re
import zipfile
from csv import DictWriter
from datetime import datetime
from io import StringIO
from pathlib import Path
from shutil import copy2
from typing import Any
from urllib.parse import urlparse

from automation_core.reporting.analysis import (
    failure_summary,
    fastest_slowest_tests,
    flaky_analysis,
    summarize_run,
)
from automation_core.reporting.events import ReportingEvent, build_timeline_events
from automation_core.reporting.history import load_history, trend_points, update_history
from automation_core.reporting.insights import ReportInsightConfig
from automation_core.reporting.models import Artifact, RunReport, StepRecord, TestCaseReport, to_jsonable
from automation_core.reporting.quality import QualityGate, QualityGateConfig
from automation_core.reporting.redaction import is_sensitive_name, redact_report, redact_text
from automation_core.reporting.sidecar import build_report_data
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
    safe_share: bool = True,
    quality_gates: QualityGateConfig
    | list[QualityGate | dict[str, Any]]
    | tuple[QualityGate | dict[str, Any], ...]
    | None = None,
    insight_config: ReportInsightConfig | dict[str, Any] | None = None,
) -> Path:
    output_path = Path(output_dir)
    tests_dir = output_path / "tests"
    data_dir = output_path / "data"
    tests_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    exports_dir = output_path / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    if bundle_artifacts:
        _bundle_report_artifacts(report, output_path, safe_share=safe_share)
    if validate:
        assert_valid_report(report)

    output_report, redaction = redact_report(report, enabled=safe_share)
    details = _write_test_pages(output_report, tests_dir, output_path, safe_share=safe_share)
    history_entries = _history_entries(output_report, history_dir, update_history_file, history_limit)
    timeline = build_timeline_events(output_report)
    report_data = build_report_data(
        report if safe_share else output_report,
        history_entries=history_entries,
        timeline_events=timeline,
        details=details,
        quality_gates=quality_gates,
        insight_config=insight_config,
        safe_share=safe_share,
        redaction=redaction,
    )

    (data_dir / "run-report.json").write_text(json.dumps(output_report.to_dict(), indent=2), encoding="utf-8")
    (output_path / "report-data.json").write_text(json.dumps(report_data, indent=2), encoding="utf-8")
    _write_share_exports(output_report, report_data, output_path)
    (output_path / "quality.html").write_text(_render_quality_page(output_report, report_data), encoding="utf-8")
    (output_path / "compare.html").write_text(_render_compare_page(output_report, report_data), encoding="utf-8")
    (output_path / "executive.html").write_text(
        _render_executive_page(output_report, history_entries, report_data), encoding="utf-8"
    )
    (output_path / "share.html").write_text(_render_share_page(output_report, report_data), encoding="utf-8")
    (output_path / "print-summary.html").write_text(
        _render_print_summary_page(output_report, history_entries, report_data), encoding="utf-8"
    )
    (output_path / "explore.html").write_text(_render_explore_page(output_report, report_data), encoding="utf-8")
    (output_path / "timeline.html").write_text(_render_timeline_page(output_report, timeline), encoding="utf-8")
    (output_path / "flaky.html").write_text(_render_flaky_page(output_report), encoding="utf-8")
    (output_path / "matrix.html").write_text(_render_matrix_page(output_report, report_data), encoding="utf-8")
    (output_path / "history.html").write_text(
        _render_history_page(output_report, history_entries, report_data), encoding="utf-8"
    )
    index_path = output_path / "index.html"
    index_path.write_text(_render_dashboard(output_report, details, history_entries, report_data), encoding="utf-8")
    return index_path


def _bundle_report_artifacts(report: RunReport, output_dir: Path, *, safe_share: bool) -> None:
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
            destination = _artifact_destination(artifacts_dir, artifact, source, index, safe_share=safe_share)
            try:
                if safe_share and artifact.artifact_type in TEXT_ARTIFACT_TYPES:
                    destination.write_text(
                        redact_text(source.read_text(encoding="utf-8", errors="replace")), encoding="utf-8"
                    )
                elif source.resolve() != destination.resolve():
                    copy2(source, destination)
                artifact.metadata.setdefault("original_path", str(source))
                artifact.metadata["bundled"] = True
                artifact.path = str(destination)
                artifact.href = f"artifacts/{destination.name}"
                artifact.size_bytes = destination.stat().st_size
            except OSError as error:
                artifact.metadata["bundle_error"] = str(error)


def _artifact_destination(
    artifacts_dir: Path, artifact: Artifact, source: Path, index: int, *, safe_share: bool
) -> Path:
    name = artifact.name or source.stem
    if safe_share and is_sensitive_name(name):
        name = artifact.artifact_type or "artifact"
    stem = _slug(name)
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


def _write_share_exports(report: RunReport, report_data: dict[str, Any], output_path: Path) -> None:
    exports_dir = output_path / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    (exports_dir / "test-index.csv").write_text(_test_index_csv(report_data["test_index"]), encoding="utf-8")
    _write_test_index_xlsx(exports_dir / "test-index.xlsx", report_data["test_index"])
    _write_executive_summary_docx(exports_dir / "executive-summary.docx", report, report_data)
    (exports_dir / "share-card.svg").write_text(_share_card_svg(report, report_data), encoding="utf-8")
    bundle = {
        "run": report_data["run"],
        "test_index": report_data["test_index"],
        "failure_clusters": report_data["failure_clusters"],
        "flaky": report_data["flaky"],
        "matrix": report_data["matrix"],
        "timeline": report_data["timeline"],
        "history": report_data["history"],
        "artifacts": report_data["artifacts"],
        "quality": report_data["quality"],
        "quality_score": report_data["quality_score"],
        "risk_signal": report_data["risk_signal"],
        "default_gate_status": report_data["default_gate_status"],
        "failure_transitions": report_data["failure_transitions"],
        "run_comparison": report_data["run_comparison"],
        "compare": report_data["compare"],
        "stability": report_data["stability"],
        "recovery": report_data["recovery"],
        "resource_efficiency": report_data["resource_efficiency"],
        "sharing": report_data["sharing"],
    }
    (exports_dir / "report-bundle.json").write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    manifest = {
        "run_id": report.run_id,
        "project_name": report.project_name,
        "framework": report.framework,
        "entrypoint": "index.html",
        "pages": [
            "index.html",
            "executive.html",
            "quality.html",
            "compare.html",
            "share.html",
            "explore.html",
            "timeline.html",
            "flaky.html",
            "matrix.html",
            "history.html",
            "print-summary.html",
        ],
        "exports": report_data["sharing"]["exports"],
        "safe_share": report_data["sharing"]["safe_share"],
        "package_guidance": "Share the full report directory so HTML pages, tests, data, exports, and artifacts stay together.",
    }
    (exports_dir / "share-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _test_index_csv(test_index: list[dict[str, Any]]) -> str:
    fields = [
        "test_id",
        "name",
        "status",
        "domain",
        "profile",
        "environment",
        "duration_ms",
        "failure_category",
        "failure_title",
        "detail_href",
        "artifact_count",
        "retry_count",
        "action_retry_count",
        "healing_event_count",
    ]
    output = StringIO()
    writer = DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for item in test_index:
        failure = item.get("failure", {})
        writer.writerow(
            {
                "test_id": item.get("test_id", ""),
                "name": item.get("name", ""),
                "status": item.get("status", ""),
                "domain": item.get("domain", ""),
                "profile": item.get("profile", ""),
                "environment": item.get("environment", ""),
                "duration_ms": item.get("duration_ms", 0),
                "failure_category": failure.get("category", ""),
                "failure_title": failure.get("title", ""),
                "detail_href": item.get("detail_href", ""),
                "artifact_count": item.get("artifact_count", 0),
                "retry_count": item.get("retry_count", 0),
                "action_retry_count": item.get("action_retry_count", 0),
                "healing_event_count": item.get("healing_event_count", 0),
            }
        )
    return output.getvalue()


def _write_test_index_xlsx(path: Path, test_index: list[dict[str, Any]]) -> None:
    headers = [
        "Test ID",
        "Name",
        "Status",
        "Domain",
        "Profile",
        "Environment",
        "Duration ms",
        "Failure Category",
        "Failure Title",
        "Detail",
        "Artifacts",
        "Test Retries",
        "Action Retries",
        "Healing Events",
    ]
    rows = [
        [
            item.get("test_id", ""),
            item.get("name", ""),
            item.get("status", ""),
            item.get("domain", ""),
            item.get("profile", ""),
            item.get("environment", ""),
            item.get("duration_ms", 0),
            item.get("failure", {}).get("category", ""),
            item.get("failure", {}).get("title", ""),
            item.get("detail_href", ""),
            item.get("artifact_count", 0),
            item.get("retry_count", 0),
            item.get("action_retry_count", 0),
            item.get("healing_event_count", 0),
        ]
        for item in test_index
    ]
    _write_xlsx(path, "Test Index", headers, rows)


def _write_executive_summary_docx(path: Path, report: RunReport, report_data: dict[str, Any]) -> None:
    summary = report_data["run"]["summary"]
    quality = report_data.get("quality", {})
    transitions = report_data.get("failure_transitions", {}).get("counts", {})
    health = report_data.get("run", {}).get("health", {})
    rows = [
        ("Project", report.project_name or "-"),
        ("Run ID", report.run_id),
        ("Framework", report.framework or "-"),
        ("Pass Rate", f"{summary.get('pass_rate', 0)}%"),
        ("Total Tests", summary.get("total", 0)),
        ("Passed", summary.get("passed", 0)),
        ("Failed/Broken", summary.get("failed", 0) + summary.get("broken", 0)),
        ("Skipped", summary.get("skipped", 0)),
        ("Flaky", summary.get("flaky", 0)),
        ("Duration", _format_duration(summary.get("duration_ms", 0))),
        ("Quality Status", quality.get("status", "passed")),
        ("New Failures", transitions.get("new", 0)),
        ("Known Failures", transitions.get("known", 0)),
        ("Resolved Failures", transitions.get("resolved", 0)),
        ("Previous Run", health.get("previous_run_id") or "-"),
    ]
    risk_items = report_data.get("risk_signals", [])[:6]
    blockers = [
        f"{item.get('severity', '').upper()}: {item.get('title', '')} ({item.get('count', 0)})" for item in risk_items
    ]
    body = [
        _docx_paragraph("Automation Report Executive Summary", bold=True),
        _docx_paragraph("Run overview"),
        _docx_table(rows),
        _docx_paragraph("Top Risk Signals"),
        *(_docx_paragraph(item) for item in blockers or ["No major risk signals."]),
    ]
    _write_docx(path, body, title="Automation Report Executive Summary")


def _share_card_svg(report: RunReport, report_data: dict[str, Any]) -> str:
    summary = report_data["run"]["summary"]
    quality = report_data.get("quality", {})
    transitions = report_data.get("failure_transitions", {}).get("counts", {})
    failed_total = summary.get("failed", 0) + summary.get("broken", 0)
    quality_status = str(quality.get("status", "passed")).upper()
    status_color = "#047857" if quality_status == "PASSED" else "#b45309" if quality_status == "WARNING" else "#b91c1c"
    title = _trim(report.project_name or "Automation Report", 48)
    subtitle = _trim(report.run_id, 58)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630" role="img" aria-label="Automation report summary">
  <rect width="1200" height="630" fill="#f5f7fa"/>
  <rect x="0" y="0" width="1200" height="160" fill="#102033"/>
  <text x="56" y="68" fill="#b7c7d7" font-family="Arial, sans-serif" font-size="24">{_xml_text(subtitle)}</text>
  <text x="56" y="120" fill="#ffffff" font-family="Arial, sans-serif" font-size="44" font-weight="700">{_xml_text(title)}</text>
  <rect x="950" y="44" width="176" height="52" rx="26" fill="#ffffff"/>
  <text x="1038" y="78" fill="{status_color}" font-family="Arial, sans-serif" font-size="22" font-weight="700" text-anchor="middle">{_xml_text(quality_status)}</text>
  {_svg_metric(56, 220, "Pass Rate", f"{summary.get('pass_rate', 0)}%")}
  {_svg_metric(326, 220, "Failed/Broken", failed_total)}
  {_svg_metric(596, 220, "Flaky", summary.get("flaky", 0))}
  {_svg_metric(866, 220, "Duration", _format_duration(summary.get("duration_ms", 0)))}
  {_svg_metric(56, 400, "New Failures", transitions.get("new", 0))}
  {_svg_metric(326, 400, "Known Failures", transitions.get("known", 0))}
  {_svg_metric(596, 400, "Resolved", transitions.get("resolved", 0))}
  {_svg_metric(866, 400, "Total Tests", summary.get("total", 0))}
</svg>
"""


def _write_xlsx(path: Path, sheet_name: str, headers: list[str], rows: list[list[Any]]) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>""",
        )
        archive.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>""",
        )
        archive.writestr(
            "xl/workbook.xml",
            f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets><sheet name="{_xml_attr(sheet_name)}" sheetId="1" r:id="rId1"/></sheets>
</workbook>""",
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>""",
        )
        archive.writestr("xl/worksheets/sheet1.xml", _xlsx_sheet(headers, rows))
        archive.writestr("docProps/core.xml", _core_properties("Automation Report Test Index"))
        archive.writestr("docProps/app.xml", _app_properties("Automation Report"))


def _xlsx_sheet(headers: list[str], rows: list[list[Any]]) -> str:
    sheet_rows = [headers, *rows]
    body = "\n".join(
        f'<row r="{row_index}">'
        + "".join(
            f'<c r="{_xlsx_col(col_index)}{row_index}" t="inlineStr"><is><t>{_xml_text(value)}</t></is></c>'
            for col_index, value in enumerate(row, start=1)
        )
        + "</row>"
        for row_index, row in enumerate(sheet_rows, start=1)
    )
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>{body}</sheetData>
</worksheet>"""


def _write_docx(path: Path, body_parts: list[str], *, title: str) -> None:
    document = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    {"".join(body_parts)}
    <w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/></w:sectPr>
  </w:body>
</w:document>"""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>""",
        )
        archive.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>""",
        )
        archive.writestr("word/document.xml", document)
        archive.writestr("docProps/core.xml", _core_properties(title))
        archive.writestr("docProps/app.xml", _app_properties("Automation Report"))


def _docx_paragraph(text: Any, *, bold: bool = False) -> str:
    run_props = "<w:rPr><w:b/></w:rPr>" if bold else ""
    return f"<w:p><w:r>{run_props}<w:t>{_xml_text(text)}</w:t></w:r></w:p>"


def _docx_table(rows: list[tuple[Any, Any]]) -> str:
    table_rows = "".join(
        "<w:tr>"
        f"<w:tc><w:p><w:r><w:t>{_xml_text(label)}</w:t></w:r></w:p></w:tc>"
        f"<w:tc><w:p><w:r><w:t>{_xml_text(value)}</w:t></w:r></w:p></w:tc>"
        "</w:tr>"
        for label, value in rows
    )
    return f"<w:tbl>{table_rows}</w:tbl>"


def _core_properties(title: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/">
  <dc:title>{_xml_text(title)}</dc:title>
</cp:coreProperties>"""


def _app_properties(application: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">
  <Application>{_xml_text(application)}</Application>
</Properties>"""


def _xlsx_col(index: int) -> str:
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _svg_metric(x: int, y: int, label: str, value: Any) -> str:
    return f"""<rect x="{x}" y="{y}" width="238" height="126" rx="18" fill="#ffffff" stroke="#dbe3ec"/>
  <text x="{x + 24}" y="{y + 46}" fill="#5b6472" font-family="Arial, sans-serif" font-size="22">{_xml_text(label)}</text>
  <text x="{x + 24}" y="{y + 94}" fill="#172033" font-family="Arial, sans-serif" font-size="42" font-weight="700">{_xml_text(value)}</text>"""


def _xml_attr(value: Any) -> str:
    return html.escape(_clean_xml_text(value), quote=True)


def _xml_text(value: Any) -> str:
    return html.escape(_clean_xml_text(value), quote=False)


def _clean_xml_text(value: Any) -> str:
    text = "" if value is None else str(value)
    return "".join(char if char in "\t\n\r" or ord(char) >= 32 else " " for char in text)


def _trim(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[: limit - 3].rstrip() + "..."


def _write_test_pages(report: RunReport, tests_dir: Path, report_root: Path, *, safe_share: bool) -> dict[str, str]:
    details: dict[str, str] = {}
    for index, test in enumerate(report.tests, start=1):
        filename = f"{index:04d}-{_slug(test.id or test.name)}.html"
        (tests_dir / filename).write_text(
            _render_test_page(report, test, tests_dir, report_root, safe_share=safe_share), encoding="utf-8"
        )
        details[test.id] = f"tests/{filename}"
    return details


def _render_dashboard(
    report: RunReport,
    details: dict[str, str],
    history_entries: list[dict[str, Any]],
    report_data: dict[str, Any],
) -> str:
    summary = summarize_run(report)
    speed = fastest_slowest_tests(report)
    flaky = flaky_analysis(report)
    trend = trend_points(history_entries)
    health = report_data["run"]["health"]
    signals = report_data["signals"]
    aggregates = report_data["aggregates"]
    rows = "\n".join(_test_row(test, details.get(test.id, "#")) for test in report.tests)

    return _page(
        "Automation Report",
        f"""
<header class="hero">
  <div>
    <p class="eyebrow">{_e(report.project_name or "automation")}</p>
    <h1>Automation Report</h1>
    <p>{_e(report.framework or "shared reporting")} · {_e(_format_datetime(summary["latest_run"]))}</p>
  </div>
  <span class="status {summary["status"]}">{_e(summary["status"])}</span>
</header>
{_nav("dashboard")}
<section class="metrics">
  {_metric("Total", summary["total"])}
  {_metric("Passed", summary["passed"])}
  {_metric("Failed", summary["failed"] + summary["broken"])}
  {_metric("Skipped", summary["skipped"])}
  {_metric("Flaky", summary["flaky"])}
  {_metric("Pass Rate", f"{summary['pass_rate']}%")}
  {_metric("Duration", _format_duration(summary["duration_ms"]))}
</section>
<section class="toolbar" data-filter-toolbar="dashboard">
  <label class="search-box">Quick search
    <input type="search" id="dashboard-search" placeholder="Search tests, failures, artifacts">
  </label>
  <a class="button" id="dashboard-explore-link" href="explore.html">Open Explore</a>
</section>
<section class="grid two">
  <article>
    <h2>Run Health</h2>
    {
            _key_values(
                {
                    "Pass Rate": f"{health['pass_rate']}%",
                    "Pass Rate Change": _format_delta(health.get("pass_rate_delta"), suffix="%"),
                    "Failed Change": _format_delta(health.get("failed_delta")),
                    "Flaky Change": _format_delta(health.get("flaky_delta")),
                    "Duration Change": _format_duration_delta(health.get("duration_delta_ms")),
                    "Previous Run": health.get("previous_run_id") or "-",
                }
            )
        }
  </article>
  <article>
    <h2>Signal Counts</h2>
    {
            _key_values(
                {
                    "Artifacts": signals["artifact_count"],
                    "Action Retries": signals["action_retry_count"],
                    "Test Retries": signals["test_retry_count"],
                    "Healing Events": signals["healing_event_count"],
                    "Healing Decisions": _inline_counts(signals["healing_decisions"]),
                }
            )
        }
  </article>
</section>
<section class="grid three">
  <article class="insight-card">
    <h2>Quality Score</h2>
    {_quality_score_card(report_data["quality_score"])}
  </article>
  <article class="insight-card">
    <h2>Risk Signal</h2>
    {_risk_signal_card(report_data["risk_signal"])}
  </article>
  <article class="insight-card">
    <h2>Recovery</h2>
    {_recovery_card(report_data["recovery"])}
  </article>
</section>
<section class="grid three chart-grid">
  <article class="chart-card">
    <h2>Status Distribution</h2>
    {_donut_chart(aggregates["status_distribution"])}
  </article>
  <article class="chart-card">
    <h2>Duration Distribution</h2>
    {_bar_chart(aggregates["duration_buckets"])}
  </article>
  <article class="chart-card">
    <h2>Retry Signals</h2>
    {_bar_chart(_retry_signal_chart_values(aggregates["retry_signals"]))}
  </article>
  <article class="chart-card">
    <h2>Slowest Tests</h2>
    {_slow_tests_chart(report_data["top_slow_tests"], details)}
  </article>
  <article class="chart-card">
    <h2>Failure Categories</h2>
    {_bar_chart(aggregates["failure_categories"], empty="No failure categories.")}
  </article>
  <article class="chart-card">
    <h2>Artifact Types</h2>
    {_bar_chart(aggregates["artifact_types"], empty="No artifacts captured.")}
  </article>
</section>
<section class="grid two">
  <article>
    <h2>History Pass Rate</h2>
    {_trend_chart(report_data["history"]["trend_points"])}
  </article>
  <article>
    <h2>Risk Signals</h2>
    {_risk_signal_list(report_data["risk_signals"])}
  </article>
</section>
<section class="grid two">
  <article>
    <h2>Quality Gates</h2>
    {_quality_overview(report_data["quality"])}
    <p><a class="button" href="quality.html">Open Quality</a></p>
  </article>
  <article>
    <h2>Failure Changes</h2>
    {_failure_transition_counts(report_data["failure_transitions"])}
  </article>
</section>
<section>
  <h2>Environment Coverage</h2>
  {_coverage_panel(aggregates["coverage"])}
</section>
<section class="grid two">
  <article>
    <h2>Run Context</h2>
    {
            _key_values(
                {
                    "Run ID": report.run_id,
                    "Generated": _format_datetime(summary["latest_run"]),
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
    <h2>Top Slow Tests</h2>
    {_test_list(speed["slowest"], details)}
  </article>
  <article>
    <h2>Failure Clusters</h2>
    {_failure_cluster_list(report_data["failure_clusters"])}
  </article>
</section>
<section>
  <h2>Flaky Breakdown</h2>
  {_flaky_breakdown_view(report_data["flaky"]["breakdown"])}
  {_analysis_table(flaky)}
</section>
<section>
  <h2>Tests</h2>
  <div class="table-wrap wide"><table>
    <thead><tr><th>Status</th><th>Test</th><th>Profile</th><th>Duration</th><th>Failure</th></tr></thead>
    <tbody>{rows or '<tr><td colspan="5">No tests found.</td></tr>'}</tbody>
  </table></div>
</section>
""",
    )


def _render_quality_page(report: RunReport, report_data: dict[str, Any]) -> str:
    quality = report_data["quality"]
    transitions = report_data["failure_transitions"]
    comparison = report_data["run_comparison"]
    return _page(
        "Quality Gates",
        f"""
<header class="hero compact">
  <div>
    <p class="eyebrow">{_e(report.run_id)}</p>
    <h1>Quality Gates</h1>
    <p>{_e(quality.get("message", "Quality gate status for this run."))}</p>
  </div>
  <span class="status {_e(quality.get("status", "unknown"))}">{_e(quality.get("status", "unknown"))}</span>
</header>
{_nav("quality")}
<section class="metrics">
  {_metric("Gate Status", quality.get("status", "passed"))}
  {_metric("Quality Score", _score_value(report_data["quality_score"]))}
  {_metric("Risk", report_data["risk_signal"].get("level", "low"))}
  {_metric("Configured", "yes" if quality.get("configured") else "no")}
  {_metric("New Failures", transitions["counts"]["new"])}
  {_metric("Known Failures", transitions["counts"]["known"])}
  {_metric("Resolved", transitions["counts"]["resolved"])}
</section>
<section class="toolbar" data-filter-scope="quality-gates">
  <label class="search-box">Search gate results
    <input type="search" data-filter-search="quality-gates" placeholder="Gate name, metric, severity, message">
  </label>
</section>
<section data-filter-root="quality-gates">
  <article>
    <h2>Gate Results</h2>
    {_quality_gate_table(quality)}
  </article>
</section>
<section>
  <article>
    <h2>Default Gate Status</h2>
    <p class="muted">Default gates are informational unless a framework or CI workflow enforces them.</p>
    {_quality_gate_table(report_data["default_gate_status"])}
  </article>
</section>
<section class="grid two">
  <article>
    <h2>Run Comparison</h2>
    {_run_comparison_detail_view(comparison)}
  </article>
  <article>
    <h2>Comparison Chart Data</h2>
    {_bar_chart({item["metric"]: abs(int(item.get("delta", 0) or 0)) for item in report_data["charts"]["run_comparison"]}, empty="No previous run comparison.")}
  </article>
</section>
<section class="toolbar" data-filter-scope="quality-failures">
  <label class="search-box">Search failure changes
    <input type="search" data-filter-search="quality-failures" placeholder="Test, category, status">
  </label>
  {_select_filter("quality-kind", "Kind", ["new", "known", "resolved"], data_filter="kind")}
</section>
<section data-filter-root="quality-failures">
  <article>
    <h2>Failure Movement</h2>
    {_failure_transition_table(transitions)}
  </article>
</section>
""",
    )


def _render_compare_page(report: RunReport, report_data: dict[str, Any]) -> str:
    compare = report_data["compare"]
    transitions = report_data["failure_transitions"]
    return _page(
        "Compare Runs",
        f"""
<header class="hero compact">
  <div>
    <p class="eyebrow">{_e(report.run_id)}</p>
    <h1>Compare Runs</h1>
    <p>Current run compared with the latest retained previous run where history is available.</p>
  </div>
  <span class="status {_e(report_data["risk_signal"].get("level", "low"))}">{_e(report_data["risk_signal"].get("level", "low"))}</span>
</header>
{_nav("compare")}
<section class="metrics">
  {_metric_with_note("Previous Run", _short_run_id(compare.get("previous_run_id") or ""), compare.get("previous_run_id") or "-")}
  {_metric("Pass Rate Delta", _compare_delta(compare, "pass_rate"))}
  {_metric("Failed Delta", _compare_delta(compare, "failed_broken"))}
  {_metric("Retry Delta", _retry_delta(compare))}
  {_metric("New Failures", transitions["counts"]["new"])}
  {_metric("Resolved", transitions["counts"]["resolved"])}
</section>
<section class="toolbar" data-filter-scope="compare-metrics">
  <label class="search-box">Search comparison metrics
    <input type="search" data-filter-search="compare-metrics" placeholder="Metric, current, previous, delta">
  </label>
</section>
<section class="grid two">
  <article data-filter-root="compare-metrics">
    <h2>Delta Breakdown</h2>
    {_compare_table(compare)}
  </article>
  <article>
    <h2>Quality Movement</h2>
    {_quality_score_card(report_data["quality_score"])}
    {_risk_signal_card(report_data["risk_signal"])}
  </article>
</section>
<section class="toolbar" data-filter-scope="compare-failures">
  <label class="search-box">Search failure movement
    <input type="search" data-filter-search="compare-failures" placeholder="Test, category, status">
  </label>
  {_select_filter("compare-kind", "Kind", ["new", "known", "resolved"], data_filter="kind")}
</section>
<section data-filter-root="compare-failures">
  <article>
    <h2>Failure Movement</h2>
    {_failure_transition_table(transitions)}
  </article>
</section>
<section class="grid two">
  <article>
    <h2>Stability</h2>
    {_stability_card(report_data["stability"])}
  </article>
  <article>
    <h2>Resource Efficiency</h2>
    {_resource_efficiency_card(report_data["resource_efficiency"])}
  </article>
</section>
""",
    )


def _render_test_page(
    report: RunReport,
    test: TestCaseReport,
    page_dir: Path,
    report_root: Path,
    *,
    safe_share: bool,
) -> str:
    action_retries = collect_action_retries(test)
    artifacts = collect_test_artifacts(test)
    healing_events = _healing_events(test)
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
{_nav("explore", prefix="../")}
<section class="toolbar" data-filter-scope="detail-page">
  <label class="search-box">Search this test
    <input type="search" data-filter-search="detail-page" placeholder="Steps, retries, healing, artifacts, logs">
  </label>
</section>
<section class="metrics">
  {_metric("Duration", _format_duration(test.duration_ms))}
  {_metric("Retries", len(test.retries))}
  {_metric("Action Retries", len(action_retries))}
  {_metric("Healing Events", len(healing_events))}
  {_metric("Artifacts", len(artifacts))}
</section>
<section class="grid two">
  <article>
    <h2>Smart Failure Summary</h2>
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
    {_data_block(test.capabilities or {})}
  </article>
  <article>
    <h2>Metadata</h2>
    {_data_block(_display_metadata(test.metadata or {}))}
  </article>
</section>
<section data-filter-root="detail-page">
  <h2>Healing Events</h2>
  {_healing_table(healing_events)}
</section>
<section data-filter-root="detail-page">
  <h2>Steps</h2>
  {_steps_view(test.steps)}
</section>
<section class="grid two" data-filter-root="detail-page">
  <article>
    <h2>Retries</h2>
    {_retry_table(test.retries)}
  </article>
  <article>
    <h2>Action Retry Attempts</h2>
    {_retry_table(action_retries)}
  </article>
</section>
<section data-filter-root="detail-page">
  <h2>Artifacts</h2>
  {_artifacts_view(artifacts, page_dir, report_root, safe_share=safe_share)}
</section>
<section data-filter-root="detail-page">
  <h2>Timeline</h2>
  {_timeline_table(timeline)}
</section>
""",
    )


def _render_executive_page(
    report: RunReport,
    history_entries: list[dict[str, Any]],
    report_data: dict[str, Any],
) -> str:
    summary = report_data["run"]["summary"]
    health = report_data["run"]["health"]
    readiness = _readiness_summary(summary)
    blockers = _executive_blockers(report_data["failure_clusters"], report_data["risk_signals"])
    return _page(
        "Executive Summary",
        f"""
<header class="hero compact">
  <div>
    <p class="eyebrow">{_e(report.run_id)}</p>
    <h1>Executive Summary</h1>
    <p>{_e(readiness["headline"])}</p>
  </div>
  <span class="status {summary["status"]}">{_e(summary["status"])}</span>
</header>
{_nav("executive")}
<section class="share-banner">
  {_safe_share_badge(report_data)}
  <span>{_e(readiness["next_action"])}</span>
</section>
<section class="metrics">
  {_metric("Pass Rate", f"{summary['pass_rate']}%")}
  {_metric("Passed", summary["passed"])}
  {_metric("Failed", summary["failed"] + summary["broken"])}
  {_metric("Skipped", summary["skipped"])}
  {_metric("Flaky", summary["flaky"])}
  {_metric("Quality Score", _score_value(report_data["quality_score"]))}
  {_metric("Risk", report_data["risk_signal"].get("level", "low"))}
  {_metric("Duration", _format_duration(summary["duration_ms"]))}
</section>
<section class="grid two">
  <article>
    <h2>Readiness</h2>
    {
            _key_values(
                {
                    "Headline": readiness["headline"],
                    "Next Action": readiness["next_action"],
                    "Pass Rate Change": _format_delta(health.get("pass_rate_delta"), suffix="%"),
                    "Failed Change": _format_delta(health.get("failed_delta")),
                    "Previous Run": health.get("previous_run_id") or "-",
                }
            )
        }
  </article>
  <article>
    <h2>Top Blockers</h2>
    {_blocker_list(blockers)}
  </article>
</section>
<section class="grid two">
  <article>
    <h2>Quality Signals</h2>
    {_risk_signal_list(report_data["risk_signals"])}
  </article>
  <article>
    <h2>Flaky And Retry Summary</h2>
    {_flaky_breakdown_view(report_data["flaky"]["breakdown"])}
    {
            _key_values(
                {
                    "Test Retries": report_data["signals"]["test_retry_count"],
                    "Action Retries": report_data["signals"]["action_retry_count"],
                    "Healing Events": report_data["signals"]["healing_event_count"],
                }
            )
        }
  </article>
</section>
<section class="grid three">
  <article>
    <h2>Quality Score</h2>
    {_quality_score_card(report_data["quality_score"])}
  </article>
  <article>
    <h2>Risk Signal</h2>
    {_risk_signal_card(report_data["risk_signal"])}
  </article>
  <article>
    <h2>Recovery</h2>
    {_recovery_card(report_data["recovery"])}
  </article>
</section>
<section>
  <h2>Environment Coverage</h2>
  {_coverage_panel(report_data["aggregates"]["coverage"])}
</section>
<section>
  <h2>History Trend</h2>
  {_trend_chart(report_data["history"]["trend_points"])}
  {_history_comparison_view(report_data["history"]["comparison"])}
</section>
<section class="grid three">
  <article><h2>Executive Links</h2>{
            _link_list(
                {"Printable summary": "print-summary.html", "Share center": "share.html", "Dashboard": "index.html"}
            )
        }</article>
  <article><h2>QA Lead Links</h2>{
            _link_list({"Tests Explore": "explore.html", "Flaky analysis": "flaky.html", "Matrix": "matrix.html"})
        }</article>
  <article><h2>Developer Links</h2>{
            _link_list(
                {"Timeline": "timeline.html", "Report data": "report-data.json", "Artifacts": "share.html#artifacts"}
            )
        }</article>
</section>
""",
    )


def _render_share_page(report: RunReport, report_data: dict[str, Any]) -> str:
    exports = report_data["sharing"]["exports"]
    return _page(
        "Share And Export",
        f"""
<header class="hero compact"><div><p class="eyebrow">{_e(report.run_id)}</p><h1>Share And Export</h1><p>Portable report assets for stakeholders and CI artifacts.</p></div></header>
{_nav("share")}
<section class="share-banner">
  {_safe_share_badge(report_data)}
  <span>Generated files are self-contained and intended for offline sharing from this report directory.</span>
</section>
<section class="grid three">
  {_export_card("Full Report Package", "Use the report directory as the package root. Keep HTML, data, exports, tests, and artifacts together.", {"Entry": "index.html", "Manifest": exports["share_manifest_json"]})}
  {_export_card("Run Data", "Machine-readable run summaries for downstream checks and dashboards.", {"Sidecar JSON": exports["sidecar_json"], "Run JSON": exports["run_report_json"], "Bundle JSON": exports["report_bundle_json"]})}
  {_export_card("Spreadsheet Exports", "Flat test indexes for spreadsheet workflows, release notes, and filtered follow-up analysis.", {"CSV": exports["test_index_csv"], "Excel Workbook": exports["test_index_xlsx"]})}
  {_export_card("Document Summary", "Portable executive summary for status updates, release notes, and stakeholder handoff.", {"Word Summary": exports["executive_summary_docx"]})}
  {_export_card("Printable Summary", "Open this page and use the browser print dialog to save a PDF when needed.", {"Print Summary": exports["print_summary_html"]})}
  {_export_card("Page And Image Export", "Use the generated share card or capture pages with an approved local renderer when screenshots are needed for status updates.", {"Share Card SVG": exports["share_card_svg"], "Executive": "executive.html", "Dashboard": "index.html", "Matrix": "matrix.html"})}
  {_export_card("Validation Targets", "Use the JSON sidecar and CSV export for CI validation without scraping HTML.", {"Report Data": "report-data.json", "Explore": "explore.html"})}
</section>
<section id="stakeholders">
  <h2>Stakeholder Views</h2>
  <div class="grid four">
    {_stakeholder_card("Executive", "Release readiness, trend, top blockers, and printable summary.", {"Executive Summary": "executive.html", "Printable Summary": "print-summary.html"})}
    {_stakeholder_card("QA Lead", "Failure clusters, flaky analysis, matrix coverage, and searchable tests.", {"Tests Explore": "explore.html", "Flaky": "flaky.html", "Matrix": "matrix.html"})}
    {_stakeholder_card("Developer", "Failure detail, timeline events, logs, retries, and artifacts.", {"Timeline": "timeline.html", "Report Data": "report-data.json"})}
    {_stakeholder_card("Release", "Readiness headline, pass rate, risk signals, and export bundle.", {"Executive Summary": "executive.html", "Share Manifest": exports["share_manifest_json"]})}
  </div>
</section>
<section>
  <h2>Safe Sharing Manifest</h2>
  {_data_block(report_data["sharing"]["safe_share"])}
</section>
<section id="artifacts">
  <h2>Artifact Index</h2>
  {_artifact_index_table(report_data["artifacts"])}
</section>
<script type="application/json" id="report-data-json">{_json_for_script(report_data)}</script>
""",
    )


def _render_print_summary_page(
    report: RunReport,
    history_entries: list[dict[str, Any]],
    report_data: dict[str, Any],
) -> str:
    summary = report_data["run"]["summary"]
    readiness = _readiness_summary(summary)
    return _page(
        "Printable Summary",
        f"""
<header class="hero compact"><div><p class="eyebrow">{_e(report.run_id)}</p><h1>Printable Summary</h1><p>{
            _e(readiness["headline"])
        }</p></div></header>
{_nav("share")}
<section class="print-summary">
  <article>
    <h2>Release Readiness</h2>
    {
            _key_values(
                {
                    "Headline": readiness["headline"],
                    "Next Action": readiness["next_action"],
                    "Pass Rate": f"{summary['pass_rate']}%",
                    "Failed": summary["failed"] + summary["broken"],
                    "Flaky": summary["flaky"],
                    "Duration": _format_duration(summary["duration_ms"]),
                }
            )
        }
  </article>
  <article>
    <h2>Top Blockers</h2>
    {_blocker_list(_executive_blockers(report_data["failure_clusters"], report_data["risk_signals"]))}
  </article>
  <article>
    <h2>Trend</h2>
    {_trend_bars(trend_points(history_entries))}
  </article>
</section>
""",
    )


def _render_explore_page(report: RunReport, report_data: dict[str, Any]) -> str:
    options = report_data["aggregates"]["filter_options"]
    return _page(
        "Tests Explore",
        f"""
<header class="hero compact"><div><p class="eyebrow">{_e(report.run_id)}</p><h1>Tests Explore</h1><p>Search, filter, sort, and inspect the neutral test index.</p></div></header>
{_nav("explore")}
<section class="toolbar explore-toolbar" data-filter-toolbar="explore">
  <label class="search-box">Search
    <input type="search" id="explore-search" placeholder="Name, suite, status, metadata, artifact, failure">
  </label>
  {_select_filter("explore-status", "Status", options.get("status", []))}
  {_select_filter("explore-domain", "Domain", options.get("domain", []))}
  {_select_filter("explore-profile", "Profile", options.get("profile", []))}
  {_select_filter("explore-environment", "Environment", options.get("environment", []))}
  {_select_filter("explore-failure", "Failure", options.get("failure_category", []))}
  {_select_filter("explore-flaky", "Flaky", options.get("flaky_category", []))}
  {_select_filter("explore-artifact", "Artifact", options.get("artifact_type", []))}
  {_select_filter("explore-duration", "Duration", options.get("duration_bucket", []))}
  <label>Sort
    <select id="explore-sort">
      <option value="status">Status</option>
      <option value="duration_desc">Duration high to low</option>
      <option value="duration_asc">Duration low to high</option>
      <option value="name">Name</option>
      <option value="profile">Profile</option>
      <option value="environment">Environment</option>
    </select>
  </label>
  <label>View
    <select id="explore-view">
      <option value="table">Table</option>
      <option value="cards">Cards</option>
    </select>
  </label>
  <button type="button" class="button" id="explore-reset">Reset</button>
</section>
<section class="result-strip">
  <strong id="explore-result-count">0 tests</strong>
  <span class="muted">Filtered charts update locally from the sidecar test index.</span>
</section>
<section class="grid three chart-grid">
  <article class="chart-card"><h2>Filtered Status</h2><div id="explore-status-chart"></div></article>
  <article class="chart-card"><h2>Filtered Duration</h2><div id="explore-duration-chart"></div></article>
  <article class="chart-card"><h2>Filtered Failures</h2><div id="explore-failure-chart"></div></article>
</section>
<section>
  <div id="explore-results" class="explore-results table-wrap"></div>
</section>
<script type="application/json" id="report-data-json">{_json_for_script(report_data)}</script>
""",
    )


def _render_timeline_page(report: RunReport, events: list[ReportingEvent]) -> str:
    return _page(
        "Timeline",
        f"""
<header class="hero compact"><div><p class="eyebrow">{_e(report.run_id)}</p><h1>Timeline</h1></div></header>
{_nav("timeline")}
<section class="toolbar" data-filter-scope="timeline-table">
  <label class="search-box">Search timeline
    <input type="search" data-filter-search="timeline-table" placeholder="Test, event, action, status">
  </label>
  {_select_filter("timeline-event", "Event", sorted({event.event_type for event in events}), data_filter="event")}
  {_select_filter("timeline-status", "Status", sorted({event.status or "" for event in events if event.status}), data_filter="status")}
</section>
<section>{_timeline_table(events, table_id="timeline-table")}</section>
""",
    )


def _render_flaky_page(report: RunReport) -> str:
    return _page(
        "Flaky Analysis",
        f"""
<header class="hero compact"><div><p class="eyebrow">{_e(report.run_id)}</p><h1>Flaky Analysis</h1></div></header>
{_nav("flaky")}
<section class="toolbar" data-filter-scope="flaky-table">
  <label class="search-box">Search flaky signals
    <input type="search" data-filter-search="flaky-table" placeholder="Category, test, reason, status">
  </label>
  {_select_filter("flaky-category", "Category", sorted({item["category"] for item in flaky_analysis(report)}), data_filter="category")}
  {_select_filter("flaky-status", "Status", sorted({item["status"] for item in flaky_analysis(report)}), data_filter="status")}
</section>
<section>{_analysis_table(flaky_analysis(report), table_id="flaky-table")}</section>
""",
    )


def _render_matrix_page(report: RunReport, report_data: dict[str, Any]) -> str:
    summary = report_data["matrix"]
    sections = "\n".join(
        f'<article class="matrix-section" data-matrix-dimension="{_e(dimension)}">'
        f"<h2>{_e(dimension)}</h2>{_matrix_heatmap(values)}{_matrix_table(values)}</article>"
        for dimension, values in summary.items()
    )
    return _page(
        "Matrix",
        f"""
<header class="hero compact"><div><p class="eyebrow">{_e(report.run_id)}</p><h1>Matrix</h1></div></header>
{_nav("matrix")}
<section class="toolbar" data-filter-scope="matrix-page">
  <label class="search-box">Search matrix
    <input type="search" data-filter-search="matrix-page" placeholder="Dimension, value, status, failure category">
  </label>
  <label>View
    <select data-matrix-view>
      <option value="heatmap">Heatmap and table</option>
      <option value="table">Table focus</option>
      <option value="heatmap-only">Heatmap focus</option>
    </select>
  </label>
</section>
<section class="matrix-page overflow-safe" data-filter-root="matrix-page">{sections or '<article class="empty-state">No matrix metadata found.</article>'}</section>
""",
    )


def _render_history_page(report: RunReport, history_entries: list[dict[str, Any]], report_data: dict[str, Any]) -> str:
    rows = "\n".join(
        f'<tr data-filter-row data-search="{_e(_row_search(entry))}"><td>{_e(_format_datetime(entry.get("latest_run", "")))}</td><td>{_e(entry.get("run_id", ""))}</td>'
        f"<td>{entry.get('pass_rate', 0)}%</td><td>{entry.get('flaky', 0)}</td>"
        f"<td>{entry.get('failed', 0) + entry.get('broken', 0)}</td><td>{_format_duration(entry.get('duration_ms', 0))}</td></tr>"
        for entry in history_entries
    )
    return _page(
        "History",
        f"""
<header class="hero compact"><div><p class="eyebrow">{_e(report.run_id)}</p><h1>History</h1></div></header>
{_nav("history")}
<section>
  <h2>Pass Rate Trend</h2>
  {_trend_bars(trend_points(history_entries))}
</section>
<section>
  <h2>Recent Comparison</h2>
  {_history_comparison_view(report_data["history"]["comparison"])}
</section>
<section class="toolbar" data-filter-scope="history-table">
  <label class="search-box">Search history
    <input type="search" data-filter-search="history-table" placeholder="Run id, date, pass rate">
  </label>
</section>
<section>
  <h2>Runs</h2>
  <div class="table-wrap wide"><table id="history-table"><thead><tr><th>Run Time</th><th>Run ID</th><th>Pass Rate</th><th>Flaky</th><th>Failed</th><th>Duration</th></tr></thead><tbody>{rows or '<tr><td colspan="6">No history yet.</td></tr>'}</tbody></table></div>
</section>
""",
    )


def _nav(active: str, *, prefix: str = "") -> str:
    items = (
        ("dashboard", "Dashboard", "index.html"),
        ("executive", "Executive", "executive.html"),
        ("quality", "Quality", "quality.html"),
        ("compare", "Compare", "compare.html"),
        ("explore", "Tests", "explore.html"),
        ("timeline", "Timeline", "timeline.html"),
        ("flaky", "Flaky", "flaky.html"),
        ("matrix", "Matrix", "matrix.html"),
        ("history", "History", "history.html"),
        ("share", "Share", "share.html"),
    )
    links = "".join(
        f'<a class="{"active" if key == active else ""}" href="{_e(prefix + href)}">{_e(label)}</a>'
        for key, label, href in items
    )
    return f'<nav class="app-nav" aria-label="Report navigation">{links}</nav>'


def _page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_e(title)}</title>
  <style>
    :root {{ color-scheme: light; --ink:#172033; --muted:#5b6472; --line:#dbe3ec; --panel:#ffffff; --bg:#f5f7fa; --accent:#0f766e; --accent-2:#2563eb; --danger:#b91c1c; --warn:#b45309; --ok:#047857; --shadow:0 12px 30px rgba(15,23,42,.08); }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family: Arial, sans-serif; color:var(--ink); background:linear-gradient(180deg,#eef3f8 0,#f7f9fb 260px,#f5f7fa 100%); overflow-x:hidden; }}
    .hero {{ background:linear-gradient(135deg,#0d1b2a,#142f43); color:#fff; padding:30px clamp(18px,4vw,42px); display:flex; justify-content:space-between; gap:18px; align-items:flex-start; border-bottom:1px solid rgba(255,255,255,.16); }}
    .hero.compact {{ padding:22px clamp(18px,4vw,42px); }}
    h1 {{ margin:0 0 8px; font-size:clamp(24px,3vw,34px); letter-spacing:0; overflow-wrap:anywhere; }}
    h2 {{ margin:0 0 14px; font-size:18px; letter-spacing:0; }}
    h3 {{ margin:0 0 10px; font-size:15px; }}
    p {{ margin:0; color:inherit; overflow-wrap:anywhere; }}
    .eyebrow {{ color:#b7c7d7; font-size:12px; text-transform:uppercase; letter-spacing:0; margin-bottom:7px; overflow-wrap:anywhere; }}
    .app-nav {{ position:sticky; top:0; z-index:3; display:flex; gap:6px; flex-wrap:nowrap; overflow-x:auto; padding:12px clamp(18px,4vw,42px); background:rgba(255,255,255,.96); border-bottom:1px solid var(--line); box-shadow:0 1px 0 rgba(15,23,42,.04); scrollbar-gutter:stable; scrollbar-width:thin; -webkit-overflow-scrolling:touch; }}
    .app-nav::-webkit-scrollbar {{ height:6px; }}
    .app-nav::-webkit-scrollbar-thumb {{ background:#cbd5e1; border-radius:999px; }}
    .app-nav a {{ color:#0f5b99; font-weight:700; text-decoration:none; padding:8px 10px; border-radius:8px; white-space:nowrap; }}
    .app-nav a.active {{ background:#e7f3ff; color:#0b4d83; box-shadow:inset 0 0 0 1px #bfdbfe; }}
    section {{ margin:22px clamp(18px,4vw,42px); max-width:100%; }}
    article {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:16px; min-width:0; max-width:100%; overflow:hidden; box-shadow:var(--shadow); }}
    .metrics {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(130px,1fr)); gap:12px; }}
    .metrics.compact {{ margin-bottom:12px; }}
    .metric {{ background:#fff; border:1px solid var(--line); border-radius:8px; padding:14px; min-width:0; box-shadow:0 4px 18px rgba(15,23,42,.05); }}
    .metric strong {{ display:block; font-size:26px; margin-bottom:4px; overflow-wrap:anywhere; }}
    .grid {{ display:grid; gap:16px; }}
    .grid.two {{ grid-template-columns:repeat(auto-fit,minmax(min(320px,100%),1fr)); }}
    .grid.three {{ grid-template-columns:repeat(auto-fit,minmax(min(260px,100%),1fr)); }}
    .grid.four {{ grid-template-columns:repeat(auto-fit,minmax(min(220px,100%),1fr)); }}
    .chart-grid article {{ min-height:220px; }}
    .insight-card {{ display:grid; gap:12px; align-content:start; }}
    .toolbar {{ display:flex; flex-wrap:wrap; gap:12px; align-items:end; padding:14px; background:#fff; border:1px solid var(--line); border-radius:8px; }}
    .toolbar label {{ display:flex; flex-direction:column; gap:5px; font-size:12px; color:var(--muted); font-weight:700; min-width:150px; }}
    .search-box {{ flex:1 1 280px; }}
    input,select,button,.button {{ border:1px solid #cbd5e1; border-radius:8px; padding:9px 10px; font:inherit; background:#fff; color:var(--ink); max-width:100%; }}
    .button {{ display:inline-flex; align-items:center; text-decoration:none; font-weight:700; color:#0f5b99; cursor:pointer; }}
    .result-strip {{ display:flex; gap:12px; flex-wrap:wrap; align-items:center; }}
    .table-wrap {{ width:100%; max-width:100%; overflow-x:auto; border-radius:8px; }}
    .table-wrap.wide table {{ min-width:720px; table-layout:auto; }}
    .compare-table table {{ min-width:520px; }}
    table {{ border-collapse:collapse; width:100%; min-width:0; background:#fff; border:1px solid var(--line); table-layout:fixed; }}
    th,td {{ border-bottom:1px solid #e9edf2; padding:10px; text-align:left; vertical-align:top; overflow-wrap:anywhere; word-break:break-word; min-width:0; }}
    th {{ background:#eef2f6; color:#263345; }}
    .kv-table th {{ width:34%; max-width:180px; }}
    .kv-table td {{ width:66%; }}
    pre {{ white-space:pre-wrap; overflow:auto; background:#f4f6f8; border:1px solid #e1e6ed; border-radius:6px; padding:10px; max-width:100%; }}
    details {{ margin-top:10px; }}
    summary {{ cursor:pointer; color:#0f5b99; font-weight:700; }}
    .status {{ display:inline-block; padding:5px 9px; border-radius:999px; font-size:12px; font-weight:700; text-transform:uppercase; white-space:nowrap; line-height:1; }}
    .passed {{ color:#047857; background:#dff7ed; }}
    .warning {{ color:#92400e; background:#fef3c7; }}
    .failed,.broken,.failed_broken {{ color:#b91c1c; background:#fee2e2; }}
    .skipped {{ color:#92400e; background:#fef3c7; }}
    .unknown {{ color:#4b5563; background:#e5e7eb; }}
    .low {{ color:#047857; background:#dff7ed; }}
    .medium {{ color:#92400e; background:#fef3c7; }}
    .high {{ color:#b91c1c; background:#fee2e2; }}
    .score-ring {{ width:min(150px,100%); aspect-ratio:1; border-radius:50%; display:grid; place-items:center; margin:4px 0 14px; background:conic-gradient(var(--ok) 0 75%,#e5e7eb 75% 100%); box-shadow:inset 0 0 0 18px #fff,0 8px 18px rgba(15,23,42,.08); }}
    .score-ring strong {{ font-size:28px; }}
    .score-ring span {{ color:var(--muted); font-size:12px; text-transform:uppercase; font-weight:700; }}
    .score-ring.status-warning {{ background:conic-gradient(var(--warn) 0 62%,#e5e7eb 62% 100%); }}
    .score-ring.status-failed {{ background:conic-gradient(var(--danger) 0 45%,#e5e7eb 45% 100%); }}
    .score-ring.status-unknown {{ background:conic-gradient(#64748b 0 20%,#e5e7eb 20% 100%); }}
    .bar,.hbar-track {{ height:9px; background:#e5e7eb; border-radius:999px; overflow:hidden; min-width:80px; }}
    .bar span,.hbar-fill {{ display:block; height:100%; background:var(--accent); }}
    .hbar-row {{ display:grid; grid-template-columns:minmax(90px,1fr) minmax(90px,2fr) auto; gap:10px; align-items:center; margin:9px 0; }}
    .hbar-label,.truncate {{ overflow:hidden; text-overflow:ellipsis; white-space:nowrap; min-width:0; }}
    .donut-wrap {{ display:flex; align-items:center; gap:16px; flex-wrap:wrap; }}
    .donut {{ width:132px; height:132px; border-radius:50%; display:grid; place-items:center; box-shadow:inset 0 0 0 24px #fff; }}
    .donut strong {{ background:#fff; border-radius:999px; padding:18px 10px; min-width:72px; text-align:center; }}
    .legend {{ display:grid; gap:7px; }}
    .legend span {{ display:inline-flex; gap:7px; align-items:center; }}
    .swatch {{ width:10px; height:10px; border-radius:3px; display:inline-block; }}
    .risk-list,.coverage-list {{ display:grid; gap:10px; min-width:0; }}
    .risk {{ border-left:4px solid var(--accent-2); padding:10px 12px; background:#f8fafc; border-radius:6px; min-width:0; overflow:hidden; }}
    .risk.high {{ border-left-color:var(--danger); }}
    .risk.medium {{ border-left-color:var(--warn); }}
    .risk a,.risk .muted {{ overflow-wrap:anywhere; word-break:break-word; }}
    .share-banner {{ display:flex; gap:12px; flex-wrap:wrap; align-items:center; padding:13px 14px; background:#edf7f4; border:1px solid #b8ded4; border-radius:8px; }}
    .safe-badge {{ display:inline-flex; align-items:center; gap:7px; font-weight:700; color:#0f5b46; background:#dff7ed; border:1px solid #a7d9c9; border-radius:999px; padding:6px 10px; }}
    .export-card,.stakeholder-card {{ display:grid; gap:10px; align-content:start; }}
    .export-links {{ display:grid; gap:7px; }}
    .print-summary {{ display:grid; gap:16px; }}
    .tag-cloud {{ display:flex; gap:8px; flex-wrap:wrap; }}
    .tag {{ background:#edf2f7; color:#263345; border-radius:999px; padding:5px 8px; font-size:12px; overflow-wrap:anywhere; }}
    .matrix-page {{ display:grid; gap:18px; }}
    .matrix-section {{ overflow:hidden; }}
    .matrix-heatmap {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(min(220px,100%),1fr)); gap:10px; margin-bottom:14px; }}
    body[data-matrix-view="table"] .matrix-heatmap {{ display:none; }}
    body[data-matrix-view="heatmap-only"] .matrix-table {{ display:none; }}
    .heat-cell {{ border:1px solid var(--line); border-radius:8px; padding:14px; background:#f8fafc; min-width:0; display:grid; gap:12px; align-content:start; }}
    .heat-head {{ display:flex; justify-content:space-between; align-items:flex-start; gap:12px; min-width:0; }}
    .heat-name {{ font-weight:700; overflow-wrap:anywhere; min-width:0; line-height:1.25; }}
    .heat-value {{ flex:0 0 auto; white-space:nowrap; }}
    .heat-bar {{ height:11px; background:#e5e7eb; border-radius:999px; overflow:hidden; margin:4px 0; }}
    .heat-bar span {{ display:block; height:100%; background:linear-gradient(90deg,#dc2626,#eab308,#16a34a); }}
    .heat-details {{ color:var(--muted); font-size:13px; line-height:1.45; display:grid; gap:3px; overflow-wrap:anywhere; word-break:break-word; }}
    .heat-failures {{ color:#425066; }}
    .explore-card-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(min(300px,100%),1fr)); gap:12px; }}
    .test-card {{ border:1px solid var(--line); border-radius:8px; padding:14px; background:#fff; min-width:0; }}
    .empty-state {{ color:var(--muted); padding:18px; background:#fff; border:1px dashed var(--line); border-radius:8px; }}
    img.preview {{ max-width:100%; border:1px solid var(--line); border-radius:6px; }}
    video {{ max-width:100%; }}
    a {{ color:#0f5b99; overflow-wrap:anywhere; word-break:break-word; }}
    li {{ min-width:0; overflow-wrap:anywhere; word-break:break-word; }}
    .muted {{ color:var(--muted); }}
    [hidden] {{ display:none !important; }}
    @media (max-width:720px) {{
      .hero {{ flex-direction:column; }}
      .toolbar label {{ flex:1 1 100%; }}
      .table-wrap.wide {{ overflow-x:visible; }}
      .table-wrap.wide table {{ min-width:0; border:0; background:transparent; table-layout:auto; }}
      .table-wrap.wide thead {{ display:none; }}
      .table-wrap.wide tbody,.table-wrap.wide tr,.table-wrap.wide td {{ display:block; width:100%; }}
      .table-wrap.wide tr {{ margin:0 0 12px; border:1px solid var(--line); border-radius:8px; background:#fff; padding:8px 10px; }}
      .table-wrap.wide td {{ border-bottom:1px solid #e9edf2; padding:8px 0; }}
      .table-wrap.wide td:last-child {{ border-bottom:0; }}
      .table-wrap.wide td::before {{ content:attr(data-label); display:block; margin-bottom:3px; color:var(--muted); font-size:11px; font-weight:700; text-transform:uppercase; }}
      .table-wrap.wide td[colspan]::before {{ display:none; }}
      .table-wrap.wide .status {{ white-space:normal; }}
      .hbar-label,.truncate {{ white-space:normal; overflow:visible; text-overflow:clip; overflow-wrap:anywhere; }}
      .bar,.hbar-track {{ min-width:0; width:100%; }}
      .hbar-row {{ grid-template-columns:1fr; }}
    }}
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
    function textOf(row) {{
      return (row.dataset.search || row.textContent || '').toLowerCase();
    }}
    function applyFilterScope(scope) {{
      const input = document.querySelector(`[data-filter-search="${{scope}}"]`);
      const query = input ? input.value.toLowerCase() : '';
      const selects = Array.from(document.querySelectorAll(`[data-filter-scope="${{scope}}"] select[data-filter]`));
      document.querySelectorAll(`#${{scope}} [data-filter-row], [data-filter-root="${{scope}}"] [data-filter-row]`).forEach((row) => {{
        const queryMatch = !query || textOf(row).includes(query);
        const selectMatch = selects.every((select) => !select.value || (row.dataset[select.dataset.filter] || '').split('|').includes(select.value));
        row.hidden = !(queryMatch && selectMatch);
      }});
    }}
    function setupGenericFilters() {{
      hydrateResponsiveTables();
      document.querySelectorAll('[data-filter-search]').forEach((input) => {{
        const scope = input.dataset.filterSearch;
        input.addEventListener('input', () => applyFilterScope(scope));
      }});
      document.querySelectorAll('select[data-filter]').forEach((select) => {{
        const toolbar = select.closest('[data-filter-scope]');
        if (toolbar) select.addEventListener('change', () => applyFilterScope(toolbar.dataset.filterScope));
      }});
      const dashSearch = document.getElementById('dashboard-search');
      const dashLink = document.getElementById('dashboard-explore-link');
      if (dashSearch && dashLink) {{
        dashSearch.addEventListener('input', () => {{
          dashLink.href = 'explore.html?q=' + encodeURIComponent(dashSearch.value);
        }});
      }}
      const matrixView = document.querySelector('[data-matrix-view]');
      if (matrixView) {{
        matrixView.addEventListener('change', () => {{
          document.body.dataset.matrixView = matrixView.value;
        }});
      }}
    }}
    function hydrateResponsiveTables(scope) {{
      const root = scope || document;
      root.querySelectorAll('.table-wrap.wide table').forEach((table) => {{
        const headers = Array.from(table.querySelectorAll('thead th')).map((header) => header.textContent.trim());
        table.querySelectorAll('tbody tr').forEach((row) => {{
          Array.from(row.children).forEach((cell, index) => {{
            if (cell.tagName === 'TD' && !cell.dataset.label) cell.dataset.label = headers[index] || '';
          }});
        }});
      }});
    }}
    function countBy(items, fn, fallback = 'unknown') {{
      return items.reduce((acc, item) => {{
        const raw = fn(item);
        if (!raw && fallback === null) return acc;
        const value = raw || fallback;
        acc[value] = (acc[value] || 0) + 1;
        return acc;
      }}, {{}});
    }}
    function barChart(values) {{
      const entries = Object.entries(values).filter(([, value]) => value);
      if (!entries.length) return '<p class="muted">No data.</p>';
      const max = Math.max(...entries.map(([, value]) => Number(value) || 0), 1);
      return entries.map(([key, value]) => `<div class="hbar-row"><div class="hbar-label" title="${{escapeAttr(key)}}">${{escapeHtml(key)}}</div><div class="hbar-track"><span class="hbar-fill" style="width:${{Math.round((num(value) / max) * 100)}}%"></span></div><strong>${{escapeHtml(value)}}</strong></div>`).join('');
    }}
    function renderExplore(items) {{
      const root = document.getElementById('explore-results');
      if (!root) return;
      const status = document.getElementById('explore-status').value;
      const domain = document.getElementById('explore-domain').value;
      const profile = document.getElementById('explore-profile').value;
      const environment = document.getElementById('explore-environment').value;
      const failure = document.getElementById('explore-failure').value;
      const flaky = document.getElementById('explore-flaky').value;
      const artifact = document.getElementById('explore-artifact').value;
      const duration = document.getElementById('explore-duration').value;
      const query = document.getElementById('explore-search').value.toLowerCase();
      const filtered = items.filter((item) =>
        (!query || (item.search_text || '').includes(query)) &&
        (!status || item.status === status) &&
        (!domain || item.domain === domain) &&
        (!profile || item.profile === profile) &&
        (!environment || item.environment === environment) &&
        (!failure || ((item.failure || {{}}).category) === failure) &&
        (!flaky || (item.flaky_categories || []).includes(flaky)) &&
        (!artifact || (item.artifact_types || []).includes(artifact)) &&
        (!duration || item.duration_bucket === duration)
      );
      const sort = document.getElementById('explore-sort').value;
      filtered.sort((a, b) => {{
        if (sort === 'duration_desc') return b.duration_ms - a.duration_ms;
        if (sort === 'duration_asc') return a.duration_ms - b.duration_ms;
        return String(a[sort] || '').localeCompare(String(b[sort] || ''));
      }});
      const view = document.getElementById('explore-view').value;
      document.getElementById('explore-result-count').textContent = `${{filtered.length}} tests`;
      document.getElementById('explore-status-chart').innerHTML = barChart(countBy(filtered, (item) => item.status));
      document.getElementById('explore-duration-chart').innerHTML = barChart(countBy(filtered, (item) => item.duration_bucket));
      document.getElementById('explore-failure-chart').innerHTML = barChart(countBy(filtered, (item) => (item.failure || {{}}).category, null));
      if (view === 'cards') {{
        root.className = 'explore-card-grid';
        root.innerHTML = filtered.map((item) => `<article class="test-card"><span class="status ${{classToken(item.status)}}">${{escapeHtml(item.status)}}</span><h3><a href="${{safeHref(item.detail_href)}}">${{escapeHtml(item.name)}}</a></h3><p class="muted">${{escapeHtml(item.full_name || item.test_id)}}</p><p>${{escapeHtml((item.failure || {{}}).title || '-')}}</p><p class="muted">${{Math.round(num(item.duration_ms))}} ms · ${{escapeHtml(item.profile || item.environment || '-')}}</p></article>`).join('') || '<p class="empty-state">No tests match the filters.</p>';
        return;
      }}
      root.className = 'table-wrap wide';
      root.innerHTML = `<table><thead><tr><th>Status</th><th>Test</th><th>Domain</th><th>Profile</th><th>Environment</th><th>Duration</th><th>Failure</th><th>Signals</th></tr></thead><tbody>${{filtered.map((item) => `<tr><td><span class="status ${{classToken(item.status)}}">${{escapeHtml(item.status)}}</span></td><td><a href="${{safeHref(item.detail_href)}}">${{escapeHtml(item.name)}}</a><br><span class="muted">${{escapeHtml(item.full_name || item.test_id)}}</span></td><td>${{escapeHtml(item.domain || '-')}}</td><td>${{escapeHtml(item.profile || '-')}}</td><td>${{escapeHtml(item.environment || '-')}}</td><td>${{Math.round(num(item.duration_ms))}} ms</td><td>${{escapeHtml((item.failure || {{}}).title || '-')}}</td><td>R:${{num(item.retry_count)}} A:${{num(item.action_retry_count)}} H:${{num(item.healing_event_count)}} Art:${{num(item.artifact_count)}}</td></tr>`).join('') || '<tr><td colspan="8">No tests match the filters.</td></tr>'}}</tbody></table>`;
      hydrateResponsiveTables(root);
    }}
    function setupExplore() {{
      const dataNode = document.getElementById('report-data-json');
      if (!dataNode) return;
      const data = JSON.parse(dataNode.textContent);
      const items = data.test_index || [];
      const params = new URLSearchParams(window.location.search);
      if (params.get('q')) document.getElementById('explore-search').value = params.get('q');
      ['explore-search','explore-status','explore-domain','explore-profile','explore-environment','explore-failure','explore-flaky','explore-artifact','explore-duration','explore-sort','explore-view'].forEach((id) => {{
        const node = document.getElementById(id);
        if (node) node.addEventListener('input', () => renderExplore(items));
        if (node) node.addEventListener('change', () => renderExplore(items));
      }});
      const reset = document.getElementById('explore-reset');
      if (reset) reset.addEventListener('click', () => {{
        document.querySelectorAll('.explore-toolbar input,.explore-toolbar select').forEach((node) => node.value = '');
        document.getElementById('explore-sort').value = 'status';
        document.getElementById('explore-view').value = 'table';
        renderExplore(items);
      }});
      renderExplore(items);
    }}
    document.addEventListener('DOMContentLoaded', () => {{
      setupGenericFilters();
      setupExplore();
    }});
  </script>
</head>
<body data-visual-system="enterprise-redesign">
{body}
</body>
</html>
"""


def _metric(label: str, value: Any) -> str:
    return f'<div class="metric"><strong>{_e(value)}</strong>{_e(label)}</div>'


def _metric_with_note(label: str, value: Any, note: Any) -> str:
    return (
        f'<div class="metric" title="{_e(note)}"><strong>{_e(value)}</strong>{_e(label)}'
        f'<br><span class="muted">{_e(note)}</span></div>'
    )


def _select_filter(
    element_id: str,
    label: str,
    options: list[str],
    *,
    data_filter: str | None = None,
) -> str:
    data_attr = f' data-filter="{_e(data_filter)}"' if data_filter else ""
    option_html = "".join(f'<option value="{_e(option)}">{_e(option)}</option>' for option in options if option)
    return (
        f"<label>{_e(label)}"
        f'<select id="{_e(element_id)}"{data_attr}><option value="">All</option>{option_html}</select>'
        "</label>"
    )


def _donut_chart(values: dict[str, Any]) -> str:
    colors = {
        "passed": "#16a34a",
        "failed_broken": "#dc2626",
        "skipped": "#d97706",
        "unknown": "#64748b",
    }
    total = sum(int(value or 0) for value in values.values())
    if not total:
        return '<p class="empty-state">No tests available.</p>'
    start = 0.0
    stops: list[str] = []
    legend: list[str] = []
    for key, value in values.items():
        count = int(value or 0)
        if not count:
            continue
        end = start + (count / total) * 100
        color = colors.get(key, "#64748b")
        stops.append(f"{color} {start:.2f}% {end:.2f}%")
        legend.append(
            f'<span><i class="swatch" style="background:{color}"></i>{_e(_humanize_label(key))}: {count}</span>'
        )
        start = end
    return (
        '<div class="donut-wrap">'
        f'<div class="donut" style="background:conic-gradient({", ".join(stops)})"><strong>{total}<br>tests</strong></div>'
        f'<div class="legend">{"".join(legend)}</div>'
        "</div>"
    )


def _bar_chart(values: dict[str, Any], *, empty: str = "No data.") -> str:
    items = [(str(key), int(value or 0)) for key, value in values.items() if int(value or 0)]
    if not items:
        return f'<p class="empty-state">{_e(empty)}</p>'
    max_value = max(value for _, value in items) or 1
    return "".join(
        f'<div class="hbar-row" data-filter-row data-search="{_e(key)}">'
        f'<div class="hbar-label" title="{_e(key)}">{_e(_humanize_label(key))}</div>'
        f'<div class="hbar-track"><span class="hbar-fill" style="width:{round((value / max_value) * 100)}%"></span></div>'
        f"<strong>{value}</strong></div>"
        for key, value in items
    )


def _slow_tests_chart(tests: list[dict[str, Any]], details: dict[str, str]) -> str:
    if not tests:
        return '<p class="empty-state">No duration data.</p>'
    max_duration = max(float(test.get("duration_ms", 0) or 0) for test in tests) or 1
    rows = []
    for test in tests[:8]:
        duration = float(test.get("duration_ms", 0) or 0)
        href = details.get(str(test.get("test_id", "")), "#")
        rows.append(
            f'<div class="hbar-row"><a class="hbar-label" href="{_e(href)}" title="{_e(test.get("name", ""))}">{_e(test.get("name", ""))}</a>'
            f'<div class="hbar-track"><span class="hbar-fill" style="width:{round((duration / max_duration) * 100)}%"></span></div>'
            f"<strong>{_format_duration(duration)}</strong></div>"
        )
    return "".join(rows)


def _retry_signal_chart_values(signals: dict[str, Any]) -> dict[str, int]:
    return {
        "test_retries": int(signals.get("test_retry_count", 0)),
        "action_retries": int(signals.get("action_retry_count", 0)),
        "healing_events": int(signals.get("healing_event_count", 0)),
    }


def _trend_chart(points: list[dict[str, Any]]) -> str:
    if not points:
        return '<p class="empty-state">No history trend yet.</p>'
    width = 520
    height = 170
    plot = points[-12:]
    if len(plot) == 1:
        x_values = [width / 2]
    else:
        x_values = [(index / (len(plot) - 1)) * (width - 40) + 20 for index in range(len(plot))]
    y_values = [height - 24 - (float(point.get("pass_rate", 0)) / 100) * (height - 48) for point in plot]
    polyline = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(x_values, y_values, strict=False))
    label_step = max(1, len(plot) // 6)
    labels = "".join(
        f'<text x="{x:.1f}" y="{height - 6}" font-size="10" text-anchor="middle">{_e(point.get("run_id", ""))[:8]}</text>'
        for index, (x, point) in enumerate(zip(x_values, plot, strict=False))
        if index % label_step == 0 or index == len(plot) - 1
    )
    dots = "".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4"><title>{_e(point.get("run_id", ""))}: {point.get("pass_rate", 0)}%</title></circle>'
        for x, y, point in zip(x_values, y_values, plot, strict=False)
    )
    return (
        f'<svg class="trend-svg" viewBox="0 0 {width} {height}" role="img" aria-label="History pass-rate trend">'
        '<line x1="20" y1="20" x2="20" y2="146" stroke="#cbd5e1"/>'
        '<line x1="20" y1="146" x2="500" y2="146" stroke="#cbd5e1"/>'
        f'<polyline points="{polyline}" fill="none" stroke="#0f766e" stroke-width="3"/>'
        f'<g fill="#0f766e">{dots}</g><g fill="#64748b">{labels}</g></svg>'
    )


def _risk_signal_list(risks: list[dict[str, Any]]) -> str:
    if not risks:
        return '<p class="empty-state">No risk signals detected.</p>'
    items = []
    for risk in risks:
        tests = risk.get("tests") or []
        test_links = ", ".join(
            f'<a href="{_e(test.get("detail_href", "#"))}">{_e(test.get("name", ""))}</a>' for test in tests
        )
        items.append(
            f'<div class="risk {_e(risk.get("severity", ""))}"><strong>{_e(risk.get("title", ""))}: {risk.get("count", 0)}</strong>'
            f'<br><span class="muted">{test_links or "Review sidecar details."}</span></div>'
        )
    return f'<div class="risk-list">{"".join(items)}</div>'


def _readiness_summary(summary: dict[str, Any]) -> dict[str, str]:
    failed = int(summary.get("failed", 0) or 0) + int(summary.get("broken", 0) or 0)
    skipped = int(summary.get("skipped", 0) or 0)
    flaky = int(summary.get("flaky", 0) or 0)
    pass_rate = float(summary.get("pass_rate", 0) or 0)
    if failed:
        return {
            "headline": f"Release attention needed: {failed} failing tests and {pass_rate:g}% pass rate.",
            "next_action": "Review top blockers, assign owners, and rerun after fixes land.",
        }
    if flaky:
        return {
            "headline": f"Release mostly ready with {flaky} flaky signals to review.",
            "next_action": "Review flaky tests and retry signals before final sign-off.",
        }
    if skipped:
        return {
            "headline": f"Release candidate passing with {skipped} skipped tests.",
            "next_action": "Confirm skipped coverage is accepted for this run.",
        }
    if summary.get("total", 0):
        return {
            "headline": f"Release candidate passing at {pass_rate:g}% pass rate.",
            "next_action": "Share the summary and keep the full report package for traceability.",
        }
    return {
        "headline": "No tests were captured in this run.",
        "next_action": "Verify results collection and rerun the suite.",
    }


def _executive_blockers(clusters: list[dict[str, Any]], risks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    for cluster in clusters[:4]:
        blockers.append(
            {
                "title": cluster.get("title", cluster.get("category", "Failure cluster")),
                "count": cluster.get("count", 0),
                "detail": cluster.get("detail", ""),
            }
        )
    if blockers:
        return blockers
    for risk in risks[:4]:
        blockers.append(
            {
                "title": risk.get("title", "Risk signal"),
                "count": risk.get("count", 0),
                "detail": "Review the linked tests and supporting artifacts.",
            }
        )
    return blockers


def _blocker_list(blockers: list[dict[str, Any]]) -> str:
    if not blockers:
        return '<p class="empty-state">No blockers detected.</p>'
    items = "".join(
        f"<li><strong>{_e(item.get('title', ''))}</strong>: {item.get('count', 0)}"
        f'<br><span class="muted">{_e(item.get("detail", ""))}</span></li>'
        for item in blockers
    )
    return f"<ul>{items}</ul>"


def _safe_share_badge(report_data: dict[str, Any]) -> str:
    safe_share = report_data.get("sharing", {}).get("safe_share", {})
    label = "Safe Sharing On" if safe_share.get("enabled") else "Safe Sharing Off"
    categories = ", ".join(safe_share.get("redacted_categories", [])) or "no sensitive categories detected"
    return f'<span class="safe-badge">{_e(label)}</span><span class="muted">{_e(categories)}</span>'


def _link_list(links: dict[str, str]) -> str:
    return (
        '<div class="export-links">'
        + "".join(f'<a class="button" href="{_e(href)}">{_e(label)}</a>' for label, href in links.items())
        + "</div>"
    )


def _export_card(title: str, body: str, links: dict[str, str]) -> str:
    return f'<article class="export-card"><h2>{_e(title)}</h2><p>{_e(body)}</p>{_link_list(links)}</article>'


def _stakeholder_card(title: str, body: str, links: dict[str, str]) -> str:
    return f'<article class="stakeholder-card"><h3>{_e(title)}</h3><p>{_e(body)}</p>{_link_list(links)}</article>'


def _artifact_index_table(artifacts: list[dict[str, Any]]) -> str:
    rows = "\n".join(
        f'<tr data-filter-row data-search="{_e(_row_search(item))}">'
        f"<td>{_e(item.get('test_name', ''))}</td><td>{_e(item.get('name', ''))}</td>"
        f"<td>{_e(item.get('artifact_type', ''))}</td><td>{_e(item.get('href') or item.get('path') or '')}</td>"
        f"<td>{_e('yes' if item.get('bundled') else 'no')}</td></tr>"
        for item in artifacts
    )
    empty = '<tr><td colspan="5">No artifacts captured.</td></tr>'
    return (
        '<div class="table-wrap wide"><table><thead><tr><th>Test</th><th>Name</th><th>Type</th><th>Link</th><th>Bundled</th></tr></thead>'
        f"<tbody>{rows or empty}</tbody></table></div>"
    )


def _coverage_panel(coverage: dict[str, dict[str, int]]) -> str:
    if not coverage:
        return '<p class="empty-state">No coverage metadata found.</p>'
    sections = []
    for dimension, counts in coverage.items():
        tags = "".join(f'<span class="tag">{_e(value)} · {count}</span>' for value, count in counts.items())
        sections.append(
            f'<article><h3>{_e(_humanize_label(dimension))}</h3><div class="tag-cloud">{tags}</div></article>'
        )
    return f'<div class="grid three coverage-list">{"".join(sections)}</div>'


def _test_row(test: TestCaseReport, href: str) -> str:
    profile = (
        test.profile or test.environment or test.metadata.get("browser") or test.metadata.get("device_name") or "-"
    )
    return (
        f'<tr data-filter-row data-search="{_e(_test_search(test))}" data-status="{_e(test.status)}">'
        f'<td><span class="status {test.status}">{_e(test.status)}</span></td>'
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


def _failure_cluster_list(clusters: list[dict[str, Any]]) -> str:
    if not clusters:
        return "<p>No failures.</p>"
    items = "".join(
        f"<li><strong>{_e(cluster['title'])}</strong>: {cluster['count']}"
        f'<br><span class="muted">{_e(cluster["detail"])}</span></li>'
        for cluster in clusters
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


def _analysis_table(items: list[dict[str, Any]], *, table_id: str = "analysis-table") -> str:
    rows = "\n".join(
        f'<tr data-filter-row data-search="{_e(_row_search(item))}" data-category="{_e(item["category"])}" data-status="{_e(item["status"])}">'
        f"<td>{_e(item['category'])}</td><td>{_e(item['name'])}</td><td>{_e(item['status'])}</td>"
        f"<td>{_format_duration(item['duration_ms'])}</td><td>{_e(item['reason'])}</td></tr>"
        for item in items
    )
    empty_row = '<tr><td colspan="5">No flaky signals found.</td></tr>'
    return (
        f'<div class="table-wrap wide"><table id="{_e(table_id)}"><thead><tr><th>Category</th><th>Test</th><th>Status</th><th>Duration</th><th>Reason</th></tr></thead>'
        f"<tbody>{rows or empty_row}</tbody></table></div>"
    )


def _flaky_breakdown_view(breakdown: dict[str, int]) -> str:
    if not any(breakdown.values()):
        return "<p>No flaky signals found.</p>"
    return (
        '<div class="metrics compact">'
        + "".join(_metric(_humanize_label(category), count) for category, count in breakdown.items())
        + "</div>"
    )


def _timeline_table(events: list[ReportingEvent], *, table_id: str = "timeline-table") -> str:
    rows = "\n".join(
        f'<tr data-filter-row data-search="{_e(_row_search(event.to_dict()))}" data-event="{_e(event.event_type)}" data-status="{_e(event.status or "")}">'
        f"<td>{_e(_format_datetime(event.timestamp))}</td><td>{_e(event.event_type)}</td><td>{_e(event.test_name or '')}</td>"
        f"<td>{_e(event.title)}</td><td>{_e(event.status or '')}</td><td>{_format_duration(event.duration_ms or 0)}</td></tr>"
        for event in events
    )
    empty_row = '<tr><td colspan="6">No timeline events.</td></tr>'
    return (
        f'<div class="table-wrap wide"><table id="{_e(table_id)}"><thead><tr><th>Time</th><th>Event</th><th>Test</th><th>Title</th><th>Status</th><th>Duration</th></tr></thead>'
        f"<tbody>{rows or empty_row}</tbody></table></div>"
    )


def _matrix_table(values: dict[str, dict[str, Any]]) -> str:
    rows = "\n".join(
        f'<tr data-filter-row data-search="{_e(name)} {_e(_inline_counts(counts.get("failure_categories", {})))}" data-status="{_e(_matrix_status(counts))}">'
        f"<td>{_e(name)}</td><td>{counts['total']}</td><td>{counts['passed']}</td>"
        f"<td>{counts['failed'] + counts['broken']}</td><td>{counts['skipped']}</td>"
        f"<td>{counts.get('pass_rate', 0)}%</td><td>{_e(_inline_counts(counts.get('failure_categories', {})))}</td></tr>"
        for name, counts in values.items()
    )
    return (
        '<div class="table-wrap wide matrix-table"><table><thead><tr><th>Name</th><th>Total</th><th>Passed</th><th>Failed</th><th>Skipped</th>'
        "<th>Pass Rate</th><th>Failure Categories</th></tr></thead><tbody>" + rows + "</tbody></table></div>"
    )


def _matrix_heatmap(values: dict[str, dict[str, Any]]) -> str:
    if not values:
        return '<p class="empty-state">No matrix values.</p>'
    cells = []
    for name, counts in values.items():
        pass_rate = float(counts.get("pass_rate", 0) or 0)
        failures = counts.get("failed", 0) + counts.get("broken", 0)
        cells.append(
            f'<div class="heat-cell" data-filter-row data-search="{_e(name)} {_e(_inline_counts(counts.get("failure_categories", {})))}" data-status="{_e(_matrix_status(counts))}">'
            f'<div class="heat-head"><span class="heat-name">{_e(name)}</span><strong class="heat-value">{pass_rate:g}%</strong></div>'
            f'<div class="heat-bar"><span style="width:{max(3, min(100, round(pass_rate)))}%"></span></div>'
            f'<p class="heat-details"><span>{counts.get("total", 0)} tests · {failures} failed</span>'
            f'<span class="heat-failures">{_e(_inline_counts(counts.get("failure_categories", {})) or "No failure categories")}</span></p>'
            "</div>"
        )
    return f'<div class="matrix-heatmap">{"".join(cells)}</div>'


def _steps_view(steps: list[StepRecord]) -> str:
    if not steps:
        return "<p>No steps captured.</p>"
    return "<ol>" + "".join(_step_item(step) for step in steps) + "</ol>"


def _step_item(step: StepRecord) -> str:
    children = "<ol>" + "".join(_step_item(child) for child in step.children) + "</ol>" if step.children else ""
    return (
        f'<li data-filter-row data-search="{_e(_row_search(step.to_dict()))}"><span class="status {step.status}">{_e(step.status)}</span> {_e(step.name)} '
        f'<span class="muted">{_format_duration(step.duration_ms)}</span>{children}</li>'
    )


def _retry_table(retries: list[Any]) -> str:
    rows = "\n".join(
        f'<tr data-filter-row data-search="{_e(_row_search(retry.to_dict()))}">'
        f"<td>{retry.attempt}</td><td>{_e(retry.retry_type)}</td><td>{_e(retry.action or '')}</td>"
        f"<td>{_e(retry.status)}</td><td>{_format_duration(retry.duration_ms)}</td><td>{_e(retry.reason)}</td></tr>"
        for retry in retries
    )
    empty_row = '<tr><td colspan="6">No retries.</td></tr>'
    return (
        '<div class="table-wrap wide">'
        "<table><thead><tr><th>Attempt</th><th>Type</th><th>Action</th><th>Status</th><th>Duration</th><th>Reason</th></tr></thead>"
        f"<tbody>{rows or empty_row}</tbody></table></div>"
    )


def _healing_table(events: list[dict[str, Any]]) -> str:
    if not events:
        return "<p>No healing events captured.</p>"
    rows = "\n".join(
        f'<tr data-filter-row data-search="{_e(_row_search(event))}">'
        f"<td>{_e(event.get('mode', ''))}</td><td>{_e(event.get('decision', ''))}</td>"
        f"<td>{_e(event.get('action', ''))}</td><td>{_e(_healing_selected_value(event))}</td>"
        f"<td>{_e(_healing_selected_score(event))}</td><td>{_e(event.get('reason', ''))}</td></tr>"
        for event in events
    )
    return (
        '<div class="table-wrap wide">'
        "<table><thead><tr><th>Mode</th><th>Decision</th><th>Action</th><th>Selected</th>"
        "<th>Score</th><th>Reason</th></tr></thead><tbody>" + rows + "</tbody></table></div>"
    )


def _healing_events(test: TestCaseReport) -> list[dict[str, Any]]:
    events = test.metadata.get("healing_events", [])
    if not isinstance(events, list):
        return []
    return [event for event in events if isinstance(event, dict)]


def _healing_selected_value(event: dict[str, Any]) -> str:
    selected = event.get("selected")
    if not isinstance(selected, dict):
        return "-"
    candidate = selected.get("candidate")
    if not isinstance(candidate, dict):
        return "-"
    return str(candidate.get("value") or "-")


def _healing_selected_score(event: dict[str, Any]) -> str:
    selected = event.get("selected")
    if not isinstance(selected, dict):
        return "-"
    score = selected.get("score")
    if score is None:
        return "-"
    return str(score)


def _artifacts_view(artifacts: list[Artifact], page_dir: Path, report_root: Path, *, safe_share: bool) -> str:
    if not artifacts:
        return "<p>No artifacts captured.</p>"
    return "\n".join(
        _artifact_panel(artifact, page_dir, report_root, index, safe_share=safe_share)
        for index, artifact in enumerate(artifacts, start=1)
    )


def _artifact_panel(artifact: Artifact, page_dir: Path, report_root: Path, index: int, *, safe_share: bool) -> str:
    href = _artifact_href(artifact, page_dir, report_root)
    link = f'<p><a href="{_e(href)}">{_e(href)}</a></p>' if href else ""
    preview = _artifact_preview(artifact, href, page_dir, index, safe_share=safe_share)
    return (
        f'<article data-filter-row data-search="{_e(_row_search(artifact.to_dict()))}">'
        f'<h3>{_e(artifact.name)} <span class="muted">{_e(artifact.artifact_type)}</span></h3>{link}{preview}</article>'
    )


def _artifact_preview(artifact: Artifact, href: str, page_dir: Path, index: int, *, safe_share: bool) -> str:
    if artifact.artifact_type in IMAGE_ARTIFACT_TYPES and href:
        return f'<img class="preview" src="{_e(href)}" alt="{_e(artifact.name)}">'
    if artifact.artifact_type in VIDEO_ARTIFACT_TYPES and href:
        return f'<video controls src="{_e(href)}"></video>'
    if artifact.artifact_type in TEXT_ARTIFACT_TYPES:
        text = _read_artifact_text(artifact)
        if text is None:
            return ""
        text = redact_text(text, enabled=safe_share)
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
        '<div class="table-wrap"><table><thead><tr><th>Run</th><th>Pass Rate</th><th>%</th><th>Flaky</th><th>Failed</th></tr></thead><tbody>'
        + rows
        + "</tbody></table></div>"
    )


def _history_comparison_view(comparison: dict[str, Any]) -> str:
    if not comparison:
        return "<p>No previous run available.</p>"
    return _key_values(
        {
            "Current Run": comparison.get("current_run_id", "-"),
            "Previous Run": comparison.get("previous_run_id", "-"),
            "Current Pass Rate": f"{comparison.get('current_pass_rate', 0)}%",
            "Previous Pass Rate": f"{comparison.get('previous_pass_rate', 0)}%",
            "Pass Rate Change": _format_delta(comparison.get("pass_rate_delta"), suffix="%"),
            "Failed Change": _format_delta(comparison.get("failed_delta")),
            "Flaky Change": _format_delta(comparison.get("flaky_delta")),
            "Duration Change": _format_duration_delta(comparison.get("duration_delta_ms")),
        }
    )


def _quality_score_card(score: dict[str, Any]) -> str:
    components = score.get("components", {})
    percent = _score_percent(score)
    color = {
        "passed": "var(--ok)",
        "warning": "var(--warn)",
        "failed": "var(--danger)",
    }.get(str(score.get("status", "unknown")), "#64748b")
    style = f' style="background:conic-gradient({color} 0 {percent:g}%,#e5e7eb {percent:g}% 100%)"'
    return (
        f'<div class="score-ring status-{_e(score.get("status", "unknown"))}"{style}><strong>{_e(_score_value(score))}</strong>'
        f"<span>{_e(score.get('grade', 'n/a'))}</span></div>"
        + _key_values(
            {
                "Base Pass Rate": f"{components.get('base_pass_rate', 0)}%",
                "Failure Penalty": components.get("failure_penalty", 0),
                "Flaky Penalty": components.get("flaky_penalty", 0),
                "Retry Penalty": components.get("retry_penalty", 0),
                "Slow Tests": components.get("slow_tests", 0),
                "Message": score.get("message", ""),
            }
        )
    )


def _risk_signal_card(risk: dict[str, Any]) -> str:
    reasons = risk.get("reasons", [])
    reason_html = "".join(
        f"<li><strong>{_e(item.get('label', ''))}</strong>: {_e(item.get('value', 0))}"
        f'<span class="muted"> · {_e(item.get("level", ""))}</span></li>'
        for item in reasons
    )
    reason_block = f"<ul>{reason_html}</ul>" if reason_html else '<p class="empty-state">No material risk signals.</p>'
    return (
        f'<p><span class="status {_e(risk.get("level", "low"))}">{_e(risk.get("level", "low"))}</span></p>'
        f'<p class="muted">{_e(risk.get("summary", ""))}</p>'
        f"{reason_block}"
    )


def _recovery_card(recovery: dict[str, Any]) -> str:
    value = recovery.get("mean_recovery_ms")
    return _key_values(
        {
            "Status": recovery.get("status", "not_available"),
            "Mean Recovery": _format_duration(value) if value is not None else "N/A",
            "Recovered Tests": len(recovery.get("recovered_tests", []) or []),
            "Message": recovery.get("message", ""),
        }
    )


def _stability_card(stability: dict[str, Any]) -> str:
    unstable = stability.get("unstable_tests", [])[:6]
    details = "".join(
        f"<li>{_e(item.get('identity', ''))}: {_e(item.get('changes', 0))} changes</li>" for item in unstable
    )
    return _key_values(
        {
            "Status": stability.get("status", "not_available"),
            "Score": stability.get("score") if stability.get("score") is not None else "N/A",
            "Available Runs": stability.get("available_runs", 0),
            "Retry Recovered": stability.get("retry_recovered_count", 0),
            "Message": stability.get("message", ""),
        }
    ) + (f"<ul>{details}</ul>" if details else "")


def _resource_efficiency_card(resource: dict[str, Any]) -> str:
    return _key_values(
        {
            "Status": resource.get("status", "not_available"),
            "Efficiency": (
                f"{resource.get('efficiency_percent')}%" if resource.get("efficiency_percent") is not None else "N/A"
            ),
            "Workers": resource.get("worker_count", "N/A"),
            "Wall Clock": (
                _format_duration(resource.get("wall_clock_duration_ms", 0))
                if resource.get("wall_clock_duration_ms")
                else "N/A"
            ),
            "Message": resource.get("message", ""),
        }
    )


def _compare_table(compare: dict[str, Any]) -> str:
    rows = "\n".join(
        f'<tr data-filter-row data-search="{_e(_row_search(item))}">'
        f"<td>{_e(item.get('label', item.get('metric', '')))}</td>"
        f"<td>{_e(item.get('current', 0))}</td><td>{_e(item.get('previous', 0))}</td>"
        f"<td>{_format_delta(item.get('delta'))}</td><td>{_e(item.get('direction', 'flat'))}</td></tr>"
        for item in compare.get("metrics", [])
    )
    empty = '<tr><td colspan="5">No previous run comparison.</td></tr>'
    return (
        '<div class="table-wrap wide"><table><thead><tr><th>Metric</th><th>Current</th><th>Previous</th>'
        f"<th>Delta</th><th>Direction</th></tr></thead><tbody>{rows or empty}</tbody></table></div>"
    )


def _compare_delta(compare: dict[str, Any], metric: str) -> str:
    for item in compare.get("metrics", []):
        if item.get("metric") == metric:
            return _format_delta(item.get("delta"), suffix="%" if metric == "pass_rate" else "")
    return "-"


def _retry_delta(compare: dict[str, Any]) -> str:
    deltas = {
        item.get("metric"): item.get("delta", 0)
        for item in compare.get("metrics", [])
        if item.get("metric") in {"test_retry_count", "action_retry_count"}
    }
    if not deltas:
        return "-"
    return _format_delta(sum(float(value or 0) for value in deltas.values()))


def _score_value(score: dict[str, Any]) -> str:
    value = score.get("score")
    return "N/A" if value is None else f"{value:g}"


def _score_percent(score: dict[str, Any]) -> float:
    try:
        return max(0.0, min(100.0, float(score.get("score", 0) or 0)))
    except (TypeError, ValueError):
        return 0.0


def _short_run_id(value: str, *, limit: int = 18) -> str:
    if not value:
        return "-"
    return value if len(value) <= limit else f"{value[: limit - 1]}..."


def _quality_overview(quality: dict[str, Any]) -> str:
    return _key_values(
        {
            "Status": quality.get("status", "passed"),
            "Configured": "yes" if quality.get("configured") else "no",
            "Passed Gates": quality.get("summary", {}).get("passed", 0),
            "Failed Gates": quality.get("summary", {}).get("failed", 0),
            "Warning Gates": quality.get("summary", {}).get("warning", 0),
            "Message": quality.get("message", ""),
        }
    )


def _quality_gate_table(quality: dict[str, Any]) -> str:
    results = quality.get("results", [])
    rows = "\n".join(
        f'<tr data-filter-row data-search="{_e(_row_search(result))}">'
        f'<td><span class="status {_e(result.get("status", "unknown"))}">{_e(result.get("status", ""))}</span></td>'
        f"<td>{_e(result.get('name', ''))}</td><td>{_e(result.get('metric', ''))}</td>"
        f"<td>{_e(result.get('expected', ''))}</td><td>{_e(result.get('actual', ''))}</td>"
        f"<td>{_e(_gate_failure_impact(result))}</td><td>{_e(result.get('message', ''))}</td></tr>"
        for result in results
    )
    empty = '<tr><td colspan="7">No quality gates configured.</td></tr>'
    return (
        '<div class="table-wrap wide"><table><thead><tr><th>Status</th><th>Name</th><th>Metric</th>'
        "<th>Expected</th><th>Actual</th><th>Failure Impact</th><th>Message</th></tr></thead>"
        f"<tbody>{rows or empty}</tbody></table></div>"
    )


def _gate_failure_impact(result: dict[str, Any]) -> str:
    if result.get("status") == "passed":
        return "N/A"
    return _humanize_label(str(result.get("severity", "")) or "failed")


def _failure_transition_counts(transitions: dict[str, Any]) -> str:
    counts = transitions.get("counts", {})
    return _key_values(
        {
            "Previous Run": transitions.get("previous_run_id") or "-",
            "New Failures": counts.get("new", 0),
            "Known Failures": counts.get("known", 0),
            "Resolved Failures": counts.get("resolved", 0),
        }
    )


def _failure_transition_table(transitions: dict[str, Any]) -> str:
    rows = "\n".join(
        _failure_transition_row(item, kind)
        for kind, key in (
            ("new", "new_failures"),
            ("known", "known_failures"),
            ("resolved", "resolved_failures"),
        )
        for item in transitions.get(key, [])
    )
    empty = '<tr><td colspan="5">No failure movement.</td></tr>'
    return (
        '<div class="table-wrap wide failure-movement"><table><thead><tr><th>Kind</th><th>Test</th>'
        f"<th>Status</th><th>Failure</th><th>Link</th></tr></thead><tbody>{rows or empty}</tbody></table></div>"
    )


def _failure_transition_row(item: dict[str, Any], kind: str) -> str:
    return (
        f'<tr data-filter-row data-kind="{_e(kind)}" data-search="{_e(kind)} {_e(_row_search(item))}">'
        f'<td><span class="status {_e(_movement_status(kind))}">{_e(kind)}</span></td>'
        f'<td>{_e(item.get("name", ""))}<br><span class="muted">{_e(item.get("identity", ""))}</span></td>'
        f"<td>{_e(item.get('status') or item.get('current_status') or '')}</td>"
        f"<td>{_e(item.get('failure_title') or item.get('failure_category') or '')}</td>"
        f"<td>{_failure_transition_link(item)}</td></tr>"
    )


def _movement_status(kind: str) -> str:
    if kind == "resolved":
        return "passed"
    if kind == "known":
        return "warning"
    return "failed"


def _failure_transition_link(item: dict[str, Any]) -> str:
    href = item.get("detail_href")
    if not href:
        return "-"
    return f'<a href="{_e(href)}">Details</a>'


def _run_comparison_detail_view(comparison: dict[str, Any]) -> str:
    if not comparison:
        return "<p>No previous run available.</p>"
    values = comparison.get("values", {})
    rows = "\n".join(
        f'<tr data-filter-row data-search="{_e(metric)} {_e(_row_search(item))}">'
        f"<td>{_e(_humanize_label(metric))}</td><td>{_e(item.get('current', 0))}</td>"
        f"<td>{_e(item.get('previous', 0))}</td><td>{_format_delta(item.get('delta'))}</td></tr>"
        for metric, item in values.items()
    )
    return (
        '<div class="table-wrap wide compare-table"><table><thead><tr><th>Metric</th><th>Current</th><th>Previous</th>'
        f"<th>Delta</th></tr></thead><tbody>{rows}</tbody></table></div>"
    )


def _key_values(values: dict[str, Any]) -> str:
    rows = "".join(f"<tr><th>{_e(key)}</th><td>{_e(value)}</td></tr>" for key, value in values.items())
    return f'<div class="table-wrap"><table class="kv-table">{rows}</table></div>'


def _data_block(value: dict[str, Any]) -> str:
    if not value:
        return "<p>No data captured.</p>"
    visible = {key: _compact_value(item) for key, item in value.items()}
    return _key_values(visible) + "<details><summary>Raw JSON</summary>" + _json_block(value) + "</details>"


def _display_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in metadata.items() if key != "healing_events"}


def _compact_value(value: Any) -> Any:
    if isinstance(value, dict):
        return f"{len(value)} keys"
    if isinstance(value, list):
        return f"{len(value)} items"
    return value


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


def _json_for_script(value: Any) -> str:
    return json.dumps(to_jsonable(value), ensure_ascii=True).replace("</", "<\\/")


def _format_delta(value: Any, *, suffix: str = "") -> str:
    if value is None:
        return "-"
    numeric = float(value)
    prefix = "+" if numeric > 0 else ""
    return f"{prefix}{numeric:g}{suffix}"


def _format_duration_delta(value: Any) -> str:
    if value is None:
        return "-"
    numeric = float(value)
    prefix = "+" if numeric > 0 else "-" if numeric < 0 else ""
    return f"{prefix}{_format_duration(abs(numeric))}" if numeric else "0s"


def _format_datetime(value: Any) -> str:
    if hasattr(value, "astimezone") and hasattr(value, "strftime"):
        return value.astimezone().strftime("%b %d, %Y %H:%M")
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone().strftime("%b %d, %Y %H:%M")
        except ValueError:
            return value
    return "-"


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


def _row_search(value: Any) -> str:
    return str(to_jsonable(value)).lower()


def _test_search(test: TestCaseReport) -> str:
    parts = [
        test.id,
        test.name,
        test.full_name,
        test.suite,
        test.status,
        test.domain,
        test.profile,
        test.environment,
        test.failure_message,
        test.failure_trace,
        str(to_jsonable(test.metadata)),
        str(to_jsonable(test.capabilities)),
    ]
    return " ".join(part for part in parts if part).lower()


def _matrix_status(counts: dict[str, Any]) -> str:
    if counts.get("failed", 0) or counts.get("broken", 0):
        return "failed"
    if counts.get("skipped", 0) and counts.get("passed", 0) == 0:
        return "skipped"
    if counts.get("passed", 0):
        return "passed"
    return "unknown"


def _inline_counts(counts: dict[str, Any]) -> str:
    if not counts:
        return "-"
    return ", ".join(f"{key}: {value}" for key, value in sorted(counts.items()))


def _humanize_label(value: str) -> str:
    return " ".join(part.capitalize() for part in value.replace("-", "_").split("_") if part)
