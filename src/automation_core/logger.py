from __future__ import annotations

import logging
from pathlib import Path
from typing import TextIO


def get_logger(
    name: str = "automation-core",
    *,
    level: int | str = logging.INFO,
    log_file: str | Path | None = None,
    log_dir: str | Path | None = None,
    file_name: str = "framework.log",
    stream: TextIO | None = None,
    propagate: bool = False,
    reset: bool = False,
) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = propagate
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")

    if reset:
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()

    if not logger.handlers:
        stream_handler = logging.StreamHandler(stream)
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

    file_path = _resolve_log_file(log_file, log_dir, file_name)
    if file_path and not _has_file_handler(logger, file_path):
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(file_path, mode="a", encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def _resolve_log_file(
    log_file: str | Path | None,
    log_dir: str | Path | None,
    file_name: str,
) -> Path | None:
    if log_file:
        return Path(log_file)
    if log_dir:
        return Path(log_dir) / file_name
    return None


def _has_file_handler(logger: logging.Logger, file_path: Path) -> bool:
    resolved = file_path.resolve()
    for handler in logger.handlers:
        if isinstance(handler, logging.FileHandler) and Path(handler.baseFilename).resolve() == resolved:
            return True
    return False
