from __future__ import annotations

import os
import shutil
import stat
import urllib.request
import zipfile
from pathlib import Path

DEFAULT_ALLURE_VERSION = "2.29.0"


def get_allure_cli(project_root: Path | str | None = None, logger=None) -> str | None:
    return get_or_install_allure_cli(project_root, logger=logger, install_if_missing=False)


def get_or_install_allure_cli(
    project_root: Path | str | None = None,
    logger=None,
    *,
    version: str | None = None,
    install_if_missing: bool = True,
) -> str | None:
    system_allure = shutil.which("allure")
    if system_allure:
        return system_allure

    if not install_if_missing:
        _log(logger, "warning", "Allure CLI was not found. Built-in HTML report fallback will be used.")
        return None

    root = Path(project_root or Path.cwd())
    selected_version = version or os.getenv("ALLURE_CLI_VERSION", DEFAULT_ALLURE_VERSION)
    install_dir = root / ".tools" / "allure" / f"allure-{selected_version}"
    executable = _allure_executable_path(install_dir)
    if executable.exists():
        return str(executable)

    try:
        _log(logger, "info", "Allure CLI not found. Installing Allure CLI %s locally...", selected_version)
        _download_and_extract_allure(root, selected_version, install_dir)
        executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
        _log(logger, "info", "Installed local Allure CLI: %s", executable)
        return str(executable)
    except Exception as error:
        _log(logger, "warning", "Could not install local Allure CLI. Falling back to built-in report: %s", error)
        return None


def _download_and_extract_allure(
    project_root: Path,
    version: str,
    install_dir: Path,
) -> None:
    tools_dir = project_root / ".tools" / "allure"
    cache_dir = tools_dir / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    archive_path = cache_dir / f"allure-commandline-{version}.zip"
    url = (
        "https://repo.maven.apache.org/maven2/io/qameta/allure/allure-commandline/"
        f"{version}/allure-commandline-{version}.zip"
    )

    if not archive_path.exists():
        urllib.request.urlretrieve(url, archive_path)

    if install_dir.exists():
        shutil.rmtree(install_dir)
    install_dir.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(archive_path) as archive:
        archive.extractall(install_dir.parent)


def _allure_executable_path(install_dir: Path) -> Path:
    if os.name == "nt":
        return install_dir / "bin" / "allure.bat"
    return install_dir / "bin" / "allure"


def _log(logger, level: str, message: str, *args) -> None:
    if logger:
        getattr(logger, level)(message, *args)
