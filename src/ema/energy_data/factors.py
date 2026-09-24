"""Explicit, sourced factors; absence is never filled by an implicit conversion."""

from __future__ import annotations

import math
from dataclasses import dataclass

from ema.energy_data.carriers import Carrier


@dataclass(frozen=True)
class Factor:
    carrier: Carrier
    unit: str
    per_unit: float
    source: str
    year: int | None = None

    def __post_init__(self) -> None:
        if (
            not self.unit
            or not self.source
            or not math.isfinite(self.per_unit)
            or self.per_unit < 0
            or (self.year is not None and self.year < 1)
        ):
            raise ValueError("factor needs a unit, source, and nonnegative value")


@dataclass(frozen=True)
class FactorTable:
    version: str
    valid_from_year: int
    tep: tuple[Factor, ...]
    co2: tuple[Factor, ...]
    valid_to_year: int | None = None

    def __post_init__(self) -> None:
        if (
            not self.version
            or self.valid_from_year < 1
            or (self.valid_to_year is not None and self.valid_to_year < self.valid_from_year)
        ):
            raise ValueError("factor table needs a version and valid year")
        for group in (self.tep, self.co2):
            keys = [(factor.carrier, factor.unit, factor.year) for factor in group]
            if len(keys) != len(set(keys)):
                raise ValueError("duplicate factor for carrier, unit, and year")

    @staticmethod
    def _find(group: tuple[Factor, ...], carrier: Carrier, unit: str, year: int) -> Factor | None:
        exact = next(
            (f for f in group if f.carrier == carrier and f.unit == unit and f.year == year),
            None,
        )
        return exact or next(
            (f for f in group if f.carrier == carrier and f.unit == unit and f.year is None),
            None,
        )

    def tep_factor(self, carrier: Carrier, unit: str, year: int) -> Factor | None:
        if year < self.valid_from_year or (
            self.valid_to_year is not None and year > self.valid_to_year
        ):
            return None
        return self._find(self.tep, carrier, unit, year)

    def co2_factor(self, carrier: Carrier, unit: str, year: int) -> Factor | None:
        if year < self.valid_from_year or (
            self.valid_to_year is not None and year > self.valid_to_year
        ):
            return None
        return self._find(self.co2, carrier, unit, year)


_PLAN_2026 = "docs/PLAN.md §5.10: 2026 document factors for 2023-2025 data"
FACTORS_2026 = FactorTable(
    version="2026",
    valid_from_year=2023,
    tep=(
        Factor(Carrier.electricity_grid, "MWh", 0.086, _PLAN_2026),
        Factor(Carrier.electricity_grid, "kWh", 0.000086, _PLAN_2026),
        Factor(Carrier.electricity_pv, "MWh", 0.086, _PLAN_2026),
        Factor(Carrier.natural_gas, "MWh", 0.086, _PLAN_2026),
        Factor(Carrier.diesel, "t", 1.015, _PLAN_2026),
        Factor(Carrier.petrol, "t", 1.05, _PLAN_2026),
    ),
    co2=(
        Factor(Carrier.electricity_grid, "MWh", 0.226, _PLAN_2026),
        Factor(Carrier.natural_gas, "MWh", 0.1787, _PLAN_2026),
        Factor(Carrier.diesel, "t", 3.259, _PLAN_2026),
        Factor(Carrier.petrol, "t", 3.068, _PLAN_2026),
    ),
    valid_to_year=2025,
)
