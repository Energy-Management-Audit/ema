"""Plain, source-unit readings and stable field identifiers."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

from ema.energy_data.carriers import Carrier


def _months() -> dict[int, Reading]:
    return {}


def _production() -> dict[str, dict[int, CarrierSeries]]:
    return {}


def _units() -> dict[str, str]:
    return {}


def _money() -> dict[int, Reading]:
    return {}


def _filed() -> dict[str, dict[int, FiledValue]]:
    return {}


@dataclass(frozen=True)
class Reading:
    value: float | None
    unit: str

    def __post_init__(self) -> None:
        if not self.unit or (self.value is not None and not math.isfinite(self.value)):
            raise ValueError("reading needs a unit and a finite value")


@dataclass(frozen=True)
class FiledValue:
    value: float
    unit: str
    decimals: int
    source: str

    def __post_init__(self) -> None:
        if not math.isfinite(self.value) or not self.unit or self.decimals < 0 or not self.source:
            raise ValueError("filed value needs a finite value, unit, precision, and source")


@dataclass(frozen=True)
class CarrierSeries:
    months: dict[int, Reading] = field(default_factory=_months)
    annual: Reading | None = None

    def __post_init__(self) -> None:
        if any(not 1 <= month <= 12 for month in self.months):
            raise ValueError("month must be 1..12")


@dataclass(frozen=True)
class EnergyDataset:
    years: tuple[int, ...]
    carriers: dict[Carrier, dict[int, CarrierSeries]]
    production: dict[str, dict[int, CarrierSeries]] = field(default_factory=_production)
    production_unit: dict[str, str] = field(default_factory=_units)
    turnover_lei: dict[int, Reading] = field(default_factory=_money)
    energy_costs_lei: dict[int, Reading] = field(default_factory=_money)
    filed_indicators: dict[str, dict[int, FiledValue]] = field(default_factory=_filed)
    energy_inventory_complete: bool = True

    def __post_init__(self) -> None:
        if self.years != tuple(sorted(set(self.years))):
            raise ValueError("dataset years must be unique and ascending")


Kind = Literal["carrier", "carrier_tep", "production", "turnover", "energy_costs"]


def field_key(kind: Kind, name: str | None, year: int, month: int | None = None) -> str:
    """Produce an unambiguous persisted key for a canonical field."""
    if year < 1 or (month is not None and not 1 <= month <= 12):
        raise ValueError("invalid year or month")
    if kind in {"carrier", "carrier_tep", "production"}:
        if not name or "." in name:
            raise ValueError("carrier and production keys need a dot-free name")
        if kind in {"carrier", "carrier_tep"} and name not in Carrier._value2member_map_:
            raise ValueError("unknown carrier")
        prefix = f"{kind}.{name}"
    else:
        if name is not None:
            raise ValueError("economic keys have no name")
        prefix = kind
    return f"{prefix}.{year}" + (f".{month:02d}" if month is not None else "")


@dataclass(frozen=True)
class Derived:
    value: float | None
    unit: str
    formula_id: str
    inputs: tuple[str, ...] = ()
    factor_version: str | None = None
    missing: tuple[str, ...] = ()
    input_weights: tuple[float, ...] = ()
    year: int | None = None

    def __post_init__(self) -> None:
        if self.value is not None and not math.isfinite(self.value):
            object.__setattr__(self, "value", None)
            object.__setattr__(
                self, "missing", tuple(dict.fromkeys((*self.missing, "result.non_finite")))
            )


@dataclass(frozen=True)
class Indicators:
    tep: dict[int, dict[Carrier, Derived]]
    tep_total: dict[int, Derived]
    shares: dict[int, dict[Carrier, Derived]]
    specific: dict[int, dict[str, dict[Carrier | None, Derived]]]
    intensity: dict[int, Derived]
    co2: dict[int, dict[Carrier | None, Derived]]
    changes: dict[int, Derived]
    trend: str | None
