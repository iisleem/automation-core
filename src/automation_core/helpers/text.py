from __future__ import annotations

import re

DEFAULT_OTP_REGEX = r"\b\d{4,8}\b"


def normalize_text(value: str) -> str:
    return " ".join(value.split())


def extract_first_match(
    text: str,
    regex: str,
    flags: int = 0,
) -> str | None:
    match = re.search(regex, text, flags)
    if not match:
        return None
    if match.groups():
        return match.group(1)
    return match.group(0)


def extract_otp(
    text: str,
    regex: str = DEFAULT_OTP_REGEX,
) -> str | None:
    return extract_first_match(text, regex)


def extract_numbers(text: str, *, allow_decimal: bool = False) -> list[str]:
    pattern = r"\d+(?:\.\d+)?" if allow_decimal else r"\d+"
    return re.findall(pattern, text)
