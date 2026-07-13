from __future__ import annotations

import json
import logging

from automation_core.config import ConfigReader, deep_get, expand_env_value, load_json, load_yaml, resolve_path
from automation_core.logger import get_logger


def test_config_reader_loads_settings_environments_and_expands_env(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "settings.yaml").write_text(
        """
framework:
  default_env: dev
timeout: ${TIMEOUT:-30}
""",
        encoding="utf-8",
    )
    (config_dir / "environments.yaml").write_text(
        """
dev:
  base_url: ${BASE_URL:-https://example.test}
  retries: 2
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("BASE_URL", "https://local.test")

    loaded = ConfigReader(tmp_path).load("dev")

    assert loaded["env"] == "dev"
    assert loaded["base_url"] == "https://local.test"
    assert loaded["timeout"] == "30"


def test_config_reader_can_match_mobile_environment_shape(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "settings.yaml").write_text("execution:\n  default_profile: android\n", encoding="utf-8")
    (config_dir / "environments.yaml").write_text("local:\n  appium: true\n", encoding="utf-8")

    loaded = ConfigReader(tmp_path).load(
        "local",
        environment_key="environment",
        environment_config_key="environment_config",
        merge_environment=False,
    )

    assert loaded == {
        "execution": {"default_profile": "android"},
        "environment": "local",
        "environment_config": {"appium": True},
    }


def test_load_helpers_and_deep_get(tmp_path):
    yaml_path = tmp_path / "settings.yaml"
    json_path = tmp_path / "data.json"
    yaml_path.write_text("root:\n  child: value\n", encoding="utf-8")
    json_path.write_text(json.dumps({"items": [1, 2]}), encoding="utf-8")

    assert resolve_path("settings.yaml", tmp_path) == yaml_path
    assert load_yaml("settings.yaml", base_dir=tmp_path)["root"]["child"] == "value"
    assert load_json(json_path)["items"] == [1, 2]
    assert deep_get({"a": {"b": 3}}, "a.b") == 3
    assert deep_get({"a": {}}, "a.missing", default="x") == "x"
    assert expand_env_value("${MISSING_VAR:-fallback}") == "fallback"


def test_get_logger_supports_file_logging(tmp_path):
    logger_name = "automation-core-test-logger"
    log_path = tmp_path / "logs" / "framework.log"

    logger = get_logger(logger_name, log_file=log_path, level=logging.DEBUG, reset=True)
    logger.info("hello")

    assert log_path.exists()
    assert "hello" in log_path.read_text(encoding="utf-8")


def test_get_logger_adds_missing_file_handler_without_duplicates(tmp_path):
    logger_name = "automation-core-test-logger-reconfigure"
    log_path = tmp_path / "logs" / "framework.log"

    logger = get_logger(logger_name, reset=True)
    initial_handler_count = len(logger.handlers)

    logger = get_logger(logger_name, log_file=log_path)
    logger = get_logger(logger_name, log_file=log_path)
    logger.info("written once")

    file_handlers = [
        handler
        for handler in logger.handlers
        if isinstance(handler, logging.FileHandler) and handler.baseFilename == str(log_path)
    ]
    assert len(logger.handlers) == initial_handler_count + 1
    assert len(file_handlers) == 1
    assert "written once" in log_path.read_text(encoding="utf-8")


def test_get_logger_reset_replaces_handlers(tmp_path):
    logger_name = "automation-core-test-logger-reset"
    first_log = tmp_path / "first.log"
    second_log = tmp_path / "second.log"

    logger = get_logger(logger_name, log_file=first_log, reset=True)
    logger = get_logger(logger_name, log_file=second_log, reset=True)
    logger.info("after reset")

    file_handlers = [handler for handler in logger.handlers if isinstance(handler, logging.FileHandler)]
    assert len(file_handlers) == 1
    assert file_handlers[0].baseFilename == str(second_log)
    assert "after reset" in second_log.read_text(encoding="utf-8")
