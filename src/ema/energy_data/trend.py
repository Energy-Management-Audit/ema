"""Classify trends in the rounded values shown to the auditor."""

from __future__ import annotations

import math
from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal


def trend(values: Sequence[float], decimals: int = 2) -> str:
    """Classify the visible, rounded series by its least-squares slope."""
    if len(values) < 2:
        raise ValueError("trend needs at least two values")
    if any(not math.isfinite(value) for value in values):
        raise ValueError("trend needs finite values")
    if decimals < 0:
        raise ValueError("trend decimals must be nonnegative")
    quantum = Decimal(1).scaleb(-decimals)
    visible = [Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP) for value in values]
    length = len(visible)
    numerator = sum(
        (Decimal(2 * index - length + 1) * value for index, value in enumerate(visible)),
        Decimal(0),
    )
    if numerator == 0:
        return "constantă"
    if numerator > 0:
        return "creștere"
    return "scădere"
