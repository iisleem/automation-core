from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import yaml

ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


class ConfigReader:
    """Read framework-style config files without binding to a framework domain."""

    def __init__(
        self,
        project_root: Path | str | None = None,
        *,
        config_dir: Path | str = "config",
        expand_env: bool = True,
    ) -> None:
        self.project_root = Path(project_root or Path.cwd()).resolve()
        self.config_dir = resolve_path(config_dir, self.project_root)
        self.expand_env = expand_env

    def read_settings(self) -> dict[str, Any]:
        return self.read_yaml(self.config_dir / "settings.yaml")

    def read_environments(self) -> dict[str, Any]:
        return self.read_yaml(self.config_dir / "environments.yaml")

    def read_yaml(self, path: Path | str, *, require_mapping: bool = True) -> Any:
        data = load_yaml(path, base_dir=self.project_root, expand_env=self.expand_env)
        if require_mapping and not isinstance(data, dict):
            raise ValueError(f"Expected YAML object in {path}")
        return data

    def read_json(self, path: Path | str) -> Any:
        data = load_json(path, base_dir=self.project_root)
        return expand_env(data) if self.expand_env else data

    def get_environment_config(self, env_name: str) -> dict[str, Any]:
        environments = self.read_environments()
        if env_name not in environments:
            available = ", ".join(sorted(environments))
            raise ValueError(f"Unknown environment '{env_name}'. Available: {available}")
        environment = environments[env_name]
        if not isinstance(environment, dict):
            raise ValueError(f"Expected environment '{env_name}' to be a mapping")
        return environment

    def load(
        self,
        env_name: str,
        *,
        environment_key: str | None = "env",
        environment_config_key: str | None = None,
        merge_environment: bool = True,
    ) -> dict[str, Any]:
        settings = self.read_settings()
        environment = self.get_environment_config(env_name)
        loaded = dict(settings)
        if merge_environment:
            loaded.update(environment)
        if environment_key:
            loaded[environment_key] = env_name
        if environment_config_key:
            loaded[environment_config_key] = environment
        return loaded


def resolve_path(path: str | Path, base_dir: str | Path | None = None) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return Path(base_dir or Path.cwd()).resolve() / candidate


def expand_env_value(value: str) -> str:
    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        fallback = match.group(2)
        return os.getenv(name, fallback if fallback is not None else "")

    return ENV_PATTERN.sub(replace, value)


def expand_env(data: Any) -> Any:
    if isinstance(data, dict):
        return {key: expand_env(value) for key, value in data.items()}
    if isinstance(data, list):
        return [expand_env(item) for item in data]
    if isinstance(data, str):
        return expand_env_value(data)
    return data


def load_yaml(
    path: str | Path,
    *,
    base_dir: str | Path | None = None,
    expand_env: bool = True,
) -> Any:
    resolved = resolve_path(path, base_dir)
    with resolved.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
    return globals()["expand_env"](data) if expand_env else data


def load_json(
    path: str | Path,
    *,
    base_dir: str | Path | None = None,
) -> Any:
    with resolve_path(path, base_dir).open("r", encoding="utf-8") as file:
        return json.load(file)


def load_settings(project_root: str | Path | None = None) -> dict[str, Any]:
    return ConfigReader(project_root).read_settings()


def load_environments(project_root: str | Path | None = None) -> dict[str, Any]:
    return ConfigReader(project_root).read_environments()


def deep_get(data: dict[str, Any], dotted_path: str, default: Any = None) -> Any:
    current: Any = data
    for part in dotted_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current
