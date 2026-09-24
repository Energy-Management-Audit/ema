"""Kinds of metric resolved from the energy dataset."""

from typing import Literal

MetricKind = Literal[
    "production",
    "carrier",
    "tep",
    "tep_monthly_sum",
    "tep_total",
    "specific",
    "water_specific",
    "intensity",
    "co2",
    "filed",
]
