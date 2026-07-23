from __future__ import annotations

import html
import json
import re
import zipfile
from csv import DictWriter
from datetime import datetime
from io import StringIO
from pathlib import Path
from shutil import copy2
from typing import Any
from urllib.parse import urlparse

from automation_core.reporting import run_render
from automation_core.reporting.events import build_timeline_events
from automation_core.reporting.history import load_history, update_history
from automation_core.reporting.insights import ReportInsightConfig
from automation_core.reporting.models import Artifact, RunReport, TestCaseReport, to_jsonable
from automation_core.reporting.quality import QualityGate, QualityGateConfig
from automation_core.reporting.redaction import is_sensitive_name, redact_report, redact_text
from automation_core.reporting.sidecar import build_report_data
from automation_core.reporting.traversal import collect_test_artifacts
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
    details = _detail_hrefs(output_report)
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

    # Design-faithful per-run pages, rendered from the neutral report_data sidecar.
    (output_path / "executive.html").write_text(run_render.render_executive(report_data), encoding="utf-8")
    (output_path / "quality.html").write_text(run_render.render_quality(report_data), encoding="utf-8")
    (output_path / "explore.html").write_text(run_render.render_explore(report_data), encoding="utf-8")
    (output_path / "timeline.html").write_text(run_render.render_timeline(report_data), encoding="utf-8")
    (output_path / "flaky.html").write_text(run_render.render_flaky(report_data), encoding="utf-8")
    (output_path / "matrix.html").write_text(run_render.render_matrix(report_data), encoding="utf-8")
    (output_path / "history.html").write_text(run_render.render_history(report_data), encoding="utf-8")
    (output_path / "share.html").write_text(run_render.render_share(report_data), encoding="utf-8")
    (output_path / "print-summary.html").write_text(run_render.render_print_summary(report_data), encoding="utf-8")
    _write_test_detail_pages(report_data, tests_dir)
    index_path = output_path / "index.html"
    index_path.write_text(run_render.render_overview(report_data), encoding="utf-8")
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
        ("Failures", _blocking_failure_count(summary)),
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
    failed_total = _blocking_failure_count(summary)
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
  {_svg_metric(326, 220, "Failures", failed_total)}
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


def _detail_hrefs(report: RunReport) -> dict[str, str]:
    """Deterministic per-test detail page hrefs (relative to the run root)."""

    details: dict[str, str] = {}
    for index, test in enumerate(report.tests, start=1):
        filename = f"{index:04d}-{_slug(test.id or test.name)}.html"
        details[test.id] = f"tests/{filename}"
    return details


def _write_test_detail_pages(report_data: dict[str, Any], tests_dir: Path) -> None:
    """Render every per-test detail page from the neutral report_data sidecar."""

    for record in report_data.get("test_index", []):
        href = record.get("detail_href", "")
        filename = href.split("/")[-1] if href else f"{record.get('test_id', 'test')}.html"
        (tests_dir / filename).write_text(
            run_render.render_test_detail(report_data, record, prefix="../"), encoding="utf-8"
        )


def _backfill_platforms(report_data: dict[str, Any]) -> bool:
    """Add web/mobile/api platform data to a pre-0.12 sidecar in place.

    Runs generated before platform classification existed have no ``platforms``
    key. Classify each test from the signals already in its index entry and
    aggregate, so retained runs gain a platform after a reskin. Returns True
    when anything was added.
    """

    from automation_core.reporting.platforms import classify_platform, platform_breakdown

    test_index = report_data.get("test_index")
    if not isinstance(test_index, list) or not test_index:
        return False
    summary = report_data.get("run", {}).get("summary", {}) if isinstance(report_data.get("run"), dict) else {}
    hint = f"{summary.get('framework', '')} {summary.get('project_name', '')}".strip()

    changed = False
    for record in test_index:
        if not record.get("platform_type"):
            record["platform_type"] = classify_platform(record, framework_hint=hint)
            changed = True
    if not report_data.get("platforms"):
        report_data["platforms"] = dict(platform_breakdown(test_index, framework_hint=hint))
        changed = True
        if isinstance(report_data.get("aggregates"), dict):
            report_data["aggregates"]["platforms"] = report_data["platforms"]
    return changed


def reskin_report_run(run_dir: str | Path) -> bool:
    """Re-render a retained run's HTML pages from its ``report-data.json``.

    The design system (CSS, layout, colours) is inlined into each generated
    page, so a design change only reaches new runs. This re-renders every page
    for one retained run from the neutral sidecar it already stored, so old
    runs adopt the current design without needing the original run objects.
    Returns ``True`` when the run was re-skinned.
    """

    run_path = Path(run_dir)
    report_data_path = run_path / "report-data.json"
    if not report_data_path.exists():
        return False
    report_data = json.loads(report_data_path.read_text(encoding="utf-8"))
    if _backfill_platforms(report_data):
        report_data_path.write_text(json.dumps(report_data, indent=2), encoding="utf-8")
    _render_run_pages(run_path, report_data)
    return True


_RESKIN_PAGES = {
    "executive.html": run_render.render_executive,
    "quality.html": run_render.render_quality,
    "explore.html": run_render.render_explore,
    "timeline.html": run_render.render_timeline,
    "flaky.html": run_render.render_flaky,
    "matrix.html": run_render.render_matrix,
    "history.html": run_render.render_history,
    "share.html": run_render.render_share,
    "print-summary.html": run_render.render_print_summary,
    "index.html": run_render.render_overview,
}


def _render_run_pages(run_path: Path, report_data: dict[str, Any]) -> None:
    for name, renderer in _RESKIN_PAGES.items():
        (run_path / name).write_text(renderer(report_data), encoding="utf-8")
    tests_dir = run_path / "tests"
    if tests_dir.exists():
        _write_test_detail_pages(report_data, tests_dir)


def _trend_point_from_data(report_data: dict[str, Any]) -> dict[str, Any]:
    summary = report_data.get("run", {}).get("summary", {}) if isinstance(report_data.get("run"), dict) else {}
    failed = summary.get(
        "blocking_failures",
        int(summary.get("failed", 0) or 0) + int(summary.get("broken", 0) or 0),
    )
    return {
        "run_id": summary.get("run_id", ""),
        "latest_run": summary.get("latest_run", ""),
        "pass_rate": summary.get("pass_rate", 0),
        "flaky": summary.get("flaky", 0),
        "failed": failed,
        "duration_ms": summary.get("duration_ms", 0),
        "platforms": report_data.get("platforms", {}),
    }


def _backfill_history(ordered: list[dict[str, Any]]) -> None:
    """Give each run a cumulative per-platform trend from its sibling runs.

    Frameworks that do not thread a shared history file leave ``trend_points``
    empty, so the pass-rate sparkline and per-platform trends render blank. Since
    every retained run lives in the same tree, rebuild each run's history as the
    ordered series of all runs up to and including it, so trends render
    consistently regardless of how a framework recorded history.
    """

    points = [_trend_point_from_data(rd) for rd in ordered]
    for index, report_data in enumerate(ordered):
        history = report_data.setdefault("history", {})
        history["trend_points"] = points[: index + 1]


def reskin_reports(report_root: str | Path) -> int:
    """Re-skin every retained run under a report root and rebuild the portfolio.

    Backfills platform classification and a cumulative per-platform history for
    older runs, re-renders every run with the current visual system, and
    rebuilds the portfolio. Returns the number of runs re-skinned; retained run
    folders are never deleted.
    """

    from automation_core.reporting.portfolio import RUNS_DIR, generate_report_portfolio

    root = Path(report_root)
    runs_dir = root / RUNS_DIR
    loaded: list[tuple[Path, dict[str, Any]]] = []
    if runs_dir.exists():
        for report_data_path in runs_dir.glob("*/report-data.json"):
            report_data = json.loads(report_data_path.read_text(encoding="utf-8"))
            _backfill_platforms(report_data)
            loaded.append((report_data_path.parent, report_data))

    loaded.sort(key=lambda item: str(item[1].get("run", {}).get("summary", {}).get("latest_run") or ""))
    _backfill_history([rd for _, rd in loaded])

    for run_path, report_data in loaded:
        (run_path / "report-data.json").write_text(json.dumps(report_data, indent=2), encoding="utf-8")
        _render_run_pages(run_path, report_data)

    if (root / "portfolio-data.json").exists() or runs_dir.exists():
        generate_report_portfolio(root)
    return len(loaded)


def _metric(label: str, value: Any) -> str:
    return f'<div class="metric"><strong>{_e(value)}</strong>{_e(label)}</div>'


def _metric_with_note(label: str, value: Any, note: Any) -> str:
    return (
        f'<div class="metric" title="{_e(note)}"><strong>{_e(value)}</strong>{_e(label)}'
        f'<br><span class="muted">{_e(note)}</span></div>'
    )


def _gate_sentence(summary: dict[str, Any], gate: dict[str, Any]) -> str:
    failed = _blocking_failure_count(summary)
    pass_rate = summary.get("pass_rate", 0)
    if gate.get("message"):
        return str(gate["message"])
    if failed:
        return f"{failed} failing test(s) need attention before release; current pass rate is {pass_rate}%."
    if int(summary.get("flaky", 0) or 0):
        return f"Pass rate is {pass_rate}% with flaky signal(s) to review before final sign-off."
    if int(summary.get("total", 0) or 0):
        return f"Adjusted pass rate {pass_rate}% meets the default release signal for this run."
    return "No tests were captured for release evaluation."


def _status_segment_bar(summary: dict[str, Any]) -> str:
    values = [
        ("passed", int(summary.get("passed", 0) or 0), "Passed"),
        ("failed", _blocking_failure_count(summary), "Failed"),
        ("skipped", int(summary.get("skipped", 0) or 0), "Skipped"),
        ("flaky", int(summary.get("flaky", 0) or 0), "Flaky"),
    ]
    total = sum(value for _, value, _ in values)
    if not total:
        return '<p class="empty-state">No status distribution available.</p>'
    segments = "".join(
        f'<span class="segment segment-{_e(key)}" style="width:{(value / total) * 100:.3f}%"></span>'
        for key, value, _ in values
        if value
    )
    legend = "".join(
        f'<span><i class="swatch segment-{_e(key)}"></i>{_e(label)} {value}</span>'
        for key, value, label in values
        if value
    )
    return f'<div class="status-segments">{segments}</div><div class="legend segment-legend">{legend}</div>'


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


def _blocking_failure_count(summary: dict[str, Any]) -> int:
    return int(
        summary.get(
            "blocking_failures",
            int(summary.get("failed", 0) or 0) + int(summary.get("broken", 0) or 0) + int(summary.get("error", 0) or 0),
        )
        or 0
    )


def _healing_events(test: TestCaseReport) -> list[dict[str, Any]]:
    events = test.metadata.get("healing_events", [])
    if not isinstance(events, list):
        return []
    return [event for event in events if isinstance(event, dict)]


def _is_external_href(href: str | None) -> bool:
    if not href:
        return False
    parsed = urlparse(href)
    return bool(parsed.scheme and parsed.scheme != "file")


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


def _key_values(values: dict[str, Any]) -> str:
    rows = "".join(f"<tr><th>{_e(key)}</th><td>{_e(value)}</td></tr>" for key, value in values.items())
    return f'<div class="table-wrap"><table class="kv-table">{rows}</table></div>'


def _json_for_script(value: Any) -> str:
    return json.dumps(to_jsonable(value), ensure_ascii=True).replace("</", "<\\/")


def _format_delta(value: Any, *, suffix: str = "") -> str:
    if value is None:
        return "-"
    numeric = float(value)
    prefix = "+" if numeric > 0 else ""
    return f"{prefix}{numeric:g}{suffix}"


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
