from __future__ import annotations

import json

from automation_core.reporting import (
    Artifact,
    EventRecorder,
    RetryAttempt,
    RunReport,
    StepRecord,
    TestCaseReport,
    assert_valid_report,
    build_timeline_events,
    classify_failure,
    collect_action_retries,
    collect_test_artifacts,
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
                metadata={"platform_version": "v2", "context": ["dev", "contract"]},
            ),
        ],
    )

    summary = matrix_summary(report)

    assert summary["platform_version"]["17.5"]["passed"] == 1
    assert summary["context"]["WEBVIEW"]["passed"] == 1
    assert summary["context"]["contract"]["failed"] == 1
    assert summary["domain"]["api"]["failed"] == 1
    assert summary["status"]["failed"]["failed"] == 1


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
    assert len(test.retries) == 2
    assert test.artifacts[0].artifact_type == "log"
    assert summarize_run(report)["flaky"] == 1
