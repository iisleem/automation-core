from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

MATRIX_DASHBOARD_DIRS = {"browser-matrix", "environment-matrix", "device-matrix"}


def open_report(report_path: Path | str, logger=None) -> bool:
    path = Path(report_path).resolve()
    if not path.exists():
        _log(logger, "warning", "Report path does not exist: %s", path)
        return False
    if _is_ci_or_server_environment():
        _log(logger, "info", "Report generated but not opened in CI/server mode: %s", path)
        return True
    if _should_open_via_http_server(path):
        return _open_report_via_http_server(path, logger)
    return _open_file_url(path, logger)


def _should_open_via_http_server(report_path: Path) -> bool:
    return _is_official_allure_report(report_path) or _is_matrix_dashboard(report_path)


def _is_official_allure_report(report_path: Path) -> bool:
    report_dir = report_path.parent
    return report_path.name == "index.html" and (report_dir / "app.js").exists() and (report_dir / "widgets").exists()


def _is_matrix_dashboard(report_path: Path) -> bool:
    return (
        report_path.name == "index.html"
        and report_path.parent.name in MATRIX_DASHBOARD_DIRS
        and (report_path.parent / "reports").exists()
    )


def _open_report_via_http_server(report_path: Path, logger=None) -> bool:
    port = _find_free_port()
    report_dir = report_path.parent
    command = [
        sys.executable,
        "-m",
        "http.server",
        str(port),
        "--bind",
        "127.0.0.1",
        "--directory",
        str(report_dir),
    ]

    try:
        subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=report_dir,
            **_detached_process_kwargs(),
        )
        time.sleep(0.4)
        url = f"http://127.0.0.1:{port}/{report_path.name}"
        opened = webbrowser.open(url)
        if opened:
            _log(logger, "info", "Opened report through local server: %s", url)
        else:
            _log(logger, "warning", "Report server started but browser did not open: %s", url)
        return True
    except Exception as error:
        _log(
            logger,
            "warning",
            "Could not open report through local server. Falling back to file URL: %s",
            error,
        )
        return _open_file_url(report_path, logger)


def _open_file_url(report_path: Path, logger=None) -> bool:
    try:
        opened = webbrowser.open(report_path.as_uri())
        if opened:
            _log(logger, "info", "Opened report in default browser: %s", report_path)
        else:
            _log(logger, "warning", "Report generated but default browser did not open it: %s", report_path)
        return True
    except Exception as error:
        _log(logger, "warning", "Report generated but could not open default browser: %s", error)
        return True


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _detached_process_kwargs() -> dict:
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS}
    return {"start_new_session": True}


def _is_ci_or_server_environment() -> bool:
    if os.getenv("CI") or os.getenv("GITHUB_ACTIONS"):
        return True
    if os.name != "nt" and not os.getenv("DISPLAY") and not os.getenv("WAYLAND_DISPLAY"):
        return os.uname().sysname != "Darwin"
    return False


def _log(logger, level: str, message: str, *args) -> None:
    if logger:
        getattr(logger, level)(message, *args)
        return
    print(message % args if args else message)
