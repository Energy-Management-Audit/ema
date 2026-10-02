"""CO₂ of a chosen carrier set: one missing reading or factor leaves the sum missing.

Like the all-carrier total, a carrier with no series that year is not part of it.
"""

from __future__ import annotations

from ema.energy_data.calc import co2
from ema.energy_data.carriers import Carrier
from ema.energy_data.factors import FactorTable
from ema.energy_data.model import Derived, EnergyDataset


def co2_sum(
    ds: EnergyDataset, factors: FactorTable, year: int, carriers: tuple[Carrier, ...]
) -> Derived:
    parts = [
        co2(ds, factors, year, carrier)
        for carrier in carriers
        if year in ds.carriers.get(carrier, {})
    ]
    missing = tuple(key for part in parts for key in part.missing)
    return Derived(
        None if missing or not parts else sum(part.value or 0.0 for part in parts),
        "t CO₂",
        "t CO₂.total",
        tuple(key for part in parts for key in part.inputs),
        factors.version,
        missing or (() if parts else (f"energy.{year}",)),
        tuple(weight for part in parts for weight in part.input_weights),
        year,
    )
