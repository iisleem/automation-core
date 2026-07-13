from __future__ import annotations

import fnmatch
import json
from collections.abc import Mapping
from typing import Any

DEFAULT_SECURITY_HEADERS = {
    "x-content-type-options",
    "x-frame-options",
    "referrer-policy",
}

BROWSER_SECURITY_HEADERS = DEFAULT_SECURITY_HEADERS | {"content-security-policy"}

SENSITIVE_VALUE_PATTERNS = (
    "*password*",
    "*secret*",
    "*token*",
    "*api_key*",
    "*apikey*",
    "*authorization*",
)


def get_response_headers(response_or_headers: Any) -> dict[str, str]:
    headers = response_or_headers.headers if hasattr(response_or_headers, "headers") else response_or_headers
    return {str(key).lower(): str(value) for key, value in dict(headers).items()}


def assert_header_present(response_or_headers: Any, header_name: str) -> None:
    headers = get_response_headers(response_or_headers)
    assert header_name.lower() in headers, f"Expected response header {header_name!r} to exist."


def assert_security_headers(
    response_or_headers: Any,
    required_headers: set[str] | None = None,
) -> None:
    headers = get_response_headers(response_or_headers)
    required = {header.lower() for header in (required_headers or DEFAULT_SECURITY_HEADERS)}
    missing = sorted(required - set(headers))
    assert not missing, f"Missing expected security headers: {missing!r}"


def assert_cookie_security_flags(
    cookies: list[Mapping[str, Any]],
    cookie_names: list[str] | None = None,
    *,
    secure: bool = True,
    http_only: bool = True,
    same_site_values: tuple[str, ...] = ("Lax", "Strict", "None"),
) -> None:
    selected_cookies = [cookie for cookie in cookies if cookie_names is None or cookie.get("name") in cookie_names]
    assert selected_cookies, f"Expected cookies to validate. Requested: {cookie_names!r}"

    failures: list[str] = []
    for cookie in selected_cookies:
        name = cookie.get("name")
        if secure and not cookie.get("secure", False):
            failures.append(f"{name}: secure flag is not enabled")
        if http_only and not cookie.get("httpOnly", False):
            failures.append(f"{name}: httpOnly flag is not enabled")
        same_site = cookie.get("sameSite")
        if same_site_values and same_site not in same_site_values:
            failures.append(f"{name}: sameSite {same_site!r} not in {same_site_values!r}")

    assert not failures, "Cookie security flag failures:\n" + "\n".join(failures)


def assert_no_sensitive_values_in_text(
    text: str,
    patterns: tuple[str, ...] = SENSITIVE_VALUE_PATTERNS,
) -> None:
    matches = _sensitive_matches(text, patterns)
    assert not matches, f"Sensitive value patterns found in text: {matches!r}"


def assert_no_sensitive_values_in_json(
    payload: Any,
    patterns: tuple[str, ...] = SENSITIVE_VALUE_PATTERNS,
) -> None:
    serialized = json.dumps(payload, default=str)
    matches = _sensitive_matches(serialized, patterns)
    assert not matches, f"Sensitive value patterns found in JSON payload: {matches!r}"


def _sensitive_matches(value: str, patterns: tuple[str, ...]) -> list[str]:
    lowered_value = value.lower()
    return [pattern for pattern in patterns if fnmatch.fnmatch(lowered_value, pattern)]
