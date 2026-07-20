from __future__ import annotations

from automation_core.reporting.adapters import apply_enrichers, run_report_from_allure_results
from automation_core.reporting.allure_cli import get_allure_cli, get_or_install_allure_cli
from automation_core.reporting.allure_debug import attach_file, attach_json, attach_text, step
from automation_core.reporting.analysis import (
    classify_failure,
    failure_summary,
    flaky_analysis,
    matrix_summary,
    summarize_run,
)
from automation_core.reporting.events import ReportingEvent, build_timeline_events
from automation_core.reporting.finalizer import (
    ReportGenerationStatus,
    ReportingFinalizeResult,
    finalize_allure_reporting,
)
from automation_core.reporting.generator import (
    generate_browser_matrix_dashboard,
    generate_device_matrix_dashboard,
    generate_environment_matrix_dashboard,
    generate_html_report,
    generate_matrix_dashboard,
    read_allure_results,
    summarize_results,
)
from automation_core.reporting.insights import QualityScoreWeights, ReportInsightConfig, RiskThresholds
from automation_core.reporting.models import Artifact, RetryAttempt, RunReport, StepRecord, TestCaseReport
from automation_core.reporting.opener import open_report
from automation_core.reporting.portfolio import (
    archive_legacy_report_if_needed,
    collect_report_runs,
    combine_report_portfolios,
    generate_report_portfolio,
    prepare_timestamped_report_dir,
)
from automation_core.reporting.product import generate_reporting_product
from automation_core.reporting.quality import (
    QualityGate,
    QualityGateConfig,
    QualityGateEvaluation,
    QualityGateResult,
    evaluate_quality_gates,
)
from automation_core.reporting.recorder import EventRecorder
from automation_core.reporting.sidecar import build_report_data
from automation_core.reporting.traversal import (
    collect_action_retries,
    collect_step_artifacts,
    collect_step_retries,
    collect_test_artifacts,
    iter_steps,
)
from automation_core.reporting.validation import assert_valid_report, validate_report

__all__ = [
    "Artifact",
    "EventRecorder",
    "ReportingEvent",
    "ReportGenerationStatus",
    "ReportingFinalizeResult",
    "RetryAttempt",
    "RunReport",
    "StepRecord",
    "TestCaseReport",
    "QualityGate",
    "QualityGateConfig",
    "QualityGateEvaluation",
    "QualityGateResult",
    "QualityScoreWeights",
    "ReportInsightConfig",
    "apply_enrichers",
    "attach_file",
    "attach_json",
    "attach_text",
    "build_timeline_events",
    "build_report_data",
    "classify_failure",
    "collect_action_retries",
    "collect_step_artifacts",
    "collect_step_retries",
    "collect_test_artifacts",
    "evaluate_quality_gates",
    "flaky_analysis",
    "finalize_allure_reporting",
    "failure_summary",
    "generate_browser_matrix_dashboard",
    "generate_device_matrix_dashboard",
    "generate_environment_matrix_dashboard",
    "generate_html_report",
    "generate_matrix_dashboard",
    "generate_report_portfolio",
    "generate_reporting_product",
    "get_allure_cli",
    "get_or_install_allure_cli",
    "iter_steps",
    "matrix_summary",
    "open_report",
    "prepare_timestamped_report_dir",
    "archive_legacy_report_if_needed",
    "collect_report_runs",
    "combine_report_portfolios",
    "read_allure_results",
    "RiskThresholds",
    "run_report_from_allure_results",
    "step",
    "summarize_run",
    "summarize_results",
    "assert_valid_report",
    "validate_report",
]
