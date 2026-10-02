"""Classify trends in the rounded values shown to the auditor."""

from __future__ import annotations

import math
from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal

# Fitted change over the series, as a fraction of the series mean. Her delivered audits and
# PIEEs (case codes audit-01..06, piee-01..03) label every series with a fitted change of
# 0.09% or more as creștere/scădere, and the exact-constant series as constantă; the one
# "relativ constantă" figure (audit-05, about -0.5%) lies inside that range and is treated
# as her slip. Any value below 0.09% separates the classes; 0.05% leaves margin.
CONSTANT_THRESHOLD = Decimal("0.0005")


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
    total = sum(visible, Decimal(0))
    # Fitted change / mean = 6 * numerator / ((length + 1) * total).
    if numerator == 0 or (
        total != 0 and abs(6 * numerator / ((length + 1) * total)) <= CONSTANT_THRESHOLD
    ):
        return "constantă"
    if numerator > 0:
        return "creștere"
    return "scădere"
