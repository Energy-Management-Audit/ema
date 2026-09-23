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

    def __post_init__(self) -> None:
        if not self.version or self.valid_from_year < 1:
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
        if year < self.valid_from_year:
            return None
        return self._find(self.tep, carrier, unit, year)

    def co2_factor(self, carrier: Carrier, unit: str, year: int) -> Factor | None:
        if year < self.valid_from_year:
            return None
        return self._find(self.co2, carrier, unit, year)


_PRIMARY = "the auditor: Principali factori de conversie"
_EUROSTAT = "the auditor: Factori de conversie in MWh (Eurostat, kgep/kg)"
_IMPACT = "the auditor: impact de mediu"
FACTORS_2026 = FactorTable(
    version="2026",
    valid_from_year=2026,
    tep=(
        Factor(Carrier.electricity_grid, "MWh", 0.086, _PRIMARY),
        Factor(Carrier.electricity_grid, "kWh", 0.000086, _PRIMARY),
        Factor(Carrier.electricity_pv, "MWh", 0.086, _PRIMARY),
        Factor(Carrier.natural_gas, "MWh", 0.086, "the auditor: Consum Gaz"),
        Factor(Carrier.natural_gas, "Nm3", 0.000805, _PRIMARY),
        Factor(Carrier.diesel, "t", 1.015, _PRIMARY),
        Factor(Carrier.petrol, "t", 1.05, _PRIMARY),
        Factor(Carrier.fuel_oil, "t", 0.955, _EUROSTAT),
        Factor(Carrier.coke, "t", 0.676, _EUROSTAT),
        Factor(Carrier.lpg, "t", 1.099, "the auditor: Consum Carburanti (CLIENT-P2)"),
        Factor(Carrier.ctl, "t", 0.95, "the auditor: Consum Carburanti (CLIENT-A3)"),
        Factor(Carrier.sunflower_husks, "Gcal", 0.1, "the auditor: Consum Coji floarea soarelui"),
        Factor(Carrier.purchased_heat, "Gcal", 0.1, _PRIMARY),
    ),
    co2=(
        Factor(Carrier.electricity_grid, "MWh", 0.226, _IMPACT),
        Factor(Carrier.natural_gas, "MWh", 0.1787, _IMPACT),
        Factor(Carrier.diesel, "t", 3.259, _IMPACT),
        Factor(Carrier.petrol, "t", 3.068, _IMPACT),
        Factor(Carrier.lpg, "t", 2.776, "the auditor: impact de mediu (CLIENT-P2)"),
        Factor(
            Carrier.purchased_heat, "MWh", 0.22111111111111112, "the auditor: impact de mediu (CLIENT-A3)"
        ),
    ),
)
