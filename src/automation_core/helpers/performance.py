from __future__ import annotations

from typing import Any


def get_elapsed_ms(response: Any) -> float:
    try:
        return response.elapsed.total_seconds() * 1000
    except RuntimeError as exc:
        raise AssertionError("Response elapsed time is unavailable on this response object") from exc


def assert_response_time_under(response: Any, max_ms: float) -> float:
    elapsed_ms = get_elapsed_ms(response)
    assert elapsed_ms <= max_ms, f"Expected response time <= {max_ms} ms, got {elapsed_ms:.2f} ms"
    return elapsed_ms


def summarize_response_timings(responses: list[Any]) -> dict[str, float]:
    timings = [get_elapsed_ms(response) for response in responses]
    if not timings:
        return {"count": 0, "min_ms": 0, "max_ms": 0, "avg_ms": 0}
    return {
        "count": len(timings),
        "min_ms": min(timings),
        "max_ms": max(timings),
        "avg_ms": round(sum(timings) / len(timings), 2),
    }
