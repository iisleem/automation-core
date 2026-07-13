from __future__ import annotations

from automation_core.helpers.cleanup import CleanupAction, CleanupRegistry, CleanupResult, assert_cleanup_success
from automation_core.helpers.data import (
    random_email,
    random_phone,
    random_string,
    random_username,
    timestamped_value,
    unique_id,
)
from automation_core.helpers.date_time import add_days, format_date, parse_date, today, tomorrow, utc_now, yesterday
from automation_core.helpers.files import (
    assert_file_exists,
    assert_file_extension,
    cleanup_directory,
    latest_file,
    wait_for_file,
)
from automation_core.helpers.retry import retry, retry_action
from automation_core.helpers.secrets import mask_secret, optional_env, require_env, validate_required_envs
from automation_core.helpers.soft_assertions import SoftAssert, SoftAssertionFailure, soft_assert
from automation_core.helpers.text import extract_first_match, extract_numbers, extract_otp, normalize_text
from automation_core.helpers.urls import build_url, get_query_param, parse_query_params, remove_query_param
from automation_core.helpers.wait import poll_until, wait_until

__all__ = [
    "CleanupAction",
    "CleanupRegistry",
    "CleanupResult",
    "SoftAssert",
    "SoftAssertionFailure",
    "add_days",
    "assert_cleanup_success",
    "assert_file_exists",
    "assert_file_extension",
    "build_url",
    "cleanup_directory",
    "extract_first_match",
    "extract_numbers",
    "extract_otp",
    "format_date",
    "get_query_param",
    "latest_file",
    "mask_secret",
    "normalize_text",
    "optional_env",
    "parse_date",
    "parse_query_params",
    "poll_until",
    "random_email",
    "random_phone",
    "random_string",
    "random_username",
    "remove_query_param",
    "require_env",
    "retry",
    "retry_action",
    "soft_assert",
    "timestamped_value",
    "today",
    "tomorrow",
    "unique_id",
    "utc_now",
    "validate_required_envs",
    "wait_for_file",
    "wait_until",
    "yesterday",
]
