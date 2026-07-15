from __future__ import annotations

import json
from contextlib import contextmanager

import pytest

from automation_core.cli import main as cli_main
from automation_core.reporting import (
    attach_file,
    attach_json,
    attach_text,
    generate_browser_matrix_dashboard,
    generate_device_matrix_dashboard,
    generate_environment_matrix_dashboard,
    generate_html_report,
    generate_matrix_dashboard,
    open_report,
    read_allure_results,
    step,
    summarize_results,
)


def test_allure_result_report_generation(tmp_path):
    results_dir = tmp_path / "allure-results"
    results_dir.mkdir()
    (results_dir / "one-result.json").write_text(
        json.dumps(
            {
                "name": "test_login",
                "fullName": "tests.test_login",
                "status": "passed",
                "start": 10,
                "stop": 45,
            }
        ),
        encoding="utf-8",
    )
    (results_dir / "two-result.json").write_text(
        json.dumps(
            {
                "name": "test_checkout",
                "status": "failed",
                "statusDetails": {"message": "total mismatch"},
                "start": 50,
                "stop": 100,
            }
        ),
        encoding="utf-8",
    )

    tests = read_allure_results(results_dir)
    summary = summarize_results(tests)
    report_path = generate_html_report(results_dir, tmp_path / "report")

    assert [test["name"] for test in tests] == ["test_checkout", "test_login"]
    assert summary["total"] == 2
    assert summary["failed"] == 1
    assert "test_checkout" in report_path.read_text(encoding="utf-8")


def test_generate_html_report_can_allow_missing_results(tmp_path):
    report_path = generate_html_report(tmp_path / "missing", tmp_path / "report", missing_ok=True)

    assert "No Allure results found" in report_path.read_text(encoding="utf-8")
    with pytest.raises(FileNotFoundError):
        read_allure_results(tmp_path / "missing")


def test_matrix_dashboard_wrappers(tmp_path):
    run = {
        "browser": "chromium",
        "env": "dev",
        "profile": "android",
        "summary": {
            "total": 2,
            "passed": 1,
            "failed": 1,
            "broken": 0,
            "skipped": 0,
            "duration_ms": 1200,
            "pass_rate": 50,
            "status": "failed",
        },
        "report_href": "reports/chromium/index.html",
        "log_href": "logs/chromium.log",
    }

    generic = generate_matrix_dashboard(
        [run],
        tmp_path / "generic",
        dimension_key="browser",
        dimension_label="Browser",
        title="Browser Matrix Dashboard",
        description="Test matrix",
    )
    browser = generate_browser_matrix_dashboard([run], tmp_path / "browser")
    environment = generate_environment_matrix_dashboard([run], tmp_path / "environment")
    device = generate_device_matrix_dashboard([run], tmp_path / "device")

    assert "chromium" in generic.read_text(encoding="utf-8")
    assert "Browser Matrix Dashboard" in browser.read_text(encoding="utf-8")
    assert "API Environment Matrix Dashboard" in environment.read_text(encoding="utf-8")
    assert "Device Matrix Dashboard" in device.read_text(encoding="utf-8")


def test_open_report_skips_browser_in_ci(tmp_path, monkeypatch):
    report = tmp_path / "index.html"
    report.write_text("<html></html>", encoding="utf-8")
    monkeypatch.setenv("CI", "true")

    assert open_report(report) is True
    assert open_report(tmp_path / "missing.html") is False


def test_allure_debug_helpers_accept_fake_allure(tmp_path):
    class AttachmentType:
        TEXT = "text"
        JSON = "json"

    class Attach:
        def __init__(self):
            self.calls = []

        def __call__(self, content, *, name, attachment_type):
            self.calls.append((name, content, attachment_type))

        def file(self, path, *, name, attachment_type=None, extension=None):
            self.calls.append((name, path, attachment_type, extension))

    class FakeAllure:
        attachment_type = AttachmentType()

        def __init__(self):
            self.attach = Attach()

        @contextmanager
        def step(self, title):
            self.title = title
            yield

    fake = FakeAllure()
    attachment = tmp_path / "debug.txt"
    attachment.write_text("debug", encoding="utf-8")

    with step("debug step", allure_api=fake):
        attach_text("hello", name="greeting", allure_api=fake)
        attach_json({"ok": True}, name="payload", allure_api=fake)
        assert attach_file(attachment, allure_api=fake) == attachment

    assert fake.title == "debug step"
    assert fake.attach.calls[0] == ("greeting", "hello", "text")
    assert fake.attach.calls[1][0] == "payload"
    assert fake.attach.calls[2][0] == "debug.txt"


def test_cli_generates_product_report_by_default_and_summary_when_requested(tmp_path, monkeypatch):
    results_dir = tmp_path / "allure-results"
    results_dir.mkdir()
    (results_dir / "one-result.json").write_text(
        json.dumps(
            {
                "historyId": "case-cli",
                "name": "test_cli",
                "fullName": "tests.test_cli",
                "status": "passed",
                "start": 100,
                "stop": 250,
            }
        ),
        encoding="utf-8",
    )

    product_output = tmp_path / "product"
    summary_output = tmp_path / "summary"
    both_output = tmp_path / "both"
    monkeypatch.setattr("automation_core.reporting.finalizer.get_allure_cli", lambda logger=None: None)

    assert (
        cli_main(
            [
                "--results",
                str(results_dir),
                "--output",
                str(product_output),
                "--project-name",
                "automation-core",
                "--framework",
                "pytest",
                "--run-id",
                "cli-run",
                "--no-history",
            ]
        )
        == 0
    )
    assert (product_output / "index.html").exists()
    assert (product_output / "reports.html").exists()
    run_dirs = list((product_output / "runs").iterdir())
    assert len(run_dirs) == 1
    assert (run_dirs[0] / "timeline.html").exists()
    assert (run_dirs[0] / "data" / "run-report.json").exists()

    assert (
        cli_main(
            [
                "--summary",
                "--results",
                str(results_dir),
                "--output",
                str(summary_output),
            ]
        )
        == 0
    )
    assert "Allure Results Summary" in (summary_output / "index.html").read_text(encoding="utf-8")

    assert (
        cli_main(
            [
                "--both",
                "--results",
                str(results_dir),
                "--output",
                str(both_output),
                "--project-name",
                "automation-core",
                "--framework",
                "pytest",
                "--run-id",
                "cli-both-run",
                "--no-history",
            ]
        )
        == 0
    )
    assert (both_output / "index.html").exists()
    assert (both_output / "reports.html").exists()
    assert not (both_output / "allure" / "index.html").exists()
