from __future__ import annotations

import json
from datetime import UTC, datetime

from automation_core.reporting import (
    ReportInsightConfig,
    RetryAttempt,
    RiskThresholds,
    RunReport,
    TestCaseReport,
    build_report_data,
    generate_report_portfolio,
    generate_reporting_product,
    prepare_timestamped_report_dir,
)
from automation_core.reporting.history import history_entry_from_report


def test_enterprise_insights_use_defaults_and_config_overrides():
    previous = RunReport(
        run_id="previous",
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
        tests=[
            TestCaseReport(id="known", name="test_known", status="failed", failure_message="timeout"),
            TestCaseReport(id="resolved", name="test_resolved", status="failed", failure_message="schema mismatch"),
        ],
    )
    current = RunReport(
        run_id="current",
        generated_at=datetime(2026, 1, 2, tzinfo=UTC),
        duration_ms=1_000,
        metadata={"worker_count": 2},
        tests=[
            TestCaseReport(id="known", name="test_known", status="failed", failure_message="timeout"),
            TestCaseReport(id="resolved", name="test_resolved", status="passed", duration_ms=100),
            TestCaseReport(
                id="retry",
                name="test_retry",
                status="passed",
                duration_ms=100,
                retries=[
                    RetryAttempt(attempt=1, status="failed"),
                    RetryAttempt(attempt=2, status="passed"),
                ],
            ),
            TestCaseReport(id="slow", name="test_slow", status="passed", duration_ms=2_000),
        ],
    )
    history = [history_entry_from_report(previous), history_entry_from_report(current)]

    sidecar = build_report_data(
        current,
        history_entries=history,
        insight_config=ReportInsightConfig(
            slow_test_threshold_ms=1_000,
            risk_thresholds=RiskThresholds(medium_failed=1, high_failed=1),
            default_min_pass_rate=70,
        ),
    )

    assert sidecar["quality_score"]["score"] < sidecar["run"]["summary"]["pass_rate"]
    assert sidecar["quality_score"]["components"]["slow_tests"] == 1
    assert sidecar["risk_signal"]["level"] == "high"
    assert sidecar["default_gate_status"]["configured"] is True
    assert sidecar["default_gate_status"]["enforced"] is False
    assert sidecar["failure_transitions"]["counts"] == {"new": 0, "known": 1, "resolved": 1}
    assert sidecar["compare"]["previous_run_id"] == "previous"
    assert any(item["metric"] == "pass_rate" for item in sidecar["compare"]["metrics"])
    assert sidecar["charts"]["compare_metrics"] == sidecar["compare"]["metrics"]
    assert sidecar["stability"]["status"] == "available"
    assert sidecar["stability"]["retry_recovered_count"] == 1
    assert sidecar["recovery"]["status"] == "available"
    assert sidecar["recovery"]["mean_recovery_ms"] == 86_400_000
    assert sidecar["resource_efficiency"]["status"] == "available"
    assert sidecar["resource_efficiency"]["worker_count"] == 2
    assert sidecar["ui_metadata"]["visual_system"] == "enterprise-redesign"
    assert "compare.html" in sidecar["ui_metadata"]["pages"]
    json.dumps(sidecar)


def test_enterprise_insights_hide_unavailable_metrics_without_extra_metadata():
    report = RunReport(run_id="empty")

    sidecar = build_report_data(report)

    assert sidecar["quality_score"]["score"] is None
    assert sidecar["quality_score"]["grade"] == "n/a"
    assert sidecar["risk_signal"]["level"] == "low"
    assert sidecar["stability"]["status"] == "insufficient_history"
    assert sidecar["recovery"]["status"] == "insufficient_history"
    assert sidecar["resource_efficiency"]["status"] == "not_available"


def test_enterprise_report_pages_sidecar_and_portfolio_surface_redesign(tmp_path):
    root = tmp_path / "portfolio"
    history_dir = tmp_path / "history"
    previous = RunReport(
        run_id="previous",
        project_name="automation-core",
        framework="pytest",
        generated_at=datetime(2026, 2, 1, tzinfo=UTC),
        tests=[
            TestCaseReport(id="known", name="test_known", status="failed", failure_message="locator not found"),
            TestCaseReport(id="resolved", name="test_resolved", status="failed", failure_message="schema validation"),
        ],
    )
    previous_dir = prepare_timestamped_report_dir(root, run_id=previous.run_id, generated_at=previous.generated_at)
    generate_reporting_product(previous, previous_dir, history_dir=history_dir)

    current = RunReport(
        run_id="current-with-enterprise-redesign",
        project_name="automation-core",
        framework="pytest",
        generated_at=datetime(2026, 2, 2, tzinfo=UTC),
        duration_ms=2_000,
        metadata={"parallel_workers": 2},
        tests=[
            TestCaseReport(
                id="known",
                name="test_known_with_a_very_long_name_that_should_wrap_without_overflow",
                full_name="tests.reports.test_known_with_a_very_long_name_that_should_wrap_without_overflow",
                status="failed",
                failure_message="locator not found",
                profile="chromium",
            ),
            TestCaseReport(id="resolved", name="test_resolved", status="passed", profile="chromium"),
            TestCaseReport(id="new", name="test_new_contract", status="broken", failure_message="schema validation"),
            TestCaseReport(
                id="retry",
                name="test_retry_recovered",
                status="passed",
                duration_ms=1_500,
                retries=[
                    RetryAttempt(attempt=1, status="failed"),
                    RetryAttempt(attempt=2, status="passed"),
                ],
            ),
        ],
    )
    current_dir = prepare_timestamped_report_dir(root, run_id=current.run_id, generated_at=current.generated_at)

    generate_reporting_product(current, current_dir, history_dir=history_dir)
    generate_report_portfolio(root, current_report_dir=current_dir)

    sidecar = json.loads((current_dir / "report-data.json").read_text(encoding="utf-8"))
    portfolio_data = json.loads((root / "portfolio-data.json").read_text(encoding="utf-8"))
    dashboard_html = (current_dir / "index.html").read_text(encoding="utf-8")
    executive_html = (current_dir / "executive.html").read_text(encoding="utf-8")
    compare_html = (current_dir / "compare.html").read_text(encoding="utf-8")
    quality_html = (current_dir / "quality.html").read_text(encoding="utf-8")
    detail_html = next((current_dir / "tests").glob("*.html")).read_text(encoding="utf-8")
    portfolio_html = (root / "index.html").read_text(encoding="utf-8")
    gallery_html = (root / "reports.html").read_text(encoding="utf-8")

    assert (current_dir / "compare.html").exists()
    assert sidecar["compare"]["failure_transitions"] == sidecar["failure_transitions"]["counts"]
    assert sidecar["report_config"]["slow_test_threshold_ms"] == 30_000
    assert sidecar["charts"]["quality_score_components"]
    assert portfolio_data["summary"]["latest_risk_level"] in {"low", "medium", "high"}
    assert portfolio_data["reports"][0]["compare_href"].endswith("/compare.html")
    assert portfolio_data["reports"][0]["quality_score"] is not None
    assert portfolio_data["reports"][0]["new_failure_count"] == 1
    assert 'data-visual-system="enterprise-redesign"' in dashboard_html
    assert 'href="compare.html"' in dashboard_html
    assert "Quality Score" in dashboard_html
    assert "Risk Signal" in executive_html
    assert 'data-filter-search="compare-metrics"' in compare_html
    assert 'data-filter-root="compare-failures"' in compare_html
    assert "Resource Efficiency" in compare_html
    assert "Default Gate Status" in quality_html
    assert "overflow-wrap:anywhere" in dashboard_html
    assert 'href="../compare.html"' in detail_html
    assert "Quality Score Trend" in portfolio_html
    assert "Risk Levels" in portfolio_html
    assert "Compare" in gallery_html
