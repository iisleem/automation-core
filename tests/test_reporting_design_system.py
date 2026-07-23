"""Focused tests for the report design-system rebuild.

Covers the neutral capabilities the redesign introduced: platform (web/mobile/
api) classification, quarantine-adjusted release gates and health score, the
design matrix dimensions, retained-run preservation, and long-text containment.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from automation_core.reporting import (
    RunReport,
    TestCaseReport,
    build_report_data,
    generate_reporting_product,
)
from automation_core.reporting.platforms import classify_platform, platform_breakdown
from automation_core.reporting.portfolio import (
    collect_report_runs,
    combine_report_portfolios,
    generate_report_portfolio,
    prepare_timestamped_report_dir,
)

LONG_NAME = "test_contract_schema_validation_for_orders_response_with_a_very_long_case_name_that_should_wrap"
LONG_PROFILE = "dev-profile-with-a-very-long-name-used-to-check-wrapping-behaviour-in-cards-and-tables"


def _mixed_report(run_id: str = "run-mixed", generated_at: datetime | None = None) -> RunReport:
    return RunReport(
        run_id=run_id,
        project_name="automation-core",
        framework="pytest",
        generated_at=generated_at or datetime(2026, 7, 16, tzinfo=UTC),
        tests=[
            TestCaseReport(
                id="web1",
                name="test_login_web",
                status="passed",
                domain="Authentication",
                profile="chromium-desktop",
                duration_ms=1200,
                metadata={"platform_type": "web", "browser": "chromium", "owner": "web-guild"},
            ),
            TestCaseReport(
                id="mob1",
                name="test_checkout_mobile",
                status="broken",
                domain="Checkout",
                duration_ms=6500,
                failure_message="WebviewContextTimeoutError: native handoff exceeded 8000ms",
                metadata={
                    "platform_type": "mobile",
                    "device_name": "iphone-15-pro",
                    "context": "webview",
                    "owner": "mobile-guild",
                    "known_issue": "JIRA-5510",
                    "quarantined": True,
                },
            ),
            TestCaseReport(
                id="api1",
                name=LONG_NAME,
                status="failed",
                domain="Checkout API",
                profile=LONG_PROFILE,
                duration_ms=900,
                failure_message="SchemaValidationError: orders.line_items[2].sku is required",
                metadata={
                    "platform_type": "api",
                    "api_profile": LONG_PROFILE,
                    "owner": "platform-api",
                    "known_issue": "JIRA-4821",
                    "quarantined": True,
                },
            ),
        ],
    )


def test_classify_platform_uses_explicit_label_then_neutral_signals():
    assert classify_platform({"platform_type": "mobile"}) == "mobile"
    assert classify_platform({"api_profile": "dev"}) == "api"
    assert classify_platform({"metadata": {"status_code": 200}}) == "api"
    assert classify_platform({"device_name": "pixel-8"}) == "mobile"
    assert classify_platform({"context": "webview"}) == "mobile"
    assert classify_platform({"browser": "chromium"}) == "web"
    # Framework hint is the last resort; unknown falls back to web.
    assert classify_platform({}, framework_hint="mobile-automation-framework") == "mobile"
    assert classify_platform({}) == "web"


def test_platform_breakdown_only_includes_present_platforms():
    index = [
        {"platform_type": "web", "status": "passed", "duration_ms": 1000, "flaky_categories": []},
        {"platform_type": "web", "status": "failed", "duration_ms": 500, "flaky_categories": []},
        {"platform_type": "api", "status": "passed", "duration_ms": 200, "flaky_categories": []},
    ]
    breakdown = platform_breakdown(index)
    assert set(breakdown) == {"web", "api"}
    assert breakdown["web"]["total"] == 2
    assert breakdown["web"]["pass_rate"] == 50.0
    assert breakdown["api"]["pass_rate"] == 100.0
    assert "mobile" not in breakdown


def test_report_data_exposes_platforms_health_and_adjusted_gate():
    sidecar = build_report_data(_mixed_report())

    platforms = sidecar["platforms"]
    assert set(platforms) == {"web", "mobile", "api"}
    assert platforms["web"]["pass_rate"] == 100.0

    # Both failing tests are quarantined/known, so the adjusted pass rate is 100%.
    assert sidecar["adjusted_pass_rate"] == 100.0
    gate = sidecar["default_gate_status"]
    metrics = {result["metric"] for result in gate["results"]}
    assert metrics == {"adjusted_pass_rate", "new_unresolved_failures", "duration"}
    assert gate["status"] == "passed"
    assert isinstance(sidecar["health_score"], int)
    assert 0 <= sidecar["health_score"] <= 100


def test_matrix_uses_design_dimensions():
    sidecar = build_report_data(_mixed_report())
    # Default neutral matrix dimensions follow the design system.
    assert "owner" in sidecar["matrix"]
    assert "domain" in sidecar["matrix"]
    assert "api_profile" in sidecar["matrix"]
    assert sidecar["matrix"]["owner"]["web-guild"]["pass_rate"] == 100.0


def test_share_page_surfaces_every_generated_export(tmp_path):
    product = tmp_path / "product"
    generate_reporting_product(_mixed_report(), product, update_history_file=False)
    share = (product / "share.html").read_text(encoding="utf-8")

    # Every export the product writes to disk is reachable from the Share page.
    generated = {
        "exports/test-index.csv",
        "exports/test-index.xlsx",
        "exports/executive-summary.docx",
        "exports/share-card.svg",
        "exports/report-bundle.json",
        "exports/share-manifest.json",
    }
    for rel in generated:
        assert (product / rel).exists(), f"missing export file {rel}"
        assert rel in share, f"share page does not link {rel}"
    # Download affordances (not just inline links) are present.
    assert "download" in share
    # Human labels for the previously-hidden formats.
    assert "Download XLSX" in share
    assert "Download DOCX" in share
    assert "Share Card (SVG)" in share


def test_expected_features_flag_coverage_gaps(tmp_path):
    generate_reporting_product(
        _mixed_report(),
        tmp_path / "product",
        update_history_file=False,
        insight_config={"expected_features": ["Authentication", "Checkout", "Payments", "Onboarding"]},
    )
    executive = (tmp_path / "product" / "executive.html").read_text(encoding="utf-8")
    # Features with no tests in the run are flagged as gaps.
    assert "Payments · no coverage" in executive
    assert "Onboarding · no coverage" in executive
    assert "Features with zero automated tests are flagged as coverage gaps." in executive


def test_long_text_is_contained_not_wrapped_open(tmp_path):
    generate_reporting_product(_mixed_report(), tmp_path / "product", update_history_file=False)
    detail = next(page for page in (tmp_path / "product" / "tests").glob("*.html") if "api1" in page.name)
    detail_html = detail.read_text(encoding="utf-8")
    # Long identifiers use a monospace face and wrap/ellipsis containment.
    assert "IBM Plex Mono" in detail_html
    assert "overflow-wrap:anywhere" in detail_html
    assert LONG_PROFILE in detail_html


def test_retained_runs_are_preserved_across_generations(tmp_path):
    root = tmp_path / "portfolio"
    first = _mixed_report(run_id="run-first", generated_at=datetime(2026, 7, 15, tzinfo=UTC))
    first_dir = prepare_timestamped_report_dir(root, run_id=first.run_id, generated_at=first.generated_at)
    generate_reporting_product(first, first_dir, update_history_file=False)

    second = _mixed_report(run_id="run-second", generated_at=datetime(2026, 7, 16, tzinfo=UTC))
    second_dir = prepare_timestamped_report_dir(root, run_id=second.run_id, generated_at=second.generated_at)
    generate_reporting_product(second, second_dir, update_history_file=False)
    generate_report_portfolio(root, current_report_dir=second_dir)

    # The older run directory is retained, not deleted or overwritten.
    assert first_dir.exists()
    assert (first_dir / "index.html").exists()
    runs = collect_report_runs(root)
    assert {run["run_id"] for run in runs} == {"run-first", "run-second"}

    portfolio_data = json.loads((root / "portfolio-data.json").read_text(encoding="utf-8"))
    assert portfolio_data["summary"]["total_reports"] == 2
    # Each retained run carries its platform breakdown for the cross-run trend.
    assert all("platforms" in run for run in portfolio_data["reports"])


def _single_platform_report(platform: str, run_id: str, day: int) -> RunReport:
    metadata = {"platform_type": platform}
    if platform == "web":
        metadata["browser"] = "chromium"
    elif platform == "mobile":
        metadata["device_name"] = "iphone-16-pro"
    else:
        metadata["api_profile"] = "rest"
    return RunReport(
        run_id=run_id,
        project_name=f"{platform}-automation-framework",
        framework="pytest",
        generated_at=datetime(2026, 7, day, tzinfo=UTC),
        tests=[TestCaseReport(id=f"{platform}-1", name=f"test_{platform}_flow", status="passed", metadata=metadata)],
    )


def test_combine_report_portfolios_merges_platforms_and_preserves_runs(tmp_path):
    # Three separate framework report trees, one per platform.
    sources = []
    for platform, day in (("web", 14), ("mobile", 15), ("api", 16)):
        source = tmp_path / f"{platform}-report"
        report = _single_platform_report(platform, f"{platform}-run", day)
        run_dir = prepare_timestamped_report_dir(source, run_id=report.run_id, generated_at=report.generated_at)
        generate_reporting_product(report, run_dir, update_history_file=False)
        sources.append(source)

    combined = tmp_path / "combined"
    combine_report_portfolios(sources, combined)

    runs = collect_report_runs(combined)
    assert {run["run_id"] for run in runs} == {"web-run", "mobile-run", "api-run"}
    portfolio_data = json.loads((combined / "portfolio-data.json").read_text(encoding="utf-8"))
    platforms = set()
    for run in portfolio_data["reports"]:
        platforms |= set(run.get("platforms", {}))
    assert platforms == {"web", "mobile", "api"}

    # Idempotent: re-combining does not duplicate or delete runs.
    combine_report_portfolios(sources, combined)
    runs_again = collect_report_runs(combined)
    assert len(runs_again) == 3
    assert (combined / "runs").exists()
