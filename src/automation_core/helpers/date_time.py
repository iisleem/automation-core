from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo


def utc_now() -> datetime:
    return datetime.now(UTC)


def today(timezone_name: str | None = None) -> date:
    return _now(timezone_name).date()


def tomorrow(timezone_name: str | None = None) -> date:
    return add_days(today(timezone_name), 1)


def yesterday(timezone_name: str | None = None) -> date:
    return add_days(today(timezone_name), -1)


def add_days(value: date, days: int) -> date:
    return value + timedelta(days=days)


def format_date(value: date | datetime, date_format: str = "%Y-%m-%d") -> str:
    return value.strftime(date_format)


def parse_date(value: str, date_format: str = "%Y-%m-%d") -> date:
    return datetime.strptime(value, date_format).date()


def _now(timezone_name: str | None) -> datetime:
    if timezone_name:
        return datetime.now(ZoneInfo(timezone_name))
    return datetime.now()
