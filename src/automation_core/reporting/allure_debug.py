from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any


@contextmanager
def step(title: str, *, allure_api: Any | None = None) -> Iterator[None]:
    api = allure_api or _import_allure()
    if api is None:
        yield
        return
    with api.step(title):
        yield


def attach_text(
    content: str,
    name: str = "text attachment",
    *,
    allure_api: Any | None = None,
) -> None:
    api = allure_api or _import_allure()
    if api is None:
        return
    api.attach(
        content,
        name=name,
        attachment_type=api.attachment_type.TEXT,
    )


def attach_json(
    data: Any,
    name: str = "json attachment",
    *,
    indent: int = 2,
    allure_api: Any | None = None,
) -> None:
    api = allure_api or _import_allure()
    if api is None:
        return
    api.attach(
        json.dumps(data, indent=indent, ensure_ascii=False, default=str),
        name=name,
        attachment_type=api.attachment_type.JSON,
    )


def attach_file(
    path: Path | str,
    name: str | None = None,
    *,
    attachment_type: Any | None = None,
    extension: str | None = None,
    allure_api: Any | None = None,
) -> Path:
    file_path = Path(path)
    assert file_path.exists(), f"Attachment file does not exist: {file_path}"
    assert file_path.is_file(), f"Attachment path is not a file: {file_path}"

    api = allure_api or _import_allure()
    if api is not None:
        api.attach.file(
            str(file_path),
            name=name or file_path.name,
            attachment_type=attachment_type,
            extension=extension,
        )
    return file_path


def _import_allure() -> Any | None:
    try:
        import allure
    except Exception:
        return None
    return allure
