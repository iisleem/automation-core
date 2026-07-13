from __future__ import annotations

import random
import string
import uuid
from datetime import UTC, datetime


def unique_id(prefix: str = "auto") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def timestamped_value(prefix: str = "auto") -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S%f")
    return f"{prefix}-{timestamp}"


def random_string(length: int = 8, alphabet: str = string.ascii_lowercase) -> str:
    if length < 1:
        raise ValueError("length must be at least 1")
    if not alphabet:
        raise ValueError("alphabet must not be empty")
    return "".join(random.choices(alphabet, k=length))


def random_email(domain: str = "example.test", prefix: str = "automation") -> str:
    return f"{prefix}.{uuid.uuid4().hex[:10]}@{domain}"


def random_username(prefix: str = "user", length: int = 8) -> str:
    suffix = random_string(length, string.ascii_lowercase + string.digits)
    return f"{prefix}_{suffix}"


def random_phone(country_code: str = "+1", digits: int = 10) -> str:
    if digits < 1:
        raise ValueError("digits must be at least 1")
    number = "".join(random.choices(string.digits, k=digits))
    return f"{country_code}{number}"
