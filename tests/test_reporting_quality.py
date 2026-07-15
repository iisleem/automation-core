from __future__ import annotations

import json

import pytest

from automation_core.reporting import (
    QualityGate,
    QualityGateConfig,
    RetryAttempt,
    RunReport,
    TestCaseReport,
    build_report_data,
    evaluate_quality_gates,
    generate_reporting_product,
)


def test_quality_gates_default_to_no_configured_failures():
    report = RunReport(run_id="quality-empty", tests=[TestCaseReport(id="pass", name="test_pass", status="passed")])

    evaluation = evaluate_quality_gates(report)

    assert evaluation.status == "passed"
    assert evaluation.configured is False
    assert evaluation.results == []
    assert evaluation.summary == {"passed": 0, "failed": 0, "warning": 0}
    assert build_report_data(report)["quality"]["configured"] is False


def test_quality_gate_config_and_failure_category_thresholds():
    report = RunReport(
        run_id="quality-config",
        tests=[
            TestCaseReport(id="pass", name="test_pass", status="passed"),
            TestCaseReport(
                id="contract",
                name="test_contract",
                status="failed",
                failure_message="schema validation failed",
                retries=[RetryAttempt(attempt=1, status="failed")],
            ),
            TestCaseReport(id="skip", name="test_skip", status="skipped"),
        ],
    )

    evaluation = evaluate_quality_gates(
        report,
        QualityGateConfig(
            min_pass_rate=50,
            max_failed_broken=0,
            max_skipped=0,
            max_test_retries=0,
            max_failures_by_category={"api_contract_mismatch": 0},
        ),
    )

    result_by_metric = {result.metric: result for result in evaluation.results}
    assert evaluation.status == "failed"
    assert result_by_metric["pass_rate"].status == "failed"
    assert result_by_metric["failed_broken"].status == "failed"
    assert result_by_metric["skipped"].status == "failed"
    assert result_by_metric["test_retries"].status == "failed"
    category_result = next(result for result in evaluation.results if result.metric == "failure_category")
    assert category_result.category == "api_contract_mismatch"
    assert category_result.actual == 1


def test_dict_based_quality_gates_and_warning_severity():
    report = RunReport(
        run_id="quality-dict",
        tests=[
            TestCaseReport(id="pass", name="test_pass", status="passed"),
            TestCaseReport(id="fail", name="test_fail", status="failed", failure_message="timeout"),
        ],
    )

    evaluation = evaluate_quality_gates(
        report,
        [
            {"name": "Warn on failures", "metric": "failed_broken", "threshold": 0, "severity": "warning"},
            QualityGate(name="Require one test", metric="total", threshold=1, operator="min"),
        ],
    )

    assert evaluation.status == "warning"
    assert evaluation.summary == {"passed": 1, "failed": 0, "warning": 1}
    assert evaluation.results[0].severity == "warning"
    assert evaluation.results[1].status == "passed"


def test_quality_gate_validation_rejects_unknown_operator_and_severity():
    report = RunReport(run_id="quality-invalid")

    with pytest.raises(ValueError, match="operator"):
        evaluate_quality_gates(report, [QualityGate(name="bad", metric="failed", threshold=0, operator="between")])

    with pytest.raises(ValueError, match="severity"):
        evaluate_quality_gates(report, [{"name": "bad", "metric": "failed", "threshold": 0, "severity": "blocker"}])


def test_quality_gate_validation_rejects_unknown_metric_and_missing_failure_category():
    report = RunReport(run_id="quality-invalid-metric")

    with pytest.raises(ValueError, match="Unsupported quality gate metric"):
        evaluate_quality_gates(report, [{"name": "typo", "metric": "passrate", "threshold": 95, "operator": "min"}])

    with pytest.raises(ValueError, match="category is required"):
        evaluate_quality_gates(
            report,
            [QualityGate(name="Missing category", metric="failure_category", threshold=0)],
        )


def test_quality_sidecar_and_page_include_gates_transitions_and_comparison(tmp_path):
    history_dir = tmp_path / "history"
    previous = RunReport(
        run_id="previous",
        tests=[
            TestCaseReport(
                id="known",
                name="test_known",
                status="failed",
                failure_message="locator not found",
                retries=[RetryAttempt(attempt=1, status="failed")],
            ),
            TestCaseReport(id="resolved", name="test_resolved", status="failed", failure_message="timeout"),
            TestCaseReport(id="absent", name="test_absent", status="broken", failure_message="unauthorized config"),
        ],
    )
    generate_reporting_product(previous, tmp_path / "previous-product", history_dir=history_dir)

    current = RunReport(
        run_id="current",
        tests=[
            TestCaseReport(id="known", name="test_known", status="failed", failure_message="locator not found"),
            TestCaseReport(id="new", name="test_new", status="broken", failure_message="schema validation failed"),
            TestCaseReport(id="resolved", name="test_resolved", status="passed"),
            TestCaseReport(
                id="retry",
                name="test_retry",
                status="passed",
                retries=[
                    RetryAttempt(attempt=1, status="failed"),
                    RetryAttempt(attempt=2, status="passed"),
                ],
                action_retries=[RetryAttempt(attempt=1, retry_type="action", status="failed", action="click")],
            ),
        ],
    )

    generate_reporting_product(
        current,
        tmp_path / "product",
        history_dir=history_dir,
        quality_gates=QualityGateConfig(min_pass_rate=75, max_failed_broken=1, max_test_retries=1),
    )

    sidecar = json.loads((tmp_path / "product" / "report-data.json").read_text(encoding="utf-8"))
    assert sidecar["quality"]["configured"] is True
    assert sidecar["quality"]["status"] == "failed"
    assert sidecar["failure_transitions"]["previous_run_id"] == "previous"
    assert sidecar["failure_transitions"]["counts"] == {"new": 1, "known": 1, "resolved": 2}
    assert {item["test_id"] for item in sidecar["failure_transitions"]["new_failures"]} == {"new"}
    assert {item["test_id"] for item in sidecar["failure_transitions"]["known_failures"]} == {"known"}
    assert {item["test_id"] for item in sidecar["failure_transitions"]["resolved_failures"]} == {
        "resolved",
        "absent",
    }
    assert sidecar["run_comparison"]["previous_run_id"] == "previous"
    assert sidecar["run_comparison"]["deltas"]["total"] == 1
    assert sidecar["run_comparison"]["deltas"]["failed_broken"] == -1
    assert sidecar["run_comparison"]["deltas"]["test_retry_count"] == 1
    assert sidecar["charts"]["run_comparison"]

    index_html = (tmp_path / "product" / "index.html").read_text(encoding="utf-8")
    quality_html = (tmp_path / "product" / "quality.html").read_text(encoding="utf-8")
    detail_html = next(page for page in (tmp_path / "product" / "tests").glob("*.html") if "known" in page.name)
    detail_text = detail_html.read_text(encoding="utf-8")
    bundle = json.loads((tmp_path / "product" / "exports" / "report-bundle.json").read_text(encoding="utf-8"))
    manifest = json.loads((tmp_path / "product" / "exports" / "share-manifest.json").read_text(encoding="utf-8"))

    assert 'href="quality.html"' in index_html
    assert "Quality Gates" in quality_html
    assert "Gate Results" in quality_html
    assert "New Failures" in quality_html
    assert "Run Comparison" in quality_html
    assert 'data-filter-search="quality-gates"' in quality_html
    assert 'data-filter-root="quality-gates"' in quality_html
    assert '<section class="grid two">\n  <article data-filter-root="quality-gates">' not in quality_html
    assert 'data-filter-search="quality-failures"' in quality_html
    assert 'data-filter-root="quality-failures"' in quality_html
    assert 'href="../quality.html"' in detail_text
    assert bundle["quality"]["configured"] is True
    assert bundle["failure_transitions"]["counts"]["new"] == 1
    assert bundle["run_comparison"]["deltas"]["failed_broken"] == -1
    assert "quality.html" in manifest["pages"]
