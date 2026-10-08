"""Official unit prices and the cost a stated consumption implies.

Prices come only from the bundled table, which `scripts/refresh_prices.py` builds from Eurostat,
the European Commission's Weekly Oil Bulletin and the BNR exchange rate. Nothing estimates a price.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import date
from functools import cache
from pathlib import Path
from typing import Any, Literal

from ema.core.office.numbers_ro import format_number
from ema.core.resources import resource_path
from ema.energy_data.calc import annual
from ema.energy_data.carriers import Carrier, counts_in_total
from ema.energy_data.factors import DIESEL_KG_PER_L, PETROL_KG_PER_L
from ema.energy_data.model import EnergyDataset, Reading

# A declared cost further than this from quantity × price is replaced by the expected cost.
TOLERANCE = 0.25
GJ_PER_MWH = 3.6
# EN 589 allows 0,50–0,58 kg/l for automotive LPG; the footnote states the value used.
LPG_KG_PER_L = 0.54
KG_PER_LITRE: dict[Carrier, float] = {
    Carrier.diesel: DIESEL_KG_PER_L,
    Carrier.petrol: PETROL_KG_PER_L,
    Carrier.lpg: LPG_KG_PER_L,
}
# Legea 141/2025 raised the standard VAT rate from 19 % to 21 % on this day.
VAT_RISE = date(2025, 8, 1)

# Eurostat consumption bands: (code, lower bound inclusive, upper bound exclusive).
ELECTRICITY_BANDS_MWH: tuple[tuple[str, float, float], ...] = (
    ("IA", 0, 20),
    ("IB", 20, 500),
    ("IC", 500, 2_000),
    ("ID", 2_000, 20_000),
    ("IE", 20_000, 70_000),
    ("IF", 70_000, 150_000),
    ("IG", 150_000, math.inf),
)
GAS_BANDS_GJ: tuple[tuple[str, float, float], ...] = (
    ("I1", 0, 1_000),
    ("I2", 1_000, 10_000),
    ("I3", 10_000, 100_000),
    ("I4", 100_000, 1_000_000),
    ("I5", 1_000_000, 4_000_000),
    ("I6", 4_000_000, math.inf),
)


@dataclass(frozen=True)
class PriceRow:
    carrier: Carrier
    year: int
    band: str | None
    value: float
    unit: str
    note: str
    vat_basis: str
    source_name: str
    source_url: str
    retrieved: str

    def __post_init__(self) -> None:
        texts = (self.unit, self.note, self.vat_basis, self.source_name, self.source_url)
        if not math.isfinite(self.value) or self.value <= 0 or not all(texts) or not self.retrieved:
            raise ValueError(f"price row needs a positive value and its source: {self}")


def vat_rate(day: date) -> float:
    return 0.21 if day >= VAT_RISE else 0.19


def net_of_vat(price: float, day: date) -> float:
    return price / (1 + vat_rate(day))


def per_tonne(price_per_litre: float, carrier: Carrier) -> float:
    """A price per litre as a price per tonne, through the carrier's stated density."""
    return price_per_litre / KG_PER_LITRE[carrier] * 1000


def band(carrier: Carrier, annual_mwh: float) -> str | None:
    """The Eurostat band of a year's consumption; electricity by MWh, gas by GJ."""
    if carrier == Carrier.electricity_grid:
        bands, amount = ELECTRICITY_BANDS_MWH, annual_mwh
    elif carrier == Carrier.natural_gas:
        # Rounded so a band boundary stated in GJ is not missed by float noise from × 3,6.
        bands, amount = GAS_BANDS_GJ, round(annual_mwh * GJ_PER_MWH, 6)
    else:
        return None
    return next(code for code, low, high in bands if low <= amount < high)


def _row(raw: Mapping[str, Any]) -> PriceRow:
    return PriceRow(
        carrier=Carrier(raw["carrier"]),
        year=int(raw["year"]),
        band=raw["band"],
        value=float(raw["value"]),
        unit=str(raw["unit"]),
        note=str(raw["note"]),
        vat_basis=str(raw["vat_basis"]),
        source_name=str(raw["source_name"]),
        source_url=str(raw["source_url"]),
        retrieved=str(raw["retrieved"]),
    )


def read_prices(path: Path) -> tuple[PriceRow, ...]:
    return tuple(_row(raw) for raw in json.loads(path.read_text(encoding="utf-8"))["rows"])


@cache
def bundled_prices() -> tuple[PriceRow, ...]:
    return read_prices(resource_path("prices", "energy_prices_ro.json"))


def price(
    rows: Iterable[PriceRow], carrier: Carrier, year: int, unit: str, quantity: float
) -> PriceRow | None:
    """The table's price for the carrier, year and unit; electricity and gas by their band."""
    wanted = band(carrier, quantity) if unit == "MWh" else None
    return next(
        (
            row
            for row in rows
            if row.carrier == carrier
            and row.year == year
            and row.unit == unit
            and row.band == wanted
        ),
        None,
    )


@dataclass(frozen=True)
class CostSettlement:
    carrier: Carrier
    year: int
    quantity: float
    unit: str
    declared: float | None
    expected: float | None
    row: PriceRow | None
    status: Literal["declared", "inferred", "unpriced"]

    @property
    def cost(self) -> float | None:
        return self.expected if self.status == "inferred" else self.declared

    @property
    def source(self) -> str | None:
        return f"{self.row.source_name}, {self.row.year}" if self.row else None

    @property
    def footnote(self) -> str | None:
        if self.status != "inferred" or self.row is None:
            return None
        return (
            f"Cost estimat: {format_number(self.quantity, 2)} {self.unit} × "
            f"{format_number(self.row.value, 2)} lei/{self.unit} "
            f"({self.row.source_name}, {self.row.year}, {self.row.note})."
        )


def settle_cost(
    rows: Iterable[PriceRow],
    carrier: Carrier,
    year: int,
    quantity: float,
    unit: str,
    declared: float | None,
) -> CostSettlement:
    """The cost of a year with a positive quantity: the declared one, or quantity × price when
    the declaration is missing or further than TOLERANCE from it."""
    row = price(rows, carrier, year, unit, quantity)
    if row is None:
        return CostSettlement(carrier, year, quantity, unit, declared, None, None, "unpriced")
    expected = quantity * row.value
    keeps = declared is not None and abs(declared - expected) <= TOLERANCE * expected
    status = "declared" if keeps else "inferred"
    return CostSettlement(carrier, year, quantity, unit, declared, expected, row, status)


def inferred_energy_costs(
    dataset: EnergyDataset, rows: Iterable[PriceRow]
) -> tuple[EnergyDataset, dict[int, tuple[str, ...]]]:
    """The yearly energy cost total, replaced by Σ quantity × price when every counted carrier
    with a positive quantity is priced and the declared total is missing or off by > TOLERANCE.

    Returns the dataset and the footnotes of each replaced year."""
    rows = tuple(rows)
    costs = dict(dataset.energy_costs_lei)
    notes: dict[int, tuple[str, ...]] = {}
    for year in dataset.years:
        settled: list[CostSettlement] = []
        for carrier, years in dataset.carriers.items():
            if not counts_in_total(carrier) or year not in years:
                continue
            quantity = annual(years[year], "carrier", carrier.value, year)
            if quantity.value is not None and quantity.value > 0:
                settled.append(
                    settle_cost(rows, carrier, year, quantity.value, quantity.unit, None)
                )
        if not settled or any(item.expected is None for item in settled):
            continue
        expected = sum(item.expected or 0 for item in settled)
        declared = costs.get(year)
        if (
            declared is not None
            and declared.value is not None
            and abs(declared.value - expected) <= TOLERANCE * expected
        ):
            continue
        costs[year] = Reading(expected, "lei")
        notes[year] = tuple(item.footnote for item in settled if item.footnote)
    return (replace(dataset, energy_costs_lei=costs) if notes else dataset), notes
