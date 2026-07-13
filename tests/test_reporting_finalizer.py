from __future__ import annotations

import json
import stat

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
    assert (tmp_path / "product" / "data" / "run-report.json").exists()
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
    assert "No tests found" in (tmp_path / "product" / "index.html").read_text(encoding="utf-8")
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

    run_report = json.loads((tmp_path / "product" / "data" / "run-report.json").read_text(encoding="utf-8"))

    assert result.ok is True
    assert run_report["matrix_dimensions"] == ["domain", "profile", "platform_version", "context"]
    assert run_report["tests"][0]["domain"] == "mobile"
    assert run_report["tests"][0]["metadata"]["platform_version"] == "17.5"


def _write_allure_result(tmp_path):
    results_dir = tmp_path / "allure-results"
    results_dir.mkdir()
    (results_dir / "one-result.json").write_text(
        json.dumps(
            {
                "historyId": "case-finalizer",
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
