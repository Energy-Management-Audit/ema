"""Matching values to whole words and numbers in research quotes."""

from __future__ import annotations

import re

_SPACE, _THOUSANDS = "[ \u00a0\u202f]", r"\d{3}(?!\d)"


def _extends(before: str, value: str, after: str) -> bool:
    """Whether the text around the value makes it part of a longer word or number."""
    first, last = value[0], value[-1]
    return bool(
        (first.isalnum() and before[-1:].isalnum())
        or (last.isalnum() and after[:1].isalnum())
        or (first.isdigit() and re.search(r"\d[.,]$", before))
        or (first.isdigit() and re.search(rf"\d{_SPACE}$", before) and re.match(_THOUSANDS, value))
        or (last.isdigit() and re.match(r"[.,]\d", after))
        or (last.isdigit() and re.match(_SPACE + _THOUSANDS, after))
    )


def in_quote(value: str, quote: str) -> bool:
    """Whether the value appears in the quote as whole words and numbers, never inside one."""
    start = quote.find(value) if value else -1
    while start >= 0:
        if not _extends(quote[:start], value, quote[start + len(value) :]):
            return True
        start = quote.find(value, start + 1)
    return False
