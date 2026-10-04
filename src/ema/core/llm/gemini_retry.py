"""Gemini retries: honour 429 delays, fail fast on a daily quota, back off on 5xx."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any, cast

from google.genai import errors

from ema.core.errors import EmaError

ATTEMPTS = 4
MAX_RETRY_DELAY_S = 60.0
SERVER_BACKOFF_S = (10.0, 20.0, 40.0)
_SECONDS = re.compile(r"^(\d+(?:\.\d+)?)s$")


def _detail_entries(exc: errors.APIError) -> list[dict[str, Any]]:
    body = cast(Any, getattr(exc, "details", None))
    if not isinstance(body, dict):
        return []
    error = cast(dict[str, Any], body).get("error", body)
    if not isinstance(error, dict):
        return []
    entries = cast(dict[str, Any], error).get("details", [])
    if not isinstance(entries, list):
        return []
    return [
        cast(dict[str, Any], entry) for entry in cast(list[Any], entries) if isinstance(entry, dict)
    ]


def _per_day(exc: errors.APIError) -> bool:
    return any(
        "PerDay" in str(violation.get("quotaId", ""))
        for entry in _detail_entries(exc)
        for violation in cast(list[dict[str, Any]], entry.get("violations", []))
    )


def _retry_delay(exc: errors.APIError) -> float | None:
    for entry in _detail_entries(exc):
        match = _SECONDS.match(str(entry.get("retryDelay", "")))
        if match:
            return min(float(match.group(1)), MAX_RETRY_DELAY_S)
    return None


def map_quota_or_credit_error(exc: errors.APIError, model: str) -> EmaError | None:
    """Map Gemini daily quota and exhausted credit errors, independent of retries."""
    if exc.code == 402 or "monthly spending cap" in str(exc.message).lower():
        return EmaError("ai_credits", "Creditul furnizorului AI s-a epuizat.", model)
    if exc.code == 429 and _per_day(exc):
        return EmaError("ai_quota_day", "Cota zilnică a furnizorului AI s-a epuizat.", model)
    return None


def call_with_retries[T](call: Callable[[], T], model: str, sleep: Callable[[float], None]) -> T:
    for attempt in range(ATTEMPTS):
        last = attempt == ATTEMPTS - 1
        try:
            return call()
        except errors.APIError as exc:
            if mapped := map_quota_or_credit_error(exc, model):
                raise mapped from exc
            if exc.code == 429:
                delay = _retry_delay(exc)
                if delay is None or last:
                    raise
                sleep(delay)
            elif exc.code in {500, 503}:
                if last:
                    raise EmaError(
                        "ai_unavailable", "Furnizorul AI nu răspunde acum.", model
                    ) from exc
                sleep(SERVER_BACKOFF_S[attempt])
            else:
                raise
    raise AssertionError("unreachable")
