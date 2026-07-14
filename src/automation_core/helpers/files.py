from __future__ import annotations

from pathlib import Path
from shutil import rmtree

from automation_core.helpers.wait import wait_until


def wait_for_file(
    directory: Path | str,
    pattern: str = "*",
    timeout_seconds: float = 30,
    interval_seconds: float = 1,
) -> Path:
    directory_path = Path(directory)
    return wait_until(
        lambda: latest_file(directory_path, pattern),
        timeout_seconds=timeout_seconds,
        interval_seconds=interval_seconds,
        failure_message=f"File matching '{pattern}' was not found in {directory_path}",
    )


def assert_file_exists(path: Path | str) -> Path:
    file_path = Path(path)
    assert file_path.exists(), f"Expected file to exist: {file_path}"
    assert file_path.is_file(), f"Expected path to be a file: {file_path}"
    return file_path


def assert_file_extension(path: Path | str, expected_extension: str) -> Path:
    file_path = assert_file_exists(path)
    normalized_extension = expected_extension if expected_extension.startswith(".") else f".{expected_extension}"
    assert file_path.suffix == normalized_extension, (
        f"Expected file extension {normalized_extension}, got {file_path.suffix}"
    )
    return file_path


def cleanup_directory(path: Path | str, *, recreate: bool = True) -> Path:
    directory = Path(path)
    if directory.exists():
        rmtree(directory)
    if recreate:
        directory.mkdir(parents=True, exist_ok=True)
    return directory


def latest_file(directory: Path | str, pattern: str = "*") -> Path | None:
    directory_path = Path(directory)
    if not directory_path.exists():
        return None
    files = [path for path in directory_path.glob(pattern) if path.is_file()]
    if not files:
        return None
    return max(files, key=lambda path: path.stat().st_mtime)
