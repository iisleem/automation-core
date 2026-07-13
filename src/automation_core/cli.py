from __future__ import annotations

import argparse
from pathlib import Path

from automation_core.reporting import (
    generate_html_report,
    generate_reporting_product,
    open_report,
    run_report_from_allure_results,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate automation-core reports from Allure result files.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--product", action="store_true", help="Generate the full reporting product. This is the default."
    )
    mode.add_argument("--summary", action="store_true", help="Generate the legacy single-page HTML summary.")
    parser.add_argument("--results", default="reports/allure-results", help="Allure results directory.")
    parser.add_argument("--output", default="reports/automation-report", help="Report output directory.")
    parser.add_argument("--project-name", default="", help="Project name shown in the product report.")
    parser.add_argument("--framework", default="", help="Framework name shown in the product report.")
    parser.add_argument("--run-id", default=None, help="Stable run id for product history.")
    parser.add_argument("--history-dir", default="reports/history", help="History directory for product trends.")
    parser.add_argument("--no-history", action="store_true", help="Do not read or update report history.")
    parser.add_argument("--open", action="store_true", help="Open the generated report in the default browser.")
    parser.add_argument("--missing-ok", action="store_true", help="Generate an empty report when results are missing.")
    args = parser.parse_args(argv)

    if args.summary:
        report_path = generate_html_report(
            Path(args.results),
            Path(args.output),
            missing_ok=args.missing_ok,
        )
    else:
        report = run_report_from_allure_results(
            Path(args.results),
            run_id=args.run_id,
            project_name=args.project_name,
            framework=args.framework,
            missing_ok=args.missing_ok,
        )
        report_path = generate_reporting_product(
            report,
            Path(args.output),
            history_dir=None if args.no_history else Path(args.history_dir),
        )
    print(f"Report generated: {report_path}")
    if args.open:
        open_report(report_path)
    return 0
