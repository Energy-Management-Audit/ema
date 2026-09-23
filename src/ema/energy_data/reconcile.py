"""Rounding intervals for filed additive totals and exact-factor products."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from ema.energy_data.model import Derived


@dataclass(frozen=True)
class Reconciliation:
    status: Literal["match", "conflict"]
    difference: float
    margin: float


def reconcile(
    filed: float, filed_decimals: int, recomputed: Derived, input_decimals: Sequence[int]
) -> Reconciliation:
    """Compare rounded filing with the worst-case propagated input half-units.

    An exact factor's scale is carried by Derived.input_weights. Ratios do not
    have an additive rounding interval and are deliberately rejected here.
    """
    if any(word in recomputed.formula_id for word in ("specific", "intensity", "share", "change")):
        raise ValueError("ratio reconciliation needs a separate uncertainty contract")
    if recomputed.value is None or not math.isfinite(filed) or not math.isfinite(recomputed.value):
        raise ValueError("reconcile needs finite filed and recomputed values")
    if filed_decimals < 0 or any(decimals < 0 for decimals in input_decimals):
        raise ValueError("decimal counts must be nonnegative")
    if len(input_decimals) != len(recomputed.inputs):
        raise ValueError("one decimal count is needed per input")
    weights = recomputed.input_weights or (1.0,) * len(input_decimals)
    if len(weights) != len(input_decimals):
        raise ValueError("one weight is needed per input")
    margin = 0.5 * 10**-filed_decimals + sum(
        abs(weight) * 0.5 * 10**-decimals
        for weight, decimals in zip(weights, input_decimals, strict=True)
    )
    difference = abs(filed - recomputed.value)
    return Reconciliation("match" if difference <= margin else "conflict", difference, margin)
