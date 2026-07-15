from __future__ import annotations

import json
import stat
from pathlib import Path

from automation_core.reporting import finalize_allure_reporting


def test_finalize_allure_reporting_generates_core_report_by_default(tmp_path):
    results_dir = _write_allure_result(tmp_path)

    result = finalize_allure_reporting(
        results_dir,
        tmp_path / "product",
        project_name="automation-core",
        framework="pytest",
        run_id="run-core",
        history_dir=tmp_path / "history",
    )

    assert result.ok is True
    assert result.core.requested is True
    assert result.core.generated is True
    assert result.summary.requested is False
    assert result.allure.requested is False
    assert result.core.path == str(tmp_path / "product" / "index.html")
    assert result.core.run_path is not None
    assert result.core.run_path.startswith(str(tmp_path / "product" / "runs"))
    assert (tmp_path / "product" / "reports.html").exists()
    assert (tmp_path / "product" / "portfolio-data.json").exists()
    assert (tmp_path / "product" / "runs").exists()
    assert (Path(result.core.run_path).parent / "data" / "run-report.json").exists()
    assert list((tmp_path / "history").glob("*.json"))


def test_finalize_both_keeps_core_when_allure_cli_is_missing(tmp_path, monkeypatch):
    results_dir = _write_allure_result(tmp_path)
    monkeypatch.setattr("automation_core.reporting.finalizer.get_allure_cli", lambda logger=None: None)

    result = finalize_allure_reporting(
        results_dir,
        tmp_path / "report",
        project_name="automation-core",
        framework="pytest",
        run_id="run-both",
        report_kind="both",
        history_dir=None,
    )

    assert result.ok is True
    assert result.core.generated is True
    assert result.allure.requested is True
    assert result.allure.generated is False
    assert result.allure.status == "missing_cli"
    assert any("Allure CLI" in warning for warning in result.warnings)


def test_finalize_both_generates_official_allure_when_cli_exists(tmp_path, monkeypatch):
    results_dir = _write_allure_result(tmp_path)
    allure_cli = _fake_allure_cli(tmp_path)
    monkeypatch.setattr("automation_core.reporting.finalizer.get_allure_cli", lambda logger=None: str(allure_cli))

    result = finalize_allure_reporting(
        results_dir,
        tmp_path / "report",
        project_name="automation-core",
        framework="pytest",
        run_id="run-both",
        report_kind="both",
        history_dir=None,
    )

    assert result.ok is True
    assert result.core.generated is True
    assert result.allure.generated is True
    assert result.allure.path == str(tmp_path / "report" / "allure" / "index.html")
    assert "Fake Allure" in (tmp_path / "report" / "allure" / "index.html").read_text(encoding="utf-8")


def test_finalize_open_false_does_not_open_report(tmp_path, monkeypatch):
    results_dir = _write_allure_result(tmp_path)

    def fail_open(path):
        raise AssertionError(f"open_report should not be called for {path}")

    monkeypatch.setattr("automation_core.reporting.finalizer.open_report_path", fail_open)

    result = finalize_allure_reporting(
        results_dir,
        tmp_path / "product",
        project_name="automation-core",
        framework="pytest",
        open_report=False,
        history_dir=None,
    )

    assert result.ok is True
    assert result.opened is False
    assert result.opened_path is None


def test_finalize_missing_results_can_generate_empty_core_report(tmp_path):
    result = finalize_allure_reporting(
        tmp_path / "missing-results",
        tmp_path / "product",
        project_name="automation-core",
        framework="pytest",
        run_id="empty-run",
        missing_ok=True,
        history_dir=tmp_path / "history",
    )

    assert result.ok is True
    assert result.core.generated is True
    assert result.core.run_path is not None
    assert "No tests found" in Path(result.core.run_path).read_text(encoding="utf-8")
    assert any("generating an empty report" in warning for warning in result.warnings)
    assert list((tmp_path / "history").glob("*.json"))


def test_finalize_missing_results_without_missing_ok_returns_failed_status(tmp_path):
    result = finalize_allure_reporting(
        tmp_path / "missing-results",
        tmp_path / "product",
        project_name="automation-core",
        framework="pytest",
        run_id="missing-run",
        history_dir=None,
    )

    assert result.ok is False
    assert result.core.status == "failed"
    assert result.core.generated is False
    assert "Allure results directory not found" in result.core.error
    assert result.errors


def test_finalize_summary_mode_uses_legacy_summary(tmp_path):
    results_dir = _write_allure_result(tmp_path)

    result = finalize_allure_reporting(
        results_dir,
        tmp_path / "summary",
        report_kind="summary",
        history_dir=None,
    )

    assert result.ok is True
    assert result.summary.generated is True
    assert result.core.requested is False
    assert "Allure Results Summary" in (tmp_path / "summary" / "index.html").read_text(encoding="utf-8")


def test_finalize_result_is_serializable_status_data(tmp_path, monkeypatch):
    results_dir = _write_allure_result(tmp_path)
    monkeypatch.setattr("automation_core.reporting.finalizer.get_allure_cli", lambda logger=None: None)

    result = finalize_allure_reporting(
        results_dir,
        tmp_path / "report",
        report_kind="both",
        history_dir=None,
    )

    payload = result.to_dict()

    assert payload["ok"] is True
    assert payload["core"]["generated"] is True
    assert payload["allure"]["status"] == "missing_cli"


def test_finalize_core_accepts_neutral_metadata_hooks(tmp_path):
    results_dir = _write_allure_result(tmp_path)

    result = finalize_allure_reporting(
        results_dir,
        tmp_path / "product",
        report_kind="core",
        history_dir=None,
        test_metadata={
            "case-finalizer": {
                "domain": "mobile",
                "profile": "ios",
                "capabilities": {"context": "WEBVIEW"},
                "platform_version": "17.5",
            }
        },
        matrix_dimensions=["domain", "profile", "platform_version", "context"],
    )

    assert result.core.run_path is not None
    run_report = json.loads(
        (Path(result.core.run_path).parent / "data" / "run-report.json").read_text(encoding="utf-8")
    )

    assert result.ok is True
    assert run_report["matrix_dimensions"] == ["domain", "profile", "platform_version", "context"]
    assert run_report["tests"][0]["domain"] == "mobile"
    assert run_report["tests"][0]["metadata"]["platform_version"] == "17.5"


def test_finalize_core_retains_multiple_timestamped_reports_and_portfolio_pages(tmp_path):
    first_results = _write_allure_result(tmp_path, name="first-result.json", history_id="case-one")
    second_results = _write_allure_result(tmp_path, name="second-result.json", history_id="case-two")
    output_dir = tmp_path / "product"

    first = finalize_allure_reporting(
        first_results,
        output_dir,
        project_name="automation-core",
        framework="pytest",
        run_id="run-one",
        history_dir=tmp_path / "history",
    )
    second = finalize_allure_reporting(
        second_results,
        output_dir,
        project_name="automation-core",
        framework="pytest",
        run_id="run-two",
        history_dir=tmp_path / "history",
    )

    assert first.core.run_path != second.core.run_path
    run_dirs = sorted((output_dir / "runs").iterdir())
    assert len(run_dirs) == 2
    assert all(path.name[:8].isdigit() and path.name[8] == "-" for path in run_dirs)
    portfolio = json.loads((output_dir / "portfolio-data.json").read_text(encoding="utf-8"))
    assert [item["run_id"] for item in portfolio["reports"]] == ["run-two", "run-one"]
    assert "Automation Reports Dashboard" in (output_dir / "index.html").read_text(encoding="utf-8")
    assert "Reports" in (output_dir / "reports.html").read_text(encoding="utf-8")


def test_finalize_core_archives_legacy_root_report_before_writing_portfolio(tmp_path):
    output_dir = tmp_path / "product"
    (output_dir / "data").mkdir(parents=True)
    (output_dir / "tests").mkdir()
    (output_dir / "index.html").write_text("<html>legacy</html>", encoding="utf-8")
    (output_dir / "data" / "run-report.json").write_text("{}", encoding="utf-8")
    (output_dir / "report-data.json").write_text(
        json.dumps(
            {
                "run": {
                    "summary": {
                        "run_id": "legacy-run",
                        "latest_run": "2026-07-16T10:00:00+00:00",
                        "status": "passed",
                        "total": 1,
                        "passed": 1,
                        "failed": 0,
                        "broken": 0,
                        "skipped": 0,
                        "flaky": 0,
                        "pass_rate": 100,
                        "duration_ms": 100,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    results_dir = _write_allure_result(tmp_path)

    result = finalize_allure_reporting(
        results_dir,
        output_dir,
        project_name="automation-core",
        framework="pytest",
        run_id="new-run",
        history_dir=None,
    )

    assert result.ok is True
    portfolio = json.loads((output_dir / "portfolio-data.json").read_text(encoding="utf-8"))
    assert {item["run_id"] for item in portfolio["reports"]} == {"legacy-run", "new-run"}
    legacy_dir = next(path for path in (output_dir / "runs").iterdir() if "legacy-run" in path.name)
    assert (legacy_dir / "index.html").read_text(encoding="utf-8") == "<html>legacy</html>"
    assert not (output_dir / "report-data.json").exists()


def _write_allure_result(tmp_path, *, name="one-result.json", history_id="case-finalizer"):
    results_dir = tmp_path / f"allure-results-{history_id}"
    results_dir.mkdir()
    (results_dir / name).write_text(
        json.dumps(
            {
                "historyId": history_id,
                "name": "test_finalizer",
                "fullName": "tests.test_finalizer",
                "status": "passed",
                "start": 100,
                "stop": 250,
            }
        ),
        encoding="utf-8",
    )
    return results_dir


def _fake_allure_cli(tmp_path):
    cli = tmp_path / "allure"
    cli.write_text(
        """#!/bin/sh
set -eu
output=""
while [ "$#" -gt 0 ]; do
  if [ "$1" = "-o" ]; then
    shift
    output="$1"
  fi
  shift || true
done
mkdir -p "$output"
printf '%s' '<html>Fake Allure</html>' > "$output/index.html"
""",
        encoding="utf-8",
    )
    cli.chmod(cli.stat().st_mode | stat.S_IXUSR)
    return cli
