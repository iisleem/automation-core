from __future__ import annotations

import json
import zipfile

from automation_core.healing import (
    CandidateDescriptor,
    HealingConfig,
    LocatorDescriptor,
    add_healing_result,
    evaluate_healing,
)
from automation_core.reporting import (
    Artifact,
    EventRecorder,
    ReportingEvent,
    RetryAttempt,
    RunReport,
    StepRecord,
    TestCaseReport,
    assert_valid_report,
    build_report_data,
    build_timeline_events,
    classify_failure,
    collect_action_retries,
    collect_test_artifacts,
    failure_summary,
    flaky_analysis,
    generate_reporting_product,
    matrix_summary,
    run_report_from_allure_results,
    summarize_run,
    validate_report,
)


def test_reporting_product_generates_dashboard_details_timeline_matrix_and_history(tmp_path):
    screenshot = tmp_path / "shot.png"
    screenshot.write_bytes(b"fakepng")
    log = tmp_path / "test.log"
    log.write_text("line 1\nlocator not found\n", encoding="utf-8")
    report = RunReport(
        run_id="run-1",
        project_name="web-automation-framework",
        framework="pytest-playwright",
        tests=[
            TestCaseReport(
                id="login",
                name="test_login",
                full_name="tests.test_login",
                status="passed",
                domain="web",
                profile="chromium",
                duration_ms=1250,
                metadata={"browser": "Chrome", "viewport": "1440x900"},
                retries=[
                    RetryAttempt(attempt=1, status="failed", reason="timeout", duration_ms=400),
                    RetryAttempt(attempt=2, status="passed", duration_ms=850),
                ],
                action_retries=[
                    RetryAttempt(attempt=1, retry_type="action", action="click login", status="failed"),
                    RetryAttempt(attempt=2, retry_type="action", action="click login", status="passed"),
                ],
                artifacts=[
                    Artifact(name="failure screenshot", path=str(screenshot), artifact_type="screenshot"),
                    Artifact(name="test log", path=str(log), artifact_type="log"),
                ],
                steps=[StepRecord(name="Open login", status="passed", duration_ms=100)],
            ),
            TestCaseReport(
                id="checkout",
                name="test_checkout",
                status="failed",
                domain="web",
                profile="chromium",
                duration_ms=900,
                failure_message="locator not found for submit button",
                metadata={"browser": "Chrome"},
            ),
        ],
    )

    index = generate_reporting_product(report, tmp_path / "product", history_dir=tmp_path / "history")

    assert index.exists()
    assert "Automation Report" in index.read_text(encoding="utf-8")
    assert (tmp_path / "product" / "timeline.html").exists()
    assert (tmp_path / "product" / "flaky.html").exists()
    assert (tmp_path / "product" / "matrix.html").exists()
    assert (tmp_path / "product" / "history.html").exists()
    assert (tmp_path / "product" / "explore.html").exists()
    assert (tmp_path / "product" / "compare.html").exists()
    assert (tmp_path / "product" / "report-data.json").exists()
    assert (tmp_path / "product" / "data" / "run-report.json").exists()
    detail_pages = list((tmp_path / "product" / "tests").glob("*.html"))
    assert len(detail_pages) == 2
    assert any("failure screenshot" in page.read_text(encoding="utf-8") for page in detail_pages)
    assert summarize_run(report)["flaky"] == 1
    assert flaky_analysis(report)[0]["category"] == "test_retry_flaky"
    assert classify_failure(report.tests[1]) == "locator_not_found"
    assert matrix_summary(report)["profile"]["chromium"]["total"] == 2
    assert build_timeline_events(report)


def test_reporting_product_bundles_local_artifacts_and_preserves_external_links(tmp_path):
    screenshot = tmp_path / "shot.png"
    log = tmp_path / "run.log"
    video = tmp_path / "recording.webm"
    text = tmp_path / "source.xml"
    screenshot.write_bytes(b"png")
    log.write_text("searchable log", encoding="utf-8")
    video.write_bytes(b"webm")
    text.write_text("<hierarchy />", encoding="utf-8")
    external = "https://example.test/external.png"
    report = RunReport(
        run_id="bundle-run",
        tests=[
            TestCaseReport(
                id="artifact-test",
                name="test_artifacts",
                status="passed",
                artifacts=[
                    Artifact(name="screenshot", artifact_type="screenshot", path=str(screenshot)),
                    Artifact(name="log", artifact_type="log", path=str(log)),
                    Artifact(name="video", artifact_type="video", path=str(video)),
                    Artifact(name="source", artifact_type="source", path=str(text)),
                    Artifact(name="external", artifact_type="screenshot", href=external),
                ],
            )
        ],
    )

    generate_reporting_product(report, tmp_path / "product", update_history_file=False)

    bundled = sorted((tmp_path / "product" / "artifacts").iterdir())
    detail_html = next((tmp_path / "product" / "tests").glob("*.html")).read_text(encoding="utf-8")
    assert len(bundled) == 4
    assert all(path.name.startswith(f"{index:04d}-") for index, path in enumerate(bundled, start=1))
    assert "../artifacts/" in detail_html
    assert "searchable log" in detail_html
    assert "&lt;hierarchy /&gt;" in detail_html
    assert "recording.webm" in detail_html or "video" in detail_html
    assert external in detail_html
    assert report.tests[0].artifacts[0].href.startswith("artifacts/")


def test_nested_steps_are_used_for_metrics_artifacts_retries_and_flaky_analysis(tmp_path):
    nested_log = tmp_path / "nested.log"
    nested_log.write_text("nested retry log", encoding="utf-8")
    child = StepRecord(
        name="Nested action",
        status="passed",
        retries=[
            RetryAttempt(attempt=1, retry_type="action", action="tap", status="failed"),
            RetryAttempt(attempt=2, retry_type="action", action="tap", status="passed"),
        ],
        artifacts=[Artifact(name="nested log", artifact_type="log", path=str(nested_log))],
    )
    parent = StepRecord(name="Parent", status="passed", children=[child])
    report = RunReport(
        run_id="nested-run",
        tests=[TestCaseReport(id="nested", name="test_nested", status="passed", steps=[parent])],
    )

    generate_reporting_product(report, tmp_path / "product", update_history_file=False)
    detail_html = next((tmp_path / "product" / "tests").glob("*.html")).read_text(encoding="utf-8")

    assert len(collect_action_retries(report.tests[0])) == 2
    assert len(collect_test_artifacts(report.tests[0])) == 1
    assert flaky_analysis(report)[0]["category"] == "action_retry_flaky"
    assert "<strong>2</strong>Action Retries" in detail_html
    assert "nested retry log" in detail_html
    assert "Action retry attempt 1" in (tmp_path / "product" / "timeline.html").read_text(encoding="utf-8")


def test_matrix_summary_respects_custom_dimensions():
    report = RunReport(
        run_id="matrix-run",
        matrix_dimensions=["platform_version", "context", "domain", "status"],
        tests=[
            TestCaseReport(
                id="mobile",
                name="test_mobile",
                status="passed",
                domain="mobile",
                metadata={"platform_version": "17.5"},
                capabilities={"context": "WEBVIEW"},
            ),
            TestCaseReport(
                id="api",
                name="test_api",
                status="failed",
                domain="api",
                failure_message="schema validation failed",
                metadata={"platform_version": "v2", "context": ["dev", "contract"]},
            ),
        ],
    )

    summary = matrix_summary(report)

    assert summary["platform_version"]["17.5"]["passed"] == 1
    assert summary["context"]["WEBVIEW"]["passed"] == 1
    assert summary["context"]["contract"]["failed"] == 1
    assert summary["domain"]["api"]["failed"] == 1
    assert summary["domain"]["api"]["pass_rate"] == 0
    assert summary["domain"]["api"]["failure_categories"] == {"api_contract_mismatch": 1}
    assert summary["status"]["failed"]["failed"] == 1


def test_reporting_product_writes_sidecar_and_polished_sections(tmp_path):
    history_dir = tmp_path / "history"
    log = tmp_path / "failure.log"
    log.write_text("schema validation failed\npayload id mismatch\n", encoding="utf-8")
    previous = RunReport(
        run_id="previous-run",
        tests=[
            TestCaseReport(id="old-pass", name="test_old_pass", status="passed", duration_ms=100),
            TestCaseReport(id="old-fail", name="test_old_fail", status="failed", duration_ms=200),
        ],
    )
    generate_reporting_product(previous, tmp_path / "previous-product", history_dir=history_dir)

    healed = TestCaseReport(
        id="login",
        name="test_login",
        status="passed",
        profile="chromium",
        duration_ms=1200,
        retries=[
            RetryAttempt(attempt=1, status="failed", reason="timeout", duration_ms=400),
            RetryAttempt(attempt=2, status="passed", duration_ms=800),
        ],
    )
    result = evaluate_healing(
        LocatorDescriptor(strategy="css", value="[data-test='login']", action="click"),
        [CandidateDescriptor(strategy="css", value="[data-test='sign-in']", signals={"stable_id": 1.0})],
        HealingConfig(mode="apply", min_score=0.7),
        action="click",
        test_id="login",
    )
    add_healing_result(healed, result)

    action_flaky = TestCaseReport(
        id="search",
        name="test_search",
        status="passed",
        profile="chromium",
        duration_ms=1500,
        action_retries=[
            RetryAttempt(attempt=1, retry_type="action", action="type search", status="failed"),
            RetryAttempt(attempt=2, retry_type="action", action="type search", status="passed"),
        ],
    )
    failed = TestCaseReport(
        id="contract",
        name="test_contract",
        status="failed",
        domain="api",
        profile="dev",
        duration_ms=900,
        failure_message="schema validation failed",
        metadata={"api_profile": "dev"},
        artifacts=[Artifact(name="failure log", artifact_type="log", path=str(log))],
    )
    slow = TestCaseReport(id="slow", name="test_slow", status="passed", profile="dev", duration_ms=35_000)
    report = RunReport(
        run_id="current-run",
        project_name="automation-core",
        framework="pytest",
        matrix_dimensions=["profile", "api_profile", "domain"],
        tests=[healed, action_flaky, failed, slow],
    )

    generate_reporting_product(report, tmp_path / "product", history_dir=history_dir)

    sidecar = json.loads((tmp_path / "product" / "report-data.json").read_text(encoding="utf-8"))
    assert sidecar["run"]["summary"]["pass_rate"] == 75.0
    assert sidecar["run"]["health"]["previous_run_id"] == "previous-run"
    assert sidecar["run"]["health"]["pass_rate_delta"] == 25.0
    assert sidecar["signals"]["artifact_count"] == 1
    assert sidecar["signals"]["action_retry_count"] == 2
    assert sidecar["signals"]["test_retry_count"] == 2
    assert sidecar["signals"]["healing_decisions"] == {"applied": 1}
    assert sidecar["flaky"]["breakdown"]["test_retry_flaky"] == 1
    assert sidecar["flaky"]["breakdown"]["action_retry_flaky"] == 1
    assert sidecar["flaky"]["breakdown"]["always_failing"] == 1
    assert sidecar["flaky"]["breakdown"]["slow_but_passing"] == 1
    assert sidecar["failure_clusters"][0]["category"] == "api_contract_mismatch"
    assert sidecar["matrix"]["api_profile"]["dev"]["failure_categories"] == {"api_contract_mismatch": 1}
    assert sidecar["timeline"]["event_counts"]["healing"] == 1
    assert sidecar["timeline"]["event_counts"]["action_retry"] == 2
    assert sidecar["history"]["comparison"]["previous_run_id"] == "previous-run"
    assert sidecar["artifacts"][0]["href"].startswith("artifacts/")
    assert sidecar["test_index"][0]["detail_href"].startswith("tests/")
    assert sidecar["test_index"][0]["search_text"]
    assert sidecar["aggregates"]["status_distribution"] == {
        "passed": 3,
        "failed_broken": 1,
        "skipped": 0,
        "unknown": 0,
    }
    assert sidecar["aggregates"]["duration_buckets"]["30s+"] == 1
    assert sidecar["aggregates"]["artifact_types"] == {"log": 1}
    assert sidecar["aggregates"]["coverage"]["profile"]["chromium"] == 2
    assert sidecar["aggregates"]["filter_options"]["failure_category"]
    assert sidecar["charts"]["retry_signals"]["healing_event_count"] == 1
    assert sidecar["quality_score"]
    assert sidecar["risk_signal"]
    assert sidecar["default_gate_status"]
    assert sidecar["compare"]
    assert sidecar["stability"]
    assert sidecar["recovery"]
    assert sidecar["resource_efficiency"]
    assert any(item["metric"] == "pass_rate" for item in sidecar["compare"]["metrics"])
    assert sidecar["risk_signals"]
    details = {item["test_id"]: item["detail_href"] for item in sidecar["test_index"]}
    assert sidecar == build_report_data(
        report,
        history_entries=json.loads((history_dir / "index.json").read_text()),
        details=details,
    )
    json.dumps(sidecar)

    index_html = (tmp_path / "product" / "index.html").read_text(encoding="utf-8")
    executive_html = (tmp_path / "product" / "executive.html").read_text(encoding="utf-8")
    share_html = (tmp_path / "product" / "share.html").read_text(encoding="utf-8")
    explore_html = (tmp_path / "product" / "explore.html").read_text(encoding="utf-8")
    timeline_html = (tmp_path / "product" / "timeline.html").read_text(encoding="utf-8")
    flaky_html = (tmp_path / "product" / "flaky.html").read_text(encoding="utf-8")
    matrix_html = (tmp_path / "product" / "matrix.html").read_text(encoding="utf-8")
    history_html = (tmp_path / "product" / "history.html").read_text(encoding="utf-8")
    compare_html = (tmp_path / "product" / "compare.html").read_text(encoding="utf-8")
    detail_html = next(
        page for page in (tmp_path / "product" / "tests").glob("*.html") if "login" in page.name
    ).read_text(encoding="utf-8")
    assert "overview-hero" in index_html
    assert "Key Wins" in index_html
    assert "Focus Areas" in index_html
    assert "Action Retries" in index_html
    assert 'href="executive.html"' in index_html
    assert 'href="compare.html"' in index_html
    assert 'href="share.html"' in index_html
    assert "Executive Summary" in executive_html
    assert "Share And Export" in share_html
    assert "Stakeholder Views" in share_html
    assert "Safe Sharing" in share_html
    assert (tmp_path / "product" / "print-summary.html").exists()
    assert (tmp_path / "product" / "exports" / "test-index.csv").exists()
    assert (tmp_path / "product" / "exports" / "test-index.xlsx").exists()
    assert (tmp_path / "product" / "exports" / "executive-summary.docx").exists()
    assert (tmp_path / "product" / "exports" / "share-card.svg").exists()
    assert (tmp_path / "product" / "exports" / "report-bundle.json").exists()
    assert (tmp_path / "product" / "exports" / "share-manifest.json").exists()
    manifest = json.loads((tmp_path / "product" / "exports" / "share-manifest.json").read_text(encoding="utf-8"))
    assert manifest["exports"]["test_index_xlsx"] == "exports/test-index.xlsx"
    assert manifest["exports"]["executive_summary_docx"] == "exports/executive-summary.docx"
    assert manifest["exports"]["share_card_svg"] == "exports/share-card.svg"
    assert "Excel Workbook" in share_html
    assert "Word Summary" in share_html
    assert "Share Card SVG" in share_html
    with zipfile.ZipFile(tmp_path / "product" / "exports" / "test-index.xlsx") as workbook:
        assert "xl/worksheets/sheet1.xml" in workbook.namelist()
        assert "test_login" in workbook.read("xl/worksheets/sheet1.xml").decode("utf-8")
    with zipfile.ZipFile(tmp_path / "product" / "exports" / "executive-summary.docx") as document:
        assert "word/document.xml" in document.namelist()
        assert "Automation Report Executive Summary" in document.read("word/document.xml").decode("utf-8")
    assert "<svg" in (tmp_path / "product" / "exports" / "share-card.svg").read_text(encoding="utf-8")
    assert "signal-chip-strip" in index_html
    assert "Failure Clusters" in index_html
    assert "Flaky Breakdown" in index_html
    assert "Status Distribution" in index_html
    assert "Duration Distribution" in index_html
    assert "Retry Signals" in index_html
    assert "History Pass Rate" in index_html
    assert "Environment Coverage" in index_html
    assert "dashboard-search" in index_html
    assert "function setupExplore" in explore_html
    assert "explore-search" in explore_html
    assert "explore-status-chart" in explore_html
    assert "report-data-json" in explore_html
    assert 'data-filter-search="timeline-table"' in timeline_html
    assert 'data-filter-search="flaky-table"' in flaky_html
    assert "Pass Rate" in matrix_html
    assert "api_contract_mismatch: 1" in matrix_html
    assert "matrix-heatmap" in matrix_html
    assert "heat-details" in matrix_html
    assert "overflow-safe" in matrix_html
    assert "data-matrix-view" in matrix_html
    assert "Recent Comparison" in history_html
    assert 'data-filter-search="history-table"' in history_html
    assert "Compare Runs" in compare_html
    assert 'data-filter-search="compare-metrics"' in compare_html
    assert 'data-filter-search="compare-failures"' in compare_html
    assert "Failure Movement" in compare_html
    assert "failure-movement" in compare_html
    assert "<th>Kind</th>" in compare_html
    assert '<section class="grid three" data-filter-root="compare-failures">' not in compare_html
    assert "Smart Failure Summary" in detail_html
    assert 'href="../executive.html"' in detail_html
    assert 'href="../compare.html"' in detail_html
    assert 'href="../share.html"' in detail_html
    assert "Healing Events" in detail_html
    assert "Search this test" in detail_html
    assert 'data-filter-root="detail-page"' in detail_html
    assert "[data-test=&#x27;sign-in&#x27;]" in detail_html


def test_safe_share_redacts_sidecar_exports_search_and_html_by_default(tmp_path):
    log = tmp_path / "plain.log"
    log.write_text("authorization: Bearer raw-log-token\nnormal log line\n", encoding="utf-8")
    raw_secret = "raw-secret-value"
    report = RunReport(
        run_id="safe-share",
        metadata={"session_id": "session-123", "release": "2026.07"},
        tests=[
            TestCaseReport(
                id="sensitive",
                name="test_sensitive",
                status="failed",
                domain="api",
                profile="dev",
                failure_message=f"schema validation failed token={raw_secret}",
                metadata={
                    "api_key": raw_secret,
                    "authorization": "Bearer raw-auth-token",
                    "normal": "public-value",
                    "browser": "chromium",
                },
                capabilities={"cookie": "raw-cookie", "platform": "neutral"},
                artifacts=[
                    Artifact(
                        name="session token log",
                        artifact_type="log",
                        path=str(log),
                        metadata={"secret_note": raw_secret, "normal": "artifact-public"},
                    )
                ],
            )
        ],
    )
    raw_timeline = [
        ReportingEvent(
            event_type="custom",
            title="Raw timeline authorization: Bearer timeline-token",
            timestamp=report.generated_at,
            test_id="sensitive",
            test_name="test_sensitive",
            metadata={"authorization": "Bearer timeline-token", "normal": "public-value"},
        )
    ]

    sidecar = build_report_data(report, timeline_events=raw_timeline)

    serialized = json.dumps(sidecar)
    assert raw_secret not in serialized
    assert "raw-auth-token" not in serialized
    assert "raw-cookie" not in serialized
    assert "timeline-token" not in serialized
    assert "public-value" in serialized
    assert sidecar["test_index"][0]["metadata"]["api_key"] == "[redacted]"
    assert sidecar["test_index"][0]["metadata"]["normal"] == "public-value"
    assert "[redacted]" in sidecar["test_index"][0]["search_text"]
    assert sidecar["sharing"]["safe_share"]["enabled"] is True

    raw_sidecar = build_report_data(report, timeline_events=raw_timeline, safe_share=False)
    assert raw_secret in json.dumps(raw_sidecar)
    assert raw_sidecar["sharing"]["safe_share"]["enabled"] is False

    generate_reporting_product(report, tmp_path / "product", update_history_file=False)

    with zipfile.ZipFile(tmp_path / "product" / "exports" / "test-index.xlsx") as workbook:
        workbook_xml = workbook.read("xl/worksheets/sheet1.xml").decode("utf-8")
    with zipfile.ZipFile(tmp_path / "product" / "exports" / "executive-summary.docx") as document:
        document_xml = document.read("word/document.xml").decode("utf-8")

    generated_text = "\n".join(
        [
            (tmp_path / "product" / "report-data.json").read_text(encoding="utf-8"),
            (tmp_path / "product" / "data" / "run-report.json").read_text(encoding="utf-8"),
            (tmp_path / "product" / "exports" / "test-index.csv").read_text(encoding="utf-8"),
            workbook_xml,
            document_xml,
            (tmp_path / "product" / "exports" / "share-card.svg").read_text(encoding="utf-8"),
            (tmp_path / "product" / "exports" / "report-bundle.json").read_text(encoding="utf-8"),
            (tmp_path / "product" / "exports" / "share-manifest.json").read_text(encoding="utf-8"),
            next((tmp_path / "product" / "artifacts").iterdir()).read_text(encoding="utf-8"),
            next((tmp_path / "product" / "tests").glob("*.html")).read_text(encoding="utf-8"),
            (tmp_path / "product" / "share.html").read_text(encoding="utf-8"),
        ]
    )
    assert raw_secret not in generated_text
    assert "raw-auth-token" not in generated_text
    assert "raw-cookie" not in generated_text
    assert "raw-log-token" not in generated_text
    assert str(log) not in generated_text
    assert "public-value" in generated_text
    assert "artifact-public" in generated_text
    assert "[redacted]" in generated_text


def test_failure_summary_covers_known_categories():
    cases = [
        ("locator not found for submit", "locator_not_found", "Locator not found"),
        ("request timed out after 30 seconds", "timeout", "Timeout"),
        ("expected 1 actual 2 mismatch", "assertion_mismatch", "Assertion mismatch"),
        ("schema validation failed", "api_contract_mismatch", "API contract mismatch"),
        ("Appium server unreachable connection refused", "appium_server_unreachable", "Appium server unreachable"),
        ("app not installed on device", "app_not_installed", "App not installed"),
        ("WEBVIEW context not found", "webview_context_missing", "Webview context missing"),
        ("401 unauthorized missing environment config", "auth_config_issue", "Auth or configuration issue"),
        ("", "unknown", "Unknown failure"),
    ]

    for message, category, title in cases:
        summary = failure_summary(TestCaseReport(id=category, name=category, status="failed", failure_message=message))
        assert summary["category"] == category
        assert summary["title"] == title
        assert summary["detail"]


def test_reporting_product_renders_smart_failure_summary(tmp_path):
    report = RunReport(
        run_id="failure-summary",
        tests=[
            TestCaseReport(
                id="assertion",
                name="test_total",
                status="failed",
                failure_message="expected total 10 actual 12 mismatch",
            )
        ],
    )

    generate_reporting_product(report, tmp_path / "product", update_history_file=False)

    index_html = (tmp_path / "product" / "index.html").read_text(encoding="utf-8")
    detail_html = next((tmp_path / "product" / "tests").glob("*.html")).read_text(encoding="utf-8")
    assert "Assertion mismatch" in index_html
    assert "Compare expected and actual values" in index_html
    assert "Probable Cause" in detail_html
    assert "assertion_mismatch" in detail_html
    assert "expected total 10 actual 12 mismatch" in detail_html


def test_validate_report_rejects_non_serializable_metadata():
    class FakeDriver:
        pass

    report = RunReport(
        run_id="invalid",
        tests=[TestCaseReport(id="bad", name="bad", metadata={"driver": FakeDriver()})],
    )

    problems = validate_report(report)

    assert any("driver/client/session" in problem for problem in problems)
    assert any("non-serializable" in problem for problem in problems)
    try:
        assert_valid_report(report)
    except ValueError as error:
        assert "Invalid report" in str(error)
    else:
        raise AssertionError("Expected invalid report to raise")


def test_event_recorder_builds_neutral_report(tmp_path):
    artifact = tmp_path / "action.log"
    artifact.write_text("clicked", encoding="utf-8")
    recorder = EventRecorder(run_id="recorded", project_name="mobile", framework="pytest")

    test = recorder.start_test(
        "login",
        "test_login",
        domain="mobile",
        profile="ios",
        metadata={"device_name": "iPhone"},
    )
    step = recorder.add_step(test, "Tap login", status="passed")
    recorder.add_action_retry(test, attempt=1, status="failed", action="tap", reason="not ready", step=step)
    recorder.add_action_retry(test, attempt=2, status="passed", action="tap", step=step)
    recorder.add_artifact(test, name="action log", artifact_type="log", path=str(artifact), step=step)
    recorder.finish_test(test, status="passed", duration_ms=250)

    assert recorder.report.tests[0].metadata["device_name"] == "iPhone"
    assert collect_action_retries(recorder.report.tests[0])[-1].status == "passed"
    assert collect_test_artifacts(recorder.report.tests[0])[0].name == "action log"


def test_allure_adapter_groups_retries_and_accepts_metadata(tmp_path):
    results = tmp_path / "allure-results"
    results.mkdir()
    attachment = results / "log.txt"
    attachment.write_text("api contract mismatch", encoding="utf-8")
    first = {
        "historyId": "case-1",
        "name": "test_contract",
        "fullName": "tests.api.test_contract",
        "status": "failed",
        "start": 1000,
        "stop": 1500,
        "statusDetails": {"message": "schema validation failed"},
    }
    second = {
        "historyId": "case-1",
        "name": "test_contract",
        "fullName": "tests.api.test_contract",
        "status": "passed",
        "start": 2000,
        "stop": 2600,
        "labels": [{"name": "env", "value": "dev"}],
        "attachments": [{"name": "response payload", "source": "log.txt", "type": "text/plain"}],
    }
    (results / "1-result.json").write_text(json.dumps(first), encoding="utf-8")
    (results / "2-result.json").write_text(json.dumps(second), encoding="utf-8")

    report = run_report_from_allure_results(
        results,
        run_id="api-run",
        project_name="api-automation-framework",
        framework="pytest-api",
        test_metadata={
            "case-1": {
                "domain": "api",
                "profile": "dev",
                "metadata": "ignored",
                "status_code": 200,
                "latency_ms": 123,
            }
        },
    )

    assert report.run_id == "api-run"
    assert len(report.tests) == 1
    test = report.tests[0]
    assert test.status == "passed"
    assert test.environment == "dev"
    assert test.domain == "api"
    assert test.metadata["status_code"] == 200
    assert len(test.retries) == 1
    assert test.retries[0].attempt == 1
    assert test.retries[0].status == "failed"
    assert test.artifacts[0].artifact_type == "log"
    assert summarize_run(report)["flaky"] == 1


def test_allure_adapter_single_results_do_not_create_retry_signals(tmp_path):
    results = tmp_path / "allure-results"
    results.mkdir()
    for index in range(1, 11):
        status = "skipped" if index == 10 else "passed"
        result = {
            "historyId": f"case-{index}",
            "name": f"test_clean_{index}",
            "fullName": f"tests.web.test_clean_{index}",
            "status": status,
            "start": index * 1000,
            "stop": index * 1000 + 100,
        }
        (results / f"{index}-result.json").write_text(json.dumps(result), encoding="utf-8")

    report = run_report_from_allure_results(
        results,
        run_id="web-clean-run",
        project_name="web-automation-framework",
        framework="pytest-web",
    )
    sidecar = build_report_data(report)
    timeline = build_timeline_events(report)

    assert len(report.tests) == 10
    assert all(test.retries == [] for test in report.tests)
    assert sidecar["signals"]["test_retry_count"] == 0
    assert sidecar["charts"]["retry_signals"]["test_retry_count"] == 0
    assert sidecar["quality_score"]["components"]["retry_penalty"] == 0
    assert sidecar["risk_signal"]["level"] == "low"
    assert not any(reason["label"] == "Retry signals" for reason in sidecar["risk_signal"]["reasons"])
    assert not any(risk["title"] == "High retry count" for risk in sidecar["risk_signals"])
    assert sidecar["default_gate_status"]["summary"]["failed"] == 0
    test_retry_gate = next(
        result for result in sidecar["default_gate_status"]["results"] if result["metric"] == "test_retries"
    )
    assert test_retry_gate["status"] == "passed"
    assert sidecar["timeline"]["event_counts"].get("test_retry", 0) == 0
    assert not any(event.event_type == "test_retry" for event in timeline)
