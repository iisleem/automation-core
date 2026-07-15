from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast

from automation_core.reporting.adapters import ReportEnricher, TestMetadata, run_report_from_allure_results
from automation_core.reporting.allure_cli import get_allure_cli, get_or_install_allure_cli
from automation_core.reporting.generator import generate_html_report
from automation_core.reporting.opener import open_report as open_report_path
from automation_core.reporting.portfolio import generate_report_portfolio, prepare_timestamped_report_dir
from automation_core.reporting.product import generate_reporting_product

ReportKind = Literal["core", "summary", "allure", "both"]
OpenTarget = Literal["auto", "core", "summary", "allure"]


@dataclass
class ReportGenerationStatus:
    requested: bool = False
    generated: bool = False
    status: str = "not_requested"
    path: str | None = None
    run_path: str | None = None
    error: str = ""
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "requested": self.requested,
            "generated": self.generated,
            "status": self.status,
            "path": self.path,
            "run_path": self.run_path,
            "error": self.error,
            "warnings": list(self.warnings),
        }


@dataclass
class ReportingFinalizeResult:
    report_kind: str
    results_dir: str
    output_dir: str
    project_name: str = ""
    framework: str = ""
    run_id: str | None = None
    core: ReportGenerationStatus = field(default_factory=ReportGenerationStatus)
    summary: ReportGenerationStatus = field(default_factory=ReportGenerationStatus)
    allure: ReportGenerationStatus = field(default_factory=ReportGenerationStatus)
    opened: bool = False
    opened_path: str | None = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        if self.core.requested:
            return self.core.generated
        if self.summary.requested:
            return self.summary.generated
        if self.allure.requested:
            return self.allure.generated
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "report_kind": self.report_kind,
            "results_dir": self.results_dir,
            "output_dir": self.output_dir,
            "project_name": self.project_name,
            "framework": self.framework,
            "run_id": self.run_id,
            "core": self.core.to_dict(),
            "summary": self.summary.to_dict(),
            "allure": self.allure.to_dict(),
            "opened": self.opened,
            "opened_path": self.opened_path,
            "warnings": list(self.warnings),
            "errors": list(self.errors),
        }


def finalize_allure_reporting(
    results_dir: str | Path,
    output_dir: str | Path,
    *,
    project_name: str = "",
    framework: str = "",
    run_id: str | None = None,
    history_dir: str | Path | None = None,
    open_report: bool = False,
    report_kind: str = "core",
    open_target: OpenTarget = "auto",
    missing_ok: bool = False,
    allure_output_dir: str | Path | None = None,
    summary_output_dir: str | Path | None = None,
    metadata: dict[str, Any] | None = None,
    test_metadata: TestMetadata | None = None,
    enrichers: list[ReportEnricher] | None = None,
    matrix_dimensions: list[str] | None = None,
    install_allure_cli: bool = False,
    bundle_artifacts: bool = True,
    update_history_file: bool = True,
    logger=None,
) -> ReportingFinalizeResult:
    """Finalize reporting from an Allure results directory.

    The default path generates the automation-core product report. Official Allure
    HTML generation is opt-in and non-fatal when core reporting can still finish.
    """

    normalized_kind = _normalize_report_kind(report_kind)
    results_path = Path(results_dir)
    output_path = Path(output_dir)
    result = ReportingFinalizeResult(
        report_kind=normalized_kind,
        results_dir=str(results_path),
        output_dir=str(output_path),
        project_name=project_name,
        framework=framework,
        run_id=run_id,
    )

    if _should_generate_core(normalized_kind):
        _generate_core_report(
            result,
            results_path,
            output_path,
            project_name=project_name,
            framework=framework,
            run_id=run_id,
            history_dir=history_dir,
            missing_ok=missing_ok,
            metadata=metadata,
            test_metadata=test_metadata,
            enrichers=enrichers,
            matrix_dimensions=matrix_dimensions,
            bundle_artifacts=bundle_artifacts,
            update_history_file=update_history_file,
        )

    if normalized_kind == "summary":
        _generate_summary_report(
            result,
            results_path,
            Path(summary_output_dir) if summary_output_dir else output_path,
            missing_ok=missing_ok,
        )

    if normalized_kind in {"allure", "both"}:
        default_allure_output = output_path if normalized_kind == "allure" else output_path / "allure"
        _generate_official_allure_report(
            result,
            results_path,
            Path(allure_output_dir) if allure_output_dir else default_allure_output,
            missing_ok=missing_ok,
            install_allure_cli=install_allure_cli,
            logger=logger,
        )

    if open_report:
        _open_generated_report(result, open_target)

    return result


def _generate_core_report(
    result: ReportingFinalizeResult,
    results_path: Path,
    output_path: Path,
    *,
    project_name: str,
    framework: str,
    run_id: str | None,
    history_dir: str | Path | None,
    missing_ok: bool,
    metadata: dict[str, Any] | None,
    test_metadata: TestMetadata | None,
    enrichers: list[ReportEnricher] | None,
    matrix_dimensions: list[str] | None,
    bundle_artifacts: bool,
    update_history_file: bool,
) -> None:
    result.core.requested = True
    _warn_if_no_results(result, results_path, missing_ok=missing_ok)
    try:
        report = run_report_from_allure_results(
            results_path,
            run_id=run_id,
            project_name=project_name,
            framework=framework,
            metadata=metadata,
            test_metadata=test_metadata,
            enrichers=enrichers,
            missing_ok=missing_ok,
        )
        if matrix_dimensions is not None:
            report.matrix_dimensions = matrix_dimensions
        report_output_path = prepare_timestamped_report_dir(
            output_path,
            run_id=report.run_id,
            generated_at=report.generated_at,
        )
        report_path = generate_reporting_product(
            report,
            report_output_path,
            history_dir=Path(history_dir) if history_dir is not None else None,
            bundle_artifacts=bundle_artifacts,
            update_history_file=update_history_file,
        )
        portfolio_path = generate_report_portfolio(output_path, current_report_dir=report_output_path)
    except Exception as error:
        _mark_failed(result.core, error)
        result.errors.append(f"Core report failed: {error}")
        return

    result.core.generated = True
    result.core.status = "generated"
    result.core.path = str(portfolio_path)
    result.core.run_path = str(report_path)


def _generate_summary_report(
    result: ReportingFinalizeResult,
    results_path: Path,
    output_path: Path,
    *,
    missing_ok: bool,
) -> None:
    result.summary.requested = True
    _warn_if_no_results(result, results_path, missing_ok=missing_ok)
    try:
        report_path = generate_html_report(results_path, output_path, missing_ok=missing_ok)
    except Exception as error:
        _mark_failed(result.summary, error)
        result.errors.append(f"Summary report failed: {error}")
        return

    result.summary.generated = True
    result.summary.status = "generated"
    result.summary.path = str(report_path)


def _generate_official_allure_report(
    result: ReportingFinalizeResult,
    results_path: Path,
    output_path: Path,
    *,
    missing_ok: bool,
    install_allure_cli: bool,
    logger=None,
) -> None:
    result.allure.requested = True
    if not _has_result_files(results_path):
        if results_path.exists() or missing_ok:
            _mark_warning(
                result,
                result.allure,
                "Official Allure report skipped because no Allure result files were found.",
            )
            result.allure.status = "no_results"
            return

        error = FileNotFoundError(f"Allure results directory not found: {results_path}")
        _mark_failed(result.allure, error)
        result.errors.append(f"Official Allure report failed: {error}")
        return

    allure_cli = (
        get_or_install_allure_cli(install_if_missing=True, logger=logger)
        if install_allure_cli
        else get_allure_cli(logger=logger)
    )
    if not allure_cli:
        _mark_warning(
            result,
            result.allure,
            "Official Allure CLI was not found; core reporting remains available.",
        )
        result.allure.status = "missing_cli"
        return

    try:
        subprocess.run(
            [allure_cli, "generate", str(results_path), "-o", str(output_path), "--clean"],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception as error:
        message = _subprocess_error_message(error)
        result.allure.generated = False
        result.allure.status = "failed"
        result.allure.error = message
        result.errors.append(f"Official Allure report failed: {message}")
        return

    report_path = output_path / "index.html"
    result.allure.generated = True
    result.allure.status = "generated"
    result.allure.path = str(report_path)


def _open_generated_report(result: ReportingFinalizeResult, open_target: OpenTarget) -> None:
    path = _select_open_path(result, open_target)
    if not path:
        result.warnings.append("Open requested, but no generated report path was available.")
        return

    result.opened_path = path
    result.opened = open_report_path(path)
    if not result.opened:
        result.warnings.append(f"Could not open report: {path}")


def _select_open_path(result: ReportingFinalizeResult, open_target: OpenTarget) -> str | None:
    if open_target != "auto":
        status = getattr(result, open_target)
        return status.path if status.generated else None

    if result.report_kind == "allure":
        return result.allure.path if result.allure.generated else None
    if result.report_kind == "summary":
        return result.summary.path if result.summary.generated else None
    return result.core.path if result.core.generated else None


def _normalize_report_kind(report_kind: str) -> ReportKind:
    aliases = {"product": "core"}
    normalized = aliases.get(report_kind.strip().lower(), report_kind.strip().lower())
    if normalized not in {"core", "summary", "allure", "both"}:
        raise ValueError(f"Unsupported report_kind: {report_kind}")
    return cast(ReportKind, normalized)


def _should_generate_core(report_kind: ReportKind) -> bool:
    return report_kind in {"core", "both"}


def _has_result_files(results_path: Path) -> bool:
    return results_path.exists() and any(results_path.glob("*-result.json"))


def _warn_if_no_results(result: ReportingFinalizeResult, results_path: Path, *, missing_ok: bool) -> None:
    if _has_result_files(results_path):
        return
    if results_path.exists():
        result.warnings.append(f"No Allure result files found in: {results_path}")
    elif missing_ok:
        result.warnings.append(f"Allure results directory not found; generating an empty report: {results_path}")


def _mark_failed(status: ReportGenerationStatus, error: Exception) -> None:
    status.generated = False
    status.status = "failed"
    status.error = str(error)


def _mark_warning(
    result: ReportingFinalizeResult,
    status: ReportGenerationStatus,
    warning: str,
) -> None:
    status.warnings.append(warning)
    result.warnings.append(warning)


def _subprocess_error_message(error: Exception) -> str:
    if isinstance(error, subprocess.CalledProcessError):
        stderr = (error.stderr or "").strip()
        stdout = (error.stdout or "").strip()
        detail = stderr or stdout
        return detail or str(error)
    return str(error)
