from __future__ import annotations

from automation_core.reporting.adapters import apply_enrichers, run_report_from_allure_results
from automation_core.reporting.allure_cli import get_allure_cli, get_or_install_allure_cli
from automation_core.reporting.allure_debug import attach_file, attach_json, attach_text, step
from automation_core.reporting.analysis import classify_failure, flaky_analysis, matrix_summary, summarize_run
from automation_core.reporting.events import ReportingEvent, build_timeline_events
from automation_core.reporting.generator import (
    generate_browser_matrix_dashboard,
    generate_device_matrix_dashboard,
    generate_environment_matrix_dashboard,
    generate_html_report,
    generate_matrix_dashboard,
    read_allure_results,
    summarize_results,
)
from automation_core.reporting.models import Artifact, RetryAttempt, RunReport, StepRecord, TestCaseReport
from automation_core.reporting.opener import open_report
from automation_core.reporting.product import generate_reporting_product
from automation_core.reporting.recorder import EventRecorder
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
    "RetryAttempt",
    "RunReport",
    "StepRecord",
    "TestCaseReport",
    "apply_enrichers",
    "attach_file",
    "attach_json",
    "attach_text",
    "build_timeline_events",
    "classify_failure",
    "collect_action_retries",
    "collect_step_artifacts",
    "collect_step_retries",
    "collect_test_artifacts",
    "flaky_analysis",
    "generate_browser_matrix_dashboard",
    "generate_device_matrix_dashboard",
    "generate_environment_matrix_dashboard",
    "generate_html_report",
    "generate_matrix_dashboard",
    "generate_reporting_product",
    "get_allure_cli",
    "get_or_install_allure_cli",
    "iter_steps",
    "matrix_summary",
    "open_report",
    "read_allure_results",
    "run_report_from_allure_results",
    "step",
    "summarize_run",
    "summarize_results",
    "assert_valid_report",
    "validate_report",
]
