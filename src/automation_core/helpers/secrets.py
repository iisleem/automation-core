from __future__ import annotations

import os


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise OSError(f"Required environment variable '{name}' is not set.")
    return value


def optional_env(name: str, default: str | None = None) -> str | None:
    return os.getenv(name, default)


def validate_required_envs(names: list[str]) -> dict[str, str]:
    return {name: require_env(name) for name in names}


def mask_secret(value: str | None, visible_chars: int = 4) -> str:
    if not value:
        return ""
    if visible_chars < 0:
        raise ValueError("visible_chars must be 0 or greater")
    if visible_chars == 0:
        return "*" * len(value)
    if len(value) <= visible_chars:
        return "*" * len(value)
    return f"{'*' * (len(value) - visible_chars)}{value[-visible_chars:]}"
