"""Number presentation used by the approved PIEE table prototype."""

from __future__ import annotations

from ema.core.office.numbers_ro import format_number


def prototype_number(value: float | int, decimals: int, *, grouping: bool = True) -> str:
    return format_number(value, decimals, grouping=grouping)
