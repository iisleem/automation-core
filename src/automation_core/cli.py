from __future__ import annotations

import argparse
from pathlib import Path

from automation_core.reporting import ReportingFinalizeResult, finalize_allure_reporting


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate automation-core reports from Allure result files.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--product",
        dest="report_kind",
        action="store_const",
        const="core",
        help="Generate the full reporting product. This is the default.",
    )
    mode.add_argument(
        "--summary",
        dest="report_kind",
        action="store_const",
        const="summary",
        help="Generate the legacy single-page HTML summary.",
    )
    mode.add_argument(
        "--allure",
        dest="report_kind",
        action="store_const",
        const="allure",
        help="Generate the official Allure HTML report only.",
    )
    mode.add_argument(
        "--both",
        dest="report_kind",
        action="store_const",
        const="both",
        help="Generate the core product report and the official Allure report when the Allure CLI is available.",
    )
    mode.add_argument(
        "--report-kind",
        choices=("core", "product", "summary", "allure", "both"),
        help="Select report output mode. Defaults to core.",
    )
    parser.add_argument("--results", default="reports/allure-results", help="Allure results directory.")
    parser.add_argument("--output", default="reports/automation-report", help="Report output directory.")
    parser.add_argument("--project-name", default="", help="Project name shown in the product report.")
    parser.add_argument("--framework", default="", help="Framework name shown in the product report.")
    parser.add_argument("--run-id", default=None, help="Stable run id for product history.")
    parser.add_argument("--history-dir", default="reports/history", help="History directory for product trends.")
    parser.add_argument("--no-history", action="store_true", help="Do not read or update report history.")
    parser.add_argument("--open", action="store_true", help="Open the generated report in the default browser.")
    parser.add_argument(
        "--open-target",
        choices=("auto", "core", "summary", "allure"),
        default="auto",
        help="Which generated report to open when --open is used.",
    )
    parser.add_argument("--missing-ok", action="store_true", help="Generate an empty report when results are missing.")
    parser.add_argument(
        "--install-allure-cli",
        action="store_true",
        help="Install the official Allure CLI locally if --allure/--both needs it and it is missing.",
    )
    parser.set_defaults(report_kind="core")
    args = parser.parse_args(argv)

    result = finalize_allure_reporting(
        Path(args.results),
        Path(args.output),
        project_name=args.project_name,
        framework=args.framework,
        run_id=args.run_id,
        history_dir=None if args.no_history else Path(args.history_dir),
        open_report=args.open,
        report_kind=args.report_kind,
        open_target=args.open_target,
        missing_ok=args.missing_ok,
        install_allure_cli=args.install_allure_cli,
    )
    _print_result(result)
    return 0 if result.ok else 1


def _print_result(result: ReportingFinalizeResult) -> None:
    for label, status in (("Core", result.core), ("Summary", result.summary), ("Allure", result.allure)):
        if not status.requested:
            continue
        if status.generated:
            print(f"{label} report generated: {status.path}")
        else:
            print(f"{label} report {status.status}: {status.error or '; '.join(status.warnings)}")

    for warning in result.warnings:
        print(f"Warning: {warning}")
    for error in result.errors:
        print(f"Error: {error}")
    if result.opened_path:
        print(f"Opened report: {result.opened_path}" if result.opened else f"Report not opened: {result.opened_path}")
