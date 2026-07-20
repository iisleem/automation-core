from __future__ import annotations

import json
from datetime import UTC, datetime
from urllib.parse import quote

import pytest

from automation_core.reporting import (
    Artifact,
    ReportInsightConfig,
    RetryAttempt,
    RiskThresholds,
    RunReport,
    TestCaseReport,
    build_report_data,
    generate_browser_matrix_dashboard,
    generate_environment_matrix_dashboard,
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
    explore_html = (current_dir / "explore.html").read_text(encoding="utf-8")
    detail_html = next((current_dir / "tests").glob("*.html")).read_text(encoding="utf-8")
    portfolio_html = (root / "index.html").read_text(encoding="utf-8")
    gallery_html = (root / "reports.html").read_text(encoding="utf-8")
    portfolio_compare_html = (root / "compare.html").read_text(encoding="utf-8")

    assert (current_dir / "compare.html").exists()
    assert (root / "compare.html").exists()
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
    assert "Failure Movement" in compare_html
    assert "failure-movement" in compare_html
    assert '<section class="grid three" data-filter-root="compare-failures">' not in compare_html
    assert "Resource Efficiency" in compare_html
    assert "Default Gate Status" in quality_html
    assert "Failure Impact" in quality_html
    assert "failure-movement" in quality_html
    assert '<section class="grid three" data-filter-root="quality-failures">' not in quality_html
    assert "Scope" in explore_html
    assert "scope-cell" in explore_html
    assert "signal-cell" in explore_html
    assert "overflow-wrap: anywhere" in dashboard_html
    assert 'href="../compare.html"' in detail_html
    assert "nav-shell" in dashboard_html
    assert "mobile-nav-toggle" in dashboard_html
    assert 'data-theme-default="system"' in dashboard_html
    assert 'data-theme-choice="system"' in dashboard_html
    assert 'data-theme-choice="light"' in dashboard_html
    assert 'data-theme-choice="dark"' in dashboard_html
    assert "max-width: 900px" in dashboard_html
    assert "min-width: 901px" in dashboard_html
    assert "max-width: 720px" not in dashboard_html
    assert "min-width: 721px" not in dashboard_html
    assert "@media (prefers-color-scheme: dark)" in dashboard_html
    assert 'font-family: "IBM Plex Sans"' in dashboard_html
    assert "--sidebar-width: 236px" in dashboard_html
    assert "--bg: oklch(98% 0.004 240)" in dashboard_html
    assert "--surface: oklch(24% 0.016 255)" in dashboard_html
    assert "-webkit-line-clamp: 2" in dashboard_html
    assert ".metric .muted" in dashboard_html
    assert "overview-hero" in dashboard_html
    assert "Key Wins" in dashboard_html
    assert "Focus Areas" in dashboard_html
    assert "Healing Events" not in dashboard_html
    assert "Healing Events" not in detail_html
    assert "Portfolio Dashboard" in portfolio_html
    assert "Quality Score Trend" in portfolio_html
    assert "Risk Levels" in portfolio_html
    assert "Compare" in gallery_html
    assert "Compare Reports" in portfolio_compare_html
    assert "--sidebar-width: 236px" in portfolio_compare_html


def test_enterprise_report_client_rendering_escapes_json_driven_values(tmp_path):
    root = tmp_path / "portfolio"
    history_dir = tmp_path / "history"
    payload = '<img src=x onerror="document.body.dataset.xss=1">'
    previous = RunReport(
        run_id="previous-safe",
        project_name="automation-core",
        framework="pytest",
        generated_at=datetime(2026, 2, 2, tzinfo=UTC),
        tests=[TestCaseReport(id="previous", name="test_previous", status="passed")],
    )
    previous_dir = prepare_timestamped_report_dir(root, run_id=previous.run_id, generated_at=previous.generated_at)
    generate_reporting_product(previous, previous_dir, history_dir=history_dir)

    report = RunReport(
        run_id=f"run-{payload}",
        project_name=f"project-{payload}",
        framework='<svg onload="document.body.dataset.framework=1"></svg>',
        generated_at=datetime(2026, 2, 3, tzinfo=UTC),
        tests=[
            TestCaseReport(
                id="malicious",
                name=payload,
                full_name='<svg onload="document.body.dataset.xss2=1"></svg>',
                status="failed",
                failure_message="<script>document.body.dataset.xss3=1</script>",
                profile=f"profile-{payload}",
                environment=f"env-{payload}",
            )
        ],
    )
    current_dir = prepare_timestamped_report_dir(root, run_id=report.run_id, generated_at=report.generated_at)

    generate_reporting_product(report, current_dir, history_dir=history_dir)
    generate_report_portfolio(root, current_report_dir=current_dir)

    explore_html = (current_dir / "explore.html").read_text(encoding="utf-8")
    dashboard_html = (current_dir / "index.html").read_text(encoding="utf-8")
    compare_html = (current_dir / "compare.html").read_text(encoding="utf-8")
    portfolio_html = (root / "index.html").read_text(encoding="utf-8")
    gallery_html = (root / "reports.html").read_text(encoding="utf-8")
    portfolio_compare_html = (root / "compare.html").read_text(encoding="utf-8")

    for html in (explore_html, portfolio_html, gallery_html, portfolio_compare_html):
        assert "function escapeHtml" in html
        assert "function safeHref" in html
        assert "javascript|data|vbscript" in html
        assert "/[\\u000d\\u000a]/.test(text)" in html
        assert "/[\n]/.test(text)" not in html

    assert "escapeHtml(item.name)" in explore_html
    assert "safeHref(item.detail_href)" in explore_html
    assert "escapeHtml(item.run_id" in portfolio_html
    assert "safeHref(item.entry_href)" in portfolio_html
    assert "escapeHtml(item.run_id" in gallery_html
    assert "safeHref(item.entry_href)" in gallery_html
    assert "escapeHtml(item.run_id" in portfolio_compare_html
    assert "safeHref(item.entry_href)" in portfolio_compare_html
    assert "className = 'table-wrap wide'" in gallery_html
    assert "hydrateResponsiveTables(root)" in gallery_html
    assert ".compare-table table" in compare_html
    assert "trend-svg" in dashboard_html
    assert "labelStep" in portfolio_html


def test_report_client_rendering_does_not_execute_malicious_values_in_browser(tmp_path):
    sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright
    root = tmp_path / "portfolio"
    report = RunReport(
        run_id='run<img src=x onerror="document.body.dataset.run=1">',
        project_name='<img src=x onerror="document.body.dataset.project=1">',
        framework='<img src=x onerror="document.body.dataset.framework=1">',
        generated_at=datetime(2026, 2, 4, tzinfo=UTC),
        tests=[
            TestCaseReport(
                id="malicious",
                name='<img src=x onerror="document.body.dataset.xss=1">',
                full_name='<svg onload="document.body.dataset.xss2=1"></svg>',
                status="passed",
                profile='<img src=x onerror="document.body.dataset.profile=1">',
            )
        ],
    )
    current_dir = prepare_timestamped_report_dir(root, run_id=report.run_id, generated_at=report.generated_at)

    generate_reporting_product(report, current_dir)
    generate_report_portfolio(root, current_report_dir=current_dir)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 900, "height": 700})
        page_errors: list[str] = []
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        for path in (current_dir / "explore.html", root / "index.html", root / "reports.html", root / "compare.html"):
            page.goto("file://" + quote(str(path)), wait_until="load")
            page.wait_for_timeout(200)
            assert page_errors == []
            assert page.evaluate("document.body.dataset.visualSystem") == "enterprise-redesign"
            assert page.evaluate("document.body.dataset.themeDefault") == "system"
            assert page.locator("img").count() == 0
            assert page.locator("svg[onload], img[onerror]").count() == 0
        page.goto("file://" + quote(str(current_dir / "explore.html")), wait_until="load")
        page.wait_for_timeout(200)
        assert page_errors == []
        assert page.locator("#explore-result-count").inner_text() == "1 tests"
        page.goto("file://" + quote(str(root / "reports.html")), wait_until="load")
        page.wait_for_timeout(200)
        assert page_errors == []
        assert page.locator("#gallery-count").inner_text() == "1 reports"
        assert page.locator(".report-card").count() == 1
        browser.close()


def test_healing_sections_render_only_when_healing_events_exist(tmp_path):
    no_healing = RunReport(
        run_id="no-healing-run",
        project_name="automation-core",
        framework="pytest",
        tests=[
            TestCaseReport(
                id="retry-only",
                name="test_retry_only",
                status="passed",
                retries=[
                    RetryAttempt(attempt=1, status="failed"),
                    RetryAttempt(attempt=2, status="passed"),
                ],
            )
        ],
    )
    no_healing_dir = tmp_path / "no-healing"

    generate_reporting_product(no_healing, no_healing_dir, update_history_file=False)

    no_healing_index = (no_healing_dir / "index.html").read_text(encoding="utf-8")
    no_healing_executive = (no_healing_dir / "executive.html").read_text(encoding="utf-8")
    no_healing_detail = next((no_healing_dir / "tests").glob("*.html")).read_text(encoding="utf-8")
    assert "Healing Events" not in no_healing_index
    assert "Healing Events" not in no_healing_executive
    assert "Healing Events" not in no_healing_detail
    assert "No healing events captured" not in no_healing_detail
    assert "Action Retries" in no_healing_index
    assert "Test Retries" in no_healing_index

    with_healing = RunReport(
        run_id="with-healing-run",
        project_name="automation-core",
        framework="pytest",
        tests=[
            TestCaseReport(
                id="healed",
                name="test_real_healing_event",
                status="passed",
                metadata={
                    "healing_events": [
                        {
                            "mode": "apply",
                            "decision": "applied",
                            "action": "click",
                            "selected": {"candidate": {"value": "[data-test='sign-in']"}, "score": 0.91},
                            "reason": "stable locator matched",
                        }
                    ]
                },
            )
        ],
    )
    with_healing_dir = tmp_path / "with-healing"

    generate_reporting_product(with_healing, with_healing_dir, update_history_file=False)

    with_healing_index = (with_healing_dir / "index.html").read_text(encoding="utf-8")
    with_healing_detail = next((with_healing_dir / "tests").glob("*.html")).read_text(encoding="utf-8")
    assert "Healing Events" in with_healing_index
    assert "Healing Events" in with_healing_detail
    assert "[data-test=&#x27;sign-in&#x27;]" in with_healing_detail


def test_product_report_navigation_does_not_overflow_narrow_viewport(tmp_path):
    sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright
    root = tmp_path / "portfolio"
    history_dir = tmp_path / "history"
    log_path = tmp_path / "long-detail.log"
    log_path.write_text(
        "2026-02-05 10:10:10,001 | INFO | framework | "
        "tests.smoke.test_login::test_login_with_a_very_long_context_value_" + ("segment_" * 36),
        encoding="utf-8",
    )
    previous = RunReport(
        run_id="previous-overflow-baseline-with-long-id-" + ("segment-" * 10),
        project_name="automation-core",
        framework="pytest",
        generated_at=datetime(2026, 2, 4, tzinfo=UTC),
        tests=[TestCaseReport(id="previous", name="test_previous", status="passed", domain="web")],
    )
    previous_dir = prepare_timestamped_report_dir(root, run_id=previous.run_id, generated_at=previous.generated_at)
    generate_reporting_product(previous, previous_dir, history_dir=history_dir)
    report = RunReport(
        run_id="narrow-nav-overflow-check",
        project_name="automation-core",
        framework="pytest",
        generated_at=datetime(2026, 2, 5, tzinfo=UTC),
        matrix_dimensions=("domain", "profile", "component", "owner", "context"),
        tests=[
            TestCaseReport(
                id="long-name",
                name="test_with_a_long_name_to_keep_the_page_representative",
                full_name="tests.reports.test_with_a_long_name_to_keep_the_page_representative",
                status="error",
                domain="web-ui-flow-with-a-very-long-domain-name-for-layout-checking",
                profile="chromium-desktop-long-profile-name-used-to-check-wrapping",
                failure_message="setup error " + ("longfailuretoken" * 20),
                capabilities={"context": "WEBVIEW_com.example.checkout.very.long.context.name"},
                metadata={
                    "component": "checkout-component-with-a-long-name-used-for-matrix-layout",
                    "owner": "quality-platform-owner-with-a-long-team-name",
                },
                artifacts=[Artifact(name="long detail log", artifact_type="log", path=str(log_path))],
            ),
            TestCaseReport(id="passed", name="test_passed", status="passed", domain="web"),
        ],
    )
    output_dir = prepare_timestamped_report_dir(root, run_id=report.run_id, generated_at=report.generated_at)

    generate_reporting_product(report, output_dir, history_dir=history_dir)
    generate_report_portfolio(root, current_report_dir=output_dir)

    pages = [
        output_dir / "index.html",
        output_dir / "executive.html",
        output_dir / "quality.html",
        output_dir / "compare.html",
        output_dir / "explore.html",
        output_dir / "timeline.html",
        output_dir / "flaky.html",
        output_dir / "matrix.html",
        output_dir / "history.html",
        output_dir / "share.html",
        output_dir / "print-summary.html",
        next((output_dir / "tests").glob("*.html")),
        root / "index.html",
        root / "reports.html",
        root / "compare.html",
    ]
    viewports = [
        {"width": 1440, "height": 1000},
        {"width": 768, "height": 1024},
        {"width": 390, "height": 900},
        {"width": 360, "height": 800},
    ]

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        for viewport in viewports:
            page = browser.new_page(viewport=viewport)
            for path in pages:
                page.goto("file://" + quote(str(path)), wait_until="load")
                page.wait_for_timeout(100)
                if viewport["width"] < 900:
                    page.locator(".mobile-nav-toggle").click()
                    page.wait_for_timeout(50)
                layout = page.evaluate(
                    """() => {
                      const viewportWidth = document.documentElement.clientWidth;
                      const documentOverflow = Math.max(
                        0,
                        Math.ceil(Math.max(document.documentElement.scrollWidth, document.body.scrollWidth) - viewportWidth)
                      );
                      const isVisible = (node) => {
                        const style = getComputedStyle(node);
                        const rect = node.getBoundingClientRect();
                        return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
                      };
                      const insideAllowedScroll = (node) => Boolean(node.closest('.table-wrap, pre, .app-nav'));
                      const offenders = Array.from(document.body.querySelectorAll('*'))
                        .filter((node) => {
                          if (!isVisible(node) || insideAllowedScroll(node)) return false;
                          const rect = node.getBoundingClientRect();
                          return rect.left < -1 || rect.right > viewportWidth + 1;
                        })
                        .map((node) => ({
                          tag: node.tagName,
                          className: node.className || '',
                          text: (node.textContent || '').trim().slice(0, 80),
                          left: Math.round(node.getBoundingClientRect().left),
                          right: Math.round(node.getBoundingClientRect().right),
                        }))
                        .slice(0, 10);
                      const nav = document.querySelector('.app-nav');
                      const navShell = document.querySelector('[data-nav-shell]');
                      const toggle = document.querySelector('.mobile-nav-toggle');
                      const firstContent = Array.from(document.querySelectorAll('.hero, section')).find(isVisible);
                      const navRect = nav ? nav.getBoundingClientRect() : null;
                      const shellRect = navShell ? navShell.getBoundingClientRect() : null;
                      const contentRect = firstContent ? firstContent.getBoundingClientRect() : null;
                      const desktopNav = viewportWidth >= 900 ? {
                        visible: Boolean(nav && isVisible(nav)),
                        toggleHidden: Boolean(toggle && getComputedStyle(toggle).display === 'none'),
                        separated: Boolean(navRect && contentRect && navRect.right <= contentRect.left + 1),
                        activeLinks: document.querySelectorAll('.app-nav a.active').length,
                        themeButtons: document.querySelectorAll('[data-theme-choice]').length,
                      } : null;
                      const mobileNav = viewportWidth < 900 ? {
                        toggleVisible: Boolean(toggle && isVisible(toggle)),
                        navVisible: Boolean(nav && isVisible(nav)),
                        contained: Boolean(shellRect && shellRect.left >= -1 && shellRect.right <= viewportWidth + 1),
                        themeButtons: document.querySelectorAll('[data-theme-choice]').length,
                      } : null;
                      const internalContainers = Array.from(document.querySelectorAll('.table-wrap, pre')).map((node) => {
                        const rect = node.getBoundingClientRect();
                        const style = getComputedStyle(node);
                        return {
                          contained: rect.left >= -1 && rect.right <= viewportWidth + 1,
                          scrollableSafely: node.scrollWidth <= node.clientWidth + 1 || ['auto', 'scroll', 'visible'].includes(style.overflowX),
                        };
                      });
                      const heatCells = Array.from(document.querySelectorAll('.heat-cell, .test-card, article')).map((node) => {
                        const rect = node.getBoundingClientRect();
                        return rect.left >= -1 && rect.right <= viewportWidth + 1;
                      });
                      const theme = {
                        defaultMode: document.body.dataset.themeDefault,
                        htmlTheme: document.documentElement.dataset.theme,
                        choices: Array.from(document.querySelectorAll('[data-theme-choice]')).map((node) => node.dataset.themeChoice),
                      };
                      return { documentOverflow, offenders, desktopNav, mobileNav, internalContainers, heatCells, theme };
                    }"""
                )
                assert layout["documentOverflow"] == 0
                assert layout["offenders"] == []
                assert layout["theme"]["defaultMode"] == "system"
                assert layout["theme"]["htmlTheme"] in {"system", "light", "dark"}
                assert layout["theme"]["choices"] == ["system", "light", "dark"]
                if viewport["width"] >= 900:
                    assert layout["desktopNav"] == {
                        "visible": True,
                        "toggleHidden": True,
                        "separated": True,
                        "activeLinks": 1,
                        "themeButtons": 3,
                    }
                else:
                    assert layout["mobileNav"] == {
                        "toggleVisible": True,
                        "navVisible": True,
                        "contained": True,
                        "themeButtons": 3,
                    }
                assert all(item["contained"] and item["scrollableSafely"] for item in layout["internalContainers"])
                assert all(layout["heatCells"])
            page.close()
        browser.close()


def test_legacy_matrix_dashboards_do_not_create_document_overflow_on_narrow_viewport(tmp_path):
    sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright
    browser_dashboard = generate_browser_matrix_dashboard(
        [
            {
                "browser": "chromium-with-a-very-long-channel-name-for-mobile-overflow-check",
                "summary": {
                    "status": "passed",
                    "total": 12,
                    "passed": 12,
                    "failed": 0,
                    "broken": 0,
                    "skipped": 0,
                    "duration_ms": 45_000,
                    "pass_rate": 100,
                },
                "report_href": "reports/chromium/index.html",
                "log_href": "logs/chromium-execution.log",
            }
        ],
        tmp_path / "browser-matrix",
    )
    environment_dashboard = generate_environment_matrix_dashboard(
        [
            {
                "env": "qa-environment-with-a-very-long-readable-name-for-mobile-overflow-check",
                "summary": {
                    "status": "failed",
                    "total": 8,
                    "passed": 7,
                    "failed": 1,
                    "broken": 0,
                    "skipped": 0,
                    "duration_ms": 12_500,
                    "pass_rate": 87.5,
                },
                "report_href": "reports/qa/index.html",
                "log_href": "logs/qa-execution.log",
            }
        ],
        tmp_path / "environment-matrix",
    )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 390, "height": 900})
        for path in [browser_dashboard, environment_dashboard]:
            page.goto("file://" + quote(str(path)), wait_until="load")
            page.wait_for_timeout(100)
            overflow = page.evaluate(
                """() => {
                  const viewportWidth = document.documentElement.clientWidth;
                  const documentOverflow = Math.max(
                    0,
                    Math.ceil(Math.max(document.documentElement.scrollWidth, document.body.scrollWidth) - viewportWidth)
                  );
                  const wrappers = Array.from(document.querySelectorAll('.table-wrap')).map((node) => {
                    const rect = node.getBoundingClientRect();
                    return {
                      contained: rect.left >= -1 && rect.right <= viewportWidth + 1,
                      scrollable: node.scrollWidth >= node.clientWidth,
                    };
                  });
                  return { documentOverflow, wrappers };
                }"""
            )
            assert overflow["documentOverflow"] == 0
            assert overflow["wrappers"]
            assert all(wrapper["contained"] for wrapper in overflow["wrappers"])
        browser.close()
