from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from automation_core.helpers.files import assert_file_exists


def read_csv_file(path: Path | str) -> list[dict[str, str]]:
    file_path = assert_file_exists(path)
    with file_path.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def assert_csv_headers(path: Path | str, expected_headers: list[str]) -> None:
    file_path = assert_file_exists(path)
    with file_path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.reader(file)
        actual_headers = next(reader, [])
    assert actual_headers == expected_headers, f"Expected CSV headers {expected_headers}, got {actual_headers}"


def assert_csv_row_count(path: Path | str, expected_count: int) -> None:
    rows = read_csv_file(path)
    assert len(rows) == expected_count, f"Expected {expected_count} CSV rows, got {len(rows)}"


def read_json_file(path: Path | str) -> Any:
    file_path = assert_file_exists(path)
    with file_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def assert_json_file_field(
    path: Path | str,
    field_path: str,
    expected_value: Any,
) -> None:
    data = read_json_file(path)
    actual_value = get_nested_value(data, field_path)
    assert actual_value == expected_value, (
        f"Expected JSON file field '{field_path}' to be {expected_value!r}, got {actual_value!r}"
    )


def get_nested_value(data: Any, field_path: str, default: Any = None) -> Any:
    current = data
    for part in field_path.split("."):
        if isinstance(current, dict):
            current = current.get(part, default)
        elif isinstance(current, list) and part.isdigit():
            index = int(part)
            if index >= len(current):
                return default
            current = current[index]
        else:
            return default
    return current
