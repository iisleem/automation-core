from __future__ import annotations

import json

from automation_core.reporting import RunReport, TestCaseReport, build_report_data, generate_reporting_product

EMPTY_FAILURE = {"category": "", "title": "", "detail": ""}


def test_passed_and_skipped_tests_have_neutral_failure_fields(tmp_path):
    report = RunReport(
        run_id="clean-run",
        project_name="web-automation-framework",
        framework="pytest-web",
        tests=[
            TestCaseReport(id="login", name="test_login", status="passed", profile="chromium"),
            TestCaseReport(id="setup", name="test_setup", status="skipped", profile="chromium"),
        ],
    )

    sidecar = build_report_data(report)

    assert [item["failure"] for item in sidecar["test_index"]] == [EMPTY_FAILURE, EMPTY_FAILURE]
    assert sidecar["charts"]["failure_categories"] == {}
    assert sidecar["aggregates"]["filter_options"]["failure_category"] == []
    assert "Unknown failure" not in json.dumps(sidecar)

    generate_reporting_product(report, tmp_path / "report")
    output_sidecar = json.loads((tmp_path / "report" / "report-data.json").read_text(encoding="utf-8"))
    explore_html = (tmp_path / "report" / "explore.html").read_text(encoding="utf-8")

    assert [item["failure"] for item in output_sidecar["test_index"]] == [EMPTY_FAILURE, EMPTY_FAILURE]
    assert output_sidecar["charts"]["failure_categories"] == {}
    assert output_sidecar["aggregates"]["filter_options"]["failure_category"] == []
    assert "Unknown failure" not in json.dumps(output_sidecar)
    assert "(t.failure||{}).title||'—'" in explore_html
    assert "countBy(out,function(t){return (t.failure||{}).category;})" in explore_html


def test_real_failures_keep_smart_default_classification_without_polluting_passed_filters():
    report = RunReport(
        run_id="failure-run",
        tests=[
            TestCaseReport(id="passed", name="test_passed", status="passed"),
            TestCaseReport(
                id="passed-with-message",
                name="test_passed_with_message",
                status="passed",
                failure_message="expected value did not match actual value",
            ),
            TestCaseReport(id="failed", name="test_failed", status="failed"),
            TestCaseReport(id="broken", name="test_broken", status="broken"),
            TestCaseReport(id="error", name="test_error", status="error"),
        ],
    )

    sidecar = build_report_data(report)
    by_id = {item["test_id"]: item for item in sidecar["test_index"]}

    assert by_id["passed"]["failure"] == EMPTY_FAILURE
    assert by_id["passed-with-message"]["failure"]["category"] == "assertion_mismatch"
    assert by_id["failed"]["failure"]["category"] == "unknown"
    assert by_id["failed"]["failure"]["title"] == "Unknown failure"
    assert by_id["broken"]["failure"]["category"] == "unknown"
    assert by_id["error"]["failure"]["category"] == "unknown"
    assert sidecar["charts"]["failure_categories"] == {"unknown": 3}
    assert sidecar["aggregates"]["filter_options"]["failure_category"] == ["unknown"]


def test_error_status_is_blocking_across_report_semantics(tmp_path):
    report = RunReport(
        run_id="error-mixed",
        matrix_dimensions=("domain",),
        tests=[
            TestCaseReport(id="p", name="pass", status="passed", domain="web"),
            TestCaseReport(id="e", name="error", status="error", domain="web"),
        ],
    )

    sidecar = build_report_data(report)
    # An error test drags the adjusted pass rate below the release gate threshold.
    pass_rate_gate = next(
        result for result in sidecar["default_gate_status"]["results"] if result["metric"] == "adjusted_pass_rate"
    )

    assert pass_rate_gate["status"] == "failed"
    assert sidecar["default_gate_status"]["status"] == "failed"
    assert sidecar["run"]["summary"]["status"] == "failed"
    assert sidecar["run"]["summary"]["error"] == 1
    assert sidecar["run"]["summary"]["blocking_failures"] == 1
    assert sidecar["aggregates"]["status_distribution"]["failed_broken"] == 1
    assert sidecar["charts"]["failure_categories"] == {"unknown": 1}
    assert sidecar["risk_signal"]["level"] != "low"
    assert pass_rate_gate["actual"] == "50%"
    assert sidecar["matrix"]["domain"]["web"]["error"] == 1
    assert sidecar["matrix"]["domain"]["web"]["failure_categories"] == {"unknown": 1}
    assert sidecar["test_index"][0]["failure"] == EMPTY_FAILURE
    assert sidecar["test_index"][1]["failure"]["title"] == "Unknown failure"

    generate_reporting_product(report, tmp_path / "report")
    output_sidecar = json.loads((tmp_path / "report" / "report-data.json").read_text(encoding="utf-8"))
    output_pass_rate_gate = next(
        result
        for result in output_sidecar["default_gate_status"]["results"]
        if result["metric"] == "adjusted_pass_rate"
    )

    assert output_sidecar["run"]["summary"]["status"] == "failed"
    assert output_pass_rate_gate["status"] == "failed"
    assert output_sidecar["default_gate_status"]["status"] == "failed"
