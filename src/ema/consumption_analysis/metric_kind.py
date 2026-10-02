"""Kinds of metric resolved from the energy dataset."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from ema.energy_data.carriers import Carrier

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


@dataclass(frozen=True)
class Metric:
    kind: MetricKind
    carriers: tuple[Carrier, ...] = ()
    product: str | None = None
    month: int | None = None
    decimals: int | None = None
    grouping: bool | None = None
