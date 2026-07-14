from __future__ import annotations

import re
import string
from datetime import timedelta

import pytest

from automation_core.helpers.cleanup import CleanupRegistry, assert_cleanup_success
from automation_core.helpers.data import (
    random_email,
    random_phone,
    random_string,
    random_username,
    timestamped_value,
    unique_id,
)
from automation_core.helpers.date_time import add_days, format_date, parse_date, today
from automation_core.helpers.files import assert_file_extension, cleanup_directory, latest_file, wait_for_file
from automation_core.helpers.performance import assert_response_time_under, summarize_response_timings
from automation_core.helpers.retry import retry, retry_action
from automation_core.helpers.secrets import mask_secret, optional_env, require_env, validate_required_envs
from automation_core.helpers.security import (
    BROWSER_SECURITY_HEADERS,
    assert_cookie_security_flags,
    assert_header_present,
    assert_no_sensitive_values_in_json,
    assert_no_sensitive_values_in_text,
    assert_security_headers,
    get_response_headers,
)
from automation_core.helpers.soft_assertions import SoftAssert, soft_assert
from automation_core.helpers.structured_files import (
    assert_csv_headers,
    assert_csv_row_count,
    assert_json_file_field,
    read_csv_file,
)
from automation_core.helpers.text import extract_first_match, extract_numbers, extract_otp, normalize_text
from automation_core.helpers.urls import build_url, get_query_param, parse_query_params, remove_query_param
from automation_core.helpers.wait import poll_until, wait_until


def test_wait_poll_and_retry_helpers():
    attempts = {"count": 0}

    def action():
        attempts["count"] += 1
        if attempts["count"] < 2:
            raise ValueError("not yet")
        return "ready"

    assert retry_action(action, attempts=2) == "ready"
    assert wait_until(lambda: "done", timeout_seconds=0.1, interval_seconds=0.01) == "done"
    assert poll_until(lambda: 3, lambda value: value == 3, timeout_seconds=0.1, interval_seconds=0.01) == 3


def test_wait_until_can_ignore_transient_exceptions():
    attempts = {"count": 0}

    def condition():
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise RuntimeError("not ready")
        return "ready"

    assert wait_until(condition, timeout_seconds=0.2, interval_seconds=0.01, ignore_exceptions=True) == "ready"

    with pytest.raises(RuntimeError, match="not ready"):
        wait_until(lambda: (_ for _ in ()).throw(RuntimeError("not ready")), timeout_seconds=0.1)

    with pytest.raises(TimeoutError, match="Last error: RuntimeError: still not ready"):
        wait_until(
            lambda: (_ for _ in ()).throw(RuntimeError("still not ready")),
            timeout_seconds=0.02,
            interval_seconds=0.01,
            ignore_exceptions=True,
        )


def test_retry_decorator_retries_function():
    calls = {"count": 0}

    @retry(attempts=2)
    def flaky():
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("first")
        return "ok"

    assert flaky() == "ok"


def test_data_text_url_and_date_helpers():
    assert re.fullmatch(r"case-[0-9a-f]{10}", unique_id("case"))
    assert re.fullmatch(r"[0-9a-f]{6}", unique_id("", length=6))
    with pytest.raises(ValueError, match="length"):
        unique_id(length=0)
    assert re.fullmatch(r"run-\d{20}", timestamped_value("run"))
    assert re.fullmatch(r"run-\d{14}", timestamped_value("run", include_microseconds=False))
    assert re.fullmatch(r"\d{8}", timestamped_value("", timestamp_format="%Y%m%d"))
    assert random_string(5, string.ascii_lowercase).islower()
    assert "@example.test" in random_email()
    assert random_username("qa").startswith("qa_")
    assert random_phone("+962", 7).startswith("+962")
    assert normalize_text(" a\n  b ") == "a b"
    assert extract_first_match("id=123", r"id=(\d+)") == "123"
    assert extract_otp("code 123456") == "123456"
    assert extract_numbers("a1 b22 c12.5") == ["1", "22", "12", "5"]
    assert extract_numbers("a1 b22 c12.5", allow_decimal=True) == ["1", "22", "12.5"]
    url = build_url("https://example.test/", "search", {"q": "qa", "tag": ["a", "b"]})
    assert get_query_param(url, "q") == "qa"
    assert parse_query_params(url)["tag"] == ["a", "b"]
    assert "q=" not in remove_query_param(url, "q")
    parsed = parse_date("2026-07-13")
    assert format_date(add_days(parsed, 1)) == "2026-07-14"
    assert today().__class__.__name__ == "date"


def test_file_and_structured_file_helpers(tmp_path):
    report = tmp_path / "report.csv"
    report.write_text("id,name\n1,qa\n", encoding="utf-8")
    payload = tmp_path / "payload.json"
    payload.write_text('{"user": {"name": "qa"}, "items": [{"id": 1}]}', encoding="utf-8")

    assert wait_for_file(tmp_path, "*.csv", timeout_seconds=0.1, interval_seconds=0.01) == report
    assert latest_file(tmp_path, "*.csv") == report
    assert_file_extension(report, "csv")
    assert read_csv_file(report) == [{"id": "1", "name": "qa"}]
    assert_csv_headers(report, ["id", "name"])
    assert_csv_row_count(report, 1)
    assert_json_file_field(payload, "items.0.id", 1)

    assert cleanup_directory(tmp_path / "nested") == tmp_path / "nested"
    assert (tmp_path / "nested").is_dir()
    removed = cleanup_directory(tmp_path / "nested", recreate=False)
    assert removed == tmp_path / "nested"
    assert not removed.exists()


def test_soft_assertions_support_object_and_context_manager():
    assertions = SoftAssert()
    assertions.assert_equal("actual", "expected", "Name mismatch")
    assertions.check(False, "Boolean mismatch")
    assertions.check("Callable mismatch", lambda: (_ for _ in ()).throw(AssertionError("boom")))

    assert assertions.has_failures
    with pytest.raises(AssertionError, match="Soft assertion failures"):
        assertions.assert_all()

    with soft_assert() as softly:
        softly.equals("mobile", "mobile")
        softly.contains(["native"], "native")


def test_secret_helpers(monkeypatch):
    monkeypatch.setenv("TOKEN", "abcdef")

    assert require_env("TOKEN") == "abcdef"
    assert optional_env("MISSING", "default") == "default"
    assert validate_required_envs(["TOKEN"]) == {"TOKEN": "abcdef"}
    assert mask_secret("abcdef", visible_chars=2) == "****ef"
    with pytest.raises(OSError):
        require_env("MISSING")


def test_cleanup_registry_collects_failures():
    calls: list[str] = []
    registry = CleanupRegistry()
    registry.add("first", calls.append, "first")
    registry.add("bad", lambda: (_ for _ in ()).throw(RuntimeError("nope")))

    results = registry.run_all(continue_on_error=True)

    assert calls == ["first"]
    with pytest.raises(AssertionError, match="Cleanup actions failed"):
        assert_cleanup_success(results)


def test_security_and_performance_helpers():
    class Response:
        headers = {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer",
            "Content-Security-Policy": "default-src 'self'",
        }
        elapsed = timedelta(milliseconds=25)

    headers = get_response_headers(Response())
    assert headers["x-frame-options"] == "DENY"
    assert_header_present(Response(), "x-frame-options")
    assert_security_headers(Response())
    assert_security_headers(Response(), BROWSER_SECURITY_HEADERS)
    assert_cookie_security_flags([{"name": "session", "secure": True, "httpOnly": True, "sameSite": "Lax"}])
    assert_no_sensitive_values_in_text("normal content")
    assert_no_sensitive_values_in_json({"message": "ok"})
    assert assert_response_time_under(Response(), 100) == 25
    assert summarize_response_timings([Response()])["avg_ms"] == 25

    with pytest.raises(AssertionError, match="Sensitive value patterns"):
        assert_no_sensitive_values_in_text("api_token=abc")
